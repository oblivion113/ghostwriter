from pathlib import Path

from ghostwriter.prompt_templates import (
    PromptTemplate,
    expand_prompt_references,
    load_prompt_templates,
)


def test_loads_named_frontmatter_and_preserves_body_line_breaks(tmp_path: Path) -> None:
    template_path = tmp_path / "review.md"
    template_path.write_text(
        "---\r\nname: review\r\ndescription: Review staged changes\r\n---\r\n"
        "Review this literally: $1.\r\n\r\n- Bugs\r\n- Security\r\n",
        encoding="utf-8",
    )

    assert load_prompt_templates(tmp_path) == [
        PromptTemplate(
            name="review",
            description="Review staged changes",
            content="Review this literally: $1.\n\n- Bugs\n- Security",
            path=template_path,
        )
    ]


def test_template_discovery_is_non_recursive_and_requires_a_valid_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "plain.md").write_text(
        "---\nname: explain\ndescription: Explain code\n---\nExplain this code.",
        encoding="utf-8",
    )
    (tmp_path / "missing-name.md").write_text(
        "---\ndescription: Missing a name\n---\nIgnored",
        encoding="utf-8",
    )
    (tmp_path / "empty-description.md").write_text(
        "---\nname: concise\ndescription:\n---\nKeep it short.",
        encoding="utf-8",
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "ignored.md").write_text(
        "---\nname: ignored\ndescription: Nested\n---\nIgnored",
        encoding="utf-8",
    )

    templates = load_prompt_templates(tmp_path)

    assert [template.name for template in templates] == ["concise", "explain"]
    assert templates[0].description == ""


def test_expands_multiple_prompt_references_in_place(tmp_path: Path) -> None:
    templates = [
        PromptTemplate("first", "First", "Line one\nLine two", tmp_path / "first.md"),
        PromptTemplate("second", "Second", "Tail", tmp_path / "second.md"),
    ]

    expanded, missing = expand_prompt_references(
        "Before /prompt:first between /prompt:second after",
        templates,
    )

    assert missing == ()
    assert expanded == "Before Line one\nLine two between Tail after"


def test_missing_reference_prevents_partial_expansion(tmp_path: Path) -> None:
    template = PromptTemplate("known", "Known", "Expanded", tmp_path / "known.md")
    original = "/prompt:known and /prompt:missing"

    expanded, missing = expand_prompt_references(original, [template])

    assert expanded == original
    assert missing == ("missing",)
