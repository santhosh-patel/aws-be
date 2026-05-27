"""
Dashboard aggregation — cost, resources, utilization, tags, burn rate, and log RCA.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.analytics.insights_engine import InsightsEngine
from app.analytics.rules import detect_tag_compliance_issues
from app.analytics.dashboard_enrichment import (
    REQUIRED_TAGS,
    attach_cpu_to_instances,
    compute_burn_rate,
    compute_tag_compliance,
    enrich_insights_with_log_rca,
    fetch_instance_cpu_metrics,
)

logger = logging.getLogger(__name__)

MAX_CPU_INSTANCES = 8


def build_dashboard(executor, insights_engine: Optional[InsightsEngine] = None) -> Dict[str, Any]:
    """Aggregate AWS dashboard data via parallel MCP tool execution."""
    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    thirty_days_ago = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    seven_days_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end_of_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

    dashboard: Dict[str, Any] = {
        "generated_at": today.isoformat(),
        "cost_summary": None,
        "cost_by_service": None,
        "cost_by_region": None,
        "cost_by_tag": None,
        "cost_trend": None,
        "cost_forecast": None,
        "ec2_instances": None,
        "s3_buckets": None,
        "lambda_functions": None,
        "rds_instances": None,
        "resource_counts": {},
        "insights": [],
        "alerts": [],
        "top_services": [],
        "idle_resources": [],
        "tag_compliance": None,
        "burn_rate": None,
        "utilization_summary": {"underutilized_count": 0, "high_cpu_count": 0},
        "cost_comparison": None,
        "cost_by_usage_type": None,
        "eks_clusters": None,
        "load_balancers": None,
        "nat_gateways": None,
        "account": None,
    }

    cost_tools = [
        {"tool": "aws_get_today_cost", "input": {}},
        {"tool": "aws_get_yesterday_cost", "input": {}},
        {"tool": "aws_get_current_month_cost", "input": {}},
        {"tool": "aws_get_last_month_cost", "input": {}},
        {"tool": "aws_get_cost_by_service", "input": {
            "start_date": month_start, "end_date": tomorrow_str
        }},
        {"tool": "aws_get_cost_by_usage_type", "input": {
            "start_date": month_start, "end_date": tomorrow_str
        }},
        {"tool": "aws_get_cost_by_region", "input": {"start_date": month_start, "end_date": tomorrow_str}},
        {"tool": "aws_get_cost_trend", "input": {
            "start_date": thirty_days_ago, "end_date": tomorrow_str, "granularity": "DAILY"
        }},
        {"tool": "aws_get_cost_forecast", "input": {
            "start_date": tomorrow_str, "end_date": end_of_month, "granularity": "DAILY"
        }},
        {"tool": "aws_get_cost_by_tag", "input": {
            "tag_key": "Environment",
            "start_date": month_start,
            "end_date": tomorrow_str,
        }},
    ]
    resource_tools = [
        {"tool": "aws_list_ec2_instances", "input": {}},
        {"tool": "aws_list_s3_buckets", "input": {}},
        {"tool": "aws_list_lambda_functions", "input": {}},
        {"tool": "aws_list_rds_instances", "input": {}},
        {"tool": "aws_list_eks_clusters", "input": {}},
        {"tool": "aws_list_load_balancers", "input": {}},
        {"tool": "aws_list_nat_gateways", "input": {}},
    ]
    account_tools = [
        {"tool": "aws_get_caller_identity", "input": {}},
        {"tool": "aws_get_enabled_regions", "input": {}},
    ]

    try:
        results = executor.execute_tools_parallel(cost_tools + resource_tools + account_tools)
        running_for_cpu: List[Dict] = []

        for item in results:
            tool_name = item.get("tool", "")
            result = item.get("result", {})
            data = result.get("data") if result.get("success") else None
            if not data:
                continue

            if tool_name == "aws_get_today_cost":
                if not dashboard["cost_summary"]:
                    dashboard["cost_summary"] = {"currency": "USD"}
                dashboard["cost_summary"]["today_cost"] = data.get("total_cost", 0)
                dashboard["cost_summary"]["date"] = data.get("date")
            elif tool_name == "aws_get_yesterday_cost":
                if not dashboard["cost_comparison"]:
                    dashboard["cost_comparison"] = {}
                dashboard["cost_comparison"]["yesterday_cost"] = data.get("total_cost", 0)
            elif tool_name == "aws_get_last_month_cost":
                if not dashboard["cost_comparison"]:
                    dashboard["cost_comparison"] = {}
                dashboard["cost_comparison"]["last_month_cost"] = data.get("total_cost", 0)
            elif tool_name == "aws_get_current_month_cost":
                mtd = data.get("total_cost", 0)
                if dashboard["cost_summary"]:
                    dashboard["cost_summary"]["month_to_date"] = mtd
                else:
                    dashboard["cost_summary"] = {
                        "today_cost": 0,
                        "month_to_date": mtd,
                        "currency": "USD",
                    }
            elif tool_name == "aws_get_cost_by_service":
                breakdown = data.get("breakdown", [])
                normalized = [
                    {
                        "name": b.get("service") or b.get("name", "Unknown"),
                        "service": b.get("service") or b.get("name"),
                        "cost": b.get("cost", 0),
                    }
                    for b in breakdown
                ]
                dashboard["cost_by_service"] = {
                    "total_cost": data.get("total_cost", 0),
                    "services": normalized[:12],
                    "service_count": len(normalized),
                }
                dashboard["top_services"] = normalized[:5]
            elif tool_name == "aws_get_cost_by_usage_type":
                breakdown = data.get("breakdown", [])
                dashboard["cost_by_usage_type"] = {
                    "total_cost": data.get("total_cost", 0),
                    "breakdown": breakdown[:15],
                }
            elif tool_name == "aws_get_cost_by_region":
                regions = data.get("breakdown", [])
                dashboard["cost_by_region"] = {
                    "total_cost": data.get("total_cost", 0),
                    "regions": regions[:10],
                }
            elif tool_name == "aws_get_cost_trend":
                trend = data.get("trend", [])
                dashboard["cost_trend"] = {
                    "points": trend[-30:],
                    "total": data.get("total_cost", 0),
                    "granularity": data.get("granularity", "DAILY"),
                }
            elif tool_name == "aws_get_cost_forecast":
                forecast_data = data.get("forecast_data", [])
                dashboard["cost_forecast"] = {
                    "forecasted_total": data.get("forecasted_cost", 0),
                    "period": data.get("period"),
                    "points": [
                        {
                            "date": fp.get("TimePeriod", {}).get("Start"),
                            "mean": round(float(fp.get("MeanValue", 0)), 2),
                        }
                        for fp in forecast_data
                    ],
                }
            elif tool_name == "aws_get_cost_by_tag":
                dashboard["cost_by_tag"] = {
                    "tag_key": data.get("tag_key", "Environment"),
                    "total_cost": data.get("total_cost", 0),
                    "breakdown": data.get("breakdown", [])[:10],
                }
            elif tool_name == "aws_list_ec2_instances":
                items = data.get("items", [])
                running = [i for i in items if (i.get("state") or "").lower() == "running"]
                stopped = [i for i in items if (i.get("state") or "").lower() == "stopped"]
                dashboard["ec2_instances"] = {
                    "total": len(items),
                    "running": len(running),
                    "stopped": len(stopped),
                    "instances": items[:20],
                }
                dashboard["resource_counts"]["EC2"] = len(items)
                running_for_cpu = running[:MAX_CPU_INSTANCES]
                for inst in stopped:
                    dashboard["idle_resources"].append({
                        "type": "EC2",
                        "id": inst.get("instance_id"),
                        "name": inst.get("name") or inst.get("instance_id"),
                        "reason": "Instance is stopped — still incurs EBS charges",
                        "instance_type": inst.get("instance_type"),
                    })
                if stopped:
                    dashboard["alerts"].append({
                        "type": "warning",
                        "title": f"{len(stopped)} Stopped EC2 Instance{'s' if len(stopped) > 1 else ''}",
                        "description": "Stopped instances still incur EBS storage charges. Consider terminating unused ones.",
                    })
            elif tool_name == "aws_list_s3_buckets":
                items = data.get("items", [])
                dashboard["s3_buckets"] = {"total": len(items), "buckets": items[:20]}
                dashboard["resource_counts"]["S3"] = len(items)
            elif tool_name == "aws_list_lambda_functions":
                items = data.get("items", [])
                dashboard["lambda_functions"] = {"total": len(items), "functions": items[:20]}
                dashboard["resource_counts"]["Lambda"] = len(items)
            elif tool_name == "aws_list_rds_instances":
                items = data.get("items", [])
                dashboard["rds_instances"] = {"total": len(items), "instances": items[:10]}
                dashboard["resource_counts"]["RDS"] = len(items)
            elif tool_name == "aws_list_eks_clusters":
                items = data.get("items", [])
                dashboard["eks_clusters"] = {"total": len(items), "clusters": items[:10]}
                dashboard["resource_counts"]["EKS"] = len(items)
            elif tool_name == "aws_list_load_balancers":
                items = data.get("items", [])
                dashboard["load_balancers"] = {"total": len(items), "items": items[:10]}
                dashboard["resource_counts"]["ALB"] = len(items)
            elif tool_name == "aws_list_nat_gateways":
                items = data.get("items", [])
                dashboard["nat_gateways"] = {"total": len(items), "items": items[:10]}
                dashboard["resource_counts"]["NAT"] = len(items)
            elif tool_name == "aws_get_caller_identity":
                if not dashboard["account"]:
                    dashboard["account"] = {}
                dashboard["account"]["identity"] = data
            elif tool_name == "aws_get_enabled_regions":
                if not dashboard["account"]:
                    dashboard["account"] = {}
                regions = data.get("regions") or data.get("items") or []
                dashboard["account"]["enabled_regions_count"] = len(regions)

        if dashboard.get("cost_summary") and dashboard.get("cost_comparison"):
            mtd = dashboard["cost_summary"].get("month_to_date", 0)
            lm = dashboard["cost_comparison"].get("last_month_cost", 0)
            if lm and lm > 0:
                dashboard["cost_comparison"]["mtd_vs_last_month_pct"] = round(
                    ((mtd - lm) / lm) * 100, 1
                )

        # CPU utilization for running EC2 (Phase 1)
        if running_for_cpu and dashboard.get("ec2_instances"):
            cpu_by_id = fetch_instance_cpu_metrics(
                executor, running_for_cpu, seven_days_ago, today_str
            )
            attach_cpu_to_instances(dashboard["ec2_instances"]["instances"], cpu_by_id)
            for inst in dashboard["ec2_instances"]["instances"]:
                avg = inst.get("avg_cpu")
                if avg is None:
                    continue
                if inst.get("state") == "running" and avg < 5:
                    dashboard["utilization_summary"]["underutilized_count"] += 1
                elif avg > 85:
                    dashboard["utilization_summary"]["high_cpu_count"] += 1

        # Tag compliance (Phase 3)
        dashboard["tag_compliance"] = compute_tag_compliance(
            ec2=dashboard["ec2_instances"]["instances"] if dashboard.get("ec2_instances") else [],
            lambdas=dashboard["lambda_functions"]["functions"] if dashboard.get("lambda_functions") else [],
            rds=dashboard["rds_instances"]["instances"] if dashboard.get("rds_instances") else [],
            required_tags=REQUIRED_TAGS,
        )

        # Burn rate (Phase 2)
        if dashboard.get("cost_trend") and dashboard.get("cost_summary"):
            dashboard["burn_rate"] = compute_burn_rate(
                points=dashboard["cost_trend"].get("points", []),
                month_to_date=dashboard["cost_summary"].get("month_to_date", 0),
                forecast_total=(dashboard.get("cost_forecast") or {}).get("forecasted_total"),
            )

        # Insights engine
        if insights_engine:
            if dashboard.get("cost_by_service"):
                dashboard["insights"].extend(insights_engine.analyze({
                    "type": "COST_BREAKDOWN",
                    "total_cost": dashboard["cost_by_service"]["total_cost"],
                    "breakdown": dashboard["cost_by_service"]["services"],
                }))
            if dashboard.get("cost_trend"):
                dashboard["insights"].extend(insights_engine.analyze({
                    "type": "COST_TIME_SERIES",
                    "total_cost": dashboard["cost_trend"]["total"],
                    "points": dashboard["cost_trend"]["points"],
                }))
            if dashboard.get("ec2_instances"):
                dashboard["insights"].extend(insights_engine.analyze({
                    "type": "RESOURCE_LIST",
                    "resource_type": "EC2 Instance",
                    "resources": dashboard["ec2_instances"]["instances"],
                }))

            seen = set()
            unique = []
            for i in dashboard["insights"]:
                if i["title"] not in seen:
                    unique.append(i)
                    seen.add(i["title"])
            dashboard["insights"] = unique[:12]

            if dashboard.get("tag_compliance"):
                dashboard["insights"].extend(
                    [i.to_dict() for i in detect_tag_compliance_issues(dashboard["tag_compliance"])]
                )
                seen2 = set()
                deduped = []
                for i in dashboard["insights"]:
                    if i["title"] not in seen2:
                        deduped.append(i)
                        seen2.add(i["title"])
                dashboard["insights"] = deduped[:12]

            # Log RCA for anomalies (Phase 4)
            dashboard["insights"] = enrich_insights_with_log_rca(
                executor, dashboard["insights"], dashboard.get("top_services", [])
            )

    except Exception as e:
        logger.error("Dashboard aggregation error: %s", e)
        dashboard["error"] = str(e)

    return dashboard
