import pytest
import sys
import os

# Add parent directory to path so we can import pipeline modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.latex import escape_latex, check_balanced_braces
from writing.dynamic_writer import calculate_word_overlap, _strip_bad_citations

class TestLatexUtils:
    def test_escape_special_chars(self):
        assert escape_latex("100%") == "100\\%"
        assert escape_latex("a_b") == "a\\_b"
        assert escape_latex("$10") == "\\$10"

    def test_balanced_braces(self):
        assert check_balanced_braces("\\textbf{hello}") is True
        assert check_balanced_braces("\\textbf{hello") is False
        assert check_balanced_braces("hello}") is False
        assert check_balanced_braces("\\{escaped\\}") is True

class TestDynamicWriterUtils:
    def test_word_overlap_identical(self):
        assert calculate_word_overlap("the quick brown fox", "the quick brown fox") == 1.0

    def test_word_overlap_disjoint(self):
        assert calculate_word_overlap("hello world", "goodbye universe") == 0.0

    def test_strip_bad_citations_preserves_math(self):
        allowed = {"arxiv_123"}
        text = "This is true [arxiv_123] but fake [fake_ref] and math \\[ x = y \\]."
        res = _strip_bad_citations(text, allowed)
        assert "[arxiv_123]" in res
        assert "[fake_ref]" not in res
        assert "\\[ x = y \\]" in res  # Crucial: math must survive

    def test_strip_bad_citations_removes_hallucinations(self):
        allowed = set()
        text = "According to [Smith2020] and [arxiv_9999], this is true."
        res = _strip_bad_citations(text, allowed)
        assert "[Smith2020]" not in res
        assert "[arxiv_9999]" not in res
