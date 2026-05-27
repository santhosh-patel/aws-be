"""
Sarvam AI LLM Client
Drop-in replacement for OpenAIClient, using OpenAI compatible API.
"""
import os
from typing import List, Dict, Any, Optional
from .openai_client import OpenAIClient
from openai import OpenAI

class SarvamClient(OpenAIClient):
    """
    Wrapper for Sarvam AI LLM
    Inherits from OpenAIClient since Sarvam uses an OpenAI-compatible API.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "sarvam-30b"):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        self.llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
        
        if not self.api_key and self.llm_enabled:
             print("WARN: SARVAM_API_KEY not found in environment, but LLM_ENABLED is true.")
        
        if self.llm_enabled and self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.sarvam.ai/v1"
            )
            print(f"[OK] Initialized Sarvam AI client (model: {model})")
        else:
            self.client = None
            if not self.llm_enabled:
                print(" LLM Kill Switch Active: LLM_ENABLED=false. No API calls will be made.")
            
        self.model = model

    # Uses the same chat() and chat_with_json() methods defined in OpenAIClient,
    # as the API signatures for completions are fully compatible.
