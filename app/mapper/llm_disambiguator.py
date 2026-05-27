"""
LLM Disambiguator
Uses LLM to select best tool from candidates with structured output
"""
import json
from typing import List, Tuple, Dict, Any
from ..llm.openai_client import OpenAIClient
from .tool_metadata import ToolMetadata


class LLMDisambiguator:
    """
    Uses LLM to select best tool from candidates
    Enforces structured output to prevent hallucination
    """
    
    def __init__(self, llm_client: OpenAIClient):
        """
        Initialize disambiguator
        
        Args:
            llm_client: OpenAI client instance
        """
        self.llm = llm_client
    
    async def select_best_tool(self, query: str, candidates: List[Tuple[ToolMetadata, float]]) -> Dict[str, Any]:
        """
        LLM selects best tool from candidates with structured output
        
        Args:
            query: User query
            candidates: List of (ToolMetadata, embedding_score) tuples
            
        Returns:
            {
                "selected_tool": str or None,
                "confidence": float (0-1),
                "reason": str
            }
        """
        if not candidates:
            return {
                "selected_tool": None,
                "confidence": 0.0,
                "reason": "No candidates provided"
            }
        
        # Build candidate info for LLM
        candidate_tools = []
        for i, (tool, emb_score) in enumerate(candidates, 1):
            candidate_tools.append({
                "name": tool.tool_name,
                "description": tool.description
            })
            
        # Structure the user payload
        user_payload = {
            "query": query,
            "detected_intent": "AMBIGUOUS_OR_MULTI_MATCH", # We could pass this in if available
            "candidate_tools": candidate_tools
        }
        
        # SYSTEM PROMPT (Production-Safe Version)
        system_prompt = """You are a strict decision engine for an AWS Admin Analytics system.

You are NOT allowed to invent tools.
You MUST select one tool ONLY from the provided candidate list.
You MUST NOT create new tool names.
You MUST NOT modify parameters.
You MUST NOT parse time ranges.
You MUST NOT assume missing information.

If the query is ambiguous or insufficient to confidently select one tool, return:
{
"selected_tool": null,
"confidence": 0.0,
"reason": "insufficient_information"
}

You must prefer clarification over guessing.
Only select a tool if the intent is clearly aligned.

DECISION RULES (Important)

If query indicates forecast, prediction, projection, budget:
→ Select aws_get_cost_forecast if available.

If query indicates breakdown, split, distribution by service:
→ Select aws_get_cost_by_service if available.

If query indicates regional comparison:
→ Select aws_get_cost_by_region if available.

If query indicates time trend, history, over months:
→ Select aws_get_cost_trend if available.

If unclear between multiple cost tools:
→ Return clarification (null tool).

If query references resource listing (instances, buckets, functions):
→ Only select resource tool if no cost-related language present.

Cost intent overrides resource intent if both appear.
If uncertainty exists, choose clarification.

REQUIRED OUTPUT FORMAT
Return ONLY valid JSON:
{
"selected_tool": "tool_name_or_null",
"confidence": 0.0-1.0,
"reason": "short explanation"
}

Confidence Interpretation Guidelines:
0.90–1.0 → Strong semantic alignment
0.75–0.89 → Clear but minor ambiguity
0.50–0.74 → Weak signal
<0.50 → Ambiguous

Your system should only execute if confidence ≥ 0.75.
If between 0.50–0.74: Return null to force clarification.
"""

        try:
            # Call LLM with structured output using JSON mode
            response_text = await self.llm.chat_with_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, indent=2)}
                ],
                temperature=0.0,  # Deterministic
                max_tokens=300
            )
            
            # Parse JSON response
            result = json.loads(response_text)
            
            selected_tool_name = result.get('selected_tool')
            confidence = float(result.get('confidence', 0.0))
            reason = result.get('reason', 'No reason provided')
            
            # Post-processing validation
            valid_tools = [t['name'] for t in candidate_tools]
            
            # 1. Check if tool is in candidates
            if selected_tool_name and selected_tool_name not in valid_tools:
                return {
                    "selected_tool": None,
                    "confidence": 0.0,
                    "reason": f"Hallucination caught: '{selected_tool_name}' not in candidates."
                }
                
            # 2. Enforce confidence threshold (Redundant if prompt works, but safe)
            if confidence < 0.75:
                return {
                    "selected_tool": None,
                    "confidence": confidence,
                    "reason": f"Confidence {confidence} below threshold 0.75. {reason}"
                }

            return {
                "selected_tool": selected_tool_name,
                "confidence": confidence,
                "reason": reason
            }
            
        except Exception as e:
            # Fallback on error
            print(f"LLM Error: {e}")
            return {
                "selected_tool": None,
                "confidence": 0.0,
                "reason": f"LLM execution failed: {str(e)}"
            }
    
    def explain_selection(self, query: str, selected_tool: str, 
                         candidates: List[Tuple[ToolMetadata, float]]) -> str:
        """
        Generate explanation for why a tool was selected
        
        Args:
            query: User query
            selected_tool: Selected tool name
            candidates: Original candidates list
            
        Returns:
            Human-readable explanation
        """
        # Find selected tool in candidates
        selected_meta = None
        selected_score = 0.0
        for tool, score in candidates:
            if tool.tool_name == selected_tool:
                selected_meta = tool
                selected_score = score
                break
        
        if not selected_meta:
            return f"Tool '{selected_tool}' was selected."
        
        explanation = (
            f"Selected '{selected_tool}' (similarity: {selected_score:.2f}) "
            f"from {selected_meta.domain} domain. "
            f"This tool {selected_meta.description.lower()}"
        )
        
        return explanation
