from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_PREVIEW_BYTES = 128 * 1024
MAX_PREVIEW_LINES = 2_000
MAX_INDEXED_FILES = 20_000
SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}


@dataclass(frozen=True, slots=True)
class FileCompletion:
    path: Path
    label: str
    is_directory: bool = False


def looks_like_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def parse_paths(value: str) -> list[Path]:
    value = value.strip()
    if not value:
        return []
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = [value]

    paths: list[Path] = []
    for part in parts:
        if part.startswith("file://"):
            part = unquote(urlparse(part).path)
        paths.append(Path(part).expanduser())
    return paths


def existing_paths(value: str) -> list[Path]:
    paths = parse_paths(value)
    if paths and all(path.is_file() for path in paths):
        return paths

    # Some terminals paste an unescaped path containing spaces.
    whole = value.strip()
    if whole.startswith("file://"):
        whole = unquote(urlparse(whole).path)
    whole_path = Path(whole).expanduser()
    return [whole_path] if whole_path.is_file() else []


def choose_native_paths() -> list[Path]:
    title = "Attach files"
    if sys.platform == "darwin":
        script = f'''
set chosenFiles to choose file with prompt "{title}" with multiple selections allowed
set chosenPaths to {{}}
repeat with chosenFile in chosenFiles
    set end of chosenPaths to POSIX path of chosenFile
end repeat
set AppleScript's text item delimiters to linefeed
return chosenPaths as text
'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            if "-128" in result.stderr or "User canceled" in result.stderr:
                return []
            raise OSError(result.stderr.strip() or "The file picker failed")
        return [Path(line) for line in result.stdout.splitlines() if line]

    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise OSError("No native file picker is available on this system") from error

    try:
        root = tk.Tk()
        root.withdraw()
        try:
            selected = filedialog.askopenfilenames(title=title)
            return [Path(path) for path in selected]
        finally:
            root.destroy()
    except tk.TclError as error:
        raise OSError("The native file picker could not be opened") from error


def build_file_index(root: Path) -> list[Path]:
    files: list[Path] = []
    try:
        for directory, names, filenames in os.walk(root):
            names[:] = sorted(name for name in names if name not in SKIPPED_DIRECTORIES)
            for filename in sorted(filenames):
                files.append(Path(directory) / filename)
                if len(files) >= MAX_INDEXED_FILES:
                    return files
    except OSError:
        return files
    return files


def find_file_completions(
    root: Path,
    query: str,
    indexed_files: list[Path],
    *,
    limit: int = 12,
) -> list[FileCompletion]:
    if query.startswith(("/", "~")):
        expanded = Path(query).expanduser()
        parent = expanded if query.endswith("/") else expanded.parent
        prefix = "" if query.endswith("/") else expanded.name.lower()
        try:
            children = sorted(parent.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError:
            return []
        matches = [child for child in children if child.name.lower().startswith(prefix)]
        return [
            FileCompletion(
                child,
                child.as_posix() + ("/" if child.is_dir() else ""),
                child.is_dir(),
            )
            for child in matches[:limit]
        ]

    needle = query.removeprefix("./").lower()
    ranked: list[tuple[int, str, Path]] = []
    for path in indexed_files:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        name = path.name.lower()
        lowered = relative.lower()
        if name.startswith(needle):
            score = 0
        elif lowered.startswith(needle):
            score = 1
        elif needle in name:
            score = 2
        elif needle in lowered:
            score = 3
        else:
            continue
        ranked.append((score, relative, path))

    ranked.sort(key=lambda item: (item[0], len(item[1]), item[1].lower()))
    return [FileCompletion(path, relative) for _, relative, path in ranked[:limit]]


def read_text_preview(path: Path) -> str | None:
    with path.open("rb") as file:
        data = file.read(MAX_PREVIEW_BYTES + 1)
    if b"\0" in data:
        return None

    truncated = len(data) > MAX_PREVIEW_BYTES
    try:
        text = data[:MAX_PREVIEW_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return None

    lines = text.splitlines(keepends=True)
    if len(lines) > MAX_PREVIEW_LINES:
        text = "".join(lines[:MAX_PREVIEW_LINES])
        truncated = True
    if truncated:
        text = text.rstrip() + "\n\n[Preview truncated]"
    return text
