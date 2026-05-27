from typing import Dict, Any, List
import json
# LLM client duck-typed: any object with chat() method
from ..llm.system_prompt import AWS_READONLY_SYSTEM_PROMPT
from ..llm.json_util import extract_json_balanced
from .models import CanonicalIntent

class IntentCanonicalizer:
    """
    Step 3: Intent Canonicalization
    Maps natural language to a canonical intent.
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client

    def canonicalize(self, user_query: str, skill: str, context_hint: str = "") -> CanonicalIntent:
        """
        Canonicalize the user query based on the routing skill.
        """
        if skill not in ['cost_query', 'resource_inventory', 'account_info', 'overview']:
            if skill == 'greeting':
                return CanonicalIntent(intent='GREETING')
            if skill == 'conversational':
                return CanonicalIntent(intent='CONVERSATIONAL')
            if skill == 'aws_knowledge':
                return CanonicalIntent(intent='AWS_KNOWLEDGE')
            if skill == 'unsupported':
                return CanonicalIntent(intent='UNSUPPORTED')
            return CanonicalIntent(intent='UNKNOWN')

        if skill == 'overview':
            return self._canonicalize_overview(user_query, context_hint)

        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}

You are the Intent Canonicalizer. Map the user query to a strict canonical intent.

SKILL: {skill}
USER QUERY: "{user_query}"
CONTEXT HINT:
{context_hint}

AVAILABLE INTENTS:
- COST_TOTAL: Total cost for a period (e.g. "how much did I spend", "total cost for January", "what's my bill?", "what are my charges?", "how much am I paying?")
- COST_BY_SERVICE: Breakdown by service (e.g. "cost per service", "EC2 cost", "which service cost most", "break down my spending", "where am I spending money?", "show me cost by service", "spending breakdown")
- COST_BY_REGION: Breakdown by region (e.g. "cost by region", "us-east-1 cost", "regional spending")
- COST_BY_ACCOUNT: Breakdown by linked account (e.g. "cost per account", "account-level spending")
- COST_BY_USAGE_TYPE: Breakdown by usage type (e.g. "which instance type cost most", "usage type breakdown")
- COST_BY_TAG: Breakdown by tag (e.g. "cost for Project X", "tagged as production")
- COST_TREND: Historical trend/time series/graph (e.g. "show trend", "cost over time", "data from June till now", "last 6 months", "show me spending history")
- COST_FORECAST: Future prediction (e.g. "predict next month", "forecast", "estimate future cost")
- COST_ANOMALY: Unusual spend detection (e.g. "any unusual spending", "anomalies", "spikes")
- COST_COMPARE: Compare costs across periods or services (e.g. "compare this month vs last month", "compare EC2 and S3 cost")
- COMPREHENSIVE_COST: In-depth cost analysis with breakdown and trend (e.g. "give me full cost details", "deep dive into my costs", "comprehensive cost report")
- RESOURCE_INVENTORY: List resources (e.g. "list ec2", "show buckets", "what resources do I have?", "show me my infrastructure", "list all resources", "what's running?")
- ACCOUNT_METADATA: Account ID, aliases, regions (e.g. "what's my account ID", "account info")
- ACCOUNT_OVERVIEW: Full account overview with cost + resources + identity (e.g. "overview of my account", "tell me everything about my AWS")
- SERVICE_DEEP_DIVE: Deep dive into a specific service (e.g. "tell me more about my EC2", "everything about S3", "deep dive into Lambda")
- CLOUDWATCH_METRICS: List or get metrics (e.g. "show metrics for EC2", "cloudwatch metrics", "list metrics")
- LOG_EVENTS: Read logs (e.g. "show log events", "read logs")

MAPPING RULES:
- IMPORTANT: Users may ask questions in unorganic, messy, or out-of-order ways (e.g. "i need to see for last month my cost break it down by the services"). You must look past grammar and identify the true goal.
- If user asks for cost data across a TIME RANGE without specifying breakdown → COST_TREND
- If user asks "how much" or "total" for a single period → COST_TOTAL
- If user asks "break down" or "by service" or "where is my money going" → COST_BY_SERVICE
- If user asks for breakdown BY something → use appropriate COST_BY_* intent
- If user asks for "full details" or "comprehensive" cost info → COMPREHENSIVE_COST
- If user asks for "overview" or "everything" about account → ACCOUNT_OVERVIEW
- If user asks for "more info" or "deep dive" into a specific service → SERVICE_DEEP_DIVE
- If user says "list all resources" or "what's running" without specifying a service → RESOURCE_INVENTORY
- If query is ambiguous but has date range → default to COST_TREND
- NEVER return UNKNOWN if the query relates to AWS costs, resources, or account info

Return JSON ONLY:
{{
  "intent": "exact_canonical_intent_from_list",
  "confidence": 0.0_to_1.0
}}
"""
        try:
            response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100
            )
            
            json_str = extract_json_balanced(response)
            if not json_str:
                return self._fallback_intent(user_query)
                
            data = json.loads(json_str)
            intent_str = data.get('intent', 'UNKNOWN')
            confidence = data.get('confidence', 1.0)
            
            # Trust LLM more by dropping threshold to 0.4
            if intent_str == 'UNKNOWN' or confidence < 0.4:
                fallback = self._fallback_intent(user_query)
                if fallback.intent != 'UNKNOWN':
                    return fallback
            
            return CanonicalIntent(intent=intent_str, confidence=confidence)
            
        except Exception:
            return self._fallback_intent(user_query)

    def _canonicalize_overview(self, user_query: str, context_hint: str = "") -> CanonicalIntent:
        """Handle overview/comprehensive queries that need multiple tools."""
        lower = user_query.lower()
        
        service_keywords = {
            'ec2': 'ec2', 'instance': 'ec2', 'compute': 'ec2',
            's3': 's3', 'bucket': 's3', 'storage': 's3',
            'lambda': 'lambda', 'function': 'lambda', 'serverless': 'lambda',
            'rds': 'rds', 'database': 'rds',
            'eks': 'eks', 'kubernetes': 'eks',
            'load balancer': 'elb', 'elb': 'elb', 'alb': 'elb',
        }
        
        detected_service = None
        for keyword, service in service_keywords.items():
            if keyword in lower:
                detected_service = service
                break
        
        if detected_service:
            return CanonicalIntent(
                intent='SERVICE_DEEP_DIVE',
                services=[detected_service],
                confidence=0.9
            )
        
        cost_keywords = ['cost', 'spend', 'bill', 'charge', 'pricing', 'expense']
        if any(k in lower for k in cost_keywords):
            return CanonicalIntent(intent='COMPREHENSIVE_COST', confidence=0.9)
        
        return CanonicalIntent(intent='ACCOUNT_OVERVIEW', confidence=0.9)

    def _fallback_intent(self, user_query: str) -> CanonicalIntent:
        """Keyword-based fallback when LLM fails or returns low confidence."""
        query_lower = user_query.lower()
        
        cost_keywords = ['cost', 'spend', 'bill', 'charge', 'price', 'expense', 'pay', 'fee']
        breakdown_keywords = ['by service', 'per service', 'breakdown', 'break down', 'where', 'which service']
        trend_keywords = ['trend', 'over time', 'history', 'historical']
        date_keywords = [
            'from', 'till', 'until', 'since', 'between',
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            'last', 'previous', 'quarter', 'year', 'month'
        ]
        resource_keywords = ['list', 'show instances', 'show buckets', 'inventory', 'resources', 'running']
        
        has_cost = any(k in query_lower for k in cost_keywords)
        has_breakdown = any(k in query_lower for k in breakdown_keywords)
        has_trend = any(k in query_lower for k in trend_keywords)
        has_date = any(k in query_lower for k in date_keywords)
        has_resource = any(k in query_lower for k in resource_keywords)
        
        if has_cost and has_breakdown:
            return CanonicalIntent(intent='COST_BY_SERVICE', confidence=0.8)
        if has_cost and has_trend:
            return CanonicalIntent(intent='COST_TREND', confidence=0.8)
        if has_cost and has_date:
            return CanonicalIntent(intent='COST_TREND', confidence=0.75)
        if has_cost:
            return CanonicalIntent(intent='COST_TOTAL', confidence=0.7)
        if has_resource:
            return CanonicalIntent(intent='RESOURCE_INVENTORY', confidence=0.7)
        
        return CanonicalIntent(intent='UNKNOWN', confidence=0.0)
