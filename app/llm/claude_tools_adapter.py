"""
Claude Tools Adapter
Converts MCP Registry tools into Claude's native tool-use format
and maps Claude tool_use responses back to the MCP executor.
"""
from typing import List, Dict, Any, Optional
from ..mcp.registry import MCPRegistry
from ..mcp.tools import MCPTool


# ─── Tool Schema Definitions ────────────────────────────────────────────────────
# These map each MCP tool to a Claude-compatible tool schema.
# We define them explicitly for precision rather than auto-generating from Pydantic.

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    # ── Cost Tools ───────────────────────────────────────────────────────────
    "aws_get_today_cost": {
        "name": "aws_get_today_cost",
        "description": "Get today's partial AWS cost (current day, may be incomplete).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_yesterday_cost": {
        "name": "aws_get_yesterday_cost",
        "description": "Get yesterday's complete AWS cost.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_current_month_cost": {
        "name": "aws_get_current_month_cost",
        "description": "Get the current month's AWS cost (month-to-date).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_last_month_cost": {
        "name": "aws_get_last_month_cost",
        "description": "Get last month's complete AWS cost.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_cost_by_service": {
        "name": "aws_get_cost_by_service",
        "description": "Get AWS cost breakdown by service for a date range. Shows which AWS services cost the most.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_by_region": {
        "name": "aws_get_cost_by_region",
        "description": "Get AWS cost breakdown by region for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_by_linked_account": {
        "name": "aws_get_cost_by_linked_account",
        "description": "Get AWS cost breakdown by linked account for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_by_usage_type": {
        "name": "aws_get_cost_by_usage_type",
        "description": "Get AWS cost breakdown by usage type (e.g. DataTransfer, EBS volumes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_by_tag": {
        "name": "aws_get_cost_by_tag",
        "description": "Get AWS cost breakdown by a specific tag key.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "tag_key": {
                    "type": "string",
                    "description": "The tag key to group costs by (e.g. 'Project', 'Environment')",
                },
            },
            "required": ["start_date", "end_date", "tag_key"],
        },
    },
    "aws_get_cost_trend": {
        "name": "aws_get_cost_trend",
        "description": "Get daily or monthly cost trend for a date range. Shows cost over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "granularity": {
                    "type": "string",
                    "description": "DAILY or MONTHLY. Use DAILY for ranges <= 45 days, MONTHLY for longer.",
                    "enum": ["DAILY", "MONTHLY"],
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_forecast": {
        "name": "aws_get_cost_forecast",
        "description": "Get AWS cost forecast for a future date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Forecast start date in YYYY-MM-DD format (must be in the future)",
                },
                "end_date": {
                    "type": "string",
                    "description": "Forecast end date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_by_time_range": {
        "name": "aws_get_cost_by_time_range",
        "description": "Get total AWS cost for any custom date range. The canonical fallback tool for all generic cost queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "granularity": {
                    "type": "string",
                    "description": "DAILY or MONTHLY",
                    "enum": ["DAILY", "MONTHLY"],
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    "aws_get_cost_anomalies": {
        "name": "aws_get_cost_anomalies",
        "description": "Get cost anomalies detected by AWS Cost Anomaly Detection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format (defaults to 90 days ago)",
                },
                "monitor_arn": {
                    "type": "string",
                    "description": "Cost Anomaly Detection monitor ARN",
                },
            },
            "required": [],
        },
    },
    # ── Account Tools ────────────────────────────────────────────────────────
    "aws_get_caller_identity": {
        "name": "aws_get_caller_identity",
        "description": "Get the current AWS account identity (account ID, ARN, user ID).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_account_alias": {
        "name": "aws_get_account_alias",
        "description": "Get the account alias for the current AWS account.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_enabled_regions": {
        "name": "aws_get_enabled_regions",
        "description": "List all enabled AWS regions in the account.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Resource Inventory Tools ─────────────────────────────────────────────
    "aws_list_ec2_instances": {
        "name": "aws_list_ec2_instances",
        "description": "List all EC2 instances with their state, type, and tags.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_s3_buckets": {
        "name": "aws_list_s3_buckets",
        "description": "List all S3 buckets in the account.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_lambda_functions": {
        "name": "aws_list_lambda_functions",
        "description": "List all Lambda functions with their runtime and memory configuration.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_rds_instances": {
        "name": "aws_list_rds_instances",
        "description": "List all RDS database instances.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_eks_clusters": {
        "name": "aws_list_eks_clusters",
        "description": "List all EKS (Kubernetes) clusters.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_load_balancers": {
        "name": "aws_list_load_balancers",
        "description": "List all Elastic Load Balancers (ALB, NLB, CLB).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_list_nat_gateways": {
        "name": "aws_list_nat_gateways",
        "description": "List all NAT Gateways.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── CloudWatch & Logs Tools ──────────────────────────────────────────────
    "aws_list_cloudwatch_metrics": {
        "name": "aws_list_cloudwatch_metrics",
        "description": "List CloudWatch metrics for a given namespace (e.g. AWS/EC2, AWS/Lambda).",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "CloudWatch namespace (e.g. AWS/EC2, AWS/S3, AWS/Lambda)",
                },
            },
            "required": ["namespace"],
        },
    },
    "aws_list_log_groups": {
        "name": "aws_list_log_groups",
        "description": "List CloudWatch Log Groups.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "aws_get_log_events": {
        "name": "aws_get_log_events",
        "description": "Get log events from a specific CloudWatch Log Group.",
        "input_schema": {
            "type": "object",
            "properties": {
                "log_group_name": {
                    "type": "string",
                    "description": "The name of the CloudWatch Log Group",
                },
            },
            "required": ["log_group_name"],
        },
    },
}


class ClaudeToolsAdapter:
    """
    Adapter that bridges MCP Registry tools with Claude's native tool-use API.

    Provides:
    - get_claude_tools(): Returns tool definitions in Claude format
    - execute_tool_calls(): Executes Claude tool_use blocks via MCP executor
    """

    def __init__(self, registry: MCPRegistry):
        self.registry = registry

    def get_claude_tools(self, mode: str = "inventory_aware") -> List[Dict[str, Any]]:
        """
        Get Claude-compatible tool definitions for all registered MCP tools.
        Filters by mode (inventory_aware or cost_only).
        """
        from ..mcp.registry import UI_TOOL_NAMES, COST_ONLY_TOOL_NAMES

        target_names = UI_TOOL_NAMES if mode == "inventory_aware" else COST_ONLY_TOOL_NAMES
        tools = []

        for tool_name in target_names:
            mcp_tool = self.registry.get_tool(tool_name)
            if not mcp_tool:
                continue

            # Use explicit schema if available, otherwise auto-generate
            if tool_name in TOOL_SCHEMAS:
                tools.append(TOOL_SCHEMAS[tool_name])
            else:
                # Auto-generate from MCP tool metadata
                tools.append(self._auto_generate_schema(mcp_tool))

        return tools

    def _auto_generate_schema(self, tool: MCPTool) -> Dict[str, Any]:
        """
        Auto-generate a Claude tool schema from an MCP tool's metadata.
        Used as fallback when explicit schema is not defined.
        """
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    def execute_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute a list of Claude tool_use blocks through the MCP registry.

        Args:
            tool_calls: List of dicts with 'id', 'name', 'input' keys
                        (from AnthropicClient.chat_with_tools response)

        Returns:
            List of tool_result blocks suitable for sending back to Claude:
            [{"type": "tool_result", "tool_use_id": ..., "content": ...}, ...]
        """
        results = []

        for call in tool_calls:
            tool_name = call.get("name", "")
            tool_input = call.get("input", {})
            tool_use_id = call.get("id", "")

            # Look up tool in registry
            tool = self.registry.get_tool(tool_name)
            if not tool:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps({
                        "success": False,
                        "error": f"Tool '{tool_name}' not found in registry",
                    }),
                    "is_error": True,
                })
                continue

            # Validate input
            if not tool.validate_input(tool_input):
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps({
                        "success": False,
                        "error": f"Invalid input for tool '{tool_name}'",
                    }),
                    "is_error": True,
                })
                continue

            # Execute the tool
            try:
                result = tool.execute(tool_input, context={})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result, default=str),
                })
            except Exception as e:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps({
                        "success": False,
                        "error": f"Tool execution failed: {str(e)}",
                    }),
                    "is_error": True,
                })

        return results


import json
