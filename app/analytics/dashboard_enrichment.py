"""
Dashboard enrichment: CPU metrics, tag compliance, burn rate, log RCA.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REQUIRED_TAGS = ["Environment", "Owner", "CostCenter"]

# Rough monthly USD savings if downgrading one size (illustrative)
_RIGHTSIZE_SAVINGS = {
    "t3.large": 25, "t3.medium": 15, "t3.small": 8,
    "m5.large": 40, "m5.xlarge": 80, "c5.large": 35,
}


def fetch_instance_cpu_metrics(
    executor,
    instances: List[Dict],
    start_date: str,
    end_date: str,
) -> Dict[str, Dict]:
    """Fetch average CPUUtilization per instance (parallel, capped)."""
    tools = []
    for inst in instances:
        iid = inst.get("instance_id")
        if not iid:
            continue
        tools.append({
            "tool": "aws_get_cloudwatch_metric_data",
            "input": {
                "namespace": "AWS/EC2",
                "metric_name": "CPUUtilization",
                "dimensions": [{"Name": "InstanceId", "Value": iid}],
                "start_date": start_date,
                "end_date": end_date,
                "period": 3600,
            },
        })
    if not tools:
        return {}

    results = executor.execute_tools_parallel(tools)
    cpu_by_id: Dict[str, Dict] = {}
    for idx, item in enumerate(results):
        if idx >= len(instances):
            break
        iid = instances[idx].get("instance_id")
        if not iid:
            continue
        result = item.get("result", {})
        data = result.get("data") if result.get("success") else None
        if not data:
            continue

        datapoints = data.get("datapoints", [])
        values = [float(p["value"]) for p in datapoints if p.get("value") is not None]
        if not values and not iid:
            continue
        if not iid:
            continue
        avg = sum(values) / len(values) if values else None
        cpu_by_id[iid] = {
            "avg_cpu": round(avg, 1) if avg is not None else None,
            "max_cpu": round(max(values), 1) if values else None,
            "sparkline": [round(v, 1) for v in values[-12:]] if values else [],
        }
    return cpu_by_id


def attach_cpu_to_instances(instances: List[Dict], cpu_by_id: Dict[str, Dict]) -> None:
    for inst in instances:
        iid = inst.get("instance_id")
        if iid and iid in cpu_by_id:
            inst.update(cpu_by_id[iid])


def compute_tag_compliance(
    ec2: List[Dict],
    lambdas: List[Dict],
    rds: List[Dict],
    required_tags: List[str],
) -> Dict[str, Any]:
    """Audit resources for required allocation tags."""
    audited = []
    for r in ec2:
        audited.append({
            "type": "EC2",
            "id": r.get("instance_id"),
            "name": r.get("name") or r.get("instance_id"),
            "tags": r.get("tags") or {},
        })
    for r in lambdas:
        audited.append({
            "type": "Lambda",
            "id": r.get("function_name"),
            "name": r.get("function_name"),
            "tags": r.get("tags") or {},
        })
    for r in rds:
        audited.append({
            "type": "RDS",
            "id": r.get("db_identifier"),
            "name": r.get("db_identifier"),
            "tags": r.get("tags") or {},
        })

    total = len(audited)
    if total == 0:
        return {
            "compliance_pct": 100,
            "total_resources": 0,
            "compliant_count": 0,
            "missing_tags": [],
            "untagged_resources": [],
            "required_tags": required_tags,
        }

    compliant = []
    untagged = []
    for res in audited:
        tags = res["tags"]
        missing = [t for t in required_tags if not tags.get(t)]
        if not missing:
            compliant.append(res)
        else:
            untagged.append({**res, "missing": missing})

    pct = round((len(compliant) / total) * 100, 1)
    return {
        "compliance_pct": pct,
        "total_resources": total,
        "compliant_count": len(compliant),
        "missing_tags": required_tags,
        "untagged_resources": untagged[:15],
        "required_tags": required_tags,
    }


def compute_burn_rate(
    points: List[Dict],
    month_to_date: float,
    forecast_total: Optional[float] = None,
) -> Dict[str, Any]:
    """Daily burn rate, acceleration, and days-to-budget at current pace."""
    costs = [float(p.get("cost", 0)) for p in points if p.get("cost") is not None]
    if not costs:
        return {
            "daily_avg": 0,
            "recent_daily_avg": 0,
            "acceleration_pct": 0,
            "projected_month_end": forecast_total or month_to_date,
            "days_in_month": datetime.now().day,
        }

    daily_avg = sum(costs) / len(costs)
    mid = max(1, len(costs) // 2)
    early = sum(costs[:mid]) / mid
    recent = sum(costs[mid:]) / max(1, len(costs) - mid)
    accel = ((recent - early) / early * 100) if early > 0 else 0

    now = datetime.now()
    days_elapsed = now.day
    days_remaining = max(1, 30 - days_elapsed)
    projected = month_to_date + (recent * days_remaining)

    return {
        "daily_avg": round(daily_avg, 2),
        "recent_daily_avg": round(recent, 2),
        "acceleration_pct": round(accel, 1),
        "projected_month_end": round(forecast_total or projected, 2),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
    }


def estimate_rightsizing_savings(instance_type: str) -> float:
    return float(_RIGHTSIZE_SAVINGS.get(instance_type, 12))


def enrich_insights_with_log_rca(
    executor,
    insights: List[Dict],
    top_services: List[Dict],
) -> List[Dict]:
    """Attach log snippets to cost spike / anomaly insights when Lambda is a top driver."""
    lambda_heavy = any(
        "lambda" in (s.get("name") or s.get("service") or "").lower()
        for s in (top_services or [])[:3]
    )
    if not lambda_heavy:
        return insights

    log_summary = _fetch_lambda_error_summary(executor)
    if not log_summary:
        return insights

    enriched = []
    for ins in insights:
        copy = dict(ins)
        if ins.get("type") in ("anomaly", "warning") and "spike" in (ins.get("title") or "").lower():
            copy["rca"] = log_summary
        elif ins.get("type") == "anomaly":
            copy["rca"] = log_summary
        enriched.append(copy)
    return enriched


def _fetch_lambda_error_summary(executor) -> Optional[Dict[str, str]]:
    """Best-effort: sample Lambda log groups for recent ERROR lines."""
    try:
        lg_result = executor.execute_tool("aws_list_log_groups", {"prefix": "/aws/lambda/", "limit": 5})
        if not lg_result.get("success"):
            return None
        groups = (lg_result.get("data") or {}).get("items", [])
        if not groups:
            return None

        top_group = groups[0].get("name")
        if not top_group:
            return None

        ev_result = executor.execute_tool("aws_get_log_events", {
            "log_group_name": top_group,
            "filter_pattern": "?ERROR ?Exception ?Timeout",
            "limit": 5,
        })
        if not ev_result.get("success"):
            return None
        events = (ev_result.get("data") or {}).get("items", [])
        if not events:
            return None

        messages = [e.get("message", "")[:120] for e in events[:3]]
        return {
            "source": top_group,
            "error_count_sample": len(events),
            "top_messages": messages,
            "conclusion": (
                f"Sampled {len(events)} error(s) in {top_group}. "
                "Lambda errors often correlate with cost spikes from retries and timeouts."
            ),
        }
    except Exception as e:
        logger.warning("Log RCA skipped: %s", e)
        return None
