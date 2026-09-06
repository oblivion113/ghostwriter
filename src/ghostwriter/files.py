from __future__ import annotations

import heapq
import os
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .system_search import search_system_file_index

IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_PREVIEW_BYTES = 128 * 1024
MAX_PREVIEW_LINES = 2_000
MAX_INDEXED_FILES = 20_000
MAX_SYSTEM_CANDIDATES = 20_000
SYSTEM_SEARCH_MIN_CHARACTERS = 3
DEFAULT_SKIPPED_DIRECTORIES = (
    ".bun",
    ".cache",
    ".git",
    ".gradle",
    ".mypy_cache",
    ".next",
    ".nox",
    ".parcel-cache",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".swiftpm",
    ".tox",
    ".turbo",
    ".venv",
    ".yarn",
    "__pycache__",
    "bower_components",
    "build",
    "coverage",
    "DerivedData",
    "dist",
    "node_modules",
    "Pods",
    "target",
    "vendor",
    "venv",
)


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
    if paths and all(path.is_file() or path.is_dir() for path in paths):
        return paths

    # Some terminals paste an unescaped path containing spaces.
    whole = value.strip()
    if whole.startswith("file://"):
        whole = unquote(urlparse(whole).path)
    whole_path = Path(whole).expanduser()
    return [whole_path] if whole_path.is_file() or whole_path.is_dir() else []


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


def build_file_index(
    root: Path,
    *,
    include_hidden: bool = False,
    skipped_directories: Sequence[str] = DEFAULT_SKIPPED_DIRECTORIES,
    ignore_files: Iterable[Path] = (),
) -> list[str]:
    """Index project files with fd, falling back to a bounded Python walk."""
    skipped = frozenset(skipped_directories)
    if files := _build_fd_index(root, include_hidden, skipped, ignore_files):
        return files
    return _build_python_index(root, include_hidden, skipped)


