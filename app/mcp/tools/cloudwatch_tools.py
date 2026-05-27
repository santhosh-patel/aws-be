"""
CloudWatch read-only tools: ListMetrics, GetMetricData
"""
from typing import Any, Dict, List
from datetime import datetime, timedelta
from . import AWSBaseTool


class ListCloudWatchMetrics(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_cloudwatch_metrics"
        self.description = "List CloudWatch metrics for a namespace (optional: metric name, dimensions)"
        self.required_permissions = ["cloudwatch:ListMetrics"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        namespace = input_data.get('namespace', 'AWS/EC2')
        metric_name = input_data.get('metric_name')
        dimensions = input_data.get('dimensions', [])

        cw_client = self.get_client('cloudwatch')

        def list_metrics():
            params = {'Namespace': namespace}
            if metric_name:
                params['MetricName'] = metric_name
            if dimensions:
                params['Dimensions'] = dimensions
            paginator = cw_client.get_paginator('list_metrics')
            metrics = []
            for page in paginator.paginate(**params):
                metrics.extend(page.get('Metrics', []))
            return {
                "resource_type": "CloudWatch Metric",
                "namespace": namespace,
                "count": len(metrics),
                "items": [
                    {
                        "namespace": m.get('Namespace'),
                        "metric_name": m.get('MetricName'),
                        "dimensions": m.get('Dimensions', [])
                    }
                    for m in metrics
                ]
            }
        return self.safe_execute(list_metrics, "Failed to list CloudWatch metrics")


class GetCloudWatchMetricData(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_cloudwatch_metric_data"
        self.description = "Get CloudWatch metric data (datapoints) for a metric in a time range"
        self.required_permissions = ["cloudwatch:GetMetricData"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        namespace = input_data.get('namespace', 'AWS/EC2')
        metric_name = input_data.get('metric_name', 'CPUUtilization')
        dimensions = input_data.get('dimensions', [])
        start_date = input_data.get('start_date')
        end_date = input_data.get('end_date')
        period = int(input_data.get('period', 3600))

        if not start_date or not end_date:
            return {"success": False, "data": None, "error": "start_date and end_date required"}

        cw_client = self.get_client('cloudwatch')

        def get_data():
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if end > datetime.now():
                end = datetime.now()
            dims = [{"Name": d["Name"], "Value": d["Value"]} for d in dimensions] if dimensions else []
            metric_query = {
                "Id": "m1",
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": metric_name,
                        "Dimensions": dims
                    },
                    "Period": period,
                    "Stat": "Average"
                }
            }
            response = cw_client.get_metric_data(
                MetricDataQueries=[metric_query],
                StartTime=start,
                EndTime=end
            )
            datapoints = []
            for r in response.get('MetricDataResults', []):
                for i, ts in enumerate(r.get('Timestamps', [])):
                    datapoints.append({
                        "timestamp": ts.isoformat(),
                        "value": r.get('Values', [None])[i] if i < len(r.get('Values', [])) else None
                    })
            return {
                "namespace": namespace,
                "metric_name": metric_name,
                "period": period,
                "time_range": {"start": start_date, "end": end_date},
                "datapoints": datapoints,
                "count": len(datapoints)
            }
        return self.safe_execute(get_data, "Failed to get CloudWatch metric data")
