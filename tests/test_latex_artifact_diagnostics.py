from processing.latex_artifact_diagnostics import analyze_latex_text


def test_unresolved_reference_detection():
    issues = analyze_latex_text(
        r"See \ref{MISSING_REF}"
    )

    assert len(issues) == 1
    assert issues[0].category == "unresolved_reference"


def test_environment_balance_detection():
    issues = analyze_latex_text(
        r"\begin{figure}"
    )

    assert len(issues) == 1
    assert issues[0].category == "environment_balance"


def test_clean_latex_has_no_issues():
    issues = analyze_latex_text(
        r"\section{Introduction}"
    )

    assert issues == []
