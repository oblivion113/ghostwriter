from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

CompletionKind = Literal["file", "slash", "skill", "template"]
Location = tuple[int, int]


class NamedCompletion(Protocol):
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class CompletionContext:
    query: str
    start: Location
    end: Location


@dataclass(frozen=True, slots=True)
class SlashCompletion:
    name: str
    description: str

    @property
    def token(self) -> str:
        return f"/{self.name}:"


SLASH_COMPLETIONS = (
    SlashCompletion("skill", "Browse Skills available in the selected Pi session"),
    SlashCompletion("prompt", "Browse Prompt templates"),
)

_PATTERNS = {
    "file": re.compile(r"(?<!\S)@([^\s]*)$"),
    "slash": re.compile(r"(?<!\S)/([A-Za-z]*)$"),
    "skill": re.compile(r"(?<!\S)/skill:([^\s]*)$"),
    "template": re.compile(r"(?<!\S)/prompt:([^\s]*)$"),
}


def find_completion_context(
    kind: CompletionKind,
    line: str,
    row: int,
    column: int,
) -> CompletionContext | None:
    """Find the active completion expression immediately before the cursor."""
    match = _PATTERNS[kind].search(line[:column])
    if match is None:
        return None
    return CompletionContext(
        query=match.group(1),
        start=(row, match.start()),
        end=(row, column),
    )


def filter_named_completions[NamedCompletionT: NamedCompletion](
    query: str,
    candidates: Sequence[NamedCompletionT],
    *,
    allow_infix: bool = True,
    limit: int = 12,
) -> list[NamedCompletionT]:
    """Prefer name prefixes, then optionally fall back to infix matches."""
    lowered = query.casefold()
    matches = [
        candidate
        for candidate in candidates
        if candidate.name.casefold().startswith(lowered)
    ]
    if not matches and allow_infix:
        matches = [
            candidate
            for candidate in candidates
            if lowered in candidate.name.casefold()
        ]
    return matches[:limit]
