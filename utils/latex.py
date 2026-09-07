#!/usr/bin/env python3
"""LaTeX utilities for math fixing and text escaping."""

import re
from typing import Optional

UNICODE_MATH_MAP = {
    '∫': r'\int', '∬': r'\iint', '∭': r'\iiint', '∮': r'\oint',
    '∑': r'\sum', '∏': r'\prod', '√': r'\sqrt', '∛': r'\sqrt[3]',
    '∜': r'\sqrt[4]', '∞': r'\infty', '∂': r'\partial', '∇': r'\nabla',
    '±': r'\pm', '∓': r'\mp', '×': r'\times', '÷': r'\div',
    '≠': r'\neq', '≈': r'\approx', '≡': r'\equiv', '≤': r'\le', '≥': r'\ge',
    '≪': r'\ll', '≫': r'\gg', '∈': r'\in', '∉': r'\notin', '⊂': r'\subset',
    '⊃': r'\supset', '⊆': r'\subseteq', '⊇': r'\supseteq', '∪': r'\cup',
    '∩': r'\cap', '∅': r'\emptyset', '∀': r'\forall', '∃': r'\exists',
    '¬': r'\neg', '∧': r'\land', '∨': r'\lor', '→': r'\rightarrow',
    '←': r'\leftarrow', '↔': r'\leftrightarrow', '↑': r'\uparrow', '↓': r'\downarrow',
    '⇒': r'\Rightarrow', '⇐': r'\Leftarrow', '⇔': r'\Leftrightarrow',
    '⇑': r'\Uparrow', '⇓': r'\Downarrow', 'α': r'\alpha', 'β': r'\beta',
    'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\epsilon', 'ζ': r'\zeta',
    'η': r'\eta', 'θ': r'\theta', 'ι': r'\iota', 'κ': r'\kappa',
    'λ': r'\lambda', 'μ': r'\mu', 'ν': r'\nu', 'ξ': r'\xi', 'π': r'\pi',
    'ρ': r'\rho', 'σ': r'\sigma', 'τ': r'\tau', 'υ': r'\upsilon',
    'φ': r'\phi', 'χ': r'\chi', 'ψ': r'\psi', 'ω': r'\omega',
    'Γ': r'\Gamma', 'Δ': r'\Delta', 'Θ': r'\Theta', 'Λ': r'\Lambda',
    'Ξ': r'\Xi', 'Π': r'\Pi', 'Σ': r'\Sigma', 'Φ': r'\Phi', 'Ψ': r'\Psi',
    'Ω': r'\Omega', '⁰': r'^0', '¹': r'^1', '²': r'^2', '³': r'^3',
    '⁴': r'^4', '⁵': r'^5', '₀': r'_0', '₁': r'_1', '₂': r'_2',
    '₃': r'_3', '₄': r'_4', '₅': r'_5',
}


def fix_latex_math(text: str) -> str:
    if not text:
        return text
    for uni, latex in UNICODE_MATH_MAP.items():
        text = text.replace(uni, f" {latex} ")
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\$\$(.*?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)
    text = text.replace(" $ ", "$").replace(" \\[ ", "\\[").replace(" \\] ", "\\]")
    return text.strip()


def escape_text(text: str) -> str:
    """Escape plain text without interpreting it as pre-authored LaTeX."""
    if not text:
        return ""
    replacements = {
        '\\': r'\textbackslash{}',
        '#': r'\#', '%': r'\%', '&': r'\&',
        '_': r'\_', '{': r'\{', '}': r'\}',
        '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
    }
    return ''.join(replacements.get(char, char) for char in text)


def escape_latex(text: str) -> str:
    """Escape simple LaTeX text while preserving existing commands."""
    if not text:
        return ""
    chars = {'#': r'\#', '%': r'\%', '&': r'\&', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    for char, escaped in chars.items():
        text = text.replace(char, escaped)
    return text


def sanitize_latex_content(text: str) -> str:
    if not text:
        return ""
    text = fix_latex_math(text)
    text = re.sub(r'(?<!\\)%', r'\%', text)
    text = re.sub(r'(?<!\\)&', r'\&', text)
    return text.replace('```latex', '').replace('```', '').strip()


def balanced_braces(text: str) -> str:
    if not text:
        return text
    open_count = text.count('{')
    close_count = text.count('}')
    if open_count > close_count:
        text += '}' * (open_count - close_count)
    elif close_count > open_count:
        text = '{' * (close_count - open_count) + text
    return text


check_balanced_braces = balanced_braces
