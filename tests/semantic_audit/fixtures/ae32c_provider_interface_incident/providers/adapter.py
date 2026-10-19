"""Minimal provider adapter used by the controlled incident fixture."""


class ProviderAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        return "fixture response"
