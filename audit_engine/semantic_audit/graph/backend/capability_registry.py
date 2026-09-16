class BackendCapabilityRegistry:
    """
    Registry of Semantic Graph backend capabilities.
    """

    def __init__(self):
        self._backends = {}

    def register(self, name, adapter, capabilities):
        self._backends[name] = {
            "adapter": adapter,
            "capabilities": capabilities,
        }

    def get(self, name):
        return self._backends[name]

    def list_backends(self):
        return list(self._backends.keys())

    def describe(self):
        return {
            name: item["capabilities"]
            for name, item in self._backends.items()
        }


def create_default_registry():
    registry = BackendCapabilityRegistry()

    registry.register(
        "networkx",
        "NetworkXAdapter",
        {
            "lossless": True,
            "metadata": True,
            "multiedges": True,
            "directed": True,
        },
    )

    registry.register(
        "scipy",
        "SciPyAdapter",
        {
            "lossless": False,
            "sparse_matrix": True,
            "metadata": False,
            "relation_side_channel": True,
        },
    )

    return registry
