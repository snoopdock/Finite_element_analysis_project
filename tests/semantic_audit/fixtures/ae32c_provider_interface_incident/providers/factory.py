"""Factory relationship for the controlled incident fixture."""
from providers.adapter import ProviderAdapter


def build_provider() -> ProviderAdapter:
    return ProviderAdapter()
