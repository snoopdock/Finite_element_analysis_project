import json
import pathlib

import tools.run_pipeline_with_document_snapshot as runner


def test_runner_persists_document_after_successful_pipeline(monkeypatch, tmp_path):
    sections = [
        {
            "section_id": "550e8400-e29b-41d4-a716-446655440000",
            "title": "Weak Form",
            "content": "A plain writer paragraph with $u=x^2$ and [source-1].",
            "key_equations": ["u=x^2"],
            "citations_used": ["source-1"],
            "parent_section_ids": [],
        }
    ]
    sections_path = tmp_path / "sections.json"
    document_path = tmp_path / "document.json"
    sections_path.write_text(json.dumps(sections), encoding="utf-8")

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        runner,
        "load_json",
        lambda path, default=None: json.loads(sections_path.read_text(encoding="utf-8"))
        if pathlib.Path(path) == sections_path
        else default,
    )

    original_persist = runner.persist_pipeline_document
    monkeypatch.setattr(
        runner,
        "persist_pipeline_document",
        lambda loaded_sections, path: original_persist(loaded_sections, document_path),
    )

    assert runner.main() == 0

    payload = json.loads(document_path.read_text(encoding="utf-8"))
    assert payload["type"] == "document"
    assert payload["children"][0]["section_id"] == sections[0]["section_id"]
    assert payload["children"][0]["children"][0]["type"] == "paragraph"
    assert payload["children"][0]["children"][0]["inline_content"][0]["text"] == sections[0]["content"]
