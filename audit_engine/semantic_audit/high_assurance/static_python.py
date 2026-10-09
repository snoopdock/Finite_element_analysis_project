"""Deterministic Python AST verifier for bounded static-import obligations."""

from __future__ import annotations

import ast
import hashlib

from audit_engine.semantic_audit.graph.analysis.models import VerificationStatus
from audit_engine.semantic_audit.verification.models import VerificationContext, VerificationDecision

from .adapter import HighAssuranceAdapterDescriptor
from .models import (
    AssuranceMechanism,
    ContainmentMode,
    HighAssuranceRequest,
    HighAssuranceResult,
    ValidationCompleteness,
    ValidationEnvelope,
    VerificationWitness,
    WitnessKind,
)


PYTHON_STATIC_IMPORT_OBLIGATION = "python_static_import_constraint"


def _source_digest(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _matches_module(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(forbidden + ".")


class PythonStaticImportAdapter:
    """Verify absence of explicitly forbidden *static* Python import statements.

    The adapter intentionally excludes runtime/dynamic import mechanisms.  That
    limitation is recorded in every validation envelope instead of being hidden.
    """

    descriptor = HighAssuranceAdapterDescriptor(
        adapter_id="python-static-import",
        version="1.0.0",
        supported_obligation_types=(PYTHON_STATIC_IMPORT_OBLIGATION,),
        mechanism=AssuranceMechanism.STATIC_ANALYSIS,
        containment_mode=ContainmentMode.IN_PROCESS_READ_ONLY,
        maximum_evidence_state=VerificationStatus.VALIDATED,
        deterministic=True,
        side_effect_free=True,
        requires_network=False,
        produces_witness=True,
    )

    def execute(
        self,
        request: HighAssuranceRequest,
        context: VerificationContext,
    ) -> HighAssuranceResult:
        source_text = request.parameters.get("source_text")
        forbidden = request.parameters.get("forbidden_modules")
        if not isinstance(source_text, str):
            raise ValueError("python_static_import_constraint requires string source_text.")
        if not isinstance(forbidden, (list, tuple)) or not all(isinstance(item, str) and item.strip() for item in forbidden):
            raise ValueError("forbidden_modules must be a non-empty-string list.")
        forbidden_modules = tuple(dict.fromkeys(item.strip() for item in forbidden))
        subject_digest = _source_digest(source_text)

        try:
            tree = ast.parse(source_text)
        except SyntaxError as exc:
            envelope = ValidationEnvelope.create(
                subject_digest=subject_digest,
                tool_id="python-ast-static-import",
                tool_version="1.0.0",
                checked_scope=("parse_attempt",),
                assumptions=("source_text is the intended Python subject",),
                excluded_scope=("static imports could not be inspected because parsing failed",),
                completeness=ValidationCompleteness.PARTIAL,
                environment={"parser_contract": "python_ast/v1"},
            )
            witness = VerificationWitness.create(
                kind=WitnessKind.COUNTEREXAMPLE,
                subject_digest=subject_digest,
                summary="Python source did not parse; static-import constraint is inconclusive.",
                reproducible=True,
                details={"line": exc.lineno, "offset": exc.offset, "message": exc.msg},
            )
            return HighAssuranceResult.create(
                request=request,
                adapter_version=self.descriptor.version,
                decision=VerificationDecision.INCONCLUSIVE,
                evidence_state=VerificationStatus.OBSERVED,
                validation_envelope=envelope,
                witnesses=(witness,),
                diagnostics=("python_syntax_error",),
            )

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        imports = sorted(dict.fromkeys(imports))
        violating = sorted(
            imported
            for imported in imports
            if any(_matches_module(imported, blocked) for blocked in forbidden_modules)
        )
        envelope = ValidationEnvelope.create(
            subject_digest=subject_digest,
            tool_id="python-ast-static-import",
            tool_version="1.0.0",
            checked_scope=("ast.Import", "ast.ImportFrom"),
            assumptions=("source_text is the complete Python source subject for this obligation",),
            excluded_scope=(
                "dynamic imports via importlib",
                "dynamic imports via __import__",
                "imports performed by executed/generated code",
            ),
            completeness=ValidationCompleteness.EXHAUSTIVE_WITHIN_SCOPE,
            environment={"parser_contract": "python_ast/v1"},
        )
        scan_witness = VerificationWitness.create(
            kind=WitnessKind.STATIC_FACT,
            subject_digest=subject_digest,
            summary=f"AST scan observed {len(imports)} unique static import target(s).",
            reproducible=True,
            details={"imports": imports, "forbidden_modules": list(forbidden_modules)},
        )
        witnesses = [scan_witness]
        decision = VerificationDecision.CONFIRMED
        if violating:
            decision = VerificationDecision.REFUTED
            witnesses.append(
                VerificationWitness.create(
                    kind=WitnessKind.COUNTEREXAMPLE,
                    subject_digest=subject_digest,
                    summary="Forbidden static import target(s) were observed.",
                    reproducible=True,
                    details={"violating_imports": violating},
                )
            )
        return HighAssuranceResult.create(
            request=request,
            adapter_version=self.descriptor.version,
            decision=decision,
            evidence_state=VerificationStatus.VALIDATED,
            validation_envelope=envelope,
            witnesses=witnesses,
        )
