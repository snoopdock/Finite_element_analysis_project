import json
from pathlib import Path



def write_report(report):


    data = {


        "imports":

        [

            {

                "file": x.file,

                "line": x.line,

                "module": x.module,

                "symbols":
                    x.imported_symbols

            }

            for x in report.imports

        ],


        "symbols":

        [

            {

                "file": x.file,

                "line": x.line,

                "symbol": x.symbol,

                "usage":
                    x.usage_type

            }

            for x in report.symbols

        ],


        "findings":

        [

            {

                "file": x.file,

                "module": x.module,

                "symbol": x.symbol,

                "classification":
                    x.classification,

                "reason":
                    x.reason

            }

            for x in report.findings

        ]

    }


    Path(
        "semantic_audit_report.json"
    ).write_text(

        json.dumps(
            data,
            indent=2
        ),

        encoding="utf-8"

    )
