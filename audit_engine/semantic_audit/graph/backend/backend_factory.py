class BackendFactory:

    def create(self, backend_name, context):

        if backend_name == "networkx":
            from audit_engine.semantic_audit.graph.backend.networkx_adapter import NetworkXAdapter
            return NetworkXAdapter(context.graph)

        if backend_name == "scipy":
            from audit_engine.semantic_audit.graph.backend.scipy_adapter import SciPyAdapter
            return SciPyAdapter(context.graph)

        raise ValueError(f"Unknown backend: {backend_name}")
