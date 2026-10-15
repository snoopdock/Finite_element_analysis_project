"""G9.15: conservative, source-bound integrity checks for G3 verification.

Identity is an integrity check, NOT a cryptographic attestation of the author.
Observation membership is checked against exact source-assigned witness IDs;
this does not establish truth of a Python program or a runtime path.
"""
from __future__ import annotations

from audit_engine.semantic_audit.graph.analysis.identity import deterministic_id
from .models import VerificationAttempt, VerificationObligation
from .receipts import VerificationReceipt
from .immutable_payload import thaw


def validate_obligation_identity(obligation: VerificationObligation) -> None:
    if not isinstance(obligation, VerificationObligation):
        raise ValueError('Not a verification obligation')
    if (len(obligation.observation_ids)!=len(set(obligation.observation_ids)) or
            len(obligation.evidence_ids)!=len(set(obligation.evidence_ids))):
        raise ValueError('Duplicate obligation selection')
    payload = {'obligation_type':obligation.obligation_type,
               'source_analysis_id':obligation.source_analysis_id,
               'observation_ids':sorted(obligation.observation_ids),
               'evidence_ids':sorted(obligation.evidence_ids),
               'graph_fingerprint':obligation.graph_fingerprint,
               'semantic_context_fingerprint':obligation.semantic_context_fingerprint,
               'requested_verifier_ids':list(obligation.requested_verifier_ids),
               'parameters':dict(obligation.parameters)}
    if obligation.obligation_id!=deterministic_id('obligation',payload,length=24):
        raise ValueError('Verification obligation identity mismatch')


def validate_selected_associations(obligation: VerificationObligation, result) -> None:
    """Prevent cross-observation witness substitution for scoped obligations.

    Analysis-wide obligations can validly consider orphan evidence and therefore
    deliberately have different semantics. A scoped obligation may select a
    SUBSET of its observed witnesses, e.g. for independent corroboration.
    """
    if not obligation.observation_ids:
        return
    observations={o.observation_id:o for o in result.observations}
    declared=set()
    for oid in obligation.observation_ids:
        observation=observations.get(oid)
        if observation is None:
            raise ValueError('Unknown selected observation')
        if len(set(observation.evidence_ids))!=len(observation.evidence_ids):
            raise ValueError('Repeated observation witness')
        declared.update(observation.evidence_ids)
    if not set(obligation.evidence_ids).issubset(declared):
        raise ValueError('Selected evidence is unrelated to selected observations')
    if obligation.obligation_type == 'observation_contract' and not obligation.evidence_ids:
        raise ValueError('Observation contract has no supporting evidence; cannot verify')


def validate_attempt_identity(attempt: VerificationAttempt, obligation: VerificationObligation, descriptor) -> None:
    if attempt.obligation_id != obligation.obligation_id:
        raise ValueError('Verifier attempt obligation mismatch')
    if attempt.verifier_id!=descriptor.verifier_id or attempt.verifier_version!=descriptor.version:
        raise ValueError('Verifier returned identity/version different from registered descriptor')
    if len(set(attempt.evidence_ids))!=len(attempt.evidence_ids):
        raise ValueError('Repeated attempt evidence')
    if not set(attempt.evidence_ids).issubset(set(obligation.evidence_ids)):
        raise ValueError('Verifier returned foreign evidence')
    payload = {'obligation_id':attempt.obligation_id,'verifier_id':attempt.verifier_id,
        'verifier_version':attempt.verifier_version,'decision':attempt.decision.value,
        'evidence_state':attempt.evidence_state.value,'evidence_ids':sorted(set(attempt.evidence_ids)),
        'details':dict(attempt.details),'error':attempt.error}
    if attempt.attempt_id!=deterministic_id('verification-attempt',payload,length=24):
        raise ValueError('Verifier attempt identity mismatch')


def validate_receipt_identity(receipt: VerificationReceipt, obligation: VerificationObligation | None = None) -> None:
    payload={'attempt_id':receipt.attempt_id,'obligation_id':receipt.obligation_id,
        'source_analysis_id':receipt.source_analysis_id,'verifier_id':receipt.verifier_id,
        'verifier_version':receipt.verifier_version,'decision':receipt.decision.value,
        'evidence_state':receipt.evidence_state.value,'evidence_ids':list(receipt.evidence_ids),
        'graph_fingerprint':receipt.graph_fingerprint,
        'semantic_context_fingerprint':receipt.semantic_context_fingerprint,
        'details':thaw(receipt.details),'error':receipt.error}
    if receipt.receipt_id!=deterministic_id('verification-receipt',payload,length=24):
        raise ValueError('Verification receipt identity mismatch')
    if obligation is not None:
        validate_obligation_identity(obligation)
        if (receipt.obligation_id!=obligation.obligation_id or
            receipt.source_analysis_id!=obligation.source_analysis_id or
            receipt.graph_fingerprint!=obligation.graph_fingerprint or
            receipt.semantic_context_fingerprint!=obligation.semantic_context_fingerprint or
            not set(receipt.evidence_ids).issubset(set(obligation.evidence_ids))):
            raise ValueError('Verification receipt is not bound to selected obligation')
