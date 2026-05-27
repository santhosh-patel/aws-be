"""
Organization Tools
"""
from typing import Any, Dict
from . import AWSBaseTool


class ListOrganizationalAccounts(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_organization_accounts"
        self.description = "List all accounts in the AWS Organization"
        self.required_permissions = ["organizations:ListAccounts"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        org_client = self.get_client('organizations')
        
        def list_accounts():
            try:
                paginator = org_client.get_paginator('list_accounts')
                accounts = []
                
                for page in paginator.paginate():
                    for account in page['Accounts']:
                        accounts.append({
                            "id": account.get('Id'),
                            "name": account.get('Name'),
                            "email": account.get('Email'),
                            "status": account.get('Status'),
                            "joined_method": account.get('JoinedMethod'),
                            "joined_timestamp": str(account.get('JoinedTimestamp'))
                        })
                
                return {
                    "resource_type": "AWS Account",
                    "count": len(accounts),
                    "items": accounts
                }
            except org_client.exceptions.AWSOrganizationsNotInUseException:
                return {"error": "This account is not a member of an AWS Organization."}
            except org_client.exceptions.AccessDeniedException:
                return {"error": "Access Denied: You do not have permission to list organization accounts. Ensure you are in the Management Account or a Delegated Administrator."}
            except Exception as e:
                raise e

        return self.safe_execute(list_accounts, "Failed to list organization accounts")


class DescribeOrganization(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_describe_organization"
        self.description = "Describe the AWS Organization (root, features, MASTER account)"
        self.required_permissions = ["organizations:DescribeOrganization"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        org_client = self.get_client('organizations')

        def describe():
            try:
                response = org_client.describe_organization()
                org = response.get('Organization', {})
                return {
                    "id": org.get('Id'),
                    "arn": org.get('Arn'),
                    "master_account_id": org.get('MasterAccountId'),
                    "master_account_email": org.get('MasterAccountEmail'),
                    "feature_set": org.get('FeatureSet'),
                    "available_policy_types": [p.get('Type') for p in org.get('AvailablePolicyTypes', [])]
                }
            except org_client.exceptions.AWSOrganizationsNotInUseException:
                return {"error": "This account is not a member of an AWS Organization."}
            except Exception as e:
                raise e
                
        return self.safe_execute(describe, "Failed to describe organization")
