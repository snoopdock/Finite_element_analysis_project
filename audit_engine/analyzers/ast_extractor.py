import ast
from pathlib import Path

from audit_engine.core.models import (
    DependencyEdge,
    SymbolReference,
    SourceLocation,
)


class ASTExtractor:

    def analyze_file(self, path: Path):

        source = path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source,
            filename=str(path)
        )

        dependencies = []
        symbols = []

        for node in ast.walk(tree):

            if isinstance(node, ast.Import):

                for item in node.names:

                    dependencies.append(
                        DependencyEdge(
                            source=str(path),
                            target=item.name,
                            kind="IMPORT",
                            location=SourceLocation(
                                str(path),
                                node.lineno,
                            ),
                        )
                    )


            elif isinstance(node, ast.ImportFrom):

                if node.module:

                    dependencies.append(
                        DependencyEdge(
                            source=str(path),
                            target=node.module,
                            kind="IMPORT_FROM",
                            location=SourceLocation(
                                str(path),
                                node.lineno,
                            ),
                        )
                    )

                    for item in node.names:

                        symbols.append(
                            SymbolReference(
                                file=str(path),
                                symbol=item.name,
                                module=node.module,
                                line=node.lineno,
                                usage="IMPORT",
                            )
                        )


            elif isinstance(node, ast.Call):

                if isinstance(node.func, ast.Name):

                    symbols.append(
                        SymbolReference(
                            file=str(path),
                            symbol=node.func.id,
                            module="",
                            line=node.lineno,
                            usage="CALL",
                        )
                    )


        return dependencies, symbols
