"""
AWS Pricing read-only: GetProducts
"""
from typing import Any, Dict, List
from . import AWSBaseTool


class GetPricingProducts(AWSBaseTool):
    def __init__(self, aws_access_key: str, aws_secret_key: str, region: str = "us-east-1"):
        super().__init__(aws_access_key, aws_secret_key, region)
        self.name = "aws_get_pricing_products"
        self.description = "Get AWS Pricing product list for a service (e.g. AmazonEC2, AmazonS3)"
        self.required_permissions = ["pricing:GetProducts"]

    def execute(self, input_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        service_code = input_data.get('service_code', 'AmazonEC2')
        filters = input_data.get('filters', [])
        max_results = min(int(input_data.get('max_results', 10)), 100)

        pricing_client = self.session.client('pricing', region_name='us-east-1')

        def get_products():
            params = {
                'ServiceCode': service_code,
                'MaxResults': max_results
            }
            if filters:
                params['Filters'] = filters
            response = pricing_client.get_products(**params)
            products = response.get('PriceList', [])
            items = []
            for p in products:
                try:
                    import json
                    prod = json.loads(p) if isinstance(p, str) else p
                    product = prod.get('product', {})
                    items.append({
                        "sku": product.get('sku'),
                        "product_family": product.get('productFamily'),
                        "attributes": product.get('attributes', {})
                    })
                except Exception:
                    items.append({"raw": str(p)[:200]})
            return {
                "resource_type": "Pricing Product",
                "service_code": service_code,
                "count": len(items),
                "items": items
            }
        return self.safe_execute(get_products, "Failed to get pricing products")
