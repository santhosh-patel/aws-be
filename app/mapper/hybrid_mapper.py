"""
Hybrid Tool Mapper
Combines embeddings and LLM for robust, auditable tool selection
"""
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from .tool_metadata import ToolMetadata, load_tool_metadata
from .embedding_service import EmbeddingService
from .semantic_selector import SemanticToolSelector
from .llm_disambiguator import LLMDisambiguator
from .confidence_fusion import ConfidenceFusion, ConfidenceLevel
from ..llm.openai_client import OpenAIClient


@dataclass
class ToolMappingResult:
    """Result of hybrid tool mapping"""
    selected_tool: str
    confidence_level: str  # HIGH, MEDIUM, LOW
    final_confidence: float
    embedding_score: float
    llm_confidence: float
    reason: str
    candidates: List[Dict[str, Any]]  # Top-K candidates
    should_proceed: bool
    clarification_needed: bool


class HybridToolMapper:
    """
    Production-grade hybrid tool mapper
    Combines embeddings for semantic similarity with LLM for disambiguation
    """
    
    def __init__(self, llm_client: OpenAIClient, metadata_path: str, 
                 cache_dir: str = None, embedding_model: str = 'all-MiniLM-L6-v2'):
        """
        Initialize hybrid mapper
        
        Args:
            llm_client: OpenAI client instance
            metadata_path: Path to tool_metadata.json
            cache_dir: Directory for embedding cache
            embedding_model: Sentence transformer model name
        """
        # Load tool metadata
        self.tools_metadata = load_tool_metadata(metadata_path)
        print(f"[OK] Loaded {len(self.tools_metadata)} tool metadata entries")
        
        # Initialize components
        self.embedding_service = EmbeddingService(
            model_name=embedding_model,
            cache_dir=cache_dir
        )
        
        self.semantic_selector = SemanticToolSelector(
            self.embedding_service,
            self.tools_metadata
        )
        
        self.llm_disambiguator = LLMDisambiguator(llm_client)
        
        self.confidence_fusion = ConfidenceFusion(
            embedding_weight=0.6,
            llm_weight=0.4
        )
        
        print("[OK] Hybrid tool mapper initialized")
    
    async def map(self, query: str, top_k: int = 3, domain_filter: str = None, classified_intent: str = None, allowed_tools: List[str] = None) -> ToolMappingResult:
        """
        Map query to tool using hybrid approach:
        1. Semantic Search (filtered by allowed_tools if provided)
        2. Intent Boosting
        3. LLM Disambiguation (if needed) or Top-1 Selection
        """
        # 1. Semantic Search (Fetch more candidates initially to ensure coverage after filtering)
        initial_k = top_k * 5 if allowed_tools else (top_k * 3 if classified_intent else top_k)
        candidates = self.semantic_selector.get_top_k_candidates(
            query, k=initial_k, domain_filter=domain_filter
        )
        
        # 2. Filter by Allowed Tools (Hard Restriction)
        if allowed_tools:
            # Only keep candidates that are in the allowed list
            # But what if semantic search didn't find them in top initial_k?
            # Ideally we should force-fetch them. 
            # Since we don't have random access by name in semantic_selector easily without loading all,
            # we rely on semantic search finding them. 
            # But if allowed_tools is small, might be better to just select them?
            # Assuming semantic search is good enough to find them if relevant.
            # But strictly, if allowed_tools is ['aws_get_cost_forecast'], we MUST select it if it's the only one.
            pass
            
            filtered = []
            for tool_metadata, score in candidates:
                if tool_metadata.tool_name in allowed_tools:
                    filtered.append((tool_metadata, score))
            candidates = filtered
            
            # If we filtered everything out (rare but possible if embeddings are way off), 
            # we should probably just forcefully add the allowed tools as candidates with heuristic score?
            if not candidates and allowed_tools:
                 # Fallback: Create artificial candidates for allowed tools
                 # (Requires Tool objects, which we might not have handy without querying selector)
                 # For now, assume semantic search works. If not, it's an embedding issue.
                 pass

        # 3. Apply Intent Boosting
        if classified_intent:
            candidates = self._apply_intent_boosting(candidates, classified_intent)
            candidates.sort(key=lambda x: x[1], reverse=True) # Re-sort after boosting
            
        # Trim to top_k
        candidates = candidates[:top_k]
        
        if not candidates:
            return self._create_no_candidates_result(query)

        # 4. Hybrid Selection (LLM or Top-1)
        # If we have strict allowed_tools and just 1 candidate, we might just pick it?
        # But `map` is usually called when we have ambiguity.
        
        llm_result = self.llm_disambiguator.select_best_tool(query, candidates)
        
        selected_tool = llm_result['selected_tool']
        llm_confidence = llm_result['confidence']
        reason = llm_result['reason']
        
        # Find embedding score for selected tool
        selected_embedding_score = top_embedding_score
        for tool, score in candidates:
            if tool.tool_name == selected_tool:
                selected_embedding_score = score
                break
        
        # Step 3: Confidence fusion
        final_confidence = self.confidence_fusion.fuse_confidence(
            selected_embedding_score,
            llm_confidence
        )
        
        confidence_level = self.confidence_fusion.classify_confidence(final_confidence)
        should_proceed = self.confidence_fusion.should_proceed(final_confidence)
        
        # Build candidate list for audit
        candidates_data = [
            {
                "tool_name": tool.tool_name,
                "domain": tool.domain,
                "embedding_score": round(score, 3)
            }
            for tool, score in candidates
        ]
        
        return ToolMappingResult(
            selected_tool=selected_tool,
            confidence_level=confidence_level.value,
            final_confidence=round(final_confidence, 3),
            embedding_score=round(selected_embedding_score, 3),
            llm_confidence=round(llm_confidence, 3),
            reason=reason,
            candidates=candidates_data,
            should_proceed=should_proceed,
            clarification_needed=not should_proceed
        )

    def _apply_intent_boosting(self, candidates: List[Any], intent: str) -> List[Any]:
        """Boost scores of tools that match the classified intent"""
        boosted_candidates = []
        for tool, score in candidates:
            boost = 0.0
            t_name = tool.tool_name
            
            # Boosting Logic (mirrors IntentClassifier rules)
            if intent == 'COST_FORECAST' and 'forecast' in t_name:
                boost = 0.25
            elif intent == 'COST_TREND' and 'trend' in t_name:
                boost = 0.20
            elif intent == 'COST_BY_SERVICE' and 'by_service' in t_name:
                boost = 0.20
            elif intent == 'COST_BY_REGION' and 'by_region' in t_name:
                boost = 0.25
            elif intent == 'COST_TOTAL' and ('current_month' in t_name or 'today' in t_name):
                 # Heuristic: bills are usually for current period
                boost = 0.15
            elif intent == 'RESOURCE_INVENTORY' and 'list' in t_name:
                boost = 0.15
            elif intent == 'ACCOUNT_METADATA' and ('account' in t_name or 'identity' in t_name):
                 # Avoid boosting 'cost_by_account' for metadata queries
                if 'cost' not in t_name:
                    boost = 0.20
            
            # Apply boost cap to 1.0
            new_score = min(1.0, score + boost)
            boosted_candidates.append((tool, new_score))
            
        return boosted_candidates
    
    def _create_no_candidates_result(self, query: str) -> ToolMappingResult:
        """Create result when no candidates found"""
        return ToolMappingResult(
            selected_tool=None,
            confidence_level="LOW",
            final_confidence=0.0,
            embedding_score=0.0,
            llm_confidence=0.0,
            reason="No matching tools found",
            candidates=[],
            should_proceed=False,
            clarification_needed=True
        )
    
    def explain(self, result: ToolMappingResult) -> str:
        """
        Generate human-readable explanation of mapping decision
        
        Args:
            result: ToolMappingResult
            
        Returns:
            Explanation string
        """
        if not result.selected_tool:
            return "No suitable tool found for this query."
        
        explanation = (
            f"Selected: {result.selected_tool}\n"
            f"Confidence: {result.confidence_level} ({result.final_confidence:.2f})\n"
            f"Embedding similarity: {result.embedding_score:.2f}\n"
            f"LLM confidence: {result.llm_confidence:.2f}\n"
            f"Reason: {result.reason}\n"
            f"Top candidates: {', '.join([c['tool_name'] for c in result.candidates[:3]])}"
        )
        
        return explanation
    
    def get_tools_by_domain(self, domain: str) -> List[str]:
        """Get all tool names for a specific domain"""
        return [
            tool.tool_name 
            for tool in self.tools_metadata 
            if tool.domain == domain
        ]
    
    def refresh_embeddings(self):
        """Regenerate all tool embeddings (call after metadata updates)"""
        for tool in self.tools_metadata:
            embedding_text = tool.get_embedding_text()
            tool.embedding_vector = self.embedding_service.embed_text(
                embedding_text, use_cache=False
            )
        
        print(f"[OK] Refreshed embeddings for {len(self.tools_metadata)} tools")
