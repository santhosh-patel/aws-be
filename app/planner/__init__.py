"""
Intent and Time Planner - Layer 1
Orchestrates the robust 8-step pipeline:
1. Routing (Skill)
2. Canonicalization (Intent)
3. Extraction (Parameters)
4. Validation (Business Rules)
5. Planning (Tool Selection)
"""
from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from datetime import timedelta
from datetime import date
# LLM client duck-typed: any object with chat() and chat_with_json() methods
# Works with OpenAIClient, AnthropicClient, or any compatible client
from .models import ExecutionPlan, PlanStep, CanonicalIntent
from .router import SkillRouter
from .canonicalizer import IntentCanonicalizer
from .extractor import ParameterExtractor
from .validator import PipelineValidator

class IntentPlanner:
    """
    Orchestrates the 8-step pipeline for robust intent understanding and execution.
    """
    
    def __init__(self, llm_client: Any, registry: Any):
        self.llm = llm_client
        self.registry = registry
        self.router = SkillRouter(llm_client)
        self.canonicalizer = IntentCanonicalizer(llm_client)
        self.extractor = ParameterExtractor(llm_client)
        self.validator = PipelineValidator()
        self.system_date = datetime.now()
        self.last_intent: Optional[CanonicalIntent] = None

    async def plan(
        self,
        user_query: str,
        mode: str = "inventory_aware",
        conversation_history: list = None,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the planning pipeline.
        session_context: optional dict with last_intent, last_time_range, last_services, last_response_type
        for follow-up resolution (e.g. "break that down", "same for last month").
        Returns a dictionary representation of the ExecutionPlan.
        """
        
        # Build conversation context for both router and canonicalizer
        context_hint = ""
        if conversation_history:
            context_lines = []
            for msg in conversation_history[-4:]:
                role_label = "User" if msg.get("role") == "user" else "Agent"
                context_lines.append(f"{role_label}: {msg.get('content', '')}")
            context_hint = "\n".join(context_lines)

        # Step 2: Skill Routing (with conversation context for follow-ups)
        route = self.router.route(user_query, context_hint=context_hint)
        
        # Step 3: Intent Canonicalization
        canonical_intent = self.canonicalizer.canonicalize(user_query, route.skill, context_hint=context_hint)
        
        # Step 4: Parameter Extraction
        enriched_intent = await self.extractor.extract(user_query, canonical_intent)
        
        # Step 4.5: Context Memory Merge (use session_context when provided)
        merged_intent = self._merge_with_history(enriched_intent, user_query=user_query, session_context=session_context)
        
        # Step 5: Validation Layer
        validation_error = self.validator.validate_intent(merged_intent)
        if validation_error:
            # If clarity needed, we could return a specific response type, but for now error plan
            # ideally we return CLARIFICATION_NEEDED intent or similar
            if "please specify" in validation_error.lower():
                 # Could we handle this better? For now user gets the error message.
                 pass
            return self._create_error_plan(validation_error, merged_intent)
            
        # Update History (only if valid)
        self.last_intent = merged_intent

        # Step 6 & 7: Planning & Registry Gate
        # Map canonical intent to tools (Deterministic Planning)
        try:
            steps = self._map_intent_to_tools(merged_intent, mode)
        except ValueError as e:
            return self._create_error_plan(str(e), merged_intent)

        # Construct Final Plan
        plan = ExecutionPlan(
            intent=merged_intent,
            steps=steps,
            user_query=user_query,
            explanation=f"Executing {len(steps)} step(s) for {merged_intent.intent}"
        )
        
        return plan.dict()

    def _merge_with_history(
        self,
        current: CanonicalIntent,
        user_query: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> CanonicalIntent:
        """
        Merge missing parameters from current intent with last successful intent or session_context.
        When session_context is provided, use last_time_range and last_services for short follow-ups.
        """
        query_lower = (user_query or "").lower().strip()
        word_count = len(query_lower.split())
        short_follow_up = word_count <= 8
        same_period_phrases = ["same period", "that period", "same dates", "same range", "that range"]
        break_down_phrases = ["break that down", "break it down", "by service", "by region"]
        what_about_phrases = ["what about", "only ", "just ", "for "]
        
        # Prefer session_context when provided (from chat endpoint)
        if session_context:
            last_tr = session_context.get("last_time_range")
            last_services = session_context.get("last_services") or []
            if last_tr and not current.time_range:
                if short_follow_up or any(p in query_lower for p in same_period_phrases + break_down_phrases):
                    from .models import DateRange
                    start = last_tr.get("start_date")
                    end = last_tr.get("end_date")
                    if start and end:
                        try:
                            current.time_range = DateRange(
                                start_date=datetime.strptime(start, "%Y-%m-%d").date(),
                                end_date=datetime.strptime(end, "%Y-%m-%d").date(),
                            )
                        except (ValueError, TypeError):
                            pass
            if last_services and not current.services and any(p in query_lower for p in what_about_phrases):
                current.services = last_services
        
        if not self.last_intent:
            return current
            
        # Heuristic: If current intent matches last intent (or is compatible), merge params
        # Compatible = both are cost queries or both are resource queries
        
        # Merge Time Range (from in-memory last_intent when not already set)
        if not current.time_range and self.last_intent.time_range:
             current.time_range = self.last_intent.time_range
             
        # Merge Services: If current has none, use last when intent matches
        if not current.services and self.last_intent.services:
            if current.intent == self.last_intent.intent:
                current.services = self.last_intent.services
        
        # Merge Regions
        if not current.regions and self.last_intent.regions:
             current.regions = self.last_intent.regions

        return current

    def _determine_granularity(self, start_date: str, end_date: str) -> str:
        """
        Determine granularity based on 45-day rule.
        > 45 days -> MONTHLY
        <= 45 days -> DAILY
        """
        if not start_date or not end_date:
            return 'MONTHLY'
            
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        delta = (end - start).days
        
        return 'MONTHLY' if delta > 45 else 'DAILY'

    def _resolve_service_tool(self, service: str) -> tuple:
        """Map a service keyword to its list tool. Returns (tool_name, description) or None."""
        service = (service or '').lower()
        mappings = [
            (['ec2', 'instance', 'compute'], 'aws_list_ec2_instances', 'List EC2 instances'),
            (['s3', 'bucket', 'storage'], 'aws_list_s3_buckets', 'List S3 buckets'),
            (['lambda', 'function', 'serverless'], 'aws_list_lambda_functions', 'List Lambda functions'),
            (['rds', 'database', 'db'], 'aws_list_rds_instances', 'List RDS instances'),
            (['eks', 'kubernetes', 'k8s'], 'aws_list_eks_clusters', 'List EKS clusters'),
            (['load balancer', 'elb', 'alb', 'nlb'], 'aws_list_load_balancers', 'List Load Balancers'),
            (['nat', 'nat gateway'], 'aws_list_nat_gateways', 'List NAT Gateways'),
            (['log group', 'cloudwatch log'], 'aws_list_log_groups', 'List CloudWatch Log Groups'),
        ]
        for keywords, tool_name, desc in mappings:
            if any(kw in service for kw in keywords):
                return (tool_name, desc)
        return None

    def _map_intent_to_tools(self, intent: CanonicalIntent, mode: str) -> List[PlanStep]:
        """
        Deterministic mapping from Canonical Intent to Tool Calls.
        Supports single-tool and multi-tool (composite) intents.
        """
        steps = []
        i = intent.intent
        p = intent.params
        
        tr = intent.time_range
        start_date = tr.start_date.strftime('%Y-%m-%d') if tr else None
        end_date = tr.end_date.strftime('%Y-%m-%d') if tr else None
        
        def add_step(name: str, args: Dict[str, Any], desc: str):
            if not self.registry.get_tool(name):
                raise ValueError(f"Required tool '{name}' not found in registry.")
            steps.append(PlanStep(tool_name=name, arguments=args, description=desc))

        def safe_add_step(name: str, args: Dict[str, Any], desc: str):
            """Add step only if tool exists in registry, skip otherwise."""
            if self.registry.get_tool(name):
                steps.append(PlanStep(tool_name=name, arguments=args, description=desc))

        def default_time_range():
            """Provide sensible default time range if none specified."""
            nonlocal start_date, end_date
            if not start_date or not end_date:
                from datetime import timedelta as td
                today = date.today()
                start_date = today.replace(day=1).strftime('%Y-%m-%d')
                end_date = (today + td(days=1)).strftime('%Y-%m-%d')

        if i in ('GREETING', 'CONVERSATIONAL', 'AWS_KNOWLEDGE'):
            pass

        elif i == 'COST_TOTAL':
            default_time_range()
            granularity = self._determine_granularity(start_date, end_date)
            add_step('aws_get_cost_by_time_range', {
                'start_date': start_date,
                'end_date': end_date,
                'granularity': granularity
            }, "Get total cost for period")

        elif i == 'COST_BY_SERVICE':
            default_time_range()
            add_step('aws_get_cost_by_service', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by service")

        elif i == 'COST_BY_REGION':
            default_time_range()
            add_step('aws_get_cost_by_region', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by region")
            
        elif i in ('COST_BY_LINKED_ACCOUNT', 'COST_BY_ACCOUNT'):
            default_time_range()
            add_step('aws_get_cost_by_linked_account', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by account")

        elif i == 'COST_BY_USAGE_TYPE':
            default_time_range()
            add_step('aws_get_cost_by_usage_type', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by usage type")

        elif i == 'COST_BY_TAG':
            default_time_range()
            add_step('aws_get_cost_by_tag', {
                'start_date': start_date,
                'end_date': end_date,
                'tag_key': p.get('tag', 'Project')
            }, "Get cost breakdown by tag")

        elif i == 'COST_TREND':
            default_time_range()
            granularity = self._determine_granularity(start_date, end_date)
            add_step('aws_get_cost_trend', {
                'start_date': start_date,
                'end_date': end_date,
                'granularity': granularity
            }, "Get cost trend")

        elif i == 'COST_FORECAST':
            add_step('aws_get_cost_forecast', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost forecast")
            
        elif i == 'COST_ANOMALY':
            add_step('aws_get_cost_anomalies', {
                'start_date': start_date
            }, "Get cost anomalies")
            
        elif i == 'COST_COMPARE':
            default_time_range()
            if intent.comparison == 'time':
                granularity = self._determine_granularity(start_date, end_date)
                add_step('aws_get_cost_by_time_range', {
                    'start_date': start_date,
                    'end_date': end_date,
                    'granularity': granularity
                }, f"Get cost for {start_date} to {end_date}")
                if tr:
                    duration = tr.end_date - tr.start_date
                    prev_end = tr.start_date - timedelta(days=1)
                    prev_start = prev_end - duration
                    prev_granularity = self._determine_granularity(
                        prev_start.strftime('%Y-%m-%d'), prev_end.strftime('%Y-%m-%d'))
                    add_step('aws_get_cost_by_time_range', {
                        'start_date': prev_start.strftime('%Y-%m-%d'),
                        'end_date': prev_end.strftime('%Y-%m-%d'),
                        'granularity': prev_granularity
                    }, f"Get cost for previous period ({prev_start} to {prev_end})")
            elif intent.comparison == 'service':
                add_step('aws_get_cost_by_service', {
                    'start_date': start_date,
                    'end_date': end_date
                }, "Get cost breakdown for service comparison")
            elif intent.comparison == 'region':
                add_step('aws_get_cost_by_region', {
                    'start_date': start_date,
                    'end_date': end_date
                }, "Get cost breakdown for region comparison")
            else:
                add_step('aws_get_cost_by_service', {
                    'start_date': start_date,
                    'end_date': end_date
                }, "Get cost breakdown")

        elif i == 'COMPREHENSIVE_COST':
            default_time_range()
            granularity = self._determine_granularity(start_date, end_date)
            add_step('aws_get_cost_by_time_range', {
                'start_date': start_date,
                'end_date': end_date,
                'granularity': granularity
            }, "Get total cost for period")
            add_step('aws_get_cost_by_service', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by service")
            add_step('aws_get_cost_trend', {
                'start_date': start_date,
                'end_date': end_date,
                'granularity': granularity
            }, "Get cost trend over time")

        elif i == 'ACCOUNT_OVERVIEW':
            default_time_range()
            safe_add_step('aws_get_caller_identity', {}, "Get account identity")
            safe_add_step('aws_get_cost_by_time_range', {
                'start_date': start_date,
                'end_date': end_date,
                'granularity': 'DAILY'
            }, "Get current period cost")
            safe_add_step('aws_get_cost_by_service', {
                'start_date': start_date,
                'end_date': end_date
            }, "Get cost breakdown by service")
            if mode == 'inventory_aware':
                safe_add_step('aws_list_ec2_instances', {}, "List EC2 instances")
                safe_add_step('aws_list_s3_buckets', {}, "List S3 buckets")

        elif i == 'SERVICE_DEEP_DIVE':
            default_time_range()
            svcs = intent.services if intent.services else [p.get('service', '')]
            for svc_raw in svcs:
                service = (svc_raw or '').lower()
                
                tool_info = self._resolve_service_tool(service)
                if tool_info and mode == 'inventory_aware':
                    safe_add_step(tool_info[0], {}, tool_info[1])
                
                safe_add_step('aws_get_cost_by_service', {
                    'start_date': start_date,
                    'end_date': end_date
                }, f"Get cost breakdown including {svc_raw}")
                
                safe_add_step('aws_get_cost_trend', {
                    'start_date': start_date,
                    'end_date': end_date,
                    'granularity': self._determine_granularity(start_date, end_date)
                }, f"Get cost trend for analysis")
                
                namespace = self._service_to_namespace(service)
                if namespace and mode == 'inventory_aware':
                    safe_add_step('aws_list_cloudwatch_metrics', {
                        'namespace': namespace
                    }, f"List CloudWatch metrics for {svc_raw}")

        elif i == 'RESOURCE_INVENTORY':
            svcs = intent.services if intent.services else [p.get('service', '')]
            
            has_valid_service = False
            for svc_raw in svcs:
                tool_info = self._resolve_service_tool(svc_raw)
                if tool_info:
                    add_step(tool_info[0], {}, tool_info[1])
                    has_valid_service = True
            
            if not has_valid_service:
                if mode == 'inventory_aware':
                    safe_add_step('aws_list_ec2_instances', {}, "List EC2 instances")
                    safe_add_step('aws_list_s3_buckets', {}, "List S3 buckets")
                    safe_add_step('aws_list_lambda_functions', {}, "List Lambda functions")
                    safe_add_step('aws_list_rds_instances', {}, "List RDS instances")
                else:
                    add_step('aws_get_tool_capabilities', {}, "Show available resource tools")

        elif i == 'ACCOUNT_METADATA':
            add_step('aws_get_caller_identity', {}, "Get account identity")
            add_step('aws_get_account_alias', {}, "Get account alias")
            add_step('aws_get_enabled_regions', {}, "List enabled regions")

        elif i == 'CLOUDWATCH_METRICS':
            namespace = p.get('namespace', '')
            if not namespace and intent.services:
                namespace = self._service_to_namespace(intent.services[0])
            if not namespace:
                namespace = 'AWS/EC2'
            add_step('aws_list_cloudwatch_metrics', {
                'namespace': namespace
            }, f"List CloudWatch metrics for {namespace}")
            
        elif i == 'LOG_EVENTS':
            add_step('aws_get_log_events', {
                'log_group_name': p.get('log_group', '')
            }, "Get log events")
             
        elif i == 'UNSUPPORTED':
            pass
             
        elif i == 'UNKNOWN':
            pass

        return steps

    def _service_to_namespace(self, service: str) -> str:
        """Map service keyword to CloudWatch namespace."""
        service = (service or '').lower()
        ns_map = {
            'ec2': 'AWS/EC2', 'instance': 'AWS/EC2', 'compute': 'AWS/EC2',
            's3': 'AWS/S3', 'bucket': 'AWS/S3', 'storage': 'AWS/S3',
            'lambda': 'AWS/Lambda', 'function': 'AWS/Lambda',
            'rds': 'AWS/RDS', 'database': 'AWS/RDS',
            'eks': 'AWS/EKS', 'kubernetes': 'AWS/EKS',
            'elb': 'AWS/ELB', 'load balancer': 'AWS/ELB', 'alb': 'AWS/ApplicationELB',
            'dynamodb': 'AWS/DynamoDB', 'sqs': 'AWS/SQS', 'sns': 'AWS/SNS',
            'cloudfront': 'AWS/CloudFront',
        }
        for keyword, namespace in ns_map.items():
            if keyword in service:
                return namespace
        return ''

    def _create_error_plan(self, message: str, intent: CanonicalIntent) -> Dict[str, Any]:
        """Create a plan that represents an error state."""
        return ExecutionPlan(
            intent=intent,
            steps=[],
            user_query="",
            explanation=message
        ).dict()

