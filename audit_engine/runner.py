from pathlib import Path
import json

from audit_engine.core.models import AuditInventory
from audit_engine.analyzers.ast_extractor import ASTExtractor


ROOT = Path(".")


def collect_python_files():

    return list(
        ROOT.rglob("*.py")
    )


def run():

    inventory = AuditInventory()

    extractor = ASTExtractor()


    for file in collect_python_files():

        inventory.python_files.append(
            str(file)
        )

        deps, symbols = extractor.analyze_file(
            file
        )

        inventory.dependencies.extend(
            deps
        )

        inventory.symbols.extend(
            symbols
        )


    output = {

        "python_files":
            inventory.python_files,

        "dependencies":
        [
            {
                "source": d.source,
                "target": d.target,
                "kind": d.kind,
                "line": d.location.line,
            }
            for d in inventory.dependencies
        ],

        "symbols":
        [
            {
                "file": s.file,
                "symbol": s.symbol,
                "module": s.module,
                "line": s.line,
                "usage": s.usage,
            }
            for s in inventory.symbols
        ]

    }


    Path(
        "semantic_audit_inventory.json"
    ).write_text(
        json.dumps(
            output,
            indent=2
        ),
        encoding="utf-8"
    )


if __name__ == "__main__":
    run()
