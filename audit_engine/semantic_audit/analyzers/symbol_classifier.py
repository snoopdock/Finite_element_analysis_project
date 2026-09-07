from ..core.models import  (
    SemanticFinding
)


class SymbolClassifier:


    def classify(
        self,
        import_ref,
        symbol=None
    ):


        module = (
            import_ref.module.lower()
        )


        if (
            "research.evidence"
            in module
        ):

            return SemanticFinding(

                file=import_ref.file,

                module=import_ref.module,

                symbol=symbol or "",

                classification=
                    "SCIENTIFIC_READ_ACCESS",

                reason=
                    "Application layer accesses scientific evidence module"

            )


        if (
            "retrieval"
            in module
        ):

            return SemanticFinding(

                file=import_ref.file,

                module=import_ref.module,

                symbol=symbol or "",

                classification=
                    "RETRIEVAL_ACCESS",

                reason=
                    "Dependency belongs to retrieval subsystem"

            )


        return SemanticFinding(

            file=import_ref.file,

            module=import_ref.module,

            symbol=symbol or "",

            classification=
                "UNCLASSIFIED",

            reason=
                "No semantic rule matched"

        )
