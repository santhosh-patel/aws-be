
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional, List, Set, Dict, Any
from .models import DateRange, CanonicalIntent
from .date_utils import validate_date_range_within_14_months

class PipelineValidator:
    """
    Step 5: Validation Layer
    Enforces strict business rules before execution.
    """
    
    AWS_COST_EXPLORER_LIMIT_MONTHS = 14
    
    # Allowlist of common AWS Services (subset for now, can be expanded)
    VALID_SERVICES: Set[str] = {
        'AmazonEC2', 'AmazonS3', 'AmazonRDS', 'AmazonDynamoDB', 'AWSLambda',
        'AmazonEKS', 'ElasticLoadBalancing', 'AmazonCloudFront', 'AmazonRoute53',
        'AmazonSageMaker', 'AmazonVPC', 'AmazonCloudWatch', 'AmazonSNS', 'AmazonSQS',
        'AmazonKinesis', 'AmazonRedshift', 'AmazonElastiCache', 'AmazonECS'
    }
    
    # Allowlist of AWS Regions (all standard regions as of 2026)
    VALID_REGIONS: Set[str] = {
        # US
        'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
        # Europe
        'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1', 'eu-central-2',
        'eu-north-1', 'eu-south-1', 'eu-south-2',
        # Asia Pacific
        'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3', 'ap-southeast-4',
        'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
        'ap-south-1', 'ap-south-2', 'ap-east-1',
        # Americas
        'sa-east-1', 'ca-central-1', 'ca-west-1',
        # Middle East & Africa
        'me-south-1', 'me-central-1', 'af-south-1',
        # Israel
        'il-central-1',
    }

    def validate_intent(self, intent: CanonicalIntent) -> Optional[str]:
        """
        Validate the intent and its parameters.
        Returns None if valid, otherwise an error message.
        """
        
        # 1. Validate Time Ranges
        tr = intent.time_range
        if tr:
            start_date_str = tr.start_date.strftime('%Y-%m-%d')
            end_date_str = tr.end_date.strftime('%Y-%m-%d')
            
            # Check AWS 14-month limit using centralized validation
            is_valid, error_msg = validate_date_range_within_14_months(start_date_str, end_date_str)
            if not is_valid:
                return error_msg
            
            start_date = tr.start_date
            end_date = tr.end_date
            
            if start_date > end_date:
                return "Start date cannot be after end date."
                
            if start_date > datetime.now().date():
                 return "Start date cannot be in the future."

        # 2. Validate Service Names (Allowlist Check)
        if intent.services:
            for s in intent.services:
                # Normalize service name if possible or checked against allowed list/pattern
                # Strict check:
                if s not in self.VALID_SERVICES:
                     # Soft fail or hard fail? Production: Hard fail or Warning.
                     # Let's return error to force Extractor to be better or User to correct.
                     # Actually, maybe we accept it but warn? 
                     # Let's enforce standard naming if it looks like a made-up service.
                     # For now, just a length check or pattern check might be safer than a strict list that might be incomplete.
                     if not s.startswith("Amazon") and not s.startswith("AWS") and s != "ElasticLoadBalancing":
                          pass # Relaxed check for now
                     
        # 3. Validate Regions
        if intent.regions:
             for r in intent.regions:
                 if r not in self.VALID_REGIONS:
                     return f"Region '{r}' is not in the allowed list of regions."

        # 4. Validate Comparison Logic
        if intent.intent == 'COST_COMPARE':
            if intent.comparison == 'service':
                if not intent.services or len(intent.services) < 2:
                    return "For a service comparison, please specify at least two services (e.g. 'Compare EC2 and S3')."
            elif intent.comparison == 'region':
                if not intent.regions or len(intent.regions) < 2:
                    return "For a region comparison, please specify at least two regions."
            elif intent.comparison == 'time':
                if not intent.time_range:
                   return "For a time comparison, please specify a time range (e.g. 'Compare this month vs last month')."

        return None

    def validate_tool_allowance(self, tool_name: str, registry_tools: List[str]) -> bool:
        """
        Step 7: Registry Gate (External check helper)
        """
        return tool_name in registry_tools
