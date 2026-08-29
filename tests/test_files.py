from __future__ import annotations

from pathlib import Path

from ghostwriter.files import (
    MAX_PREVIEW_BYTES,
    build_file_index,
    existing_paths,
    find_file_completions,
    read_text_preview,
)


def test_existing_paths_accepts_unescaped_path_with_spaces(tmp_path: Path) -> None:
    source = tmp_path / "notes with spaces.md"
    source.write_text("notes", encoding="utf-8")

    assert existing_paths(str(source)) == [source]


def test_text_preview_returns_raw_source(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")

    assert read_text_preview(source) == "def answer():\n    return 42\n"


def test_text_preview_rejects_binary_and_truncates_large_files(tmp_path: Path) -> None:
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"hello\0world")
    assert read_text_preview(binary) is None

    large = tmp_path / "large.md"
    large.write_bytes(b"x" * (MAX_PREVIEW_BYTES + 1))
    assert read_text_preview(large).endswith("[Preview truncated]")


def test_file_completions_search_project_and_absolute_paths(tmp_path: Path) -> None:
    source = tmp_path / "src" / "candidate_prompt.md"
    source.parent.mkdir()
    source.write_text("prompt", encoding="utf-8")
    index = build_file_index(tmp_path)

    project_matches = find_file_completions(tmp_path, "candidate", index)
    absolute_matches = find_file_completions(
        tmp_path,
        f"{source.parent}/cand",
        index,
    )

    assert project_matches[0].path == source
    assert project_matches[0].label == "src/candidate_prompt.md"
    assert absolute_matches[0].path == source
