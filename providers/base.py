#!/usr/bin/env python3
"""Abstract base class for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple



@dataclass(frozen=True)
class ProviderToolCall:
    """A provider-native function call, preserved as data and never executed here."""

    name: str
    arguments: Any


class BaseLLMProvider(ABC):
    """Interface that all LLM providers must implement."""

    @abstractmethod
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.2, 
        max_tokens: Optional[int] = None, 
        model: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Send a chat completion request.
        
        Returns:
            Tuple of (response_text, error_message).
            If successful, error_message is None.
            If failed, response_text is None.
        """
        pass

    def chat_text(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Request an unconstrained text response; adapters may choose their text endpoint."""
        return self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    @abstractmethod
    def get_stats(self) -> Dict:
        """Return usage statistics for this provider."""
        pass


@dataclass(frozen=True)
class ProviderResponse:
    """Provider-neutral response envelope consumed by the AE-32C normalizer.

    Adapters may return text, one or more provider-native calls, or both. Native
    calls are inert data: the response normalizer accepts only the virtual
    AE-32C response function and never executes provider-supplied calls.
    """

    text: Optional[str] = None
    tool_calls: Tuple[ProviderToolCall, ...] = ()
    finish_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.text is not None and not isinstance(self.text, str):
            raise TypeError("ProviderResponse.text must be str or None")
        calls = self.tool_calls
        if not isinstance(calls, (tuple, list)):
            raise TypeError("ProviderResponse.tool_calls must be a tuple or list")
        if any(not isinstance(call, ProviderToolCall) for call in calls):
            raise TypeError("ProviderResponse.tool_calls must contain ProviderToolCall values")
        object.__setattr__(self, "tool_calls", tuple(calls))
        if self.finish_reason is not None and not isinstance(self.finish_reason, str):
            raise TypeError("ProviderResponse.finish_reason must be str or None")
