"""
OpenAI LLM Client
"""
import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

class OpenAIClient:
    """
    Wrapper for OpenAI LLM
    Used for both planning and response generation
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
        
        # If API key is missing, init fails unless we handle it gracefully later
        # For now, let's allow it to be None and fail on use, or check env
        if not self.api_key and self.llm_enabled:
             # Just print warning, might be set later?
             print("WARN: OPENAI_API_KEY not found in environment, but LLM_ENABLED is true.")
        
        if self.llm_enabled:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
            print(" LLM Kill Switch Active: LLM_ENABLED=false. No API calls will be made.")
            
        self.model = model
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """
        Send chat completion request
        Returns the response text
        """
        if not self.llm_enabled:
            raise RuntimeError("LLM Kill Switch Active: API calls are disabled.")
            
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is missing. Please set it in .env file.")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content or ""
        
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def chat_with_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1024
    ) -> str:
        """
        Chat with JSON mode for structured output
        """
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is missing. Please set it in .env file.")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content or "{}"
        except Exception as e:
             raise Exception(f"OpenAI API error (JSON mode): {str(e)}")
