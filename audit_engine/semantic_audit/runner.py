from pathlib import Path


from .core.models import (
    AuditReport
)

from .extractors.ast_extractor import (
    ASTExtractor
)

from .analyzers.symbol_classifier import (
    SymbolClassifier
)

from .reports.json_report import (
    write_report
)

from .graph.builder import (
    SemanticGraphBuilder
)

from .graph.serializer import (
    serialize_graph
)



def run():

    report = AuditReport()


    extractor = ASTExtractor()

    classifier = SymbolClassifier()



    for file in Path(".").rglob(
        "*.py"
    ):


        if ".git" in str(file):
            continue


        imports, symbols = extractor.extract(
            file
        )


        report.imports.extend(
            imports
        )


        report.symbols.extend(
            symbols
        )


        for imp in imports:


            for symbol in (
                imp.imported_symbols
                or [""]
            ):


                finding = classifier.classify(
                    imp,
                    symbol
                )


                report.findings.append(
                    finding
                )



    #
    # Semantic Graph Generation
    #
    # Converts existing audit observations
    # into an explicit semantic graph.
    #
    # The graph is an additional artifact.
    # It does not modify audit decisions.
    #


    semantic_graph = SemanticGraphBuilder().build(
        report
    )


    serialize_graph(
        semantic_graph,
        "semantic_graph.json"
    )



    write_report(
        report
    )



if __name__ == "__main__":
    run()
