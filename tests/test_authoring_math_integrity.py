from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.authoring_integrity import (
    AuthoringIntegrityError,
    assert_section_records_math_integrity,
    audit_authoring_math_integrity,
)
from core.document_assembler import DocumentAssemblyError, assemble_section, validate_authoring_text
from writing.dynamic_writer import DynamicWriter


def test_authoring_integrity_rejects_third_run_raw_gamma_pattern():
    text = r"The natural boundary is denoted by \Gamma and carries prescribed traction."
    issues = audit_authoring_math_integrity(text)
    assert [issue.code for issue in issues] == ["RAW_MATH_IN_AUTHORING_TEXT"]
    assert "\\Gamma" in issues[0].message


def test_authoring_integrity_accepts_explicit_math_regions():
    text = (
        r"The boundary $\Gamma$ is explicit; "
        r"the gradient \(\nabla u\) is inline; "
        r"and \[\int_\Omega f\,d\Omega\] is displayed."
    )
    assert audit_authoring_math_integrity(text) == ()


def test_validate_authoring_text_rejects_raw_math_before_semantic_assembly():
    with pytest.raises(DocumentAssemblyError, match="semantic math integrity"):
        validate_authoring_text(
            r"Boundary \Gamma is prescribed.",
            equation_ids=set(),
            source_ids=set(),
            target_ids=set(),
        )


def test_assemble_section_rejects_raw_math_even_when_validation_helper_is_bypassed():
    with pytest.raises(DocumentAssemblyError, match="semantic math integrity"):
        assemble_section(
            section_id="00000000-0000-4000-8000-000000000001",
            title="Boundary Conditions",
            authoring_text=r"Boundary \Gamma is prescribed.",
            equation_ids=set(),
            source_ids=set(),
            target_ids=set(),
            parse_legacy_math=True,
        )


def test_section_collection_preflight_rejects_invalid_content_before_persistence():
    with pytest.raises(AuthoringIntegrityError, match=r"\\Gamma"):
        assert_section_records_math_integrity(
            [
                {
                    "section_id": "00000000-0000-4000-8000-000000000002",
                    "title": "Material Properties",
                    "content": r"A surface \Gamma appears outside math.",
                }
            ]
        )


class _SequenceProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.messages = []

    def budget_exhausted(self):
        return False

    def chat(self, messages, temperature, max_tokens, model=None):
        self.messages.append(messages)
        response = self.responses[self.calls]
        self.calls += 1
        return response, None


class _History:
    def record_clean_audit(self, section):
        pass

    def record_failed_audit(self, section):
        pass


class _Indicator:
    def compute(self, section, history):
        return 0.9


def test_dynamic_writer_retries_when_llm_emits_raw_math(monkeypatch):
    invalid = (
        r"The material boundary \Gamma represents an interface in the model and "
        "must be described consistently with constitutive assumptions so that the "
        "finite element approximation preserves the intended physical constraints "
        "throughout the numerical solution process without introducing ambiguity."
    )
    valid = (
        r"The material boundary $\Gamma$ represents an interface in the model and "
        "must be described consistently with constitutive assumptions so that the "
        "finite element approximation preserves the intended physical constraints "
        "throughout the numerical solution process without introducing ambiguity."
    )
    provider = _SequenceProvider([invalid, valid])
    writer = DynamicWriter(
        provider,
        parser=SimpleNamespace(),
        config={
            "writing": {"max_retries_per_paragraph": 2},
            "cloudflare_models": ["test-model"],
        },
        iteration_history=_History(),
        writing_indicator=_Indicator(),
    )
    monkeypatch.setattr(writer, "_generate_outline", lambda topic, kb, model: ["material interface"])
    monkeypatch.setattr(writer, "_get_relevant_concepts", lambda topic, kb: [])
    monkeypatch.setattr("writing.dynamic_writer.time.sleep", lambda _: None)

    errors = []
    section = writer.write_section(
        "Material Properties",
        kb={},
        errors=errors,
        document_map=[],
    )

    assert provider.calls == 2
    assert len(writer.authoring_integrity_rejections) == 1
    assert writer.authoring_integrity_rejections[0]["codes"] == ["RAW_MATH_IN_AUTHORING_TEXT"]
    assert writer.authoring_integrity_rejections[0]["section"] == "Material Properties"
    assert section is not None
    assert r"$\Gamma$" in section["content"]
    assert r" \Gamma " not in section["content"].replace(r"$\Gamma$", "")
    assert errors == []
    prompt = provider.messages[0][-1]["content"]
    assert "Every LaTeX mathematical command" in prompt
    assert "MUST be inside an explicit $...$ math region" in prompt
