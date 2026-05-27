from typing import Set, Dict

class RoleBasedAccessControl:
    """
    Enforces Role-Based Access Control (RBAC) for intents.
    """
    
    # Define Roles and their allowed intent prefixes or specific intents
    ROLE_PERMISSIONS: Dict[str, Set[str]] = {
        'ADMIN': {'*'},  # Access to everything

        'USER': {
            'COST_*',
            'FORECAST_*',
            'ANOMALY_*',
            'RESOURCE_*',
            'CLOUDWATCH_*',
            'LOG_*',
            'ACCOUNT_*',
            'GREETING',
            'CONVERSATIONAL',
            'AWS_KNOWLEDGE',  # /help, /tools, general AWS Q&A
        },

        'FINANCE': {
            'COST_*',       # All cost queries
            'FORECAST_*',   # Cost forecasts
            'ANOMALY_*',     # Cost anomalies
            'GREETING',
            'CONVERSATIONAL',
            'AWS_KNOWLEDGE'
        },
        
        'DEVOPS': {
            'RESOURCE_*',       # Inventory
            'CLOUDWATCH_*',     # Metrics
            'LOG_*',            # Logs
            'ACCOUNT_METADATA', # Identity
            'GREETING',
            'CONVERSATIONAL',
            'AWS_KNOWLEDGE'
        },
        
        'VIEWER': {
            'COST_TOTAL',       # High level only
            'COST_BY_SERVICE', 
            'GREETING',
            'CONVERSATIONAL',
            'AWS_KNOWLEDGE'    # /help, /tools
        }
    }

    def verify_permission(self, role: str, intent_name: str) -> bool:
        """
        Verify if the given role is allowed to execute the given intent.
        
        Args:
            role: The user's role (e.g., 'ADMIN', 'FINANCE'). Defaults to 'VIEWER' if unknown.
            intent_name: The canonical intent name (e.g., 'COST_TOTAL').
            
        Returns:
            True if allowed, False otherwise.
        """
        role = role.upper() if role else 'VIEWER'
        
        # Default to Viewer if role not defined
        if role not in self.ROLE_PERMISSIONS:
            role = 'VIEWER'
            
        allowed_patterns = self.ROLE_PERMISSIONS[role]
        
        # Admin check
        if '*' in allowed_patterns:
            return True
            
        # Check exact match
        if intent_name in allowed_patterns:
            return True
            
        # Check wildcard (prefix) match
        for pattern in allowed_patterns:
            if pattern.endswith('*'):
                prefix = pattern[:-1]
                if intent_name.startswith(prefix):
                    return True
                    
        return False
