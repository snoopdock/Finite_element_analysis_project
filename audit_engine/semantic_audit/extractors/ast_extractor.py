"""Snapshot-safe Python AST extraction; repository source is never executed."""
import ast
from ..core.models import ImportReference, SymbolUsage
class ASTExtractor:
    def extract(self, file_path):
        return self.extract_source(file_path.read_bytes(), str(file_path))
    def extract_source(self, source, file_path="<memory>"):
        tree = ast.parse(source, filename=str(file_path))
        imports, symbols = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    imports.append(ImportReference(str(file_path), node.lineno, item.name))
            elif isinstance(node, ast.ImportFrom):
                imports.append(ImportReference(str(file_path), node.lineno, node.module or "", [x.name for x in node.names]))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    symbols.append(SymbolUsage(str(file_path), node.lineno, node.func.id, "", "CALL"))
                elif isinstance(node.func, ast.Attribute):
                    symbols.append(SymbolUsage(str(file_path), node.lineno, node.func.attr, "", "CALL"))
        return imports, symbols
