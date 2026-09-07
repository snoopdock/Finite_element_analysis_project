from audit_engine.core.models import SymbolReference


class SymbolClassifier:
    """
    Classifies imported symbols according to their
    apparent semantic role.

    This is observation only.
    It does not determine allowed/forbidden behavior.
    """


    READ_PATTERNS = [
        "get",
        "read",
        "fetch",
        "load",
        "find",
        "query",
        "summary",
        "retrieve",
    ]


    MUTATION_PATTERNS = [
        "update",
        "set",
        "delete",
        "remove",
        "write",
        "save",
        "commit",
        "persist",
    ]


    CREATE_PATTERNS = [
        "create",
        "build",
        "construct",
        "make",
    ]


    EXECUTION_PATTERNS = [
        "execute",
        "run",
        "dispatch",
        "submit",
        "invoke",
    ]


    def classify(
        self,
        symbol: SymbolReference
    ):

        name = symbol.symbol.lower()


        for pattern in self.MUTATION_PATTERNS:

            if pattern in name:

                symbol.classification = (
                    "MUTATION_SERVICE"
                )

                symbol.classification_reason = (
                    f"name contains mutation pattern '{pattern}'"
                )

                return symbol



        for pattern in self.EXECUTION_PATTERNS:

            if pattern in name:

                symbol.classification = (
                    "EXECUTION_SERVICE"
                )

                symbol.classification_reason = (
                    f"name contains execution pattern '{pattern}'"
                )

                return symbol



        for pattern in self.CREATE_PATTERNS:

            if pattern in name:

                symbol.classification = (
                    "CONSTRUCTION_SERVICE"
                )

                symbol.classification_reason = (
                    f"name contains construction pattern '{pattern}'"
                )

                return symbol



        for pattern in self.READ_PATTERNS:

            if pattern in name:

                symbol.classification = (
                    "READ_SERVICE"
                )

                symbol.classification_reason = (
                    f"name contains read pattern '{pattern}'"
                )

                return symbol



        symbol.classification = (
            "UNKNOWN"
        )

        symbol.classification_reason = (
            "no semantic naming pattern detected"
        )

        return symbol
