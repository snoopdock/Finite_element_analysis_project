#!/usr/bin/env python3
"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

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

    @abstractmethod
    def get_stats(self) -> Dict:
        """Return usage statistics for this provider."""
        pass
