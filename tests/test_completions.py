from __future__ import annotations

import pytest

from ghostwriter.completions import (
    CompletionContext,
    SlashCompletion,
    filter_named_completions,
    find_completion_context,
)


@pytest.mark.parametrize(
    ("kind", "line", "query", "start"),
    [
        ("file", "Review @src/ma", "src/ma", 7),
        ("slash", "Then /s", "s", 5),
        ("skill", "Use /skill:teach", "teach", 4),
        ("template", "Use /prompt:review", "review", 4),
    ],
)
def test_finds_completion_immediately_before_cursor(kind, line, query, start) -> None:
    assert find_completion_context(kind, line, 2, len(line)) == CompletionContext(
        query=query,
        start=(2, start),
        end=(2, len(line)),
    )


def test_slash_route_owns_command_name_until_colon() -> None:
    line = "/skill"

    assert find_completion_context("slash", line, 0, len(line)) is not None
    assert find_completion_context("skill", line, 0, len(line)) is None
    assert find_completion_context("skill", f"{line}:", 0, len(line) + 1) is not None


def test_named_completion_prefers_prefix_then_falls_back_to_infix() -> None:
    candidates = (
        SlashCompletion("teaching", ""),
        SlashCompletion("team", ""),
        SlashCompletion("architecture", ""),
    )

    assert [item.name for item in filter_named_completions("te", candidates)] == [
        "teaching",
        "team",
    ]
    assert [item.name for item in filter_named_completions("eac", candidates)] == [
        "teaching"
    ]
    assert filter_named_completions("eac", candidates, allow_infix=False) == []
