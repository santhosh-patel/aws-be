from typing import Dict, Any
import json
import re
# LLM client duck-typed: any object with chat() method
from ..llm.system_prompt import AWS_READONLY_SYSTEM_PROMPT
from ..llm.json_util import extract_json_balanced
from .models import SkillRoute

VALID_SKILLS = {
    'cost_query', 'resource_inventory', 'account_info', 'overview',
    'aws_knowledge', 'greeting', 'conversational', 'unsupported',
    'clarification_needed',
}

class SkillRouter:
    """
    Step 2: Skill Routing
    Classifies user input into a specific skill domain.
    """
    
    GREETING_PATTERNS = [
        'hi', 'hello', 'hey', 'hola', 'howdy', 'good morning', 'good afternoon',
        'good evening', 'help', 'what can you do', 'who are you'
    ]
    CONVERSATIONAL_PATTERNS = [
        'thanks', 'thank you', 'thx', 'bye', 'goodbye', 'see you',
        'ok', 'okay', 'sure', 'got it', 'cool', 'great', 'nice',
        'how are you', "how's it going", "what's up", 'whats up',
        'good night', 'appreciate it'
    ]
    OVERVIEW_PATTERNS = [
        'overview', 'summary of my account', 'tell me everything',
        'complete summary', 'full report', 'account dashboard',
        'what does my aws look like', 'show me my aws', 'aws summary',
        'give me a complete', 'comprehensive', 'full picture',
        'all about my account', 'account summary', 'overall'
    ]
    
    COST_KEYWORDS = [
        'cost', 'spend', 'spending', 'spent', 'bill', 'billing', 'charge',
        'charges', 'price', 'pricing', 'expense', 'budget', 'invoice',
        'pay', 'paying', 'payment', 'money', 'dollar', 'forecast',
        'anomaly', 'anomalies', 'trend', 'how much',
    ]
    RESOURCE_KEYWORDS = [
        'list', 'show', 'describe', 'count', 'how many', 'instances',
        'buckets', 'functions', 'databases', 'clusters', 'resources',
        'running', 'infrastructure', 'ec2', 's3', 'lambda', 'rds',
        'eks', 'elb', 'nat', 'load balancer',
    ]
    ACCOUNT_KEYWORDS = [
        'account id', 'account alias', 'who am i', 'my account',
        'region', 'which region', 'identity', 'caller identity',
    ]
    KNOWLEDGE_PATTERNS = [
        r'\bwhat is\b', r'\bwhat are\b', r'\bexplain\b', r'\bhow does\b',
        r'\bdifference between\b', r'\bwhat\'s the diff\b',
    ]
    UNSUPPORTED_KEYWORDS = [
        'delete', 'remove', 'create', 'launch', 'start', 'stop',
        'terminate', 'reboot', 'resize', 'modify', 'update', 'put',
    ]
    
    def __init__(self, llm_client):
        self.llm = llm_client

    def _keyword_fallback(self, lower_query: str) -> SkillRoute:
        """Deterministic keyword heuristics when LLM routing fails or returns ambiguous result."""
        if any(kw in lower_query for kw in self.COST_KEYWORDS):
            return SkillRoute(skill='cost_query', confidence=0.75)
        if any(kw in lower_query for kw in self.RESOURCE_KEYWORDS):
            return SkillRoute(skill='resource_inventory', confidence=0.70)
        if any(kw in lower_query for kw in self.ACCOUNT_KEYWORDS):
            return SkillRoute(skill='account_info', confidence=0.70)
        if any(re.search(p, lower_query) for p in self.KNOWLEDGE_PATTERNS):
            return SkillRoute(skill='aws_knowledge', confidence=0.65)
        if any(kw in lower_query for kw in self.UNSUPPORTED_KEYWORDS):
            return SkillRoute(skill='unsupported', confidence=0.70)
        return SkillRoute(skill='aws_knowledge', confidence=0.40)

    def route(self, user_query: str, context_hint: str = "") -> SkillRoute:
        """
        Route the user query to a skill.
        Uses fast keyword matching first, then LLM for complex queries,
        with keyword fallback when LLM is ambiguous.
        """
        lower_query = user_query.lower().strip()
        
        if any(lower_query.startswith(p) or lower_query == p for p in self.GREETING_PATTERNS):
            return SkillRoute(skill='greeting', confidence=1.0)
        if any(p in lower_query for p in self.CONVERSATIONAL_PATTERNS) and len(lower_query.split()) <= 6:
            return SkillRoute(skill='conversational', confidence=1.0)
        if any(p in lower_query for p in self.OVERVIEW_PATTERNS):
            return SkillRoute(skill='overview', confidence=0.95)
        
        context_block = ""
        if context_hint:
            context_block = f"""
RECENT CONVERSATION (use this to understand follow-up questions like "what about EC2?" or "break that down"):
{context_hint}
"""

        prompt = f"""{AWS_READONLY_SYSTEM_PROMPT}

You are the Skill Router. Classify the user query into EXACTLY ONE skill.
{context_block}
SKILLS (with examples):

1. cost_query — Questions about AWS costs, billing, spend, usage fees, pricing, charges, trends, forecasts, anomalies, or anything money-related.
   Examples: "how much did I spend today?", "show me last month's cost", "EC2 cost breakdown", "cost trend from Jan to now", "any spending anomalies?", "predict next month's cost", "what is my bill?", "what are my charges?", "break down my spending", "show me where I'm spending money", "how much am I paying for Lambda?"

2. resource_inventory — Questions about listing or describing AWS resources.
   Examples: "list my EC2 instances", "show S3 buckets", "how many Lambda functions?", "describe my RDS databases", "list EKS clusters", "what resources do I have?", "show me my infrastructure", "what's running in my account?", "list all resources"

3. account_info — Questions about AWS account identity, organization, or region.
   Examples: "what's my account ID?", "which region am I in?", "who am I?", "show account alias"

4. overview — Broad queries that want comprehensive information across multiple domains.
   Examples: "give me an overview of my AWS account", "tell me everything about my account", "summary of my AWS", "comprehensive report", "dashboard of my AWS", "what does my AWS look like?", "tell me more about my EC2 setup", "give me all EC2 details"

5. aws_knowledge — Conceptual/educational questions about AWS that need an explanation (no tool call needed). Also use this for general conversational questions that aren't simple greetings but need a thoughtful response.
   Examples: "what is EC2?", "how does S3 pricing work?", "explain CloudWatch", "what's the difference between Lambda and Fargate?", "how does Cost Explorer calculate costs?", "what are reserved instances?", "tell me about your capabilities", "what can you help me with?"

6. greeting — User says hello or asks what the agent can do.
   Examples: "hi", "hello", "hey", "good morning", "who are you?", "what can you do?", "help"

7. conversational — Small talk, social pleasantries, acknowledgements.
   Examples: "thanks", "bye", "ok", "got it", "how are you?", "what's up?"

8. unsupported — Requests that would MODIFY, WRITE, or DELETE AWS resources (read-only agent).
   Examples: "delete this bucket", "stop that instance", "create a new IAM user", "resize my instance"

9. clarification_needed — Query is genuinely ambiguous and you cannot determine intent even with generous interpretation. Use this VERY RARELY — prefer routing to the most likely skill. Almost every query can be routed somewhere.

ROUTING RULES:
- IMPORTANT: Users may ask questions in completely unorganic, out-of-order, or messy formats (e.g. "for last month what is cost breakdown by services please"). You must carefully parse the underlying intent regardless of grammar or sentence structure.
- If the query asks for "more info", "more details", "tell me more", "deep dive", or "everything" about a specific service -> overview
- If the query mentions cost/spend/billing/money/charges -> cost_query
- If the query mentions listing/showing specific resources -> resource_inventory
- If the query is a conceptual "what is X?" question -> aws_knowledge
- If the query is broad and asks for multiple types of info -> overview
- If the query is a follow-up referencing the conversation context, use the RECENT CONVERSATION to understand what skill it belongs to
- NEVER classify a query with cost keywords as "clarification_needed"
- When in doubt, prefer aws_knowledge over clarification_needed — the agent can always give a helpful conversational reply

USER QUERY: "{user_query}"

Return JSON ONLY:
{{
  "skill": "one_of_the_above",
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
                return self._keyword_fallback(lower_query)
                
            data = json.loads(json_str)
            skill = (data.get('skill') or '').strip().lower().replace(' ', '_')
            confidence = float(data.get('confidence', 0.0))
            
            if skill not in VALID_SKILLS:
                return self._keyword_fallback(lower_query)
            
            if skill == 'clarification_needed' and confidence < 0.6:
                fallback = self._keyword_fallback(lower_query)
                if fallback.skill != 'aws_knowledge' or fallback.confidence > 0.5:
                    return fallback
            
            return SkillRoute(skill=skill, confidence=confidence)
            
        except Exception as e:
            print(f"Router Error: {e}")
            return self._keyword_fallback(lower_query)
