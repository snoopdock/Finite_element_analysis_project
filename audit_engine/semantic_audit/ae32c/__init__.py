"""AE-32C provider-neutral interactive LLM repository investigation.

Exports are loaded lazily so importing lightweight rule contracts does not
initialize investigator adapters or optional parser dependencies.
"""
from importlib import import_module

_INVESTIGATOR_EXPORTS = {
    "InvestigationError", "InvestigationLimits", "RepositoryInvestigator",
    "render_markdown_report", "write_report_artifacts",
}
_CLAIM_EXPORTS = {
    "build_adjudication_template", "build_claim_evidence_assessment",
    "compute_inter_rater_agreement", "validate_adjudication_record",
}

__all__ = sorted(_INVESTIGATOR_EXPORTS | _CLAIM_EXPORTS)


def __getattr__(name):
    if name in _INVESTIGATOR_EXPORTS:
        module = import_module(".investigator", __name__)
    elif name in _CLAIM_EXPORTS:
        module = import_module(".claim_evidence", __name__)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
