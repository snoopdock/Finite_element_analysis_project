from pathlib import Path


from semantic_audit.core.models import (
    AuditReport
)

from semantic_audit.extractors.ast_extractor import (
    ASTExtractor
)

from semantic_audit.analyzers.symbol_classifier import (
    SymbolClassifier
)

from semantic_audit.reports.json_report import (
    write_report
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



    write_report(
        report
    )


if __name__ == "__main__":
    run()
