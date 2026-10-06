"""Continuation-run regressions for Package 5.4.2 citation syntax closure."""

from core.citation_syntax import (
    iter_raw_citation_groups,
    normalize_parenthesized_known_citations,
)


def _groups(text: str, **kwargs):
    return list(iter_raw_citation_groups(text, **kwargs))


def test_final_tex_gate_does_not_treat_fe_trial_test_symbols_as_citations():
    assert _groups(r"a(u_h, v_h) = l(v_h)", latex_escaped=True) == []


def test_final_tex_gate_does_not_treat_single_fe_symbol_as_citation():
    assert _groups(r"V_h and (v_h) remain mathematical notation", latex_escaped=True) == []


def test_final_tex_gate_still_detects_explicit_namespaced_raw_source_id():
    groups = _groups(r"Claim (wiki_c_a_s_lemma).", latex_escaped=True)
    assert len(groups) == 1
    assert groups[0].source_ids == ("wiki_c_a_s_lemma",)


def test_final_tex_gate_still_detects_explicit_namespaced_source_group():
    groups = _groups(r"Claim (wiki_alpha, doi:10.1000/test).", latex_escaped=True)
    assert len(groups) == 1
    assert groups[0].source_ids == ("wiki_alpha", "doi:10.1000/test")


def test_registry_gate_still_detects_custom_source_ids():
    groups = _groups("Claim (s1).", known_source_ids={"s1"})
    assert len(groups) == 1
    assert groups[0].registry_related is True


def test_registry_normalization_still_promotes_exact_custom_source_id():
    text, diagnostics = normalize_parenthesized_known_citations(
        "Claim (s1).", known_source_ids={"s1"}
    )
    assert text == "Claim [s1]."
    assert diagnostics == ("parenthesized_citation_normalized:s1",)
