from pathlib import Path

import pytest

from ghostwriter.model import Attachment, Draft
from ghostwriter.serializer import format_file_reference, serialize_draft


def test_file_references_are_relative_and_quote_spaces(tmp_path: Path) -> None:
    plain = tmp_path / "src" / "main.py"
    spaced = tmp_path / "notes" / "design brief.md"

    assert format_file_reference(plain, tmp_path) == "@src/main.py"
    assert format_file_reference(spaced, tmp_path) == '@"notes/design brief.md"'


def test_serialize_draft_preserves_order_and_image_path(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    image = tmp_path / "cache" / "image.png"
    draft = Draft(
        text="Review these.",
        attachments=[
            Attachment("file", str(source), str(source)),
            Attachment("image", str(image), str(image)),
        ],
    )

    assert serialize_draft(draft, tmp_path) == (
        "Review these.\n\nReferenced attachments:\n"
        "- @source.py\n"
        f"- {image}"
    )


def test_inline_attachment_token_is_replaced_in_place(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    attachment = Attachment("file", str(source), str(source), id="inline123456789")
    draft = Draft(text=f"Before {attachment.editor_token} after", attachments=[attachment])

    assert serialize_draft(draft, tmp_path) == "Before @context.md after"


def test_file_reference_rejects_unrepresentable_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot safely represent"):
        format_file_reference(tmp_path / 'bad"name.txt', tmp_path)
