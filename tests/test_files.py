from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ghostwriter.files import (
    MAX_PREVIEW_BYTES,
    FileCompletion,
    build_file_index,
    existing_paths,
    find_file_completions,
    read_text_preview,
)


def test_existing_paths_accepts_unescaped_path_with_spaces(tmp_path: Path) -> None:
    source = tmp_path / "notes with spaces.md"
    source.write_text("notes", encoding="utf-8")

    assert existing_paths(str(source)) == [source]


def test_existing_paths_accepts_directories(tmp_path: Path) -> None:
    source = tmp_path / "reference notes"
    source.mkdir()

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


def test_python_index_fallback_skips_hidden_and_generated_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visible = tmp_path / "src" / "visible.py"
    hidden = tmp_path / ".config" / "settings.json"
    cached = tmp_path / "__pycache__" / "module.pyc"
    for path in (visible, hidden, cached):
        path.parent.mkdir(exist_ok=True)
        path.write_text("data", encoding="utf-8")
    monkeypatch.setattr("ghostwriter.files.shutil.which", lambda _name: None)

    assert build_file_index(tmp_path) == ["src/", "src/visible.py"]


def test_index_includes_directories_and_git_local_excludes(tmp_path: Path) -> None:
    excluded_directory = tmp_path / "local-context"
    excluded_directory.mkdir()
    excluded_file = excluded_directory / "notes.md"
    excluded_file.write_text("local", encoding="utf-8")
    info = tmp_path / ".git" / "info"
    info.mkdir(parents=True)
    (info / "exclude").write_text("local-context/\n", encoding="utf-8")

    index = build_file_index(tmp_path)

    assert "local-context/" in index
    assert "local-context/notes.md" in index


def test_fd_index_requests_directories_and_bypasses_vcs_excludes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ghostwriter.files.shutil.which", lambda _name: "/bin/fd")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "--type=file" in command
        assert "--type=directory" in command
        assert "--no-ignore-vcs" in command
        return subprocess.CompletedProcess(command, 0, b"src/\0src/app.py\0", b"")

    monkeypatch.setattr("ghostwriter.files.subprocess.run", fake_run)

    assert build_file_index(tmp_path) == ["src/", "src/app.py"]


def test_fzf_ranks_non_contiguous_path_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / "ghostwriter" / "app.py"
    source.parent.mkdir(parents=True)
    source.touch()

    monkeypatch.setattr("ghostwriter.files.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "--filter=gapp" in command
        assert kwargs["input"] == b"src/ghostwriter/app.py\0"
        return subprocess.CompletedProcess(command, 0, b"src/ghostwriter/app.py\0", b"")

    monkeypatch.setattr("ghostwriter.files.subprocess.run", fake_run)

    matches = find_file_completions(tmp_path, "gapp", ["src/ghostwriter/app.py"])

    assert matches == [FileCompletion(source, "src/ghostwriter/app.py")]


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


def test_file_completions_return_project_directories(tmp_path: Path) -> None:
    directory = tmp_path / "reference-notes"
    directory.mkdir()
    index = build_file_index(tmp_path)

    matches = find_file_completions(tmp_path, "reference", index)

    assert matches[0] == FileCompletion(directory, "reference-notes/", is_directory=True)
