"""
Confidence Fusion
Combines embedding and LLM scores for final confidence
"""
from typing import Dict, Any
from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence level classification"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceFusion:
    """
    Fuses embedding similarity and LLM confidence scores
    """
    
    def __init__(self, embedding_weight: float = 0.6, llm_weight: float = 0.4):
        """
        Initialize fusion with weights
        
        Args:
            embedding_weight: Weight for embedding score (default 0.6)
            llm_weight: Weight for LLM confidence (default 0.4)
        """
        if not abs(embedding_weight + llm_weight - 1.0) < 0.01:
            raise ValueError("Weights must sum to 1.0")
        
        self.w_emb = embedding_weight
        self.w_llm = llm_weight
    
    def fuse_confidence(self, embedding_score: float, llm_confidence: float) -> float:
        """
        Combine embedding and LLM confidence scores
        
        Args:
            embedding_score: 0-1 cosine similarity score
            llm_confidence: 0-1 LLM confidence
            
        Returns:
            Final confidence score 0-1
        """
        # Validate inputs
        embedding_score = max(0.0, min(1.0, embedding_score))
        llm_confidence = max(0.0, min(1.0, llm_confidence))
        
        # Weighted average
        final_score = (self.w_emb * embedding_score) + (self.w_llm * llm_confidence)
        
        return final_score
    
    def classify_confidence(self, final_score: float) -> ConfidenceLevel:
        """
        Classify confidence level
        
        Args:
            final_score: Fused confidence score
            
        Returns:
            ConfidenceLevel enum
        """
        if final_score >= 0.75:
            return ConfidenceLevel.HIGH
        elif final_score >= 0.5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get current confidence thresholds"""
        return {
            "HIGH": 0.75,
            "MEDIUM": 0.5,
            "LOW": 0.0
        }
    
    def should_proceed(self, final_score: float) -> bool:
        """
        Determine if tool should be executed or clarification needed
        
        Args:
            final_score: Fused confidence score
            
        Returns:
            True if should proceed with execution
        """
        # Proceed for HIGH and MEDIUM confidence
        # Request clarification for LOW
        return final_score >= 0.5
    
    def get_decision_rationale(self, final_score: float, 
                               embedding_score: float, 
                               llm_confidence: float) -> str:
        """
        Generate rationale for confidence decision
        
        Args:
            final_score: Fused score
            embedding_score: Original embedding score
            llm_confidence: Original LLM confidence
            
        Returns:
            Human-readable rationale
        """
        level = self.classify_confidence(final_score)
        
        breakdown = (
            f"Confidence: {level.value} (score: {final_score:.2f}). "
            f"Embedding similarity: {embedding_score:.2f}, "
            f"LLM confidence: {llm_confidence:.2f}"
        )
        
        if level == ConfidenceLevel.HIGH:
            return f"{breakdown}. Proceeding with high confidence."
        elif level == ConfidenceLevel.MEDIUM:
            return f"{breakdown}. Proceeding with moderate confidence (will log for review)."
        else:
            return f"{breakdown}. Confidence too low, requesting clarification."
