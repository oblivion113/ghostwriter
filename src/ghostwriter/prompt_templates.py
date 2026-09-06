from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROMPT_REFERENCE_PATTERN = re.compile(
    r"(?<!\S)/prompt:([A-Za-z0-9][A-Za-z0-9._-]*)(?=$|\s)"
)
_VALID_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    description: str
    content: str
    path: Path

    @property
    def reference(self) -> str:
        return f"/prompt:{self.name}"


def load_prompt_templates(directory: Path) -> list[PromptTemplate]:
    """Load simple Markdown Prompt templates from one directory, non-recursively."""
    directory = directory.expanduser()
    try:
        paths = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError:
        return []

    templates: list[PromptTemplate] = []
    names: set[str] = set()
    for path in paths:
        if not path.name.endswith(".md") or not path.is_file():
            continue
        template = _load_prompt_template(path)
        if template is not None and template.name not in names:
            templates.append(template)
            names.add(template.name)
    return templates


def expand_prompt_references(
    text: str,
    templates: list[PromptTemplate],
) -> tuple[str, tuple[str, ...]]:
    """Replace all known Prompt references and report missing template names."""
    by_name = {template.name: template for template in templates}
    missing = tuple(
        dict.fromkeys(
            match.group(1)
            for match in PROMPT_REFERENCE_PATTERN.finditer(text)
            if match.group(1) not in by_name
        )
    )
    if missing:
        return text, missing
    return (
        PROMPT_REFERENCE_PATTERN.sub(
            lambda match: by_name[match.group(1)].content,
            text,
        ),
        (),
    )


def _load_prompt_template(path: Path) -> PromptTemplate | None:
    try:
        raw_content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    frontmatter, body = _parse_frontmatter(raw_content)
    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not _VALID_NAME_PATTERN.fullmatch(name):
        return None
    return PromptTemplate(
        name=name,
        description=description,
        content=body,
        path=path,
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    normalized = content.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end_index = normalized.find("\n---", 4)
    if end_index < 0:
        return {}, normalized

    values: dict[str, str] = {}
    for line in normalized[4:end_index].splitlines():
        key, separator, raw_value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            values[key.strip()] = _parse_scalar(raw_value.strip())
    return values, normalized[end_index + 4 :].strip()


def _parse_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
