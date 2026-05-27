"""
Deterministic Router
Routes queries using hard-coded pattern matching for instant responses
"""
import json
from typing import Dict, Any, Optional, List
from pathlib import Path


class DeterministicRouter:
    """
    Routes queries using deterministic pattern matching
    Handles 30%+ of queries with zero AI inference
    """
    
    def __init__(self, rules_path: Optional[str] = None):
        """
        Initialize router with rules
        
        Args:
            rules_path: Path to deterministic_rules.json (optional)
        """
        if rules_path is None:
            # Default to rules directory
            current_dir = Path(__file__).parent
            rules_path = current_dir / 'rules' / 'deterministic_rules.json'
        
        self.rules = self._load_rules(rules_path)
        print(f"[OK] Loaded {len(self.rules)} deterministic routing rules")
    
    def _load_rules(self, rules_path: str) -> List[Dict[str, Any]]:
        """Load routing rules from JSON file"""
        path = Path(rules_path)
        if not path.exists():
            print(f"WARN: Rules file not found: {rules_path}, using empty ruleset")
            return []
        
        with open(path, 'r') as f:
            return json.load(f)
    
    def route(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Attempt deterministic routing
        
        Args:
            query: User query
            
        Returns:
            {
                "tool": str,
                "confidence": 1.0,
                "matched_pattern": str,
                "skip_ai": True,
                "reason": str
            } or None if no match
        """
        normalized = query.lower().strip()
        
        # Try to match each rule
        for rule in self.rules:
            for pattern in rule['patterns']:
                # Exact substring match
                if pattern in normalized:
                    return {
                        "tool": rule['tool'],
                        "confidence": rule['confidence'],
                        "matched_pattern": pattern,
                        "skip_ai": True,
                        "reason": f"Deterministic match: '{pattern}' → {rule['description']}",
                        "description": rule['description']
                    }
        
        # No match found
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        return {
            "total_rules": len(self.rules),
            "total_patterns": sum(len(r['patterns']) for r in self.rules),
            "tools_covered": list(set(r['tool'] for r in self.rules))
        }
    
    def add_rule(self, patterns: List[str], tool: str, description: str, 
                 confidence: float = 1.0):
        """
        Add new routing rule dynamically
        
        Args:
            patterns: List of patterns to match
            tool: Tool name to route to
            description: Human-readable description
            confidence: Confidence score (default 1.0)
        """
        self.rules.append({
            "patterns": patterns,
            "tool": tool,
            "confidence": confidence,
            "description": description
        })
    
    def save_rules(self, rules_path: str):
        """Save current rules to file"""
        path = Path(rules_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.rules, f, indent=2)
        
        print(f"[OK] Saved {len(self.rules)} rules to {rules_path}")
