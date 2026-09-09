"""Diagnostic probe for the LaTeX escaping boundary.

This script intentionally reports behavior rather than deciding whether the
behavior is correct. The audit decision is made from the workflow log.
"""

from utils.latex import escape_latex, escape_text, fix_latex_math, sanitize_latex_content


CASES = [
    "plain text",
    r"A & B # C % D _ E { F } G ~ H ^ I",
    r"already \\textbf{bold} and \\alpha",
    r"100% & 50%",
    r"URL https://example.com/a&b#section?x=1%2F2",
    r"$x^2 + y_1$",
    "α + β → γ",
    r"A \\% already escaped",
    r"A \\& already escaped",
    r"{unbalanced",
    r"unbalanced}",
]


def show(label, function, value):
    try:
        result = function(value)
        print(f"[{label}] INPUT : {value!r}")
        print(f"[{label}] OUTPUT: {result!r}")
    except Exception as exc:
        print(f"[{label}] ERROR : {type(exc).__name__}: {exc}")


def main():
    print("=== LATEX ESCAPING CONTRACT AUDIT ===")
    print("Diagnostic only: outputs are evidence, not pass/fail judgments.")
    print()

    for case in CASES:
        print(f"--- CASE {case!r} ---")
        show("escape_text", escape_text, case)
        show("escape_latex", escape_latex, case)
        show("sanitize_latex_content", sanitize_latex_content, case)
        show("fix_latex_math", fix_latex_math, case)
        print()

    print("=== DIRECT COMPARISON ===")
    value = r"A & B % C _ D { E } ~ F ^ G \\command{x}"
    print(f"INPUT: {value!r}")
    print(f"escape_text:            {escape_text(value)!r}")
    print(f"escape_latex:           {escape_latex(value)!r}")
    print(f"sanitize_latex_content: {sanitize_latex_content(value)!r}")


if __name__ == "__main__":
    main()
