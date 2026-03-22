"""LLM client for paper analysis."""

from __future__ import annotations

from typing import Any, Optional

from openai import OpenAI


class LLMClient:
    """OpenAI-compatible LLM client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        fallback_model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """Initialize LLM client.

        Args:
            api_key: API key
            base_url: API base URL
            model: Primary model name
            fallback_model: Fallback model name
            temperature: Temperature for generation
            max_tokens: Maximum tokens in response
        """
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Send chat completion request.

        Args:
            messages: List of message dicts with role and content
            model: Override model name
            **kwargs: Additional arguments

        Returns:
            Generated text
        """
        model = model or self.model

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            # Try fallback model
            if model != self.fallback_model:
                try:
                    response = self.client.chat.completions.create(
                        model=self.fallback_model,
                        messages=messages,
                        temperature=kwargs.get("temperature", self.temperature),
                        max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    )
                    return response.choices[0].message.content or ""
                except Exception:
                    pass

            raise RuntimeError(f"LLM request failed: {e}")

    def analyze(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Analyze with a prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            Generated analysis
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return self.chat(messages)

    def preflight(self) -> tuple[bool, str]:
        """Check if LLM is accessible.

        Returns:
            Tuple of (success, message)
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=5,
            )
            return True, f"LLM OK ({self.model})"
        except Exception as e:
            return False, f"LLM error: {e}"


def create_llm_client(config) -> LLMClient:
    """Create LLM client from config.

    Args:
        config: LLMConfig instance

    Returns:
        LLMClient instance
    """
    api_key = config.get_api_key()
    if not api_key:
        raise ValueError(f"API key not found. Set {config.api_key_env} environment variable.")

    return LLMClient(
        api_key=api_key,
        base_url=config.base_url,
        model=config.primary_model,
        fallback_model=config.fallback_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )