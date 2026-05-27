"""
Modifier Detector - Detects follow-up modifiers in user queries
Examples: "in INR", "show daily", "only EC2", "compare with last month"
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import re


class ModifierType(Enum):
    """Types of query modifiers"""
    CURRENCY_CONVERSION = "currency_conversion"
    GRANULARITY_CHANGE = "granularity_change"
    SERVICE_FILTER = "service_filter"
    COMPARISON = "comparison"
    DRILLDOWN = "drilldown"
    FOLLOW_UP_EXPLAIN = "follow_up_explain"
    UNKNOWN = "unknown"


@dataclass
class ModifierIntent:
    """Detected modifier intent"""
    modifier_type: ModifierType
    params: Dict[str, Any]
    requires_context: bool = True
    confidence: float = 1.0


class ModifierDetector:
    """Detects modifier intents in user queries"""
    
    # Currency patterns
    CURRENCY_PATTERNS = {
        'INR': [r'\bin\s+inr\b', r'\binr\b', r'\b(?:indian\s+)?rupees?\b', r'₹'],
        'EUR': [r'\bin\s+eur(?:o|os)?\b', r'\beur(?:o|os)?\b', r'€'],
        'GBP': [r'\bin\s+(?:gbp|pounds?)\b', r'\bgbp\b', r'£'],
        'JPY': [r'\bin\s+(?:jpy|yen)\b', r'\byen\b', r'¥'],
        'CNY': [r'\bin\s+(?:cny|yuan)\b', r'\byuan\b'],
    }
    
    # Granularity patterns
    GRANULARITY_PATTERNS = {
        'DAILY': [
            r'\bshow\s+daily\b',
            r'\bdaily\s+(?:breakdown|view|data)\b',
            r'\bby\s+day\b',
            r'\bper\s+day\b',
            r'\bdaily\s+instead\b'
        ],
        'MONTHLY': [
            r'\bshow\s+monthly\b',
            r'\bmonthly\s+(?:breakdown|view|data)\b',
            r'\bby\s+month\b',
            r'\bper\s+month\b',
            r'\bmonthly\s+instead\b'
        ]
    }
    
    # Service filter patterns
    SERVICE_FILTER_KEYWORDS = ['only', 'just', 'exclude', 'without', 'filter']
    
    # Comparison patterns
    COMPARISON_PATTERNS = [
        r'\bcompare\s+(?:with|to|vs)\b',
        r'\bvs\s+\b',
        r'\bagainst\s+\b',
        r'\bdifference\s+(?:from|with)\b'
    ]
    
    def detect(self, query: str, has_context: bool = False) -> Optional[ModifierIntent]:
        """
        Detect if query is a modifier intent.
        
        Args:
            query: User query
            has_context: Whether session context exists
            
        Returns:
            ModifierIntent if detected, None otherwise
        """
        query_lower = query.lower().strip()
        
        # Check currency conversion (works even without context to provide helpful error)
        currency_result = self._detect_currency(query_lower)
        if currency_result:
            return currency_result
        
        # Check granularity change (works even without context to provide helpful error)
        granularity_result = self._detect_granularity(query_lower)
        if granularity_result:
            return granularity_result
        
        # For very short queries, be more aggressive if context exists
        if has_context and len(query_lower.split()) <= 4:
            # Check service filter
            service_result = self._detect_service_filter(query_lower)
            if service_result:
                return service_result
        
        # Follow-up explanation: "why is this cost more?", "explain this", "why so high?"
        if has_context:
            explain_result = self._detect_follow_up_explain(query_lower)
            if explain_result:
                return explain_result
        
        # Check comparison (can be longer)
        comparison_result = self._detect_comparison(query_lower)
        if comparison_result:
            return comparison_result
        
        return None
    
    def _detect_currency(self, query: str) -> Optional[ModifierIntent]:
        """Detect currency conversion intent"""
        # Pattern: "in INR", "convert to EUR", "show in rupees", "get it in inr"
        for currency_code, patterns in self.CURRENCY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return ModifierIntent(
                        modifier_type=ModifierType.CURRENCY_CONVERSION,
                        params={'target_currency': currency_code},
                        requires_context=True,
                        confidence=0.95
                    )
        
        # Generic conversion request
        if re.search(r'\bconvert\s+(?:to|into)\b', query, re.IGNORECASE):
            return ModifierIntent(
                modifier_type=ModifierType.CURRENCY_CONVERSION,
                params={'target_currency': 'UNKNOWN'},  # Need to ask user
                requires_context=True,
                confidence=0.8
            )
        
        return None
    
    def _detect_granularity(self, query: str) -> Optional[ModifierIntent]:
        """Detect granularity change intent"""
        for granularity, patterns in self.GRANULARITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return ModifierIntent(
                        modifier_type=ModifierType.GRANULARITY_CHANGE,
                        params={'granularity': granularity},
                        requires_context=True,
                        confidence=0.9
                    )
        
        return None
    
    def _detect_service_filter(self, query: str) -> Optional[ModifierIntent]:
        """Detect service filter intent"""
        # Pattern: "only EC2", "just S3", "exclude RDS"
        for keyword in self.SERVICE_FILTER_KEYWORDS:
            if keyword in query:
                # Extract service name (very basic)
                # This is simplified - production should use better NER
                words = query.split()
                if keyword in words:
                    idx = words.index(keyword)
                    if idx + 1 < len(words):
                        service_hint = words[idx + 1]
                        return ModifierIntent(
                            modifier_type=ModifierType.SERVICE_FILTER,
                            params={
                                'action': 'include' if keyword in ['only', 'just'] else 'exclude',
                                'service_hint': service_hint
                            },
                            requires_context=True,
                            confidence=0.7
                        )
        
        return None
    
    def _detect_follow_up_explain(self, query: str) -> Optional[ModifierIntent]:
        """Detect follow-up explanation request (why, explain, reason, etc.)."""
        explain_patterns = [
            r'\bwhy\s+(?:is|are|did|was|does|do)\b',
            r'\bwhy\s+(?:this|that|it)\b',
            r'\bexplain\s+(?:this|that|it|the)\b',
            r'\b(?:can you\s+)?explain\b',
            r'\b(?:what|who)\s+caused\b',
            r'\bhow\s+come\b',
            r'\breason\s+(?:for|why)\b',
            r'\b(?:give me|tell me)\s+more\b',
            r'\b(?:break\s+)?(?:it\s+)?down\s+for\s+me\b',
            r'\bwhat\s+drives?\s+(?:this|that|the)\b',
            r'\b(?:cost|spend|bill)\s+more\b',
            r'\b(?:so\s+)?high\s+\?\s*$',
            r'\b(?:so\s+)?low\s+\?\s*$',
        ]
        for pattern in explain_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return ModifierIntent(
                    modifier_type=ModifierType.FOLLOW_UP_EXPLAIN,
                    params={"user_question": query.strip()},
                    requires_context=True,
                    confidence=0.9
                )
        return None
    
    def _detect_comparison(self, query: str) -> Optional[ModifierIntent]:
        """Detect comparison intent"""
        for pattern in self.COMPARISON_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return ModifierIntent(
                    modifier_type=ModifierType.COMPARISON,
                    params={},  # Will need time range extraction
                    requires_context=True,
                    confidence=0.85
                )
        
        return None
    
    def is_likely_modifier(self, query: str) -> bool:
        """
        Quick check if query looks like a modifier.
        Used for early detection before full parsing.
        
        Args:
            query: User query
            
        Returns:
            True if query pattern matches common modifiers
        """
        query_lower = query.lower().strip()
        
        # Very short queries
        if len(query_lower.split()) <= 3:
            # Common modifier patterns
            modifier_keywords = [
                'in', 'convert', 'show', 'display', 'get it',
                'only', 'just', 'exclude', 'daily', 'monthly',
                'compare', 'vs', 'breakdown'
            ]
            
            return any(keyword in query_lower for keyword in modifier_keywords)
        
        return False

    def strip_modifiers(self, query: str) -> str:
        """
        Strip granularity and other noise modifiers from query 
        to improve semantic matching.
        """
        clean_query = query
        
        # Strip granularity keywords
        for granularity, patterns in self.GRANULARITY_PATTERNS.items():
            for pattern in patterns:
                # Replace with empty string (keeping spaces safe)
                clean_query = re.sub(pattern, '', clean_query, flags=re.IGNORECASE)
                
        # Strip simple currency keywords e.g. "in USD"
        for currency_code, patterns in self.CURRENCY_PATTERNS.items():
            for pattern in patterns:
                 clean_query = re.sub(pattern, '', clean_query, flags=re.IGNORECASE)

        # Cleanup whitespace
        clean_query = re.sub(r'\s+', ' ', clean_query).strip()
        return clean_query
