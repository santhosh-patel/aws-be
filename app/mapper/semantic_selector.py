"""
Semantic Tool Selector
Uses embeddings to find top-K candidate tools by similarity
"""
import numpy as np
from typing import List, Tuple, Dict
from .embedding_service import EmbeddingService
from .tool_metadata import ToolMetadata


class SemanticToolSelector:
    """
    Selects top-K tool candidates using semantic similarity
    """
    
    def __init__(self, embedding_service: EmbeddingService, tools_metadata: List[ToolMetadata]):
        """
        Initialize selector
        
        Args:
            embedding_service: Embedding service instance
            tools_metadata: List of tool metadata objects
        """
        self.embeddings = embedding_service
        self.tools_metadata = tools_metadata
        self._ensure_tool_embeddings()
    
    def _ensure_tool_embeddings(self):
        """Ensure all tools have cached embeddings"""
        for tool in self.tools_metadata:
            if tool.embedding_vector is None:
                # Generate and cache embedding
                embedding_text = tool.get_embedding_text()
                tool.embedding_vector = self.embeddings.embed_text(embedding_text)
    
    def get_top_k_candidates(self, query: str, k: int = 3, 
                            domain_filter: str = None) -> List[Tuple[ToolMetadata, float]]:
        """
        Get top-K tools by semantic similarity
        
        Args:
            query: User query
            k: Number of candidates to return
            domain_filter: Optional domain filter ('cost', 'inventory', 'logs', 'account')
            
        Returns:
            List of (ToolMetadata, similarity_score) tuples, sorted by score
        """
        # Embed query
        query_vec = self.embeddings.embed_text(query)
        
        # Compute similarities
        scores = []
        for tool in self.tools_metadata:
            # Apply domain filter if specified
            if domain_filter and tool.domain != domain_filter:
                continue
            
            # Compute similarity
            similarity = self.embeddings.compute_similarity(query_vec, tool.embedding_vector)
            scores.append((tool, similarity))
        
        # Sort by similarity (descending)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top-K
        return scores[:k]
    
    def get_domain_distribution(self, query: str) -> Dict[str, float]:
        """
        Get probability distribution over domains
        Helps determine if query is ambiguous across domains
        
        Args:
            query: User query
            
        Returns:
            Dict of {domain: avg_similarity} 
        """
        query_vec = self.embeddings.embed_text(query)
        
        # Group by domain
        domain_scores = {}
        domain_counts = {}
        
        for tool in self.tools_metadata:
            domain = tool.domain
            similarity = self.embeddings.compute_similarity(query_vec, tool.embedding_vector)
            
            if domain not in domain_scores:
                domain_scores[domain] = 0.0
                domain_counts[domain] = 0
            
            domain_scores[domain] += similarity
            domain_counts[domain] += 1
        
        # Average per domain
        domain_avg = {
            domain: domain_scores[domain] / domain_counts[domain]
            for domain in domain_scores
        }
        
        return domain_avg
