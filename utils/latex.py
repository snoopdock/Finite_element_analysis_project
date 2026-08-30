#!/usr/bin/env python3
"""LaTeX utilities for math fixing and text escaping."""

import re
from typing import Optional

# Comprehensive map of Unicode math symbols to LaTeX commands
UNICODE_MATH_MAP = {
    # Integrals, Sums, Products
    '∫': r'\int', '∬': r'\iint', '∭': r'\iiint', '∮': r'\oint',
    '∑': r'\sum', '∏': r'\prod',
    # Operators and Relations
    '√': r'\sqrt', '∛': r'\sqrt[3]', '∜': r'\sqrt[4]',
    '∞': r'\infty', '∂': r'\partial', '∇': r'\nabla',
    '±': r'\pm', '∓': r'\mp', '×': r'\times', '÷': r'\div',
    '≠': r'\neq', '≈': r'\approx', '≡': r'\equiv',
    '≤': r'\le', '≥': r'\ge', '≪': r'\ll', '≫': r'\gg',
    # Sets and Logic
    '∈': r'\in', '∉': r'\notin', '⊂': r'\subset', '⊃': r'\supset',
    '⊆': r'\subseteq', '⊇': r'\supseteq', '∪': r'\cup', '∩': r'\cap', '∅': r'\emptyset',
    '∀': r'\forall', '∃': r'\exists', '¬': r'\neg', '∧': r'\land', '∨': r'\lor',
    # Arrows
    '→': r'\rightarrow', '←': r'\leftarrow', '↔': r'\leftrightarrow', '↑': r'\uparrow', '↓': r'\downarrow',
    '⇒': r'\Rightarrow', '⇐': r'\Leftarrow', '⇔': r'\Leftrightarrow', '⇑': r'\Uparrow', '⇓': r'\Downarrow',
    # Greek Lowercase
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\epsilon',
    'ζ': r'\zeta', 'η': r'\eta', 'θ': r'\theta', 'ι': r'\iota', 'κ': r'\kappa',
    'λ': r'\lambda', 'μ': r'\mu', 'ν': r'\nu', 'ξ': r'\xi', 'π': r'\pi',
    'ρ': r'\rho', 'σ': r'\sigma', 'τ': r'\tau', 'υ': r'\upsilon', 'φ': r'\phi',
    'χ': r'\chi', 'ψ': r'\psi', 'ω': r'\omega',
    # Greek Uppercase
    'Γ': r'\Gamma', 'Δ': r'\Delta', 'Θ': r'\Theta', 'Λ': r'\Lambda',
    'Ξ': r'\Xi', 'Π': r'\Pi', 'Σ': r'\Sigma', 'Φ': r'\Phi', 'Ψ': r'\Psi', 'Ω': r'\Omega',
    # Superscripts and Subscripts
    '⁰': r'^0', '¹': r'^1', '²': r'^2', '³': r'^3', '⁴': r'^4', '⁵': r'^5',
    '₀': r'_0', '₁': r'_1', '₂': r'_2', '₃': r'_3', '₄': r'_4', '₅': r'_5',
}

def fix_latex_math(text: str) -> str:
    """
    Converts raw Unicode math symbols to LaTeX commands and fixes deprecated display math.
    """
    if not text:
        return text
        
    # 1. Replace Unicode math symbols with spaced LaTeX commands
    # Spacing prevents "\intV" errors (e.g. "∫V" -> " \int V ")
    for uni, latex in UNICODE_MATH_MAP.items():
        if uni in text:
            text = text.replace(uni, f" {latex} ")
            
    # 2. Collapse multiple spaces created by replacements
    text = re.sub(r' +', ' ', text)
    
    # 3. Convert deprecated $$...$$ display math to \[...\]
    text = re.sub(r'\$\$(.*?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)
    
    # 4. Clean up spacing around math delimiters
    text = text.replace(" $ ", "$")
    text = text.replace(" \\[ ", "\\[")
    text = text.replace(" \\] ", "\\]")
    
    return text.strip()

def escape_latex(text: str) -> str:
    """
    Escapes special LaTeX characters in simple text (like titles).
    Preserves existing backslashes used for commands.
    """
    if not text:
        return ""
    # Only escape characters that break text mode
    chars = {
        '#': r'\#',
        '%': r'\%',
        '&': r'\&',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    for char, escaped in chars.items():
        text = text.replace(char, escaped)
    return text

def sanitize_latex_content(text: str) -> str:
    """
    Sanitizes LLM-generated prose for safe LaTeX inclusion.
    1. Fixes Unicode math and deprecated $$ math.
    2. Escapes stray % and & which crash compilers.
    """
    if not text:
        return ""
        
    # Step 1: Fix the math
    text = fix_latex_math(text)
    
    # Step 2: Escape % and & outside of math mode
    # Regex uses negative lookbehind (?<!\\) to avoid double-escaping already escaped chars
    text = re.sub(r'(?<!\\)%', r'\%', text)
    text = re.sub(r'(?<!\\)&', r'\&', text)
    
    # Step 3: Fix common LLM markdown artifacts
    text = text.replace('```latex', '')
    text = text.replace('```', '')
    
    return text.strip()

def balanced_braces(text: str) -> str:
    """Ensures braces are balanced."""
    if not text: return text
    open_count = text.count('{')
    close_count = text.count('}')
    if open_count > close_count:
        text += '}' * (open_count - close_count)
    elif close_count > open_count:
        text = '{' * (close_count - open_count) + text
    return text

# Alias for backward compatibility with test_pure_functions.py
check_balanced_braces = balanced_braces
