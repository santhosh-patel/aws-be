from typing import Optional, Dict, List, Tuple
import re

class IntentClassifier:
    """
    Rule-based intent classifier.
    Maps query patterns directly to specific Intent Enums.
    """

    # Full Matrix
    PATTERNS = [
        # --- COST INTENTS ---
        
        # 1. Cost Today
        (r'\b(today)\b', 'COST_TODAY'),
        
        # 2. Cost Yesterday
        (r'\b(yesterday)\b', 'COST_YESTERDAY'),
        (r'\b(day before today)\b', 'COST_YESTERDAY'),
        
        # 3. Cost Current Month
        (r'\b(this month|current month|month to date|mtd)\b', 'COST_CURRENT_MONTH'),
        (r'\b(bill|total cost|how much is my bill|spending status|spend so far)\b', 'COST_CURRENT_MONTH'),
        (r'\b(costs? this mnth)\b', 'COST_CURRENT_MONTH'), # Typos
        
        # 4. Cost Last Month
        (r'\b(last month|previous month)\b', 'COST_LAST_MONTH'),
        (r'\b(last mnth)\b', 'COST_LAST_MONTH'),
        
        # 5. Cost Forecast (Priority over Trend)
        (r'\b(forecast|forcast|predict|projection|projected|future|estimated|expected bill|budget)\b', 'COST_FORECAST'),
        
        # 7. Breakdown by Service (Specific triggers)
        (r'\b(breakdown|split|distribution)\s+.*by\s+service\b', 'COST_BY_SERVICE'),
        (r'\b(service|services)\s+.*(breakdown|distribution|costs|spend)\b', 'COST_BY_SERVICE'),
        (r'\b(service wise|by service)\b', 'COST_BY_SERVICE'),
        (r'\b(which service costs? most)\b', 'COST_BY_SERVICE'),
        
        # 8. Breakdown by Region
        (r'\b(breakdown|split|distribution)\s+.*by\s+region\b', 'COST_BY_REGION'),
        (r'\b(regional|region)\s+.*(breakdown|distribution|costs|spend)\b', 'COST_BY_REGION'),
        (r'\b(region wise|by region)\b', 'COST_BY_REGION'),
        (r'\b(which region costs? most)\b', 'COST_BY_REGION'),
        (r'\b(region spending)\b', 'COST_BY_REGION'), # Explicit short form
        (r'\b(in which region)\b', 'COST_BY_REGION'),

        # 6. Cost Trend (Generic Fallback for time ranges)
        (r'\b(trend|history|historical|over time|trajectory|evolution)\b', 'COST_TREND'),
        (r'\b(last|past|prev|previous)\s+\d+\s+(day|week|month|year)s?\b', 'COST_TREND'),
        (r'\b(last|past|prev|previous)\s+quarter\b', 'COST_TREND'),
        (r'\b(year to date|ytd|this year)\b', 'COST_TREND'),
        (r'\b(from\s+.+\s+to\s+.+)\b', 'COST_TREND'),

        # Default Cost (If just "cost" and NO specific modifier found yet, might be ambiguous. 
        # But usually handled by confidence gate or "show cost" -> clarification. 
        # We'll leave general "cost" for clarification or default to current month if strict?)
        
        # --- RESOURCE INTENTS ---
        
        # 1. EC2
        (r'\b(ec2|instances|virtual machines|compute inventory)\b', 'RESOURCE_EC2'),
        
        # 2. S3
        (r'\b(s3|buckets|storage buckets)\b', 'RESOURCE_S3'),
        
        # 3. Lambda
        (r'\b(lambda|functions|serverless functions)\b', 'RESOURCE_LAMBDA'),
        
        # 4. RDS
        (r'\b(rds|databases|db instances)\b', 'RESOURCE_RDS'),
        
        # --- ACCOUNT INTENTS ---
        
        # 1. Identity
        (r'\b(who am i|account id|caller identity|my identity)\b', 'ACCOUNT_IDENTITY'),
        
        # 2. Alias
        (r'\b(account name|account alias)\b', 'ACCOUNT_ALIAS'),
        
        # 3. Regions
        (r'\b(enabled regions|available regions|which regions|active regions)\b', 'ACCOUNT_REGIONS'),
    ]

    def classify(self, query: str) -> str:
        """
        Classify query into a specific Intent string.
        Returns 'CLARIFICATION_REQUIRED' if no strong match.
        """
        query_lower = query.lower().strip()
        
        # 1. Check Cost Intents FIRST (User rule: Cost > Resource)
        # But we need to be careful. "ec2 cost" -> COST (by service probably, or trend filtered by ec2)
        # "list ec2" -> RESOURCE
        
        # Check explicit patterns
        best_intent = None
        
        # Pre-check for "cost", "spend", "bill", "invoice", "payment" to prioritize Cost intents
        has_cost_keyword = re.search(r'\b(cost|spend|spending|bill|invoice|payment|budget)\b', query_lower)
        
        matched_intents = []
        for pattern, intent in self.PATTERNS:
            if re.search(pattern, query_lower):
                matched_intents.append(intent)
        
        if not matched_intents:
            return 'CLARIFICATION_REQUIRED'
            
        # Conflict Resolution
        
        # If multiple matches, prioritize:
        # Forecast > Breakdown > Trend > Period > Resource > Account
        
        # Priority Map (Lower is higher priority)
        priority = {
            'COST_FORECAST': 1,
            'COST_BY_REGION': 2, # Region overrides Service
            'COST_BY_SERVICE': 3,
            'COST_TODAY': 4,
            'COST_YESTERDAY': 4,
            'COST_LAST_MONTH': 4,
            'COST_TREND': 5, # Specific trend modifiers
            'COST_CURRENT_MONTH': 6, # Default for "bill" / "cost" if no other specific found
            
            'RESOURCE_EC2': 7, # Resources lower than Cost triggers
            'RESOURCE_S3': 7,
            'RESOURCE_LAMBDA': 7,
            'RESOURCE_RDS': 7,
            
            'ACCOUNT_IDENTITY': 8,
            'ACCOUNT_ALIAS': 8,
            'ACCOUNT_REGIONS': 8
        }
        
        # If has_cost_keyword is True, ignore RESOURCE_* matches, force mapping to a Cost intent.
        if has_cost_keyword:
            # Filter matches to only COST_*
            cost_matches = [i for i in matched_intents if i.startswith('COST_')]
            if cost_matches:
                # Return highest priority cost match
                cost_matches.sort(key=lambda x: priority.get(x, 10))
                return cost_matches[0]
            else:
                # SPECIAL RULE: Region Priority Override
                # If query contains "region" or "regional", force COST_BY_REGION even if pattern didn't fully match?
                # No, rely on patterns. But if we matched RESOURCE_EC2 ("ec2") and have "cost", 
                # and no specific cost intent, we fallback.
                
                # Check for region keyword explicitly to force BY_REGION if ambiguous
                if re.search(r'\b(region|regional)\b', query_lower):
                    return 'COST_BY_REGION'
                    
                return 'COST_BY_SERVICE' # Default fallback for "ec2 cost" -> Breakdown by service
        
        # No cost keyword
        # Return highest priority match (likely RESOURCE or ACCOUNT)
        matched_intents.sort(key=lambda x: priority.get(x, 10))
        return matched_intents[0]
