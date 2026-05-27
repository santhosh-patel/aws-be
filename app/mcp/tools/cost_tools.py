"""
Cost Explorer Tools - All cost-related MCP tools
"""
from typing import Any, Dict
from datetime import datetime, timedelta
from . import AWSBaseTool
from ..schemas import DateRangeInput, CostOutput


class GetTodayCost(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_today_cost"
        self.description = "Get today's AWS cost (partial day)"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': today, 'End': tomorrow},
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            total = 0.0
            if response.get('ResultsByTime'):
                for result in response['ResultsByTime']:
                    amount = result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')
                    total += float(amount)
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "date": today,
                "breakdown": response.get('ResultsByTime', [])
            }
        
        return self.safe_execute(get_cost, "Failed to fetch today's cost")


class GetYesterdayCost(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_yesterday_cost"
        self.description = "Get yesterday's complete AWS cost"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': yesterday, 'End': today},
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            total = 0.0
            if response.get('ResultsByTime'):
                for result in response['ResultsByTime']:
                    amount = result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')
                    total += float(amount)
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "date": yesterday,
                "breakdown": response.get('ResultsByTime', [])
            }
        
        return self.safe_execute(get_cost, "Failed to fetch yesterday's cost")


class GetCurrentMonthCost(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_current_month_cost"
        self.description = "Get current month's AWS cost (month-to-date)"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now()
        month_start = now.replace(day=1).strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': month_start, 'End': tomorrow},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost']
            )
            
            total = 0.0
            if response.get('ResultsByTime'):
                for result in response['ResultsByTime']:
                    amount = result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')
                    total += float(amount)
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{month_start} to {tomorrow}",
                "breakdown": response.get('ResultsByTime', [])
            }
        
        return self.safe_execute(get_cost, "Failed to fetch current month cost")


class GetLastMonthCost(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_last_month_cost"
        self.description = "Get last month's complete AWS cost"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now()
        last_month = now.replace(day=1) - timedelta(days=1)
        month_start = last_month.replace(day=1).strftime("%Y-%m-%d")
        month_end = (now.replace(day=1)).strftime("%Y-%m-%d")
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': month_start, 'End': month_end},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost']
            )
            
            total = 0.0
            if response.get('ResultsByTime'):
                for result in response['ResultsByTime']:
                    amount = result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')
                    total += float(amount)
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{month_start} to {month_end}",
                "breakdown": response.get('ResultsByTime', [])
            }
        
        return self.safe_execute(get_cost, "Failed to fetch last month cost")


class GetCostByService(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_service"
        self.description = "Get AWS cost breakdown by service for a date range"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            services = {}
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    service_name = group.get('Keys', ['Unknown'])[0]
                    amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0'))
                    
                    if service_name not in services:
                        services[service_name] = 0.0
                    services[service_name] += amount
                    total += amount
            
            breakdown = [
                {"service": k, "cost": round(v, 2)} 
                for k, v in sorted(services.items(), key=lambda x: x[1], reverse=True)
            ]
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "breakdown": breakdown
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost by service")


class GetCostByRegion(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_region"
        self.description = "Get AWS cost breakdown by region for a date range"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'REGION'}]
            )
            
            regions = {}
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    region_name = group.get('Keys', ['Unknown'])[0]
                    amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0'))
                    
                    if region_name not in regions:
                        regions[region_name] = 0.0
                    regions[region_name] += amount
                    total += amount
            
            breakdown = [
                {"region": k, "cost": round(v, 2)} 
                for k, v in sorted(regions.items(), key=lambda x: x[1], reverse=True)
            ]
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "breakdown": breakdown
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost by region")


