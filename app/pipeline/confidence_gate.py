"""
Confidence Gate
Gates tool execution based on confidence thresholds
"""
from typing import Dict, Any
from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence level classification"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceGate:
    """
    Gates tool execution based on confidence thresholds
    Prevents low-confidence execution to avoid wrong answers
    """
    
    def __init__(self, high_threshold: float = 0.75, medium_threshold: float = 0.5):
        """
        Initialize gate with thresholds
        
        Args:
            high_threshold: Threshold for HIGH confidence (default 0.75)
            medium_threshold: Threshold for MEDIUM confidence (default 0.5)
        """
        if not 0 <= medium_threshold < high_threshold <= 1:
            raise ValueError("Thresholds must satisfy: 0 <= medium < high <= 1")
        
        self.high = high_threshold
        self.medium = medium_threshold
    
    def evaluate(self, confidence: float) -> Dict[str, Any]:
        """
        Evaluate if tool should execute based on confidence
        
        Args:
            confidence: Confidence score 0-1
            
        Returns:
            {
                "execute": bool,
                "level": str (HIGH/MEDIUM/LOW),
                "action": str,
                "reason": str,
                "log_for_review": bool
            }
        """
        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, confidence))
        
        if confidence >= self.high:
            return {
                "execute": True,
                "level": ConfidenceLevel.HIGH.value,
                "action": "proceed",
                "reason": f"High confidence ({confidence:.2f} ≥ {self.high})",
                "log_for_review": False
            }
        elif confidence >= self.medium:
            return {
                "execute": True,
                "level": ConfidenceLevel.MEDIUM.value,
                "action": "proceed_with_logging",
                "reason": f"Medium confidence ({confidence:.2f} ≥ {self.medium}), proceeding with caution",
                "log_for_review": True
            }
        else:
            return {
                "execute": False,
                "level": ConfidenceLevel.LOW.value,
                "action": "request_clarification",
                "reason": f"Low confidence ({confidence:.2f} < {self.medium}), need clarification",
                "log_for_review": True
            }
    
    def should_execute(self, confidence: float) -> bool:
        """
        Simple boolean check if execution should proceed
        
        Args:
            confidence: Confidence score 0-1
            
        Returns:
            True if should execute, False otherwise
        """
        return confidence >= self.medium
    
    def classify_level(self, confidence: float) -> ConfidenceLevel:
        """
        Classify confidence level
        
        Args:
            confidence: Confidence score 0-1
            
        Returns:
            ConfidenceLevel enum
        """
        if confidence >= self.high:
            return ConfidenceLevel.HIGH
        elif confidence >= self.medium:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get current threshold values"""
        return {
            "high": self.high,
            "medium": self.medium,
            "low": 0.0
        }
    
    def update_thresholds(self, high: float = None, medium: float = None):
        """
        Update threshold values
        
        Args:
            high: New high threshold (optional)
            medium: New medium threshold (optional)
        """
        if high is not None:
            if not 0 < high <= 1:
                raise ValueError("High threshold must be 0 < high <= 1")
            self.high = high
        
        if medium is not None:
            if not 0 <= medium < 1:
                raise ValueError("Medium threshold must be 0 <= medium < 1")
            self.medium = medium
        
        # Validate relationship
        if self.medium >= self.high:
            raise ValueError("Medium threshold must be less than high threshold")
    
    def get_statistics(self, confidence_scores: list) -> Dict[str, Any]:
        """
        Get statistics for a list of confidence scores
        
        Args:
            confidence_scores: List of confidence scores
            
        Returns:
            Statistics dict with distribution
        """
        if not confidence_scores:
            return {
                "total": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            }
        
        high_count = sum(1 for s in confidence_scores if s >= self.high)
        medium_count = sum(1 for s in confidence_scores if self.medium <= s < self.high)
        low_count = sum(1 for s in confidence_scores if s < self.medium)
        
        total = len(confidence_scores)
        
        return {
            "total": total,
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
            "high_pct": round(high_count / total * 100, 1),
            "medium_pct": round(medium_count / total * 100, 1),
            "low_pct": round(low_count / total * 100, 1),
            "average": round(sum(confidence_scores) / total, 3)
        }
