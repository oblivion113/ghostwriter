from __future__ import annotations

import pytest

from ghostwriter.model import Attachment
from ghostwriter.rewrite import AttachmentProtector, PlaceholderIntegrityError


def attachment() -> Attachment:
    return Attachment(
        "file",
        "/private/notes/secret plan.md",
        id="abcdef1234567890",
    )


def test_attachment_contents_and_filename_are_not_sent() -> None:
    item = attachment()
    original = f"Read {item.editor_token} before answering."
    protector = AttachmentProtector(original, [item], nonce="TESTNONCE")

    protected = protector.protect(original)

    assert protected == "Read __GW_TESTNONCE_ATTACHMENT_0000__ before answering."
    assert "secret plan.md" not in protected
    assert protector.restore(protected) == original


def test_restore_rejects_missing_or_duplicated_placeholders() -> None:
    item = attachment()
    original = f"Read {item.editor_token}."
    protector = AttachmentProtector(original, [item], nonce="TESTNONCE")
    placeholder = "__GW_TESTNONCE_ATTACHMENT_0000__"

    with pytest.raises(PlaceholderIntegrityError, match="changed protected"):
        protector.restore("Read nothing.")
    with pytest.raises(PlaceholderIntegrityError, match="duplicated"):
        protector.restore(f"{placeholder} {placeholder}")


def test_protect_rejects_locally_deleted_attachment_marker() -> None:
    item = attachment()
    protector = AttachmentProtector(item.editor_token, [item], nonce="TESTNONCE")

    with pytest.raises(PlaceholderIntegrityError, match="marker count changed"):
        protector.protect("marker was deleted")
