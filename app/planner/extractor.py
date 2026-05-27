from typing import Dict, Any
import json
import logging
from datetime import datetime, timedelta, date
from ..llm.json_util import extract_json_balanced
from .models import CanonicalIntent, DateRange

logger = logging.getLogger(__name__)


class ParameterExtractor:
    """
    Step 4: Parameter Extraction
    Extracts structured parameters from the query based on intent.
    Handles relative time resolution.
    LLM-agnostic: works with any client that implements chat().
    """
    
    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def _call_llm_json(self, messages: list) -> str:
        """
        Call the LLM for structured JSON output.
        Uses chat_with_json() if available (OpenAI), falls back to
        chat() + extract_json_balanced() for other providers.
        """
        if hasattr(self.llm, 'chat_with_json'):
            try:
                return self.llm.chat_with_json(messages)
            except Exception as e:
                logger.warning(f"chat_with_json failed, falling back to chat(): {e}")
        
        # Fallback: regular chat + JSON extraction
        raw_response = self.llm.chat(
            messages=messages,
            temperature=0.1,
            max_tokens=1024
        )
        extracted = extract_json_balanced(raw_response)
        if extracted:
            return extracted
        
        # Last resort: try cleaning markdown fences
        cleaned = self._clean_json(raw_response)
        return cleaned

    async def extract(self, user_query: str, canonical_intent: CanonicalIntent) -> CanonicalIntent:
        """
        Extract structured parameters from the user query into the CanonicalIntent.
        """
        system_date = datetime.now().strftime('%Y-%m-%d')
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        month_start = date.today().replace(day=1).strftime('%Y-%m-%d')
        last_month_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')
        
        prompt = f"""You are the Parameter Extractor. Extract strict JSON parameters from the query.

CURRENT SYSTEM DATE: {system_date}
INTENT: {canonical_intent.intent}
USER QUERY: "{user_query}"

TIME RESOLUTION RULES (AWS Cost Explorer uses start=inclusive, end=exclusive):
- "today" -> start_date: {system_date}, end_date: {tomorrow}
- "yesterday" -> start_date: {yesterday}, end_date: {system_date}
- "this month" -> start_date: {month_start}, end_date: {tomorrow}
- "last month" -> start_date: {last_month_start}, end_date: {month_start}
- "January 2026" -> start_date: "2026-01-01", end_date: "2026-02-01" (end is first day of NEXT month)
- Relative dates like "last 7 days" -> calculate exact start/end, end_date should be tomorrow to include today.

EXTRACTION RULES:
- The user query may be poorly formatted. Extract services, regions, and dates aggressively.
- Map colloquial service names: "functions" -> "lambda", "servers" -> "ec2", "storage" -> "s3"

OUTPUT SCHEMA:
{{
  "time_range": {{ "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD" }} (or null if not specified),
  "services": ["AmazonEC2", "AmazonS3", ...] (AWS service codes, normalized),
  "regions": ["us-east-1", ...] (region codes),
  "comparison": "time" | "service" | "region" (optional),
  "params": {{ 
      "filter_tag": "key=value",
      "granularity": "DAILY" | "MONTHLY"
  }}
}}

Return JSON ONLY.
"""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self._call_llm_json(messages)
            data = json.loads(response)

            # Construct CanonicalIntent with extracted fields
            time_range = None
            if data.get('time_range'):
                try:
                    time_range = DateRange(**data['time_range'])
                except Exception:
                    pass

            return CanonicalIntent(
                intent=canonical_intent.intent,
                time_range=time_range,
                services=data.get('services', []),
                regions=data.get('regions', []),
                comparison=data.get('comparison'),
                params=data.get('params', {}),
                confidence=canonical_intent.confidence
            )

        except Exception as e:
            logger.error(f"Parameter extraction error: {e}")
            return canonical_intent

    def _clean_json(self, text: str) -> str:
        """Clean markdown code blocks from JSON response"""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        return text.strip()

