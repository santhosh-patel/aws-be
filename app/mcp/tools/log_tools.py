"""
CloudWatch Logs Tools
"""
from typing import Any, Dict, List
from datetime import datetime
from . import AWSBaseTool


class ListLogGroups(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_log_groups"
        self.description = "List CloudWatch Log Groups"
        self.required_permissions = ["logs:DescribeLogGroups"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        logs_client = self.get_client('logs')
        limit = min(int(input_data.get('limit', 50)), 50)
        prefix = input_data.get('prefix')
        
        def list_groups():
            params = {'limit': limit}
            if prefix:
                params['logGroupNamePrefix'] = prefix
                
            response = logs_client.describe_log_groups(**params)
            groups = []
            
            for group in response.get('logGroups', []):
                groups.append({
                    "name": group.get('logGroupName'),
                    "arn": group.get('arn'),
                    "stored_bytes": group.get('storedBytes'),
                    "created": str(datetime.fromtimestamp(group.get('creationTime', 0)/1000)) if group.get('creationTime') else None
                })
            
            return {
                "resource_type": "Log Group",
                "count": len(groups),
                "items": groups
            }
        
        return self.safe_execute(list_groups, "Failed to list log groups")


class GetLogEvents(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_log_events"
        self.description = "Get log events from a Log Group (requires log_group_name, optional: filter_pattern, time range)"
        self.required_permissions = ["logs:FilterLogEvents"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        log_group_name = input_data.get('log_group_name')
        limit = min(int(input_data.get('limit', 20)), 100)
        filter_pattern = input_data.get('filter_pattern')
        start_time = input_data.get('start_time') # Optional timestamp/ISO
        
        if not log_group_name:
            return {"error": "log_group_name is required"}
            
        logs_client = self.get_client('logs')
        
        def get_events():
            params = {
                'logGroupName': log_group_name,
                'limit': limit
            }
            if filter_pattern:
                params['filterPattern'] = filter_pattern
            if start_time:
                # Basic handling, assuming millisecond timestamp for now if int, else ignore
                try:
                    params['startTime'] = int(start_time)
                except:
                    pass
                    
            response = logs_client.filter_log_events(**params)
            events = []
            
            for event in response.get('events', []):
                events.append({
                    "timestamp": str(datetime.fromtimestamp(event.get('timestamp', 0)/1000)),
                    "message": event.get('message'),
                    "stream": event.get('logStreamName')
                })
            
            return {
                "resource_type": "Log Event",
                "log_group": log_group_name,
                "count": len(events),
                "items": events
            }
        
        return self.safe_execute(get_events, "Failed to get log events")
