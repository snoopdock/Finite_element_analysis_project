from ..core.semantic_graph import (
    SemanticGraph,
    SemanticNode,
    SemanticEdge
)



class SemanticGraphBuilder:
    """
    Converts audit observations into a semantic graph.
    """


    def __init__(self):

        self.graph = SemanticGraph()



    def add_file_node(
        self,
        file_path: str
    ) -> None:

        if not self.graph.has_node(file_path):

            self.graph.add_node(

                SemanticNode(

                    node_id=file_path,

                    entity_type="SoftwareModule"

                )

            )



    def add_module_node(
        self,
        module_name: str
    ) -> None:

        if not self.graph.has_node(module_name):

            self.graph.add_node(

                SemanticNode(

                    node_id=module_name,

                    entity_type="SoftwareDependency"

                )

            )



    def build_from_imports(
        self,
        imports
    ) -> None:
        """
        Converts ImportReference objects
        into IMPORTS relationships.
        """


        for item in imports:

            self.add_file_node(
                item.file
            )

            self.add_module_node(
                item.module
            )


            self.graph.add_edge(

                SemanticEdge(

                    source_id=item.file,

                    target_id=item.module,

                    relation_type="IMPORTS",

                    metadata={

                        "line":
                            item.line,

                        "symbols":
                            item.imported_symbols

                    }

                )

            )



    def build_from_symbols(
        self,
        symbols
    ) -> None:
        """
        Converts symbol usage into semantic relationships.
        """


        for item in symbols:

            self.add_file_node(
                item.file
            )


            symbol_id = (

                f"{item.module}."
                f"{item.symbol}"

            )


            if not self.graph.has_node(
                symbol_id
            ):

                self.graph.add_node(

                    SemanticNode(

                        node_id=symbol_id,

                        entity_type="Symbol"

                    )

                )


            self.graph.add_edge(

                SemanticEdge(

                    source_id=item.file,

                    target_id=symbol_id,

                    relation_type="USES",

                    metadata={

                        "line":
                            item.line,

                        "usage":
                            item.usage_type

                    }

                )

            )



    def build(
        self,
        report
    ) -> SemanticGraph:
        """
        Build semantic graph from AuditReport.
        """


        self.build_from_imports(
            report.imports
        )


        self.build_from_symbols(
            report.symbols
        )


        return self.graph