class GetCostTrend(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_trend"
        self.description = "Get daily cost trend for a date range"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        granularity = input_data.get('granularity', 'DAILY')  # Respect granularity parameter
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity=granularity,  # Use provided granularity instead of hardcoding DAILY
                Metrics=['UnblendedCost']
            )
            
            trend = []
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                period_key = 'date' if granularity == 'DAILY' else 'period'
                date = result.get('TimePeriod', {}).get('Start')
                amount = float(result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0'))
                trend.append({period_key: date, "cost": round(amount, 2)})
                total += amount
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "granularity": granularity,  # Include granularity in response
                "trend": trend
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost trend")


class GetCostForecast(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_forecast"
        self.description = "Get AWS cost forecast for future date range"
        self.required_permissions = ["ce:GetCostForecast"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        ce_client = self.get_client('ce')
        
        granularity = input_data.get('granularity', 'MONTHLY')
        if granularity not in ('DAILY', 'MONTHLY'):
            granularity = 'MONTHLY'
        
        def get_forecast():
            response = ce_client.get_cost_forecast(
                TimePeriod={'Start': start_date, 'End': end_date},
                Metric='UNBLENDED_COST',
                Granularity=granularity
            )
            
            total = float(response.get('Total', {}).get('Amount', '0'))
            
            return {
                "forecasted_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "granularity": granularity,
                "forecast_data": response.get('ForecastResultsByTime', [])
            }
        
        return self.safe_execute(get_forecast, "Failed to fetch cost forecast")

class GetCostByTimeRange(AWSBaseTool):
    """
    CANONICAL COST FALLBACK TOOL
    This is the single authoritative tool for generic cost queries.
    All year-based, rolling-range, and custom date queries map here.
    """
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_time_range"
        self.description = "Get total AWS cost for any custom date range (CANONICAL FALLBACK for all year/range queries)"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        if not start_date or not end_date:
            return {
                "success": False,
                "error": "Missing required fields: start_date and end_date",
                "data": None
            }
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days
            
            # Determine granularity: explicit override > 45-day heuristic
            input_granularity = input_data.get('granularity')
            if input_granularity in ('DAILY', 'MONTHLY'):
                granularity = input_granularity
            else:
                granularity = 'MONTHLY' if days_diff > 45 else 'DAILY'
            
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity=granularity,
                Metrics=['UnblendedCost']
            )
            
            total = 0.0
            data_points = []
            
            for result in response.get('ResultsByTime', []):
                period_start = result.get('TimePeriod', {}).get('Start')
                amount = float(result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0'))
                total += amount
                data_points.append({"date": period_start, "cost": round(amount, 2)})
            
            view_type = 'monthly_chart' if granularity == 'MONTHLY' else 'daily_chart'
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": {
                    "start": start_date,
                    "end": end_date
                },
                "granularity": granularity,
                "view_type": view_type,
                "data_points": data_points,
                "days_in_range": days_diff
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost for time range")


class GetCostAnomalies(AWSBaseTool):
    """Uses ce:GetAnomalies only. Requires monitor_arn in input (GetAnomalyMonitors not in IAM)."""
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_anomalies"
        self.description = "Get cost anomalies for a Cost Anomaly Detection monitor (requires monitor_arn)"
        self.required_permissions = ["ce:GetAnomalies"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        today = datetime.now()
        start_date = input_data.get('start_date') or (today - timedelta(days=90)).strftime("%Y-%m-%d")
        end_date = input_data.get('end_date') or today.strftime("%Y-%m-%d")
        monitor_arn = input_data.get('monitor_arn')

        if not monitor_arn:
            return {
                "success": False,
                "data": None,
                "error": "monitor_arn is required. IAM allows only ce:GetAnomalies; provide an anomaly monitor ARN to list anomalies."
            }

        ce_client = self.get_client('ce')

        def get_anomalies():
            response = ce_client.get_anomalies(
                MonitorArn=monitor_arn,
                DateInterval={'StartDate': start_date, 'EndDate': end_date}
            )
            all_anomalies = []
            for anomaly in response.get('Anomalies', []):
                all_anomalies.append({
                    "id": anomaly.get('AnomalyId'),
                    "start_date": anomaly.get('AnomalyStartDate'),
                    "end_date": anomaly.get('AnomalyEndDate'),
                    "score": anomaly.get('AnomalyScore', {}).get('CurrentScore'),
                    "impact": anomaly.get('Impact', {}).get('TotalImpact'),
                    "root_causes": anomaly.get('RootCauses', [])
                })
            return {
                "anomalies": all_anomalies,
                "count": len(all_anomalies),
                "period": f"{start_date} to {end_date}"
            }
        return self.safe_execute(get_anomalies, "Failed to fetch cost anomalies")


class GetCostDimensionValues(AWSBaseTool):
    """Get dimension values for Cost Explorer (e.g. SERVICE, REGION, AZ)."""
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_dimension_values"
        self.description = "Get Cost Explorer dimension values (SERVICE, REGION, AZ, etc.) for a date range"
        self.required_permissions = ["ce:GetDimensionValues"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        dimension = input_data.get('dimension', 'SERVICE')
        if not start_date or not end_date:
            return {"success": False, "data": None, "error": "start_date and end_date required"}
        ce_client = self.get_client('ce')

        def get_dimensions():
            response = ce_client.get_dimension_values(
                TimePeriod={'Start': start_date, 'End': end_date},
                Dimension=dimension,
                Context='COST_AND_USAGE'
            )
            values = [v.get('Value') for v in response.get('DimensionValues', [])]
            return {
                "dimension": dimension,
                "values": values,
                "count": len(values),
                "period": f"{start_date} to {end_date}"
            }
        return self.safe_execute(get_dimensions, "Failed to get dimension values")


class GetCostTags(AWSBaseTool):
    """Get tag keys/values used in Cost Explorer."""
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_tags"
        self.description = "Get Cost Explorer tag keys and values for a date range"
        self.required_permissions = ["ce:GetTags"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        tag_key = input_data.get('tag_key')
        if not start_date or not end_date:
            return {"success": False, "data": None, "error": "start_date and end_date required"}
        ce_client = self.get_client('ce')

        def get_tags():
            params = {'TimePeriod': {'Start': start_date, 'End': end_date}}
            if tag_key:
                params['TagKey'] = tag_key
            response = ce_client.get_tags(**params)
            tags = response.get('Tags', [])
            return {
                "tags": tags,
                "count": len(tags),
                "period": f"{start_date} to {end_date}"
            }
        return self.safe_execute(get_tags, "Failed to get cost tags")


class GetCostByLinkedAccount(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_linked_account"
        self.description = "Get AWS cost breakdown by linked account"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}]
            )
            
            accounts = {}
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    # Key is the Account ID
                    account_id = group.get('Keys', ['Unknown'])[0]
                    amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0'))
                    
                    if account_id not in accounts:
                        accounts[account_id] = 0.0
                    accounts[account_id] += amount
                    total += amount
            
            breakdown = [
                {"account": k, "cost": round(v, 2)} 
                for k, v in sorted(accounts.items(), key=lambda x: x[1], reverse=True)
            ]
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "breakdown": breakdown
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost by linked account")


class GetCostByUsageType(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_usage_type"
        self.description = "Get AWS cost breakdown by usage type (e.g. DataTransfer-Out-Bytes)"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}]
            )
            
            usage_types = {}
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    usage_type = group.get('Keys', ['Unknown'])[0]
                    amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0'))
                    
                    if usage_type not in usage_types:
                        usage_types[usage_type] = 0.0
                    usage_types[usage_type] += amount
                    total += amount
            
            breakdown = [
                {"usage_type": k, "cost": round(v, 2)} 
                for k, v in sorted(usage_types.items(), key=lambda x: x[1], reverse=True)
            ]
            
            # Filter top 50 to avoid huge payloads if too many types
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "breakdown": breakdown[:50],
                "count": len(breakdown)
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost by usage type")


class GetCostByTag(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cost_by_tag"
        self.description = "Get AWS cost breakdown by a specific tag key"
        self.required_permissions = ["ce:GetCostAndUsage"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        tag_key = input_data.get('tag_key')
        
        if not tag_key:
            return {"success": False, "data": None, "error": "tag_key is required"}
        
        ce_client = self.get_client('ce')
        
        def get_cost():
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'TAG', 'Key': tag_key}]
            )
            
            tags = {}
            total = 0.0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    # Key is the Tag Value
                    tag_value = group.get('Keys', ['Unknown'])[0]
                    # Format is often "tag_key$tag_value" or just value depending on API version, 
                    # but usually for GroupBy TAG it returns the value (or key$value).
                    # Boto3 docs: "The keys are returned in the following format: Key:Value."
                    if '$' in tag_value:
                        tag_value = tag_value.split('$', 1)[1]
                    if not tag_value:
                        tag_value = "No Tag"
                        
                    amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0'))
                    
                    if tag_value not in tags:
                        tags[tag_value] = 0.0
                    tags[tag_value] += amount
                    total += amount
            
            breakdown = [
                {"tag_value": k, "cost": round(v, 2)} 
                for k, v in sorted(tags.items(), key=lambda x: x[1], reverse=True)
            ]
            
            return {
                "total_cost": round(total, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "tag_key": tag_key,
                "breakdown": breakdown
            }
        
        return self.safe_execute(get_cost, "Failed to fetch cost by tag")
