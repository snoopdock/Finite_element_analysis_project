"""Capability selection excludes unavailable optional libraries by default."""


class BackendSelectionPolicy:
    def __init__(self, registry):
        self.registry = registry

    def find_backends(self, requirements):
        results = []
        for backend, capabilities in self.registry.describe().items():
            # Checking available=False as a requirement does not make the backend executable.
            if not capabilities.get("available", True):
                continue
            if all(capabilities.get(key) == value for key, value in requirements.items()):
                results.append(backend)
        return results

    def select(self, requirements):
        candidates = self.find_backends(requirements)
        if not candidates:
            raise ValueError("No available backend satisfies requirements")
        return candidates[0]