def _build_fd_index(
    root: Path,
    include_hidden: bool,
    skipped_directories: frozenset[str],
    ignore_files: Iterable[Path],
) -> list[str]:
    fd = shutil.which("fd")
    if fd is None:
        return []

    command = [
        fd,
        "--type=file",
        "--type=directory",
        "--no-ignore-vcs",
        "--color=never",
        "--print0",
        "--strip-cwd-prefix=always",
        f"--max-results={MAX_INDEXED_FILES}",
    ]
    if include_hidden:
        command.append("--hidden")
    for directory in sorted(skipped_directories):
        command.extend(("--exclude", directory))
    for ignore_file in ignore_files:
        path = ignore_file.expanduser().resolve()
        if path.is_file():
            command.extend(("--ignore-file", str(path)))
    command.append(".")

    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    return [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def _build_python_index(
    root: Path,
    include_hidden: bool,
    skipped_directories: frozenset[str],
) -> list[str]:
    files: list[str] = []
    try:
        for directory, names, filenames in os.walk(root):
            names[:] = sorted(
                name
                for name in names
                if name not in skipped_directories and (include_hidden or not name.startswith("."))
            )
            relative_directory = Path(directory).relative_to(root)
            for name in names:
                files.append((relative_directory / name).as_posix() + "/")
                if len(files) >= MAX_INDEXED_FILES:
                    return files
            for filename in sorted(filenames):
                if not include_hidden and filename.startswith("."):
                    continue
                files.append((relative_directory / filename).as_posix())
                if len(files) >= MAX_INDEXED_FILES:
                    return files
    except OSError:
        pass
    return files


def find_file_completions(
    root: Path,
    query: str,
    indexed_files: Sequence[str],
    *,
    limit: int = 12,
    include_hidden: bool = False,
    fzf_options: Sequence[str] = (),
    use_global_fzf_options: bool = True,
) -> list[FileCompletion]:
    expanded = _expand_direct_query(query)
    if expanded is not None:
        parent = expanded if query.endswith("/") else expanded.parent
        prefix = "" if query.endswith("/") else expanded.name.lower()
        try:
            children = [
                (child, child.is_dir())
                for child in parent.iterdir()
                if include_hidden or not child.name.startswith(".")
            ]
        except OSError:
            return []
        children.sort(key=lambda item: (not item[1], item[0].name.lower()))
        matches = [
            (child, is_directory)
            for child, is_directory in children
            if child.name.lower().startswith(prefix)
        ]
        return [
            FileCompletion(
                child,
                child.as_posix() + ("/" if is_directory else ""),
                is_directory,
            )
            for child, is_directory in matches[:limit]
        ]

    needle = query.removeprefix("./")
    fuzzy_matches = _rank_with_fzf(
        needle,
        indexed_files,
        fzf_options=fzf_options,
        use_global_options=use_global_fzf_options,
        limit=limit,
    )
    if fuzzy_matches is not None:
        return [
            FileCompletion(root / relative, relative, relative.endswith("/"))
            for relative in fuzzy_matches
        ]

    lowered_needle = needle.lower()

    def ranked_candidates() -> Iterable[tuple[int, str]]:
        for relative in indexed_files:
            name = relative.rsplit("/", 1)[-1].lower()
            lowered = relative.lower()
            if name.startswith(lowered_needle):
                score = 0
            elif lowered.startswith(lowered_needle):
                score = 1
            elif lowered_needle in name:
                score = 2
            elif lowered_needle in lowered:
                score = 3
            else:
                continue
            yield score, relative

    ranked = heapq.nsmallest(
        limit,
        ranked_candidates(),
        key=lambda item: (item[0], len(item[1]), item[1].lower()),
    )
    return [
        FileCompletion(root / relative, relative, relative.endswith("/"))
        for _, relative in ranked
    ]


def _expand_direct_query(query: str) -> Path | None:
    if not query.startswith(("/", "~")):
        return None
    try:
        return Path(query).expanduser()
    except (OSError, RuntimeError):
        # An incomplete or mistyped user expression such as `~.` is still editable.
        return None


def can_search_system_files(query: str) -> bool:
    return (
        len(query) >= SYSTEM_SEARCH_MIN_CHARACTERS
        and not query.startswith(("/", "~"))
        and "/" not in query
        and "\\" not in query
    )


def find_system_file_completions(
    root: Path,
    query: str,
    *,
    limit: int = 12,
    include_hidden: bool = False,
    skipped_directories: Sequence[str] = DEFAULT_SKIPPED_DIRECTORIES,
    fzf_options: Sequence[str] = (),
    use_global_fzf_options: bool = True,
    cancelled: Callable[[], bool] | None = None,
) -> list[FileCompletion]:
    """Find paths outside the project through the operating system's file index."""
    if not can_search_system_files(query) or (cancelled is not None and cancelled()):
        return []

    root = root.expanduser().resolve()
    raw_paths = search_system_file_index(
        query,
        limit=MAX_SYSTEM_CANDIDATES,
        timeout=1,
        cancelled=cancelled,
    )
    skipped = frozenset(skipped_directories)
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute() or raw_path in seen:
            continue
        seen.add(raw_path)
        if path.is_relative_to(root):
            continue
        parts = path.parts[1:]
        if any(part in skipped for part in parts):
            continue
        if not include_hidden and any(part.startswith(".") for part in parts):
            continue
        candidates.append(raw_path)
        if len(candidates) >= MAX_SYSTEM_CANDIDATES:
            break

    if cancelled is not None and cancelled():
        return []
    ranked = _rank_with_fzf(
        query,
        candidates,
        fzf_options=fzf_options,
        use_global_options=use_global_fzf_options,
        limit=limit * 4,
    )
    paths = candidates if ranked is None else ranked
    completions: list[FileCompletion] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        is_directory = stat.S_ISDIR(mode)
        if not is_directory and not stat.S_ISREG(mode):
            continue
        completions.append(
            FileCompletion(
                path,
                path.as_posix() + ("/" if is_directory else ""),
                is_directory,
            )
        )
        if len(completions) >= limit:
            break
    return completions


def _rank_with_fzf(
    query: str,
    relative_paths: Sequence[str],
    *,
    fzf_options: Sequence[str],
    use_global_options: bool,
    limit: int,
) -> list[str] | None:
    fzf = shutil.which("fzf")
    if fzf is None:
        return None
    if not relative_paths:
        return []

    source = b"\0".join(os.fsencode(relative) for relative in relative_paths)
    if source:
        source += b"\0"
    command = [
        fzf,
        *fzf_options,
        f"--filter={query}",
        "--scheme=path",
        "--tiebreak=pathname,index",
        "--read0",
        "--print0",
        "--no-multi-line",
    ]
    environment = os.environ.copy()
    if not use_global_options:
        environment.pop("FZF_DEFAULT_OPTS", None)
        environment.pop("FZF_DEFAULT_OPTS_FILE", None)
    try:
        result = subprocess.run(
            command,
            input=source,
            capture_output=True,
            check=False,
            env=environment,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in {0, 1}:
        return None

    matches: list[str] = []
    allowed = frozenset(relative_paths)
    start = 0
    while len(matches) < limit:
        end = result.stdout.find(b"\0", start)
        if end < 0:
            break
        raw_match = result.stdout[start:end]
        start = end + 1
        if not raw_match:
            continue
        relative = os.fsdecode(raw_match)
        if relative in allowed:
            matches.append(relative)
    return matches


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
