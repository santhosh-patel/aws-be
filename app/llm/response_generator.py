from __future__ import annotations
"""
Response Generator - Converts AWS data to structured JSON responses
LLM returns structured data only; frontend renders.
Uses AWS Read-Only Observability persona for any LLM fallback.
"""
import json
from typing import Dict, Any, List, Optional
# LLM client duck-typed: any object with chat() method
# Works with OpenAIClient, AnthropicClient, or any compatible client
from .system_prompt import AWS_READONLY_SYSTEM_PROMPT
from .json_util import extract_json_balanced
from .prompt_library import (
    GREETING_RESPONSE, SOCIAL_REPLIES,
    HELP_RESPONSE, TOOLS_RESPONSE, ABOUT_RESPONSE,
    build_tools_response_from_catalog,
)
import random


class ResponseGenerator:
    """
    Converts AWS execution results into structured JSON responses
    Enforces response schemas - no markdown, no tables, no charts in LLM output
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def generate(
        self,
        plan: Dict[str, Any],
        execution_results: Dict[str, Any],
        conversation_history: List[Dict[str, str]] = None,
        mode: Optional[str] = None,
        registry: Any = None,
        last_agent_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON response from execution results
        Returns dict that conforms to one of the response schemas.
        mode/registry: when provided, /tools is built from registry.get_ui_tools_catalog(mode).
        last_agent_summary: optional one-line summary of last agent response for LLM context.
        """
        self._conversation_history = conversation_history or []
        self._last_agent_summary = last_agent_summary
        
        # Extract intent string robustly (handle legacy string vs new dict/object)
        intent_data = plan.get('intent')
        if isinstance(intent_data, dict):
            intent = intent_data.get('intent', 'UNKNOWN')
        else:
            intent = str(intent_data or 'UNKNOWN')

        user_message = (plan.get('user_query') or '').strip()

        # Handle /tools with registry when provided (dynamic catalog)
        if user_message.strip().lower() == '/tools' and registry is not None:
            try:
                catalog = registry.get_ui_tools_catalog(mode or 'inventory_aware')
                return build_tools_response_from_catalog(catalog)
            except Exception:
                pass

        # Handle slash commands FIRST — /help, /tools, /about
        slash_response = self._handle_slash_command(user_message)
        if slash_response:
            return slash_response

        # Handle greeting — rich intro card
        if intent == 'GREETING':
            return self._create_greeting_response(user_message)

        # Handle conversational/social
        if intent == 'CONVERSATIONAL':
            social_reply = self._get_short_social_reply(user_message)
            if social_reply:
                return {
                    "type": "CONVERSATIONAL",
                    "content": social_reply,
                    "message": social_reply
                }
            return self._generate_conversational_response(plan)

        # Handle AWS knowledge questions with LLM explanation
        if intent == 'AWS_KNOWLEDGE':
            return self._generate_knowledge_response(plan)
        
        # Handle clarification needed — use LLM to give a smart, context-aware reply
        if intent == 'CLARIFICATION_NEEDED' or intent == 'UNKNOWN':
            return self._create_smart_clarification(plan)
        
        # Handle error states (explicit failures)
        if not execution_results.get('success', False):
            return self._create_error_response(plan, execution_results)
        
        # Handle embedded errors (successful tool call but returned error data, e.g. "Org not in use")
        results = execution_results.get('results', [])
        for res in results:
            result_obj = res.get('result', {})
            if result_obj and result_obj.get('success'):
                data = result_obj.get('data', {})
                if isinstance(data, dict) and data.get('error'):
                    return {
                        "type": "ERROR_STATE",
                        "error_code": "AWS_ERROR",
                        "message": data['error'],
                        "suggestion": "This usually happens if a service (like AWS Organizations) is not enabled or configured in your account.",
                        "suggestions": ["What's my AWS cost this month?", "List EC2 instances"],
                    }
        
        # Route to appropriate response builder based on intent
        if intent in ['UNSUPPORTED_TIME_RANGE', 'UNSUPPORTED']:
            return self._create_unsupported_time_range_response(plan)
        
        # Determine response type from intent and execution results
        response_type = self._determine_response_type(intent, execution_results)
        
        if response_type == 'COMPOSITE_RESPONSE':
            response = self._create_composite_response(plan, execution_results)
        elif response_type == 'COST_SUMMARY':
            response = self._create_cost_summary(plan, execution_results)
        elif response_type == 'COST_BREAKDOWN':
            response = self._create_cost_breakdown(plan, execution_results)
        elif response_type == 'COST_TIME_SERIES':
            response = self._create_cost_time_series(plan, execution_results)
        elif response_type == 'RESOURCE_LIST':
            response = self._create_resource_list(plan, execution_results)
        elif response_type == 'LOG_EVENTS':
            response = self._create_log_events(plan, execution_results)
        elif response_type == 'METRIC_LIST':
            response = self._create_metric_list(plan, execution_results)
        elif response_type == 'LLM_RESPONSE':
            response = self._generate_with_llm(plan, execution_results)
        else:
            response = self._generate_with_llm(plan, execution_results)
            
        # Inject natural language summary and follow-up suggestions for data responses
        if response and response.get('type') in ['COST_SUMMARY', 'COST_BREAKDOWN', 'COST_TIME_SERIES', 'RESOURCE_LIST', 'METRIC_LIST', 'LOG_EVENTS', 'COMPOSITE_RESPONSE']:
            try:
                ai_message = self._generate_conversational_summary(plan, response)
                response['ai_message'] = ai_message
            except Exception:
                pass
            try:
                response['follow_up_suggestions'] = self._get_follow_up_suggestions(
                    intent, response_type, plan, execution_results
                )
            except Exception:
                response['follow_up_suggestions'] = []
                
        return response
        
    def _generate_conversational_summary(self, plan: Dict[str, Any], response_data: Dict[str, Any]) -> str:
        """Generates a 1-2 sentence conversational summary of the data returned."""
        user_message = (plan.get('user_query') or '').strip()
        data_preview = json.dumps(response_data, default=str)[:1000] # Provide enough structural context
        last_agent_line = ""
        if getattr(self, "_last_agent_summary", None):
            last_agent_line = f"\nLast thing you showed the user: {self._last_agent_summary}\n"
        
        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}
{last_agent_line}
You are a knowledgeable, friendly DevOps engineer explaining AWS data to a colleague.
We just fetched the requested data from AWS. Below is a raw JSON preview of it.
Provide a 1-2 sentence conversational summary that can be displayed above the data table/chart.
End with one short, natural follow-up suggestion in the same tone (e.g. "Want me to break that down by service?" or "I can show the trend for this period if you'd like.").
Do NOT output JSON or lists. Just the natural language string. Use <strong> for emphasis if needed.

