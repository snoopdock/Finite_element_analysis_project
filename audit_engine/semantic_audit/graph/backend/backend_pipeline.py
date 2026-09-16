"""
Semantic Graph Backend Pipeline.
"""


class BackendPipeline:

    def __init__(self, selector, factory):
        self.selector = selector
        self.factory = factory

    def execute(self, requirements, context):
        backend_name = self.selector.select(requirements)

        adapter = self.factory.create(
            backend_name,
            context,
        )

        return adapter, backend_name
