"""
Insight Rules — Individual analysis functions that detect patterns in AWS data.

Each rule takes a response dict and optional historical context,
then returns a list of Insight objects (or an empty list if nothing notable).
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import math

from .dashboard_enrichment import estimate_rightsizing_savings


@dataclass
class Insight:
    """A single actionable insight derived from AWS data."""
    type: str           # "anomaly" | "optimization" | "trend" | "warning" | "info"
    severity: str       # "info" | "warning" | "critical"
    title: str          # Human-readable title
    description: str    # Detailed explanation
    metric: Dict        # Quantitative data: {"current": X, "previous": Y, "change_pct": Z}
    suggestion: str     # Actionable recommendation

    def to_dict(self) -> Dict:
        return asdict(self)


# ─── Cost Anomaly Detection ──────────────────────────────────────────────────

def detect_cost_anomalies(response: Dict, history: Optional[List[Dict]] = None) -> List[Insight]:
    """
    Detects cost spikes and anomalies.
    
    Rules:
      - Daily cost > 2× the average → anomaly
      - Time series with a single point > 3× average → spike
    """
    insights = []
    resp_type = response.get("type", "")

    # For time series: detect spikes within the data
    if resp_type == "COST_TIME_SERIES":
        points = response.get("points", [])
        if len(points) >= 3:
            costs = [float(p.get("cost", 0)) for p in points]
            avg = sum(costs) / len(costs)
            if avg > 0:
                for p in points:
                    cost = float(p.get("cost", 0))
                    if cost > avg * 2.5 and cost > 10:  # Only flag meaningful amounts
                        insights.append(Insight(
                            type="anomaly",
                            severity="warning",
                            title="Cost Spike Detected",
                            description=f"Spend on {p.get('date', 'unknown')} was ${cost:.2f}, which is {cost/avg:.1f}× the average (${avg:.2f}).",
                            metric={"date": p.get("date"), "cost": cost, "average": round(avg, 2), "multiplier": round(cost / avg, 1)},
                            suggestion="Review what changed on this date — new deployments, scaling events, or data transfer spikes."
                        ))
                        break  # Only report the most notable spike

    # For cost breakdowns: detect if total cost is unusually high vs history
    if resp_type == "COST_BREAKDOWN" and history:
        current_total = response.get("total_cost", 0)
        prev_totals = [h.get("total_cost", 0) for h in history if h.get("total_cost")]
        if prev_totals and current_total > 0:
            prev_avg = sum(prev_totals) / len(prev_totals)
            if prev_avg > 0:
                change_pct = ((current_total - prev_avg) / prev_avg) * 100
                if change_pct > 30:
                    sev = "critical" if change_pct > 50 else "warning"
                    insights.append(Insight(
                        type="anomaly",
                        severity=sev,
                        title="Cost Increase vs Previous Periods",
                        description=f"Current total (${current_total:.2f}) is {change_pct:.0f}% higher than your historical average (${prev_avg:.2f}).",
                        metric={"current": current_total, "previous_avg": round(prev_avg, 2), "change_pct": round(change_pct, 1)},
                        suggestion="Compare service-level breakdown to identify which service drove the increase."
                    ))

    return insights


# ─── Cost Concentration Analysis ─────────────────────────────────────────────

def detect_cost_concentration(response: Dict) -> List[Insight]:
    """
    Warns when spending is heavily concentrated on a single service.
    
    Rules:
      - Single service > 70% of total → warning
      - Top 2 services > 90% of total → info
    """
    insights = []
    if response.get("type") != "COST_BREAKDOWN":
        return insights

    breakdown = response.get("breakdown", [])
    total = response.get("total_cost", 0)
    if not breakdown or total <= 0:
        return insights

    # Check single service concentration
    top = breakdown[0]
    top_cost = float(top.get("cost", 0))
    top_pct = (top_cost / total) * 100

    if top_pct > 70:
        insights.append(Insight(
            type="warning",
            severity="warning",
            title="High Cost Concentration",
            description=f"{top.get('name', 'Unknown')} accounts for {top_pct:.0f}% of your total spend (${top_cost:.2f} of ${total:.2f}).",
            metric={"service": top.get("name"), "cost": top_cost, "percentage": round(top_pct, 1), "total": total},
            suggestion="Consider whether this concentration is expected. Diversifying workloads or optimizing this service could reduce risk."
        ))

    # Check top-2 concentration
    if len(breakdown) >= 3:
        top2_cost = sum(float(b.get("cost", 0)) for b in breakdown[:2])
        top2_pct = (top2_cost / total) * 100
        if top2_pct > 90 and top_pct <= 70:
            names = f"{breakdown[0].get('name', '')} + {breakdown[1].get('name', '')}"
            insights.append(Insight(
                type="info",
                severity="info",
                title="Spend Dominated by Two Services",
                description=f"{names} together account for {top2_pct:.0f}% of total spend.",
                metric={"services": names, "percentage": round(top2_pct, 1)},
                suggestion="This is common for many workloads. Monitor these two services closely for cost changes."
            ))

    return insights


# ─── Trend Analysis ──────────────────────────────────────────────────────────

def analyze_trends(response: Dict) -> List[Insight]:
    """
    Computes trend direction and projects future costs.
    
    Rules:
      - Rising trend (>15% increase first→second half) → warning
      - Falling trend (<-15%) → positive info
      - Volatility (CV > 40%) → warning
    """
    insights = []
    if response.get("type") != "COST_TIME_SERIES":
        return insights

    points = response.get("points", [])
    if len(points) < 4:
        return insights

    costs = [float(p.get("cost", 0)) for p in points]
    n = len(costs)
    mid = n // 2
    avg = sum(costs) / n

    if avg <= 0:
        return insights

    first_avg = sum(costs[:mid]) / mid
    second_avg = sum(costs[mid:]) / (n - mid)

    if first_avg > 0:
        trend_pct = ((second_avg - first_avg) / first_avg) * 100

        if trend_pct > 15:
            # Rising costs
            projected = second_avg * 30  # Simple 30-day projection
            insights.append(Insight(
                type="trend",
                severity="warning",
                title="Costs Trending Upward",
                description=f"Your daily spend is trending up {trend_pct:.0f}% (${first_avg:.2f}/day → ${second_avg:.2f}/day). At this rate, next month could reach ~${projected:.0f}.",
                metric={"trend_pct": round(trend_pct, 1), "early_avg": round(first_avg, 2), "late_avg": round(second_avg, 2), "projected_monthly": round(projected, 0)},
                suggestion="Review recent deployments or scaling changes. Consider setting AWS Budget alerts to catch further increases."
            ))
        elif trend_pct < -15:
            # Falling costs
            insights.append(Insight(
                type="trend",
                severity="info",
                title="Costs Trending Downward",
                description=f"Good news — daily spend is down {abs(trend_pct):.0f}% (${first_avg:.2f}/day → ${second_avg:.2f}/day). Your optimizations are working.",
                metric={"trend_pct": round(trend_pct, 1), "early_avg": round(first_avg, 2), "late_avg": round(second_avg, 2)},
                suggestion="Keep monitoring to ensure the trend continues."
            ))

    # Volatility check
    variance = sum((c - avg) ** 2 for c in costs) / n
    std_dev = math.sqrt(variance)
    cv = (std_dev / avg) * 100 if avg > 0 else 0

    if cv > 40:
        insights.append(Insight(
            type="warning",
            severity="warning",
            title="High Cost Volatility",
            description=f"Your daily costs vary significantly (CV={cv:.0f}%). Range: ${min(costs):.2f} – ${max(costs):.2f}.",
            metric={"cv": round(cv, 1), "min": round(min(costs), 2), "max": round(max(costs), 2), "std_dev": round(std_dev, 2)},
            suggestion="Volatile costs often indicate batch jobs, auto-scaling, or uneven data transfer. Consider reserved capacity for baseline loads."
        ))

    return insights


# ─── Unused Resource Detection ───────────────────────────────────────────────

def detect_unused_resources(response: Dict) -> List[Insight]:
    """
    Identifies stopped, unused, or idle resources.
    
    Rules:
      - Stopped EC2 instances → optimization opportunity
      - Multiple running instances of same type → possible over-provisioning
    """
    insights = []
    if response.get("type") != "RESOURCE_LIST":
        return insights

    resources = response.get("resources", [])
    resource_type = response.get("resource_type", "")

    if not resources:
        return insights

    # EC2: check for stopped instances
    if resource_type == "EC2 Instance":
        stopped = [r for r in resources if (r.get("state", "") or "").lower() == "stopped"]
        running = [r for r in resources if (r.get("state", "") or "").lower() == "running"]

        if stopped:
            insights.append(Insight(
                type="optimization",
                severity="warning",
                title=f"{len(stopped)} Stopped EC2 Instance{'s' if len(stopped) > 1 else ''}",
                description=f"You have {len(stopped)} stopped instance(s) that may still incur EBS storage charges.",
                metric={"stopped_count": len(stopped), "running_count": len(running), "total": len(resources)},
                suggestion="Consider terminating stopped instances you no longer need, or snapshot their volumes and terminate to save on storage costs."
            ))

        # Underutilized running instances (CPU from CloudWatch enrichment)
        for r in running:
            avg_cpu = r.get("avg_cpu")
            if avg_cpu is not None and avg_cpu < 5:
                itype = r.get("instance_type", "unknown")
                savings = estimate_rightsizing_savings(itype)
                insights.append(Insight(
                    type="optimization",
                    severity="warning",
                    title=f"Underutilized: {r.get('name') or r.get('instance_id')}",
                    description=(
                        f"Running instance {r.get('instance_id')} ({itype}) averaged "
                        f"{avg_cpu:.1f}% CPU — likely oversized."
                    ),
                    metric={
                        "instance_id": r.get("instance_id"),
                        "avg_cpu": avg_cpu,
                        "potential_savings": savings,
                    },
                    suggestion=(
                        f"Consider downsizing or stopping this instance. "
                        f"Estimated savings ~${savings:.0f}/month if rightsized."
                    ),
                ))

        # Check for over-provisioning (many instances of same type)
        if len(running) >= 3:
            type_counts = {}
            for r in running:
                t = r.get("instance_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            for itype, count in type_counts.items():
                if count >= 4:
                    insights.append(Insight(
                        type="optimization",
                        severity="info",
                        title=f"{count} Identical {itype} Instances Running",
                        description=f"You're running {count} instances of type {itype}. This may indicate an opportunity for Reserved Instances or Savings Plans.",
                        metric={"instance_type": itype, "count": count},
                        suggestion=f"If these {itype} instances run 24/7, a 1-year Reserved Instance could save ~30-40% vs On-Demand pricing."
                    ))
                    break  # Only flag the most common type

    return insights


# ─── Quick Wins / Optimization Advisor ────────────────────────────────────────

def suggest_optimizations(response: Dict) -> List[Insight]:
    """
    Suggests cost optimization opportunities based on cost data patterns.
    
    Rules:
      - S3 costs > $50/month → suggest lifecycle policies
      - Data transfer > 20% of total → suggest CloudFront/VPC endpoints
    """
    insights = []
    if response.get("type") != "COST_BREAKDOWN":
        return insights

    breakdown = response.get("breakdown", [])
    total = response.get("total_cost", 0)

    for item in breakdown:
        name = (item.get("name", "") or "").lower()
        cost = float(item.get("cost", 0))

        if "s3" in name or "storage" in name:
            if cost > 50:
                insights.append(Insight(
                    type="optimization",
                    severity="info",
                    title="S3 Storage Costs Could Be Reduced",
                    description=f"S3 storage costs are ${cost:.2f}. Lifecycle policies can automatically move infrequently accessed data to cheaper tiers.",
                    metric={"service": item.get("name"), "cost": cost},
                    suggestion="Enable S3 Intelligent-Tiering or set lifecycle rules to move objects to S3 Glacier after 90 days."
                ))
                break

        if "data transfer" in name or "cloudfront" in name:
            if total > 0 and (cost / total) > 0.2:
                pct = (cost / total) * 100
                insights.append(Insight(
                    type="optimization",
                    severity="info",
                    title="High Data Transfer Costs",
                    description=f"Data transfer accounts for {pct:.0f}% of your spend (${cost:.2f}). CloudFront caching or VPC endpoints could help.",
                    metric={"service": item.get("name"), "cost": cost, "percentage": round(pct, 1)},
                    suggestion="Use CloudFront for frequently accessed content, and VPC endpoints for AWS service traffic to reduce NAT gateway charges."
                ))
                break

    return insights


# ─── Tag Compliance ───────────────────────────────────────────────────────────

def detect_tag_compliance_issues(tag_compliance: Dict) -> List[Insight]:
    """Warn when allocation tags are missing on a significant share of resources."""
    insights = []
    if not tag_compliance or tag_compliance.get("total_resources", 0) == 0:
        return insights

    pct = tag_compliance.get("compliance_pct", 100)
    untagged = tag_compliance.get("untagged_resources", [])
    required = tag_compliance.get("required_tags", [])

    if pct < 100 and untagged:
        sev = "critical" if pct < 50 else "warning"
        insights.append(Insight(
            type="warning",
            severity=sev,
            title=f"Tag Compliance: {pct}%",
            description=(
                f"{len(untagged)} of {tag_compliance.get('total_resources')} resources "
                f"are missing required tags ({', '.join(required)})."
            ),
            metric={
                "compliance_pct": pct,
                "untagged_count": len(untagged),
            },
            suggestion="Add Environment, Owner, and CostCenter tags for cost allocation and governance.",
        ))

    return insights
