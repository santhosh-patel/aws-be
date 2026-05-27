"""
Resource Inventory Tools
"""
from typing import Any, Dict
from . import AWSBaseTool


class ListEC2Instances(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_ec2_instances"
        self.description = "List all EC2 instances"
        self.required_permissions = ["ec2:DescribeInstances"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        ec2_client = self.get_client('ec2')
        
        def list_instances():
            try:
                paginator = ec2_client.get_paginator('describe_instances')
                instances = []
                
                for page in paginator.paginate():
                    for reservation in page.get('Reservations', []):
                        for instance in reservation.get('Instances', []):
                            tags = {
                                t.get('Key'): t.get('Value')
                                for t in instance.get('Tags', [])
                                if t.get('Key')
                            }
                            name = tags.get('Name', '')
                            instances.append({
                                "instance_id": instance.get('InstanceId'),
                                "instance_type": instance.get('InstanceType'),
                                "state": instance.get('State', {}).get('Name'),
                                "name": name,
                                "tags": tags,
                                "launch_time": str(instance.get('LaunchTime')),
                                "availability_zone": instance.get('Placement', {}).get('AvailabilityZone'),
                                "private_ip": instance.get('PrivateIpAddress'),
                                "public_ip": instance.get('PublicIpAddress'),
                            })
                
                return {
                    "resource_type": "EC2 Instance",
                    "count": len(instances),
                    "items": instances
                }
            except Exception as e:
                if "UnauthorizedOperation" in str(e) or "AccessDenied" in str(e):
                    return {"error": "Access Denied: You do not have permission to list EC2 instances."}
                raise e
        
        return self.safe_execute(list_instances, "Failed to list EC2 instances")


class ListS3Buckets(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_s3_buckets"
        self.description = "List all S3 buckets"
        self.required_permissions = ["s3:ListAllMyBuckets"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        s3_client = self.get_client('s3')
        
        def list_buckets():
            response = s3_client.list_buckets()
            buckets = []
            
            for bucket in response.get('Buckets', []):
                buckets.append({
                    "name": bucket.get('Name'),
                    "creation_date": str(bucket.get('CreationDate'))
                })
            
            return {
                "resource_type": "S3 Bucket",
                "count": len(buckets),
                "items": buckets
            }
        
        return self.safe_execute(list_buckets, "Failed to list S3 buckets")


class ListLambdaFunctions(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_lambda_functions"
        self.description = "List all Lambda functions"
        self.required_permissions = ["lambda:ListFunctions"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        lambda_client = self.get_client('lambda')
        
        def list_functions():
            paginator = lambda_client.get_paginator('list_functions')
            functions = []
            
            for page in paginator.paginate():
                for func in page.get('Functions', []):
                    functions.append({
                        "function_name": func.get('FunctionName'),
                        "runtime": func.get('Runtime'),
                        "memory": func.get('MemorySize'),
                        "timeout": func.get('Timeout'),
                        "code_size": func.get('CodeSize'),
                        "last_modified": func.get('LastModified'),
                        "handler": func.get('Handler')
                    })
            
            return {
                "resource_type": "Lambda Function",
                "count": len(functions),
                "items": functions
            }
        
        return self.safe_execute(list_functions, "Failed to list Lambda functions")


class ListRDSInstances(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_rds_instances"
        self.description = "List all RDS instances"
        self.required_permissions = ["rds:DescribeDBInstances"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        rds_client = self.get_client('rds')
        
        def list_instances():
            response = rds_client.describe_db_instances()
            instances = []
            
            for db in response.get('DBInstances', []):
                instances.append({
                    "db_identifier": db.get('DBInstanceIdentifier'),
                    "engine": db.get('Engine'),
                    "instance_class": db.get('DBInstanceClass'),
                    "status": db.get('DBInstanceStatus')
                })
            
            return {
                "resource_type": "RDS Instance",
                "count": len(instances),
                "items": instances
            }
        
        return self.safe_execute(list_instances, "Failed to list RDS instances")


class ListEKSClusters(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_eks_clusters"
        self.description = "List all EKS clusters"
        self.required_permissions = ["eks:ListClusters"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        eks_client = self.get_client('eks')
        
        def list_clusters():
            response = eks_client.list_clusters()
            clusters = response.get('clusters', [])
            
            # Optionally describe clusters for more details, but kept simple for now
            cluster_details = []
            for cluster_name in clusters:
                cluster_details.append({
                    "name": cluster_name,
                    "type": "EKS Cluster"
                })
            
            return {
                "resource_type": "EKS Cluster",
                "count": len(cluster_details),
                "items": cluster_details
            }
        
        return self.safe_execute(list_clusters, "Failed to list EKS clusters")


class ListLoadBalancers(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_load_balancers"
        self.description = "List all Elastic Load Balancers (ALB/ELB/NLB)"
        self.required_permissions = ["elasticloadbalancing:DescribeLoadBalancers"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        elbv2_client = self.get_client('elbv2')
        
        def list_lbs():
            # This only covers V2 (ALB/NLB). Classic ELB needs a different client ('elb').
            # Prioritizing Modern V2.
            response = elbv2_client.describe_load_balancers()
            lbs = []
            
            for lb in response.get('LoadBalancers', []):
                lbs.append({
                    "name": lb.get('LoadBalancerName'),
                    "dns_name": lb.get('DNSName'),
                    "type": lb.get('Type'),
                    "state": lb.get('State', {}).get('Code'),
                    "scheme": lb.get('Scheme')
                })
            
            return {
                "resource_type": "Load Balancer",
                "count": len(lbs),
                "items": lbs
            }
        
        return self.safe_execute(list_lbs, "Failed to list load balancers")


class ListNatGateways(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_list_nat_gateways"
        self.description = "List all NAT Gateways"
        self.required_permissions = ["ec2:DescribeNatGateways"]
    
    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        ec2_client = self.get_client('ec2')
        
        def list_nat_gateways():
            response = ec2_client.describe_nat_gateways()
            nats = []
            
            for nat in response.get('NatGateways', []):
                nats.append({
                    "nat_gateway_id": nat.get('NatGatewayId'),
                    "vpc_id": nat.get('VpcId'),
                    "subnet_id": nat.get('SubnetId'),
                    "state": nat.get('State'),
                    "public_ip": nat.get('NatGatewayAddresses', [{}])[0].get('PublicIp')
                })
            
            return {
                "resource_type": "NAT Gateway",
                "count": len(nats),
                "items": nats
            }
        
        return self.safe_execute(list_nat_gateways, "Failed to list NAT gateways")
