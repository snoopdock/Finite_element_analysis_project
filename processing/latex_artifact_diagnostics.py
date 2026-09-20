from .artifact_issue import ArtifactIssue


def analyze_latex_text(latex_text: str):
    issues = []

    if "\\ref{" in latex_text and "MISSING_REF" in latex_text:
        issues.append(
            ArtifactIssue(
                category="unresolved_reference",
                severity="error",
                message="Potential unresolved reference detected"
            )
        )

    if latex_text.count("\\begin{") != latex_text.count("\\end{"):
        issues.append(
            ArtifactIssue(
                category="environment_balance",
                severity="error",
                message="Possible unbalanced LaTeX environments"
            )
        )

    return issues
