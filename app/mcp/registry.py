"""
MCP Registry - Authoritative list of all executable capabilities
Tools match IAM read-only policy: Get*, List*, Describe* only.
"""
from typing import Dict, List, Optional
from .tools import MCPTool
from .tools.cost_tools import (
    GetTodayCost, GetYesterdayCost, GetCurrentMonthCost, GetLastMonthCost,
    GetCostByService, GetCostByRegion, GetCostTrend, GetCostForecast,
    GetCostByTimeRange, GetCostAnomalies, GetCostDimensionValues, GetCostTags,
    GetCostByLinkedAccount, GetCostByUsageType, GetCostByTag
)
from .tools.account_tools import GetCallerIdentity, GetAccountAlias, GetEnabledRegions, GetAccountSummary
from .tools.resource_tools import (
    ListEC2Instances, ListS3Buckets, ListLambdaFunctions, ListRDSInstances,
    ListEKSClusters, ListLoadBalancers, ListNatGateways
)
from .tools.organization_tools import ListOrganizationalAccounts, DescribeOrganization
from .tools.cloudwatch_tools import ListCloudWatchMetrics, GetCloudWatchMetricData
from .tools.log_tools import ListLogGroups, GetLogEvents
from .tools.pricing_tools import GetPricingProducts
from .tools.capability_tool import GetToolCapabilities

# Tools shown in UI dropdown — only the most useful and meaningful (single-tool use cases)
UI_TOOL_NAMES = [
    "aws_get_today_cost",
    "aws_get_yesterday_cost",
    "aws_get_current_month_cost",
    "aws_get_last_month_cost",
    "aws_get_cost_by_service",
    "aws_get_cost_by_region",
    "aws_get_cost_by_linked_account",
    "aws_get_cost_by_usage_type",
    "aws_get_cost_by_tag",
    "aws_get_cost_trend",
    "aws_get_cost_forecast",
    "aws_get_cost_by_time_range",
    "aws_get_caller_identity",
    "aws_list_ec2_instances",
    "aws_list_s3_buckets",
    "aws_list_lambda_functions",
    "aws_list_rds_instances",
    "aws_list_eks_clusters",
    "aws_list_load_balancers",
    "aws_list_organization_accounts",
    "aws_describe_organization",
    "aws_list_log_groups",
]


# Cost Only Tools (subset of UI tools)
COST_ONLY_TOOL_NAMES = [
    "aws_get_today_cost",
    "aws_get_yesterday_cost",
    "aws_get_current_month_cost",
    "aws_get_last_month_cost",
    "aws_get_cost_by_service",
    "aws_get_cost_by_region",
    "aws_get_cost_by_linked_account",
    "aws_get_cost_by_usage_type",
    "aws_get_cost_by_tag",
    "aws_get_cost_trend",
    "aws_get_cost_forecast",
    "aws_get_cost_by_time_range",
]

class MCPRegistry:
    """
    Central registry for all MCP tools
    Prevents hallucinated tools and enforces contracts
    """
    
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.region = region
        self._tools: Dict[str, MCPTool] = {}
        self._register_all_tools()
    
    def _register_all_tools(self):
        """Register all available MCP tools"""
        
        # Cost & Billing Tools
        self._register(GetTodayCost(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetYesterdayCost(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCurrentMonthCost(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetLastMonthCost(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostByService(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostByRegion(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostTrend(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostForecast(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostAnomalies(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostDimensionValues(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostTags(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostByLinkedAccount(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostByUsageType(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCostByTag(self.aws_access_key, self.aws_secret_key, self.region))
        
        # CANONICAL COST FALLBACK TOOL - Must exist
        self._register(GetCostByTimeRange(self.aws_access_key, self.aws_secret_key, self.region))
        
        # Account & Org Tools
        self._register(GetCallerIdentity(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetAccountAlias(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetAccountSummary(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetEnabledRegions(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListOrganizationalAccounts(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(DescribeOrganization(self.aws_access_key, self.aws_secret_key, self.region))
        
        # Resource Inventory Tools
        self._register(ListEC2Instances(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListS3Buckets(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListLambdaFunctions(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListRDSInstances(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListEKSClusters(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListLoadBalancers(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListNatGateways(self.aws_access_key, self.aws_secret_key, self.region))
        
        # CloudWatch & Pricing & Logs
        self._register(ListCloudWatchMetrics(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetCloudWatchMetricData(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(ListLogGroups(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetLogEvents(self.aws_access_key, self.aws_secret_key, self.region))
        self._register(GetPricingProducts(self.aws_access_key, self.aws_secret_key, self.region))
        
        # Agent Capabilities Tool (Meta-tool)
        # Pass registered tools list (excluding itself, handled inside)
        self._register(GetToolCapabilities(
            self.aws_access_key, 
            self.aws_secret_key, 
            self.region, 
            list(self._tools.values())
        ))
        
        # CRITICAL: Validate canonical tool exists
        self._validate_canonical_tools()
    
    def _validate_canonical_tools(self):
        """Fail fast if critical canonical tools are missing"""
        canonical_tool = "aws_get_cost_by_time_range"
        if canonical_tool not in self._tools:
            raise RuntimeError(
                f"CRITICAL: Canonical cost tool '{canonical_tool}' is missing from registry. "
                "This tool is required for all year/range-based cost queries."
            )
    
    def _register(self, tool: MCPTool):
        """Register a single tool"""
        self._tools[tool.name] = tool
    
    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """Get a tool by name"""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())
    
    def get_tool_description(self, tool_name: str) -> Optional[str]:
        """Get tool description"""
        tool = self.get_tool(tool_name)
        return tool.description if tool else None
    
    def validate_tools(self, tool_names: List[str]) -> Dict[str, bool]:
        """Validate if tool names exist in registry"""
        return {name: name in self._tools for name in tool_names}
    
    def get_tools_catalog(self, mode: str = "inventory_aware") -> List[Dict[str, str]]:
        """Get catalog of all tools for planner context, filtered by mode"""
        
        allowed_list = UI_TOOL_NAMES if mode == "inventory_aware" else COST_ONLY_TOOL_NAMES
        
        # If mode is inventory_aware logic, we basically allow everything except really internal stuff if needed.
        # But 'UI_TOOL_NAMES' seems to be the curated list for the UI.
        # However, planner uses 'get_tools_catalog'. 
        # The user said: "on selection the list of tools should be updated and shown" implying UI selection.
        # But should the Planner also be restricted? Yes, likely.
        
        # Let's just return everything for planner but rely on UI logic?
        # No, if the user works in "Cost Only" mode, planner should probably not try to use inventory tools.
        
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permissions": ", ".join(tool.required_permissions)
            }
            for tool in self._tools.values()
            if (mode == "inventory_aware" or tool.name in COST_ONLY_TOOL_NAMES)
        ]

    def get_ui_tools_catalog(self, mode: str = "inventory_aware") -> List[Dict[str, str]]:
        """Get catalog of tools for UI dropdown only (IAM-allowed list, no meta-tools)"""
        
        target_list = UI_TOOL_NAMES if mode == "inventory_aware" else COST_ONLY_TOOL_NAMES
        
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permissions": ", ".join(tool.required_permissions)
            }
            for name, tool in self._tools.items()
            if name in target_list
        ]
