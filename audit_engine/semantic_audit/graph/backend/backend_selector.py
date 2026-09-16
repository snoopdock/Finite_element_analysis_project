"""
Semantic Graph Backend Selection Policy.

Chooses suitable backend candidates based on declared capabilities.
"""


class BackendSelectionPolicy:

    def __init__(self, registry):
        self.registry = registry


    def find_backends(self, requirements):

        results = []

        descriptions = self.registry.describe()

        for backend, capabilities in descriptions.items():

            matches = True

            for key, value in requirements.items():

                if capabilities.get(key) != value:
                    matches = False
                    break

            if matches:
                results.append(backend)

        return results


    def select(self, requirements):

        candidates = self.find_backends(requirements)

        if not candidates:
            raise ValueError(
                "No backend satisfies requirements"
            )

        return candidates[0]
