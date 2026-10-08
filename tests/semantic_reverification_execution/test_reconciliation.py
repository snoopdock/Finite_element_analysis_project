from audit_engine.semantic_audit.evolution import ReconciliationDisposition, reconcile_analysis, reconcile_finding, reconcile_receipt
from audit_engine.semantic_audit.rules.models import RuleDisposition


def test_analysis_reconciliation_can_be_equivalent(audit_chain):
    _, analysis, _, _, _ = audit_chain
    assert reconcile_analysis(analysis, analysis).disposition is ReconciliationDisposition.ANALYSIS_EQUIVALENT


def test_receipt_reconciliation_can_be_equivalent(audit_chain):
    receipt = audit_chain[2].receipts[0]
    assert reconcile_receipt(receipt, receipt).disposition is ReconciliationDisposition.RECEIPT_EQUIVALENT


def test_finding_not_triggered_is_not_lifecycle_mutation(audit_chain):
    finding = audit_chain[2].findings[0]
    reconciliation = reconcile_finding(finding, disposition=RuleDisposition.NOT_TRIGGERED, successor=None)
    assert reconciliation.disposition is ReconciliationDisposition.FINDING_NOT_TRIGGERED
    assert reconciliation.details["lifecycle_mutated"] is False
    assert finding.lifecycle_status.value == "open"
