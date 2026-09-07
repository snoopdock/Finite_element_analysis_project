import ast

from semantic_audit.core.models import (
    ImportReference,
    SymbolUsage
)


class ASTExtractor:


    def extract(self, file_path):

        source = file_path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            source
        )


        imports = []

        symbols = []


        for node in ast.walk(tree):


            if isinstance(
                node,
                ast.Import
            ):

                for item in node.names:

                    imports.append(
                        ImportReference(

                            file=str(file_path),

                            line=node.lineno,

                            module=item.name

                        )
                    )


            elif isinstance(
                node,
                ast.ImportFrom
            ):


                module = node.module or ""


                names = [
                    x.name
                    for x in node.names
                ]


                imports.append(

                    ImportReference(

                        file=str(file_path),

                        line=node.lineno,

                        module=module,

                        imported_symbols=names

                    )

                )



            elif isinstance(
                node,
                ast.Call
            ):


                if isinstance(
                    node.func,
                    ast.Name
                ):

                    symbols.append(

                        SymbolUsage(

                            file=str(file_path),

                            line=node.lineno,

                            symbol=node.func.id,

                            module="",

                            usage_type="CALL"

                        )

                    )


                elif isinstance(
                    node.func,
                    ast.Attribute
                ):

                    symbols.append(

                        SymbolUsage(

                            file=str(file_path),

                            line=node.lineno,

                            symbol=node.func.attr,

                            module="",

                            usage_type="CALL"

                        )

                    )


        return imports, symbols
