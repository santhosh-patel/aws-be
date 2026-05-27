from typing import List, Dict, Optional

class ToolRestrictionLayer:
    """
    Strictly maps Intent -> Allowed Tools.
    Eliminates cross-domain confusion.
    """
    
    # Strict Mapping Matrix provided by User
    RESTRICTIONS = {
        # --- COST ---
        'COST_TODAY': ['aws_get_today_cost'],
        'COST_YESTERDAY': ['aws_get_yesterday_cost'],
        'COST_CURRENT_MONTH': ['aws_get_current_month_cost'],
        'COST_LAST_MONTH': ['aws_get_last_month_cost'],
        'COST_FORECAST': ['aws_get_cost_forecast'],
        'COST_TREND': ['aws_get_cost_trend'],
        'COST_BY_SERVICE': ['aws_get_cost_by_service'],
        'COST_BY_REGION': ['aws_get_cost_by_region'],
        
        # --- RESOURCE ---
        'RESOURCE_EC2': ['aws_list_ec2_instances'],
        'RESOURCE_S3': ['aws_list_s3_buckets'],
        'RESOURCE_LAMBDA': ['aws_list_lambda_functions'],
        'RESOURCE_RDS': ['aws_list_rds_instances'],
        
        # --- ACCOUNT ---
        'ACCOUNT_IDENTITY': ['aws_get_caller_identity'],
        'ACCOUNT_ALIAS': ['aws_get_account_alias'],
        'ACCOUNT_REGIONS': ['aws_get_enabled_regions'],
        
        # --- FALLBACK ---
        'CLARIFICATION_REQUIRED': [] # Should trigger clarification, no tools
    }

    def get_allowed_tools(self, intent: str) -> List[str]:
        """
        Get allowed tools for a specific intent.
        Returns empty list if intent is unknown or requires clarification.
        """
        return self.RESTRICTIONS.get(intent, [])
        
    def is_deterministic(self, intent: str) -> bool:
        """
        Check if intent maps to exactly one tool.
        """
        tools = self.get_allowed_tools(intent)
        return len(tools) == 1
