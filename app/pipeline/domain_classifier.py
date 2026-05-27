"""
Domain Classifier
Classifies queries into domains to filter tool search space
"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


class DomainClassifier:
    """
    Classifies queries into domains (cost, inventory, logs, account, metrics)
    Reduces tool search space by 80%+
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize classifier
        
        Args:
            config_path: Path to domain_config.json (optional)
        """
        if config_path is None:
            current_dir = Path(__file__).parent
            config_path = current_dir / 'rules' / 'domain_config.json'
        
        self.domains = self._load_config(config_path)
        print(f"[OK] Loaded {len(self.domains)} domain configurations")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load domain configuration from JSON"""
        path = Path(config_path)
        if not path.exists():
            print(f"WARN: Domain config not found: {config_path}, using default")
            return self._get_default_config()
        
        with open(path, 'r') as f:
            return json.load(f)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Fallback default configuration"""
        return {
            "cost": {
                "keywords": ["cost", "billing", "spend"],
                "tools": []
            }
        }
    
    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classify query into domain
        
        Args:
            query: User query
            
        Returns:
            {
                "domain": str,
                "confidence": float,
                "filtered_tools": List[str],
                "clarification_needed": bool,
                "all_scores": Dict[str, int]
            }
        """
        normalized = query.lower().strip()
        
        # Score each domain by keyword matches
        scores = {}
        for domain, config in self.domains.items():
            score = sum(1 for keyword in config['keywords'] if keyword in normalized)
            scores[domain] = score
        
        # Check if any domain matched
        max_score = max(scores.values()) if scores else 0
        
        if max_score == 0:
            return {
                "domain": "unknown",
                "confidence": 0.0,
                "filtered_tools": [],
                "clarification_needed": True,
                "all_scores": scores,
                "reason": "No domain keywords detected"
            }
        
        # Get best domain
        best_domain = max(scores, key=scores.get)
        domain_config = self.domains[best_domain]
        
        # Calculate confidence (normalized by keyword count)
        total_keywords = len(domain_config['keywords'])
        confidence = min(scores[best_domain] / max(total_keywords * 0.3, 1), 1.0)
        
        # Check for ambiguity (multiple high-scoring domains)
        high_scores = [d for d, s in scores.items() if s >= max_score * 0.8]
        is_ambiguous = len(high_scores) > 1
        
        return {
            "domain": best_domain,
            "confidence": round(confidence, 3),
            "filtered_tools": domain_config['tools'],
            "clarification_needed": is_ambiguous,
            "all_scores": scores,
            "ambiguous_domains": high_scores if is_ambiguous else [],
            "reason": f"Matched {scores[best_domain]} keywords in '{best_domain}' domain"
        }
    
    def get_domain_tools(self, domain: str) -> List[str]:
        """Get all tools for a specific domain"""
        if domain not in self.domains:
            return []
        return self.domains[domain]['tools']
    
    def get_all_domains(self) -> List[str]:
        """Get list of all domains"""
        return list(self.domains.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get classifier statistics"""
        return {
            "total_domains": len(self.domains),
            "domains": {
                domain: {
                    "keywords": len(config['keywords']),
                    "tools": len(config['tools'])
                }
                for domain, config in self.domains.items()
            }
        }
