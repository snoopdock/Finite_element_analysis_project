"""Non-collected fixture test source used only for static evidence discovery."""
from pipeline.extractor import extract
from providers.adapter import ProviderAdapter


def check_extractor_contract():
    provider = ProviderAdapter()
    return extract(provider)
