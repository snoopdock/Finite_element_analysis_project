"""Controlled historical incident fixture: consumer/provider counter mismatch."""
from providers.adapter import ProviderAdapter


def extract(provider: ProviderAdapter) -> int:
    return provider.total_calls
