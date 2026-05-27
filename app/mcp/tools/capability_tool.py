from typing import Any, Dict, List
from . import AWSBaseTool


class GetToolCapabilities(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1", tools_list: List[Dict] = []):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_tool_capabilities"
        self.description = "Check what policies and abilities the agent has (IAM permissions)"
        self.required_permissions = [] # Meta-tool, no AWS API calls directly unless validating
        self.tools_list = tools_list
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        
        def get_capabilities():
            capabilities = []
            for tool in self.tools_list:
                if tool.name == self.name:
                    continue
                    
                capabilities.append({
                    "name": tool.name.replace("aws_", "").replace("_", " ").title(),
                    "permission_needed": ", ".join(tool.required_permissions),
                    "description": tool.description
                })
                
            return {
                "resource_type": "Agent Capability",
                "count": len(capabilities),
                "items": capabilities
            }
        
        return self.safe_execute(get_capabilities, "Failed to get tool capabilities")
