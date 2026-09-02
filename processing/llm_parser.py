#!/usr/bin/env python3
"""
LLM JSON Parser - Robust parsing cascade for flaky LLM outputs.
"""

import ast
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


class LLMJSONParseError(Exception):
    """Raised when all parsing strategies fail."""

    def __init__(self, message: str, text: str = "", errors: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.text = text
        self.errors = errors or []


class UniversalLLMJSONParser:
    """Robust parser for common LLM JSON formatting failures."""

    def __init__(
        self,
        enable_repair: bool = False,
        repair_provider=None,
        verbose: bool = False,
    ):
        self.enable_repair = enable_repair
        self.repair_provider = repair_provider
        self.verbose = verbose
        self.stats = {}

    def _log(self, message: str):
        if self.verbose:
            print(f"  [Parser] {message}", file=sys.stderr)

    def _sanitize(self, text: str) -> str:
        """Clean raw LLM output before parsing."""
        if not text or not isinstance(text, str):
            return ""

        text = text.strip()
        text = re.sub(r'```(?:json|JSON)?\s*', '', text, flags=re.IGNORECASE)
        text = self._strip_json_comments(text)

        preamble_patterns = [
            r'^(?:Here is|Here\'s|Below is|The following is|JSON output:?)\s*',
            r'^(?:Sure|Of course|Certainly)[,!]?\s*',
            r'^I\'ve generated the (?:following )?JSON[:\s]*',
        ]
        for pattern in preamble_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        text = re.sub(
            r'\n(?:Let me know|Hope this helps|Is there anything else|Feel free to ask).*$',
            '',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return text.strip()

    def _strip_json_comments(self, text: str) -> str:
        """Remove JSON comments while preserving quoted strings."""
        result = []
        i = 0
        in_string = False
        string_char = None
        escape_next = False

        while i < len(text):
            char = text[i]

            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                i += 1
                continue

            if char in ('"', "'"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                result.append(char)
                i += 1
                continue

            if in_string:
                result.append(char)
                i += 1
                continue

            if char == '/' and i + 1 < len(text) and text[i + 1] == '/':
                while i < len(text) and text[i] != '\n':
                    i += 1
                continue

            if char == '/' and i + 1 < len(text) and text[i + 1] == '*':
                i += 2
                while i + 1 < len(text) and not (text[i] == '*' and text[i + 1] == '/'):
                    i += 1
                i += 2
                continue

            result.append(char)
            i += 1

        return ''.join(result)

    def _normalize_quotes(self, text: str) -> str:
        """Convert single-quoted strings to double-quoted strings."""
        result = []
        in_string = False
        string_char = None
        escape_next = False

        for char in text:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            if char in ('"', "'"):
                if not in_string:
                    in_string = True
                    string_char = char
                    result.append('"')
                elif char == string_char:
                    in_string = False
                    string_char = None
                    result.append('"')
                else:
                    result.append(char)
            else:
                result.append(char)

        return ''.join(result)

    def _escape_latex_backslashes_for_json(self, text: str) -> str:
        """Escape LaTeX backslashes occurring inside JSON strings.

        Strict JSON already uses doubled backslashes. This helper is only for
        the normalized/single-quoted fallback, where LLMs often emit LaTeX as
        `\\partial`, `\\theta`, etc. without JSON escaping. It preserves real
        JSON escapes and valid Unicode escapes.
        """
        result = []
        in_string = False
        i = 0

        while i < len(text):
            char = text[i]

            if not in_string:
                result.append(char)
                if char == '"':
                    in_string = True
                i += 1
                continue

            if char == '"':
                result.append(char)
                in_string = False
                i += 1
                continue

            if char != '\\':
                result.append(char)
                i += 1
                continue

            if i + 1 >= len(text):
                result.append('\\\\')
                i += 1
                continue

            nxt = text[i + 1]

            if nxt == 'u' and i + 5 < len(text) and re.fullmatch(r'[0-9A-Fa-f]{4}', text[i + 2:i + 6]):
                result.append(text[i:i + 6])
                i += 6
                continue

            if nxt in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't'):
                # A JSON escape followed by an alphabetic character is very
                # likely a LaTeX command such as \\theta or \\text.
                if nxt.isalpha() and i + 2 < len(text) and text[i + 2].isalpha():
                    result.append('\\\\')
                    i += 1
                    continue
                result.append('\\' + nxt)
                i += 2
                continue

            # Any other backslash sequence is invalid JSON unless escaped.
            result.append('\\\\')
            i += 1

        return ''.join(result)

    def _find_json_boundaries(self, text: str) -> Optional[Tuple[int, int]]:
        """Find outermost balanced JSON object or array."""
        for open_char, close_char in [('{', '}'), ('[', ']')]:
            start = text.find(open_char)
            if start == -1:
                continue

            depth = 0
            in_string = False
            escape_next = False

            for i in range(start, len(text)):
                char = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == open_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1
                    if depth == 0:
                        return start, i + 1

        return None

    def _detect_truncation(self, text: str) -> bool:
        """Detect likely truncation of JSON output."""
        if not text:
            return False

        if self._find_json_boundaries(text):
            return False

        open_count = text.count('{') + text.count('[')
        close_count = text.count('}') + text.count(']')
        if open_count > close_count:
            return True

        stripped = text.rstrip()
        if stripped and stripped[-1] not in ('}', ']', '"', 'e', 'l', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.'):
            return True
        return False

    def _attempt_truncation_repair(self, text: str) -> Optional[str]:
        """Attempt to close unbalanced JSON brackets."""
        if not text:
            return None

        stack = []
        in_string = False
        escape_next = False

        for char in text:
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char in ('{', '['):
                stack.append(char)
            elif char == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif char == ']' and stack and stack[-1] == '[':
                stack.pop()

        if in_string:
            text += '"'

        while stack:
            bracket = stack.pop()
            text += '}' if bracket == '{' else ']'

        return text

    def _try_strict_json(self, text: str) -> Optional[Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _try_normalized_json(self, text: str) -> Optional[Any]:
        try:
            normalized = self._normalize_quotes(text)
            normalized = self._escape_latex_backslashes_for_json(normalized)
            return json.loads(normalized)
        except json.JSONDecodeError:
            return None

    def _try_python_literal(self, text: str) -> Optional[Any]:
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None

    def _try_candidate_extraction(self, text: str) -> Optional[Any]:
        candidates = []
        for pattern in [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
            r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]',
        ]:
            for match in re.finditer(pattern, text, re.DOTALL):
                candidate = match.group(0)
                if len(candidate) > 10:
                    candidates.append(candidate)

        candidates.sort(key=len, reverse=True)
        for candidate in candidates[:5]:
            for strategy in [
                self._try_strict_json,
                self._try_normalized_json,
                self._try_python_literal,
            ]:
                result = strategy(candidate)
                if result is not None:
                    return result
        return None

    def _try_jsonl(self, text: str) -> Optional[List[Any]]:
        """Try to parse JSON Lines format."""
        results = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            for strategy in [self._try_strict_json, self._try_normalized_json]:
                result = strategy(line)
                if result is not None:
                    results.append(result)
                    break
        return results if len(results) >= 2 else None

    def _repair_with_llm(self, text: str, error_message: str = "") -> Optional[Any]:
        """Use an LLM to repair malformed JSON as a last resort."""
        if not self.enable_repair or not self.repair_provider:
            return None

        error_context = ""
        if error_message:
            error_context = (
                f"\n\nThe specific parsing error was: {error_message}\n"
                "Please fix this specific issue."
            )

        repair_system = """You are a JSON repair specialist.
Fix the malformed JSON and return ONLY valid JSON.
Common fixes:
- Replace single quotes with double quotes
- Add missing quotes around keys
- Remove trailing commas
- Close unclosed brackets
- Remove comments and markdown
Return ONLY the fixed JSON. No explanation."""

        messages = [
            {"role": "system", "content": repair_system},
            {"role": "user", "content": f"Fix this JSON:{error_context}\n\n{text[:4000]}"},
        ]

        try:
            repaired_text, error = self.repair_provider.chat(
                messages,
                temperature=0.0,
                max_tokens=2000,
            )
            if error:
                self._log(f"LLM repair failed: {error}")
                return None
            return self._try_strict_json(repaired_text)
        except Exception as exc:
            self._log(f"LLM repair exception: {exc}")
            return None

    def _validate_schema(self, data: Any, schema: Dict) -> Tuple[bool, List[str]]:
        """Validate parsed data against expected schema."""
        errors = []
        if not isinstance(data, dict):
            return False, [f"Expected dict, got {type(data).__name__}"]

        for key, expected_type in schema.items():
            if key not in data:
                errors.append(f"Missing required key: '{key}'")
                continue
            actual_value = data[key]
            actual_type = type(actual_value).__name__

            if isinstance(expected_type, dict):
                if not isinstance(actual_value, dict):
                    errors.append(f"Key '{key}' should be dict, got {actual_type}")
                else:
                    ok, nested = self._validate_schema(actual_value, expected_type)
                    if not ok:
                        errors.extend(f"{key}.{item}" for item in nested)
                continue

            if isinstance(expected_type, list) and len(expected_type) == 1 and isinstance(expected_type[0], dict):
                if not isinstance(actual_value, list):
                    errors.append(f"Key '{key}' should be list, got {actual_type}")
                else:
                    for i, item in enumerate(actual_value):
                        if not isinstance(item, dict):
                            errors.append(f"Key '{key}[{i}]' should be dict, got {type(item).__name__}")
                        else:
                            ok, nested = self._validate_schema(item, expected_type[0])
                            if not ok:
                                errors.extend(f"{key}[{i}].{err}" for err in nested)
                continue

            if expected_type == list and not isinstance(actual_value, list):
                errors.append(f"Key '{key}' should be list, got {actual_type}")
            elif expected_type == dict and not isinstance(actual_value, dict):
                errors.append(f"Key '{key}' should be dict, got {actual_type}")
            elif expected_type == str and not isinstance(actual_value, str):
                errors.append(f"Key '{key}' should be string, got {actual_type}")
            elif expected_type == int and not isinstance(actual_value, int):
                errors.append(f"Key '{key}' should be int, got {actual_type}")
            elif expected_type == float and not isinstance(actual_value, (int, float)):
                errors.append(f"Key '{key}' should be number, got {actual_type}")

        return not errors, errors

    def parse(
        self,
        text: str,
        schema: Optional[Dict] = None,
        model_name: str = "unknown",
    ) -> Any:
        """Parse LLM output into a Python object."""
        errors = []

        if not text:
            raise LLMJSONParseError("Empty input", text="")
        if not isinstance(text, str):
            raise LLMJSONParseError(
                f"Expected string, got {type(text).__name__}",
                text=str(text)[:200],
            )

        sanitized = self._sanitize(text)
        self._log(f"Sanitized (length: {len(sanitized)})")

        if self._detect_truncation(sanitized):
            self._log("Detected truncated JSON, attempting repair...")
            repaired = self._attempt_truncation_repair(sanitized)
            if repaired:
                sanitized = repaired
                self._log("Truncation repair applied")

        boundaries = self._find_json_boundaries(sanitized)
        if boundaries:
            start, end = boundaries
            candidate = sanitized[start:end]
            self._log(f"Found boundaries: {start}-{end}")
        else:
            candidate = sanitized
            self._log("No clear boundaries found, using full text")

        strategies = [
            ("strict", self._try_strict_json),
            ("normalized", self._try_normalized_json),
            ("python_literal", self._try_python_literal),
            ("candidate_extraction", self._try_candidate_extraction),
        ]

        last_error = None
        for strategy_name, strategy_func in strategies:
            try:
                result = strategy_func(candidate)
                if result is None:
                    continue

                self._log(f"Success with strategy: {strategy_name}")
                key = f"{model_name}:{strategy_name}"
                self.stats[key] = self.stats.get(key, 0) + 1

                if schema:
                    ok, schema_errors = self._validate_schema(result, schema)
                    if not ok:
                        errors.append(f"Schema validation failed: {schema_errors}")
                        continue

                return result
            except json.JSONDecodeError as exc:
                last_error = str(exc)
                errors.append(f"{strategy_name}: {exc}")
            except Exception as exc:
                errors.append(f"{strategy_name}: {exc}")

        jsonl_result = self._try_jsonl(candidate)
        if jsonl_result is not None:
            self._log(f"Success with JSONL parsing ({len(jsonl_result)} objects)")
            key = f"{model_name}:jsonl"
            self.stats[key] = self.stats.get(key, 0) + 1
            return jsonl_result

        if self.enable_repair:
            self._log("Trying LLM repair with error feedback...")
            repaired = self._repair_with_llm(candidate, error_message=last_error or "")
            if repaired is not None:
                self.stats[f"{model_name}:llm_repair"] = self.stats.get(f"{model_name}:llm_repair", 0) + 1
                return repaired

        raise LLMJSONParseError(
            "All parsing strategies failed",
            text=candidate[:500],
            errors=errors,
        )

    def get_stats(self) -> Dict[str, int]:
        return dict(self.stats)


def parse_llm_json(
    text: str,
    schema: Optional[Dict] = None,
    enable_repair: bool = False,
    repair_provider=None,
    verbose: bool = False,
) -> Any:
    """Convenience function to parse LLM JSON output."""
    parser = UniversalLLMJSONParser(
        enable_repair=enable_repair,
        repair_provider=repair_provider,
        verbose=verbose,
    )
    return parser.parse(text, schema=schema)
