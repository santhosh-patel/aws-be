"""
Account and Organization Tools
"""
from typing import Any, Dict
from . import AWSBaseTool


class GetCallerIdentity(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_caller_identity"
        self.description = "Get current AWS account identity"
        self.required_permissions = ["sts:GetCallerIdentity"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        sts_client = self.get_client('sts')
        
        def get_identity():
            response = sts_client.get_caller_identity()
            return {
                "account_id": response.get('Account'),
                "user_id": response.get('UserId'),
                "arn": response.get('Arn')
            }
        
        return self.safe_execute(get_identity, "Failed to get caller identity")


class GetAccountAlias(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_account_alias"
        self.description = "Get AWS account alias"
        self.required_permissions = ["iam:ListAccountAliases"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        iam_client = self.get_client('iam')
        
        def get_alias():
            response = iam_client.list_account_aliases()
            aliases = response.get('AccountAliases', [])
            return {
                "aliases": aliases,
                "primary_alias": aliases[0] if aliases else None
            }
        
        return self.safe_execute(get_alias, "Failed to get account alias")


class GetEnabledRegions(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_enabled_regions"
        self.description = "Get list of enabled AWS regions"
        self.required_permissions = ["ec2:DescribeRegions"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        ec2_client = self.get_client('ec2')
        
        def get_regions():
            response = ec2_client.describe_regions(AllRegions=False)
            regions = [r['RegionName'] for r in response.get('Regions', [])]
            return {
                "regions": regions,
                "count": len(regions)
            }
        
        return self.safe_execute(get_regions, "Failed to get enabled regions")


class GetAccountSummary(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_account_summary"
        self.description = "Get IAM account summary (users, roles, groups, policies counts)"
        self.required_permissions = ["iam:GetAccountSummary"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        iam_client = self.get_client('iam')

        def get_summary():
            response = iam_client.get_account_summary()
            return {"summary": response.get('Summary', {})}
        return self.safe_execute(get_summary, "Failed to get account summary")
