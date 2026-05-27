from typing import Optional, Dict, Any
import re

class ConversationalFilter:
    """
    Hard gate for conversational queries to prevent them from reaching the tool mapper.
    """
    
    PATTERNS = {
        'GREETING': [
            r'^\s*(hi|hello|hey|greetings|good morning|good evening|yo|sup)\b',
            r'^\s*how (are|r) (you|u)\b'
        ],
        'THANKS': [
            r'^\s*(thanks|thank you|thx|ty|cool|ok|okay|great|perfect)\b',
            r'^\s*good job\b'
        ],
        'HELP': [
            r'^\s*help\b',
            r'^\s*what can you do\b',
            r'^\s*usage\b',
            r'^\s*commands\b'
        ],
        'CANCEL': [
            r'^\s*(cancel|stop|abort|quit|exit)\b'
        ]
    }

    RESPONSES = {
        'GREETING': "Hello! I'm your AWS Admin Agent. I can help you with cost analysis, resource inventory, and account details. What would you like to know?",
        'THANKS': "You're welcome! Let me know if you need anything else.",
        'HELP': "I can help with:\n- **Cost**: Forecasts, trends, breakdowns (service/region).\n- **Resources**: List EC2, S3, Lambda, RDS.\n- **Account**: ID, Alias, Enabled Regions.\n\nTry asking: 'Forecast AWS cost for next month' or 'List my EC2 instances'.",
        'CANCEL': "Operation cancelled. Ready for your next command."
    }

    def detect(self, query: str) -> Optional[Dict[str, str]]:
        """
        Check if query is purely conversational.
        Returns dict with response if matched, None otherwise.
        """
        query_lower = query.lower().strip()
        
        for category, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    # Check if it's a mixed query (e.g. "hi show me ec2")
                    # If it's short or matches exactly, catch it.
                    # If it has other substantive words, maybe let it pass? 
                    # User requirement: "Hard gate... These must never enter tool mapping."
                    # But "hi show me ec2" should probably process "show me ec2".
                    # For now, simplistic check: if match spans most of query or it's a known short phrase.
                    
                    # Heuristic: If query length is short (< 5 words) and matches, catch it.
                    # Or if it matches ^...$ exactly.
                    
                    # Refined: The regexes have \b boundaries.
                    # If the query is JUST the match, return.
                    # If the query starts with the match but has more content, we might want to strip it?
                    # The user said: "Conversational Filter... Return direct response."
                    # Usually applies to "hi", "thanks". 
                    # "hi show me ec2" -> "show me ec2" (handled by intent classifier usually ignoring "hi").
                    # Let's enforce strictness: only capture if it looks like the *entire* intent.
                    
                    if len(query_lower.split()) <= 3:
                         return {
                             "type": category,
                             "response": self.RESPONSES[category]
                         }
                         
        return None