USER ASKED: "{user_message}"
DATA PREVIEW: {data_preview}

Your concise, conversational summary:"""

        llm_response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150
        )
        return llm_response.strip() if llm_response else ""
    
    def _get_follow_up_suggestions(
        self,
        intent: str,
        response_type: str,
        plan: Dict[str, Any],
        execution_results: Dict[str, Any],
    ) -> List[str]:
        """Return 2-4 natural-language follow-up suggestions based on intent and response type."""
        suggestions: List[str] = []
        intent_str = intent if isinstance(intent, str) else str(intent or "")
        results = (execution_results or {}).get("results", [])
        first_tool = results[0].get("tool", "") if results and len(results) > 0 else ""
        # Infer service/resource type for RESOURCE_LIST from tool name
        tool_to_service = {
            "aws_list_ec2_instances": "EC2",
            "aws_list_s3_buckets": "S3",
            "aws_list_lambda_functions": "Lambda",
            "aws_list_rds_instances": "RDS",
            "aws_list_eks_clusters": "EKS",
            "aws_list_load_balancers": "Load Balancers",
            "aws_list_nat_gateways": "NAT Gateways",
            "aws_list_log_groups": "CloudWatch Logs",
        }
        service_label = tool_to_service.get(first_tool, "")
        
        if response_type == "COST_SUMMARY":
            suggestions = [
                "Break down by service",
                "Show daily trend for this period",
                "Compare with last month",
            ]
            try:
                from ..utils.currency_converter import get_currency_converter
                if get_currency_converter():
                    suggestions.append("Show in INR")
            except Exception:
                pass
        elif response_type == "COST_BREAKDOWN":
            suggestions = [
                "Show trend for same period",
                "Break down by region",
                "Show cost for last month",
            ]
            if "COST_BY_SERVICE" in intent_str:
                suggestions.append("Break down by region")
            elif "COST_BY_REGION" in intent_str:
                suggestions.append("Break down by service")
        elif response_type == "COST_TIME_SERIES":
            suggestions = [
                "Break down by service for this period",
                "Forecast next month",
                "Compare with previous period",
            ]
        elif response_type == "RESOURCE_LIST":
            suggestions = ["What's the cost for these resources?"]
            if service_label:
                suggestions.append(f"Show CloudWatch metrics for {service_label}")
            suggestions.extend(["List S3 buckets", "List EC2 instances"])
            suggestions = suggestions[:4]
        elif response_type == "METRIC_LIST":
            suggestions = ["Get metric data for this namespace", "Show cost for this service"]
        elif response_type == "LOG_EVENTS":
            suggestions = ["List all log groups", "Show cost for last month"]
        elif response_type == "COMPOSITE_RESPONSE":
            # Derive from primary intent
            if "COST" in intent_str:
                suggestions = ["Break down by service", "Show trend", "Compare with last month"]
            else:
                suggestions = ["Show cost for these resources", "Break down by service"]
        
        return suggestions[:4] if suggestions else []
    
    def _extract_name_from_greeting(self, message: str) -> str:
        """Extract a name from messages like 'Hi Ram', 'Hello Sarah', 'Hey John'. Returns 'there' if none found."""
        import re
        if not message:
            return "there"
        message = message.strip()
        # Patterns: hi/hello/hey followed by a single word (name)
        match = re.search(r"^(?:hi|hello|hey|hiya|howdy)\s+([a-zA-Z][a-zA-Z0-9']{0,20})\b", message, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            return name.capitalize() if name else "there"
        return "there"

    def _time_based_greeting(self) -> str:
        """Return Good morning / Good afternoon / Good evening based on current hour."""
        from datetime import datetime
        hour = datetime.now().hour
        if hour < 12:
            return "Good morning"
        if hour < 17:
            return "Good afternoon"
        return "Good evening"

    def _handle_slash_command(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Detect and handle slash commands: /help, /tools, /about."""
        msg = user_message.strip().lower()
        if msg == '/help':
            return HELP_RESPONSE
        elif msg == '/tools':
            return TOOLS_RESPONSE
        elif msg == '/about':
            return ABOUT_RESPONSE
        return None

    def _create_greeting_response(self, user_message: str = "") -> Dict[str, Any]:
        """Create rich greeting card from prompt library with personalized opening."""
        name = self._extract_name_from_greeting(user_message)
        time_greeting = self._time_based_greeting()
        response = dict(GREETING_RESPONSE)  # copy to avoid mutating the template
        response["title"] = f"Hey {name}! {time_greeting}"
        return response

    def _get_short_social_reply(self, user_message: str) -> Optional[str]:
        """Friendly, contextual reply for conversational intents."""
        user_lower = user_message.lower().strip()
        if any(x in user_lower for x in ["thank", "thanks", "thx", "appreciate"]):
            return "You're welcome! Happy to help. Want me to pull up anything else — costs, resources, metrics? Just say the word."
        elif any(x in user_lower for x in ["bye", "goodbye", "good night", "see you"]):
            return "Take care! I'll be here whenever you need to check on your AWS environment."
        elif any(x in user_lower for x in ["how are you", "how's it going", "how are things", "how do you do"]):
            return "Doing great, thanks for asking! I've been keeping tabs on your cloud. Want to check your spend, list some resources, or dive into metrics?"
        elif any(x in user_lower for x in ["what's up", "whats up", "sup", "wassup"]):
            return "Not much — just watching the clouds! Literally. Want to see what's happening in your AWS account?"
        elif any(x in user_lower for x in ["ok", "okay", "sure", "got it", "understood", "cool", "great", "nice", "perfect", "sounds good", "makes sense"]):
            return "Awesome! I'm right here when you need me — costs, resources, metrics, or type /help if you want to see everything I can do."
        return None

    def _format_history_block(self) -> str:
        """Format conversation history into a string block for LLM prompts."""
        if not self._conversation_history:
            return ""
        lines = []
        for msg in self._conversation_history[-6:]:
            role = "User" if msg.get("role") == "user" else "You"
            lines.append(f"{role}: {msg.get('content', '')}")
        return "\nRECENT CONVERSATION:\n" + "\n".join(lines) + "\n"

    def generate_follow_up_explanation(
        self,
        last_result: Dict[str, Any],
        user_query: str,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate a clear, full explanation when the user asks a follow-up about the previous response
        (e.g. "why is this cost more?", "explain this"). Uses last result + conversation context.
        """
        self._conversation_history = conversation_history or []
        history_block = self._format_history_block()
        last_response = (last_result or {}).get("response") or {}
        if isinstance(last_response, dict):
            summary_parts = []
            if last_response.get("total_cost") is not None:
                summary_parts.append(f"Total cost: ${last_response.get('total_cost', 0):.2f} ({last_response.get('label', 'period')})")
            if last_response.get("time_range"):
                tr = last_response["time_range"]
                summary_parts.append(f"Time range: {tr.get('start', '')} to {tr.get('end', '')}")
            if last_response.get("breakdown"):
                top = last_response["breakdown"][:3]
                summary_parts.append("Top services: " + ", ".join(f"{x.get('name', '')} (${x.get('cost', 0):.2f})" for x in top))
            if last_response.get("points"):
                summary_parts.append(f"Trend: {len(last_response['points'])} data points")
            context_summary = "; ".join(summary_parts) if summary_parts else json.dumps(last_response)[:800]
        else:
            context_summary = str(last_response)[:800]
        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}
{history_block}
You previously showed the user some AWS data. Summary of that response:
{context_summary}

The user is now asking a follow-up about that data. Answer clearly and fully. Reference the numbers above. If they ask "why is this cost more" or "why so high", explain possible reasons (usage, top services, suggestions). Use 2-5 sentences. Use HTML: <strong>, <br>.

USER FOLLOW-UP: "{user_query}"

Your response:"""
        try:
            llm_response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            content = llm_response or "Based on the data I showed you, try asking for a breakdown by service to see what's driving the total."
            return {
                "type": "CONVERSATIONAL",
                "content": content,
                "message": content
            }
        except Exception:
            return {
                "type": "CONVERSATIONAL",
                "content": "To dig into why costs are what they are, try asking for a <strong>breakdown by service</strong> or <strong>daily trend</strong> for the same period.",
                "message": "Fallback follow-up"
            }

    def _generate_conversational_response(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a warm, context-aware conversational response using LLM."""
        user_message = (plan.get('user_query') or '').strip()
        history_block = self._format_history_block()

        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}
{history_block}
The user sent a conversational message. Respond naturally like a friendly DevOps engineer chatting with a colleague.
Be warm, helpful, and if appropriate, suggest something useful you can do (check costs, list resources, etc.).
Use HTML formatting: <strong> for emphasis, <br> for line breaks.
Keep it concise — 2-4 sentences max.

USER MESSAGE: "{user_message}"

Your response:"""

        try:
            llm_response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=300
            )
            content = llm_response or "Hey, I'm here to help! Try asking about your AWS costs, resources, or type /help to see what I can do."
            return {
                "type": "CONVERSATIONAL",
                "content": content,
                "message": content
            }
        except Exception:
            return {
                "type": "CONVERSATIONAL",
                "content": "I'm here and ready to help! Ask me about your AWS costs, resources, metrics, or type /help for a full guide.",
                "message": "Fallback conversational"
            }

    def _create_smart_clarification(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to generate a helpful, context-aware clarification instead of a generic message."""
        user_message = (plan.get('user_query') or '').strip()
        history_block = self._format_history_block()
        last_agent_line = ""
        if getattr(self, "_last_agent_summary", None):
            last_agent_line = f"\nLast agent response: {self._last_agent_summary}\n"

        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}
{history_block}
{last_agent_line}
The user's query was ambiguous. Instead of saying "I don't understand", be helpful:
- Acknowledge what they might be asking about
- Suggest 2-3 specific things you CAN help with based on their message
- Be friendly and conversational, like a DevOps engineer chatting with a colleague
Use HTML formatting: <strong> for emphasis, <br> for line breaks, <ul><li> for suggestions.
Keep it concise — 3-5 sentences.

USER MESSAGE: "{user_message}"

Your helpful response:"""

        try:
            llm_response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=400
            )
            content = llm_response or self._generic_clarification()
            return {
                "type": "CONVERSATIONAL",
                "content": content,
                "message": content,
                "suggestions": [
                    "What's my AWS cost this month?",
                    "List EC2 instances",
                    "Show cost breakdown by service",
                ],
            }
        except Exception:
            return self._create_clarification_response(plan, {})

    def _determine_response_type(self, intent: str, execution_results: Dict[str, Any]) -> str:
        """Determine which response schema to use"""
        
        # Check if tool result explicitly specifies view_type
        results = execution_results.get('results', [])
        view_type = None  # Initialize to prevent UnboundLocalError
        if results:
            first_result = results[0]
            result_data = first_result.get('result', {}).get('data')
            # Defensive check: result_data might be None
            if result_data is not None:
                view_type = result_data.get('view_type')
            
            if view_type == 'monthly_chart':
                return 'COST_TIME_SERIES'
            elif view_type == 'daily_chart':
                return 'COST_TIME_SERIES'
            elif view_type == 'summary_card':
                return 'COST_SUMMARY'
        
        intent_map = {
            'COST_TOTAL': 'COST_SUMMARY',
            'COST_BY_SERVICE': 'COST_BREAKDOWN',
            'COST_BY_REGION': 'COST_BREAKDOWN',
            'COST_BY_ACCOUNT': 'COST_BREAKDOWN',
            'COST_BY_LINKED_ACCOUNT': 'COST_BREAKDOWN',
            'COST_BY_USAGE_TYPE': 'COST_BREAKDOWN',
            'COST_BY_TAG': 'COST_BREAKDOWN',
            'COST_TREND': 'COST_TIME_SERIES',
            'COST_FORECAST': 'COST_TIME_SERIES',
            'COST_ANOMALY': 'RESOURCE_LIST',
            'RESOURCE_INVENTORY': 'RESOURCE_LIST',
            'ACCOUNT_METADATA': 'RESOURCE_LIST',
            'ACCOUNT_OVERVIEW': 'COMPOSITE_RESPONSE',
            'COMPREHENSIVE_COST': 'COMPOSITE_RESPONSE',
            'SERVICE_DEEP_DIVE': 'COMPOSITE_RESPONSE',
            'CLOUDWATCH_METRICS': 'METRIC_LIST', 
            'LOG_EVENTS': 'LOG_EVENTS',
            'PRICING_QUERY': 'RESOURCE_LIST'
        }
        
        if intent in intent_map:
            mapped = intent_map[intent]
            if mapped == 'RESOURCE_LIST' and len(results) > 1:
                tools_used = set(r.get('tool', '') for r in results)
                has_mixed_types = len(tools_used) > 1
                if has_mixed_types:
                    return 'COMPOSITE_RESPONSE'
            return mapped

        # Fallback inspection of tools if intent is ambiguous or UNKNOWN
        if not results:
            return 'ERROR_STATE'
        
        first_result = results[0]
        tool_name = first_result.get('tool', '')
        
        # Simple cost queries → COST_SUMMARY
        if tool_name in ['aws_get_today_cost', 'aws_get_yesterday_cost', 
                         'aws_get_current_month_cost', 'aws_get_last_month_cost']:
            return 'COST_SUMMARY'
        
        # Log Groups List → RESOURCE_LIST
        if tool_name == 'aws_list_log_groups':
            return 'RESOURCE_LIST'
            
        # Log Events
        if tool_name == 'aws_get_log_events':
            return 'LOG_EVENTS'
            
        # CloudWatch Metrics List
        if tool_name == 'aws_list_cloudwatch_metrics':
             return 'METRIC_LIST'

        # Capability check
        if tool_name == 'aws_get_tool_capabilities':
             return 'RESOURCE_LIST'
        
        return 'RESOURCE_LIST'  # Default fallback for conversational/complex queries
    
    def _create_cost_summary(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create COST_SUMMARY response with universal structure
        """
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        if not results[0] or not isinstance(results[0], dict):
            return self._create_no_data_error()
        
        result_obj = results[0].get('result')
        if not result_obj or not isinstance(result_obj, dict):
            return self._create_no_data_error()
            
        result_data = result_obj.get('data') or {}
        if not isinstance(result_data, dict):
            result_data = {}
        time_range = plan.get('resolved_time_range') or {}
        
        # Determine label from tool name
        tool_name = results[0].get('tool', '')
        label_map = {
            'aws_get_today_cost': "Today",
            'aws_get_yesterday_cost': "Yesterday",
            'aws_get_current_month_cost': "Current month",
            'aws_get_last_month_cost': "Last month"
        }
        label = label_map.get(tool_name, "Cost summary")
        
        # Extract period from result_data if available
        period_data = result_data.get('period', {})
        if isinstance(period_data, dict):
            start = period_data.get('start', time_range.get('start_date', result_data.get('date', '')))
            end = period_data.get('end', time_range.get('end_date', result_data.get('date', '')))
        else:
            start = time_range.get('start_date', result_data.get('date', ''))
            end = time_range.get('end_date', result_data.get('date', ''))
        
        # Calculate if drill-down is available (for single month queries)
        drilldown_available = result_data.get('drilldown_available', False)
        
        response = {
            "type": "COST_SUMMARY",
            "label": label,
            "period": {
                "start": start,
                "end": end
            },
            "currency": result_data.get('currency', 'USD'),
            "total_cost": float(result_data.get('total_cost', 0.0)),
            "metadata": {
                "granularity": result_data.get('granularity'),
                "days_in_range": result_data.get('days_in_range')
            },
            "data_freshness_note": "Cost Explorer data may lag by up to 48 hours"
        }
        
        if drilldown_available:
            response["drilldown_available"] = True
        
        return response
    
    def _create_cost_breakdown(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create COST_BREAKDOWN response with universal structure
        """
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        if not results[0] or not isinstance(results[0], dict):
            return self._create_no_data_error()
        
        result_obj = results[0].get('result')
        if not result_obj or not isinstance(result_obj, dict):
            return self._create_no_data_error()
            
        result_data = result_obj.get('data') or {}
        if not isinstance(result_data, dict):
            result_data = {}
        if not isinstance(result_data, dict):
             result_data = {}
        intent_data = plan.get('intent')
        if isinstance(intent_data, dict):
            intent = intent_data.get('intent', 'UNKNOWN')
        else:
            intent = str(intent_data or 'UNKNOWN')
        time_range = plan.get('resolved_time_range') or {}
        
        # Determine dimension
        dimension_map = {
            'COST_BY_SERVICE': 'SERVICE',
            'COST_BY_REGION': 'REGION',
            'COST_BY_ACCOUNT': 'ACCOUNT',
            'COST_BY_USAGE_TYPE': 'USAGE_TYPE',
            'COST_BY_TAG': 'TAG'
        }
        dimension = dimension_map.get(intent, 'SERVICE')
        
        # Fallback detection
        if not dimension or dimension == 'SERVICE':
            breakdown_str = str(result_data.get('breakdown', [])).lower()
            if 'account' in breakdown_str:
                 dimension = 'ACCOUNT'
            elif 'usage_type' in breakdown_str:
                 dimension = 'USAGE_TYPE'
            elif 'tag_value' in breakdown_str:
                 dimension = 'TAG'
        
        # Extract breakdown
        breakdown_raw = result_data.get('breakdown', [])
        breakdown = []
        for item in breakdown_raw:
            name = (
                item.get('service') or 
                item.get('region') or 
                item.get('account') or 
                item.get('usage_type') or 
                item.get('tag_value') or 
                'Unknown'
            )
            cost = float(item.get('cost', 0.0))
            breakdown.append({"name": name, "cost": cost})
        
        # Sort by cost descending
        breakdown.sort(key=lambda x: x['cost'], reverse=True)
        
        # Limit to top 20 for cleaner UI
        breakdown = breakdown[:20]
        
        # Standardized period format
        period_data = result_data.get('period', {})
        if isinstance(period_data, dict):
            start = period_data.get('start', time_range.get('start_date', ''))
            end = period_data.get('end', time_range.get('end_date', ''))
        else:
            start = time_range.get('start_date', '')
            end = time_range.get('end_date', '')
        
        return {
            "type": "COST_BREAKDOWN",
            "dimension": dimension,
            "tag_key": result_data.get('tag_key'),
            "period": {
                "start": start,
                "end": end
            },
            "currency": result_data.get('currency', 'USD'),
            "total_cost": float(result_data.get('total_cost', 0.0)),
            "metadata": {
                "granularity": result_data.get('granularity'),
                "days_in_range": result_data.get('days_in_range')
            },
            "breakdown": breakdown
        }
    
    def _create_cost_time_series(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create COST_TIME_SERIES response with universal structure
        """
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        # Check if first result exists and is not None
        if not results[0] or not isinstance(results[0], dict):
            return self._create_no_data_error()
        
        result_obj = results[0].get('result')
        if not result_obj or not isinstance(result_obj, dict):
            return self._create_no_data_error()
            
        result_data = result_obj.get('data')
        
        # Add null safety check
        if not result_data or not isinstance(result_data, dict):
            return {
                "type": "ERROR_STATE",
                "error_code": "NO_DATA",
                "message": "No cost trend data available for the requested period.",
                "suggestion": "Try a different time range or check AWS credentials."
            }
        
        time_range = plan.get('resolved_time_range') or {}
        
        # Extract time series points (support new data_points field)
        trend = result_data.get('data_points', result_data.get('trend', result_data.get('breakdown', [])))
        points = []
        total_cost = 0.0
        
        for item in trend:
            if not item or not isinstance(item, dict):
                continue
            date = item.get('date') or item.get('period', '')
            cost = float(item.get('cost', 0.0))
            points.append({"date": date, "cost": cost})
            # use provided total if available, otherwise sum it up
            if 'total_cost' not in result_data:
                 total_cost += cost
        
        if 'total_cost' in result_data:
             total_cost = float(result_data['total_cost'])
        
        # Determine granularity
        granularity = result_data.get('granularity', 'MONTHLY')
        if granularity not in ['DAILY', 'MONTHLY']:
            granularity = 'MONTHLY'
            
        view_type = result_data.get('view_type', 'monthly_chart')
        
        # Standardized period format
        period_data = result_data.get('period', {})
        if isinstance(period_data, dict):
            start = period_data.get('start', time_range.get('start_date', ''))
            end = period_data.get('end', time_range.get('end_date', ''))
        else:
            start = time_range.get('start_date', '')
            end = time_range.get('end_date', '')
        
        return {
            "type": "COST_TIME_SERIES",
            "view_type": view_type,
            "granularity": granularity,
            "currency": result_data.get('currency', 'USD'),
            "period": {
                "start": start,
                "end": end
            },
            "total_cost": round(total_cost, 2),
            "metadata": {
                "granularity": granularity,
                "days_in_range": result_data.get('days_in_range')
            },
            "points": points
        }
    
    def _create_resource_list(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create RESOURCE_LIST response"""
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        # Collect resources from all tools
        all_resources = []
        resource_type = 'Resource'
        
        resource_type_map = {
            'aws_list_ec2_instances': 'EC2 Instance',
            'aws_list_s3_buckets': 'S3 Bucket',
            'aws_list_lambda_functions': 'Lambda Function',
            'aws_list_rds_instances': 'RDS Instance',
            'aws_list_eks_clusters': 'EKS Cluster',
            'aws_list_load_balancers': 'Load Balancer',
            'aws_list_nat_gateways': 'NAT Gateway',
            'aws_list_organization_accounts': 'AWS Account',
            'aws_describe_organization': 'Organization',
            'aws_get_account_summary': 'Account Summary',
            'aws_get_cost_anomalies': 'Cost Anomaly',
            'aws_get_cost_dimension_values': 'Cost Dimension',
            'aws_get_cost_tags': 'Cost Tag',
            'aws_get_tool_capabilities': 'Agent Capability',
            'aws_get_caller_identity': 'Identity',
            'aws_get_account_alias': 'Account Alias',
            'aws_get_enabled_regions': 'AWS Region',
            'aws_list_cloudwatch_metrics': 'CloudWatch Metric',
            'aws_get_cloudwatch_metric_data': 'CloudWatch Datapoint',
            'aws_list_log_groups': 'CloudWatch Log Group',
            'aws_get_log_events': 'Log Event',
            'aws_get_pricing_products': 'Pricing Product'
        }
        
        for result in results:
            tool_name = result.get('tool', '')
            result_obj = result.get('result', {})
            
            # Handle None result
            if result_obj is None:
                continue
            
            result_data = result_obj.get('data', {})
            
            # Handle None result_data
            if result_data is None:
                continue
            
            current_type = resource_type_map.get(tool_name, 'Resource')
            
            # Try different keys for resources
            resources_raw = (
                result_data.get('items') or
                result_data.get('resources') or
                result_data.get('anomalies') or
                result_data.get('aliases') or
                result_data.get('regions') or
                result_data.get('instances') or
                result_data.get('buckets') or
                result_data.get('functions') or
                result_data.get('db_instances') or
                result_data.get('datapoints') or
                result_data.get('tags') or
                result_data.get('values') or
                []
            )
            
            # Special case for flat dict results (Caller Identity or Org Description)
            if not resources_raw and (result_data.get('account_id') or result_data.get('master_account_id')):
                resources_raw = [result_data]
            
            for res in resources_raw:
                if res is None:
                    continue
                    
                # Handle string resources (Regions, Aliases)
                if isinstance(res, str):
                    res = {"id": res, "name": res}
                    
                # Intelligent mapping for different fields
                # ID Mapping
                res_id = (
                    res.get('id') or 
                    res.get('instance_id') or
                    res.get('InstanceId') or 
                    res.get('Name') or 
                    res.get('FunctionName') or 
                    res.get('account_id') or 
                    res.get('Namespace') or         # CloudWatch Metric
                    res.get('timestamp') or         # CloudWatch Datapoint
                    'Unknown'
                )

                # Name Mapping
                res_name = (
                    res.get('name') or 
                    res.get('Name') or 
                    res.get('FunctionName') or 
                    res.get('user_id') or 
                    res.get('primary_alias') or 
                    res.get('MetricName') or        # CloudWatch Metric
                    str(res.get('value', '')) or    # CloudWatch Datapoint
                    res.get('service') or           # Pricing
                    res.get('master_account_id') or # Org Master
                    res.get('feature_set')          # Org Feature Set
                )
                
                # Region Mapping
                res_region = (
                    res.get('region') or 
                    res.get('Region') or 
                    res.get('arn') or 
                    'Global'
                )

                all_resources.append({
                    "id": res_id,
                    "type": current_type,
                    "name": res_name,
                    "region": res_region,
                    "state": res.get('state', res.get('State', 'active')),
                    "metadata": res
                })
            
            # Use first non-default resource type
            if current_type != 'Resource':
                resource_type = current_type
        
        return {
            "type": "RESOURCE_LIST",
            "resource_type": resource_type,
            "count": len(all_resources),
            "resources": all_resources
        }
    
    def _create_log_events(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create LOG_EVENTS response"""
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        if not results[0] or not isinstance(results[0], dict):
            return self._create_no_data_error()
        
        result_obj = results[0].get('result')
        if not result_obj or not isinstance(result_obj, dict):
            return self._create_no_data_error()
            
        result_data = result_obj.get('data') or {}
        if not isinstance(result_data, dict):
             result_data = {}
        
        # Handle ListLogGroups results
        if results[0].get('tool') == 'aws_list_log_groups':
            # Map log groups to a resource list style or custom log format
            # For now, let's treat log groups as Resources in RESOURCE_LIST, but if intent is LOG_EVENTS we might want a specific format.
            # However, if the tool was ListLogGroups, _determine_response_type might have returned RESOURCE_LIST if not carefully handled.
            # Let's ensure ListLogGroups returns RESOURCE_LIST and GetLogEvents returns LOG_EVENTS.
            # The current logic makes 'aws_get_log_events' return 'LOG_EVENTS'.
            pass

        events = result_data.get('items', [])
        log_group = result_data.get('log_group', 'Unknown Group')
        
        formatted_events = []
        for event in events:
            formatted_events.append({
                "timestamp": event.get('timestamp'),
                "message": event.get('message'),
                "stream": event.get('stream')
            })
            
        return {
            "type": "LOG_EVENTS",
            "log_group": log_group,
            "count": len(formatted_events),
            "events": formatted_events
        }

    def _create_error_response(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create ERROR_STATE response with clickable suggestions."""
        
        message = execution_results.get('message', 'An error occurred')
        suggestion = execution_results.get('suggestion')
        
        # Determine error code
        error_code = 'UNKNOWN_ERROR'
        if 'permission' in message.lower() or 'unauthorized' in message.lower():
            error_code = 'MISSING_PERMISSION'
        elif 'no data' in message.lower() or 'empty' in message.lower():
            error_code = 'NO_DATA'
        elif 'unsupported' in message.lower() or '14 month' in message.lower():
            error_code = 'UNSUPPORTED_TIME_RANGE'
        
        # Add suggestions for recovery
        if error_code == 'NO_DATA' or error_code == 'UNSUPPORTED_TIME_RANGE':
            suggestions = ["Last 30 days cost", "Current month cost", "Last month cost"]
        elif error_code == 'MISSING_PERMISSION':
            suggestions = ["What's my AWS cost this month?", "List EC2 instances"]
        else:
            suggestions = ["What's my AWS cost this month?", "List EC2 instances", "Show cost breakdown by service"]
        
        return {
            "type": "ERROR_STATE",
            "error_code": error_code,
            "message": message,
            "suggestion": suggestion,
            "suggestions": suggestions,
        }
    
    def _create_unsupported_time_range_response(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Create ERROR_STATE for unsupported time range"""
        return {
            "type": "ERROR_STATE",
            "error_code": "UNSUPPORTED_TIME_RANGE",
            "message": "AWS Cost Explorer only retains the last 14 months of data.",
            "suggestion": plan.get('fallback_suggestion', "Try asking for the last 12 months instead."),
            "suggestions": ["Last 30 days cost", "Current month cost", "Last month cost"],
        }
    
    def _create_no_data_error(self) -> Dict[str, Any]:
        """Create ERROR_STATE for no data"""
        return {
            "type": "ERROR_STATE",
            "error_code": "NO_DATA",
            "message": "No data available for the requested query.",
            "suggestion": "Try a different time range or check your AWS account activity.",
            "suggestions": ["Last 30 days cost", "Current month cost", "Last month cost"],
        }
    
    def _create_clarification_response(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create CLARIFICATION_NEEDED response"""
        intent_data = plan.get('intent', {})
        if isinstance(intent_data, dict):
            intent_obj = intent_data
        else:
            intent_obj = {}
        
        # Determine what's missing
        missing_params = []
        suggestions = []
        
        # Check for missing time range
        if not intent_obj.get('time_range'):
            missing_params.append("time_range")
            suggestions.extend(["today", "yesterday", "current month", "last month", "last 30 days"])
        
        # Check for missing services in service comparison
        if intent_obj.get('intent') == 'COST_BY_SERVICE' and not intent_obj.get('services'):
            missing_params.append("services")
            suggestions.extend(["EC2", "S3", "RDS", "Lambda"])
        
        # Default message
        if not missing_params:
            message = "I need more information to complete your request. Could you please provide more details?"
            suggestions = ["What's my AWS cost this month?", "List EC2 instances", "Show cost breakdown by service"]
        elif "time_range" in missing_params:
            message = "Please specify a time range for your cost query. For example: 'today', 'yesterday', 'current month', 'last month', or a custom range like 'last 3 months'."
            suggestions = ["What's my cost today?", "Show last month cost", "Current month cost"]
        elif "services" in missing_params:
            message = "Please specify which AWS services you'd like to analyze. For example: 'EC2', 'S3', or 'RDS'."
            suggestions = ["Cost breakdown by service for last 30 days", "EC2 cost", "S3 cost"]
        else:
            message = f"Please provide: {', '.join(missing_params)}"
            suggestions = ["What's my AWS cost this month?", "List EC2 instances"]
        
        return {
            "type": "CLARIFICATION_NEEDED",
            "message": message,
            "missing_parameters": missing_params,
            "suggestions": suggestions,
        }
    
    def _create_metric_list(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create METRIC_LIST response with unrolled dimensions for tabular display"""
        
        # Comprehensive null safety
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()
        
        results = execution_results.get('results', [])
        if not results or not isinstance(results, list):
            return self._create_no_data_error()
        
        if not results[0] or not isinstance(results[0], dict):
            return self._create_no_data_error()

        result_obj = results[0].get('result')
        if not result_obj or not isinstance(result_obj, dict):
            return self._create_no_data_error()
            
        result_data = result_obj.get('data') or {}
        if not isinstance(result_data, dict):
             result_data = {}
        items = result_data.get('items', [])
        
        flattened_metrics = []
        for item in items:
            namespace = item.get('namespace', 'Unknown')
            metric_name = item.get('metric_name', 'Unknown')
            dimensions = item.get('dimensions', [])
            
            # If no dimensions, add single row with empty dim fields
            if not dimensions:
                flattened_metrics.append({
                    "namespace": namespace,
                    "metric_name": metric_name,
                    "dimension_name": "-",
                    "dimension_value": "-"
                })
            else:
                # Unroll dimensions into separate rows as requested by user
                for d in dimensions:
                    flattened_metrics.append({
                        "namespace": namespace,
                        "metric_name": metric_name,
                        "dimension_name": d.get('Name', '-'),
                        "dimension_value": d.get('Value', '-')
                    })
        
        return {
            "type": "METRIC_LIST",
            "count": len(flattened_metrics),
            "metrics": flattened_metrics
        }

    def _create_composite_response(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create COMPOSITE_RESPONSE that bundles multiple sub-responses from multi-tool execution.
        Each tool result is mapped to its appropriate response type.
        """
        if not execution_results or not isinstance(execution_results, dict):
            return self._create_no_data_error()

        results = execution_results.get('results', [])
        if not results:
            return self._create_no_data_error()

        intent_data = plan.get('intent', {})
        intent = intent_data.get('intent', 'UNKNOWN') if isinstance(intent_data, dict) else str(intent_data)
        steps = plan.get('steps', [])

        sections = []
        tool_response_map = {
            'aws_get_cost_by_time_range': 'COST_SUMMARY',
            'aws_get_cost_by_service': 'COST_BREAKDOWN',
            'aws_get_cost_by_region': 'COST_BREAKDOWN',
            'aws_get_cost_trend': 'COST_TIME_SERIES',
            'aws_get_cost_forecast': 'COST_TIME_SERIES',
            'aws_list_ec2_instances': 'RESOURCE_LIST',
            'aws_list_s3_buckets': 'RESOURCE_LIST',
            'aws_list_lambda_functions': 'RESOURCE_LIST',
            'aws_list_rds_instances': 'RESOURCE_LIST',
            'aws_list_eks_clusters': 'RESOURCE_LIST',
            'aws_list_load_balancers': 'RESOURCE_LIST',
            'aws_list_nat_gateways': 'RESOURCE_LIST',
            'aws_list_log_groups': 'RESOURCE_LIST',
            'aws_get_caller_identity': 'RESOURCE_LIST',
            'aws_get_account_alias': 'RESOURCE_LIST',
            'aws_get_enabled_regions': 'RESOURCE_LIST',
            'aws_list_cloudwatch_metrics': 'METRIC_LIST',
            'aws_get_cost_anomalies': 'RESOURCE_LIST',
        }

        for idx, result in enumerate(results):
            tool_name = result.get('tool', '')
            result_obj = result.get('result', {})

            if not result_obj or not isinstance(result_obj, dict):
                continue
            if not result_obj.get('success', False):
                continue

            response_type = tool_response_map.get(tool_name, 'RESOURCE_LIST')
            
            sub_execution = {
                'success': True,
                'intent': intent,
                'results': [result]
            }

            try:
                if response_type == 'COST_SUMMARY':
                    sub_response = self._create_cost_summary(plan, sub_execution)
                elif response_type == 'COST_BREAKDOWN':
                    sub_response = self._create_cost_breakdown(plan, sub_execution)
                elif response_type == 'COST_TIME_SERIES':
                    sub_response = self._create_cost_time_series(plan, sub_execution)
                elif response_type == 'METRIC_LIST':
                    sub_response = self._create_metric_list(plan, sub_execution)
                else:
                    sub_response = self._create_resource_list(plan, sub_execution)

                if sub_response and sub_response.get('type') != 'ERROR_STATE':
                    step_desc = steps[idx].get('description', tool_name) if idx < len(steps) else tool_name
                    sections.append({
                        'title': step_desc,
                        'response': sub_response
                    })
            except Exception:
                continue

        if not sections:
            return self._create_no_data_error()

        title_map = {
            'ACCOUNT_OVERVIEW': 'Account Overview',
            'COMPREHENSIVE_COST': 'Comprehensive Cost Analysis',
            'SERVICE_DEEP_DIVE': 'Service Deep Dive',
        }

        return {
            'type': 'COMPOSITE_RESPONSE',
            'title': title_map.get(intent, 'Detailed Report'),
            'section_count': len(sections),
            'sections': sections
        }

    def _generic_clarification(self) -> str:
        return ("Hmm, I'm not quite sure what you're looking for there! Here are some things I can help with:<br>"
                "<ul><li><strong>Cost queries</strong> — \"What's my AWS cost this month?\"</li>"
                "<li><strong>Resources</strong> — \"List my EC2 instances\"</li>"
                "<li><strong>Metrics</strong> — \"Show CloudWatch metrics for EC2\"</li>"
                "<li><strong>AWS knowledge</strong> — \"What is Lambda?\"</li></ul>"
                "Just let me know what you'd like to explore!")

    def _generate_knowledge_response(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an educational/knowledge response using LLM with conversation context."""
        user_message = (plan.get('user_query') or '').strip()
        history_block = self._format_history_block()
        last_agent_line = ""
        if getattr(self, "_last_agent_summary", None):
            last_agent_line = f"\nLast agent response: {self._last_agent_summary}\n"

        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}
{history_block}
{last_agent_line}
The user is asking a question. Provide a clear, concise, helpful explanation.
Be conversational like a DevOps engineer explaining to a colleague — friendly and practical.
Use the conversation history above to stay on topic and reference earlier context when relevant.
Use HTML formatting: <strong> for emphasis, <br> for line breaks, <ul><li> for lists.
Keep the response focused and practical. Do NOT include JSON or code blocks.
If you can suggest a follow-up action (like checking actual data), mention it naturally.

USER QUESTION: "{user_message}"

Your response:"""

        try:
            llm_response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024
            )
            return {
                "type": "LLM_RESPONSE",
                "content": llm_response or "I don't have information on that topic, but feel free to ask me about your AWS costs, resources, or metrics!",
                "message": "AWS knowledge explanation"
            }
        except Exception:
            return {
                "type": "LLM_RESPONSE",
                "content": "I wasn't able to generate an explanation right now. Try rephrasing your question, or ask me to check your AWS costs or resources instead!",
                "message": "Fallback"
            }

    def _generate_with_llm(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback: Use LLM to generate structured response for complex cases
        LLM must return ONLY valid JSON conforming to response schemas
        """
        
        prompt = self._build_structured_response_prompt(plan, execution_results)
        
        try:
            llm_response = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048
            )
            
            # Extract JSON robustly using balanced brace counter
            if not llm_response:
                 return self._create_no_data_error()
            
            json_str = extract_json_balanced(llm_response)
            if not json_str:
                 return {
                    "type": "LLM_RESPONSE",
                    "content": llm_response,
                    "message": "Conversational explanation from AWS tool results."
                 }
            
            response_json = json.loads(json_str)
            
            # Validate it has correct type
            if response_json.get('type') not in ['COST_SUMMARY', 'COST_BREAKDOWN', 'COST_TIME_SERIES', 'RESOURCE_LIST', 'METRIC_LIST', 'ERROR_STATE', 'LLM_RESPONSE']:
                return self._create_no_data_error()
            
            return response_json
            
        except Exception as e:
            return {
                "type": "ERROR_STATE",
                "error_code": "UNKNOWN_ERROR",
                "message": f"Failed to generate structured response: {str(e)}",
                "suggestion": "Please try rephrasing your question."
            }
    
    def _build_structured_response_prompt(self, plan: Dict[str, Any], execution_results: Dict[str, Any]) -> str:
        """Build prompt for LLM to generate structured JSON response"""
        
        intent = plan.get('intent')
        time_range = plan.get('resolved_time_range') or {}
        results_json = json.dumps(execution_results, indent=2)
        
        return f"""{AWS_READONLY_SYSTEM_PROMPT}

---

You are formatting tool output into structured JSON for the same read-only agent. You MUST return valid JSON only.
Do NOT return markdown.
Do NOT print tables.
Do NOT describe charts.
Do NOT add explanations outside JSON fields.

USER INTENT: {intent}
TIME RANGE: {time_range.get('start_date')} to {time_range.get('end_date')}

EXECUTION RESULTS:
{results_json}

REQUIRED RESPONSE TYPES:
1. COST_SUMMARY - for single cost values (today, yesterday, month total)
2. COST_BREAKDOWN - for breakdowns by service/region/account
3. COST_TIME_SERIES - for historical trends and time series
4. RESOURCE_LIST - for resource inventory and capabilities
5. ERROR_STATE - for errors or unsupported queries
6. LLM_RESPONSE - for conversational answers, explanations without data, or when no tool matches (return "content" field with markdown)

Rules:
- Choose the correct response type based on the intent and data
- Preserve numeric accuracy from AWS data
- Never invent values
- Never infer missing data
- Never change time ranges
- Return ONLY the JSON object, no extra text

The frontend will render tables and charts from your JSON.

Generate the structured JSON response now:"""
