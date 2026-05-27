"""
Gemini LLM Client
"""
import os
import json
from typing import List, Dict, Any, Optional
import google.generativeai as genai

class GeminiClient:
    """
    Wrapper for Google Gemini LLM
    Used for both planning and response generation as an alternative to OpenAI
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3-preview"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
        
        if not self.api_key and self.llm_enabled:
             print("WARN: GEMINI_API_KEY not found in environment, but LLM_ENABLED is true.")
        
        if self.llm_enabled and self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model)
        else:
            self.model = None
            if not self.llm_enabled:
                print(" LLM Kill Switch Active: LLM_ENABLED=false. No API calls will be made.")
            
        self.model_name = model
    
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
            raise ValueError("GEMINI_API_KEY is missing. Please set it in .env file.")

        try:
            # Convert OpenAI-style messages to Gemini history
            history = []
            system_instruction = None
            last_user_message = ""

            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                
                if role == "system":
                    system_instruction = content
                elif role == "user":
                    last_user_message = content 
                    history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})
            
            # Remove the last user message from history as it will be sent as the current prompt
            if history and history[-1]["role"] == "user":
                history.pop()

            # Configure generation config
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens
            )

            # Start chat session
            chat = self.model.start_chat(history=history)
            
            # Handle System Instruction by prepending to prompt if needed
            # For 1.5 models, we could pass system_instruction to GenerativeModel constructor
            # But since we reuse the client for different prompts, mixing them is tricky.
            # Best practice for dynamic system prompts: Prepend to first message or current message.
            if system_instruction:
                 last_user_message = f"System Instruction: {system_instruction}\n\nUser Message: {last_user_message}"

            response = chat.send_message(
                last_user_message,
                generation_config=generation_config
            )
            
            return response.text or ""
        
        except Exception as e:
            raise Exception(f"Gemini API error: {str(e)}")
    
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
            raise ValueError("GEMINI_API_KEY is missing. Please set it in .env file.")

        try:
            # Append strict JSON instruction
            json_instruction = "IMPORTANT: Return ONLY valid JSON with no markdown formatting. Do not include ```json or ``` blocks."
            
            # Convert messages
            history = []
            last_user_message = ""
            system_instruction = None
            
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                
                if role == "system":
                   system_instruction = content
                elif role == "user":
                    last_user_message = content
                    history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})
            
            if history and history[-1]["role"] == "user":
                history.pop()
            
            # Combine system instruction + user message + json instruction
            full_prompt = last_user_message
            if system_instruction:
                full_prompt = f"System Instruction: {system_instruction}\n\n{full_prompt}"
            
            full_prompt = f"{full_prompt}\n\n{json_instruction}"

            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" # Explicit JSON mode for 1.5 Pro/Flash
            )

            chat = self.model.start_chat(history=history)
            response = chat.send_message(
                full_prompt,
                generation_config=generation_config
            )
            
            text = response.text or "{}"
            # Cleanup potential markdown if model ignores mime_type (fallback)
            text = text.replace("```json", "").replace("```", "").strip()
            return text
            
        except Exception as e:
             raise Exception(f"Gemini API error (JSON mode): {str(e)}")
