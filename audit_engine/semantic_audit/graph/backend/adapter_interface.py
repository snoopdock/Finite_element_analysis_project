"""
Semantic Graph Adapter Interface

This module defines the conceptual contract for future backend adapters.

It intentionally contains no dependency on:
- NetworkX
- SciPy
- RDF libraries
- graph databases

Concrete adapters should implement this contract.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class SemanticGraphAdapter(ABC):
    """
    Base contract for SemanticGraph backend projections.
    """

    @abstractmethod
    def export(self) -> Any:
        """
        Produce backend-specific representation.
        """
        raise NotImplementedError


    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """
        Describe backend capabilities.
        """
        raise NotImplementedError


    @abstractmethod
    def identity_mapping(self) -> Dict[str, Any]:
        """
        Return semantic identity to backend identity mapping.
        """
        raise NotImplementedError


    @abstractmethod
    def loss_report(self) -> Dict[str, Any]:
        """
        Report unsupported or transformed semantic information.
        """
        raise NotImplementedError
