"""
Anthropic Claude LLM Client
Drop-in replacement for OpenAIClient with same interface contract.
Supports both standard chat and Claude's native tool-use API.
"""
import os
import json
import re
from typing import List, Dict, Any, Optional


class AnthropicClient:
    """
    Wrapper for Anthropic Claude LLM.
    Used for both planning and response generation.
    Implements same interface as OpenAIClient: chat() and chat_with_json().
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"

        if not self.api_key and self.llm_enabled:
            print("WARN: ANTHROPIC_API_KEY not found in environment, but LLM_ENABLED is true.")

        self.client = None
        if self.llm_enabled and self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                print(f"[OK] Initialized Anthropic Claude client (model: {model})")
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Run: pip install anthropic>=0.39.0"
                )
        elif not self.llm_enabled:
            print(" LLM Kill Switch Active: LLM_ENABLED=false. No API calls will be made.")

        self.model = model

    # ─── Core Chat (same interface as OpenAIClient.chat) ────────────────────────

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send chat completion request to Claude.
        Accepts OpenAI-style messages list and converts to Claude format.
        Returns the response text.
        """
        if not self.llm_enabled:
            raise RuntimeError("LLM Kill Switch Active: API calls are disabled.")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is missing. Please set it in .env file.")
        if not self.client:
            raise RuntimeError("Anthropic client not initialized.")

        try:
            system_prompt, claude_messages = self._convert_messages(messages)

            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": claude_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # Extract text from response content blocks
            return self._extract_text(response)

        except Exception as e:
            raise Exception(f"Anthropic API error: {str(e)}")

    # ─── JSON Mode (same interface as OpenAIClient.chat_with_json) ──────────────

    def chat_with_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        """
        Chat with structured JSON output.
        Claude doesn't have a native JSON mode, so we use explicit prompting
        and extract the JSON from the response.
        """
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is missing. Please set it in .env file.")

        try:
            # Append explicit JSON instruction to the last user message
            json_messages = list(messages)
            if json_messages:
                last = json_messages[-1]
                if last.get("role") == "user":
                    json_messages[-1] = {
                        "role": "user",
                        "content": (
                            last["content"]
                            + "\n\nIMPORTANT: Return ONLY valid JSON with no markdown "
                            "formatting, no ```json blocks, no explanation text. "
                            "Output the raw JSON object only."
                        ),
                    }

            system_prompt, claude_messages = self._convert_messages(json_messages)

            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": claude_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)
            text = self._extract_text(response)

            # Clean up any markdown formatting that Claude might add
            text = text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            # Validate it's parseable JSON
            try:
                json.loads(text)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                from .json_util import extract_json_balanced
                extracted = extract_json_balanced(text)
                if extracted:
                    text = extracted
                else:
                    text = "{}"

            return text

        except Exception as e:
            raise Exception(f"Anthropic API error (JSON mode): {str(e)}")

    # ─── Tool-Use Chat (Claude-specific, used for native MCP integration) ───────

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Claude native tool-use API.
        Returns the full response object with tool_use blocks.

        Args:
            messages: OpenAI-style messages
            tools: List of Claude tool definitions
            temperature: Sampling temperature
            max_tokens: Max output tokens

        Returns:
            Dict with 'text' (any text content), 'tool_calls' (list of tool use blocks),
            and 'stop_reason'.
        """
        if not self.llm_enabled:
            raise RuntimeError("LLM Kill Switch Active: API calls are disabled.")
        if not self.client:
            raise RuntimeError("Anthropic client not initialized.")

        try:
            system_prompt, claude_messages = self._convert_messages(messages)

            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": claude_messages,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # Parse response into structured format
            result: Dict[str, Any] = {
                "text": "",
                "tool_calls": [],
                "stop_reason": response.stop_reason,
            }

            for block in response.content:
                if block.type == "text":
                    result["text"] += block.text
                elif block.type == "tool_use":
                    result["tool_calls"].append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            return result

        except Exception as e:
            raise Exception(f"Anthropic tool-use API error: {str(e)}")

    def send_tool_results(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Continue a tool-use conversation by sending tool results back to Claude.
        The messages should include the original assistant response with tool_use
        and a user message with tool_result blocks.

        Args:
            messages: Full conversation including tool results (Claude-native format)
            tools: Same tool definitions as original call
            temperature: Sampling temperature
            max_tokens: Max output tokens

        Returns:
            Same structure as chat_with_tools
        """
        if not self.client:
            raise RuntimeError("Anthropic client not initialized.")

        try:
            # Extract system prompt if the first message is a system message
            system_prompt = None
            claude_messages = []
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                else:
                    claude_messages.append(msg)

            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": claude_messages,
                "tools": tools,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            result: Dict[str, Any] = {
                "text": "",
                "tool_calls": [],
                "stop_reason": response.stop_reason,
            }

            for block in response.content:
                if block.type == "text":
                    result["text"] += block.text
                elif block.type == "tool_use":
                    result["tool_calls"].append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            return result

        except Exception as e:
            raise Exception(f"Anthropic tool-result API error: {str(e)}")

    # ─── Internal Helpers ───────────────────────────────────────────────────────

    def _convert_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple:
        """
        Convert OpenAI-style messages to Claude format.
        Claude requires:
        - system prompt as a separate parameter (not in messages)
        - messages must alternate user/assistant
        - first message must be from user

        Returns:
            (system_prompt: str | None, claude_messages: list)
        """
        system_prompt = None
        claude_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Claude takes system as a separate parameter
                if system_prompt:
                    system_prompt += "\n\n" + content
                else:
                    system_prompt = content
            elif role == "user":
                # Merge consecutive user messages
                if claude_messages and claude_messages[-1]["role"] == "user":
                    claude_messages[-1]["content"] += "\n\n" + content
                else:
                    claude_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                # Merge consecutive assistant messages
                if claude_messages and claude_messages[-1]["role"] == "assistant":
                    claude_messages[-1]["content"] += "\n\n" + content
                else:
                    claude_messages.append({"role": "assistant", "content": content})

        # Claude requires at least one user message
        if not claude_messages:
            claude_messages.append({"role": "user", "content": "Hello"})

        # Claude requires first message to be from user
        if claude_messages[0]["role"] != "user":
            claude_messages.insert(0, {"role": "user", "content": "Hello"})

        return system_prompt, claude_messages

    def _extract_text(self, response) -> str:
        """Extract text content from Claude response."""
        texts = []
        for block in response.content:
            if block.type == "text":
                texts.append(block.text)
        return "\n".join(texts) if texts else ""
