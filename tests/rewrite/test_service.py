from __future__ import annotations

import re

import pytest

from ghostwriter.model import Attachment, Draft
from ghostwriter.rewrite import RewriteOptions, RewriteSession


class FakeRpc:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.closed = False

    async def prompt(self, message: str) -> str:
        self.prompts.append(message)
        placeholder = re.search(r"__GW_[A-F0-9]+_ATTACHMENT_0000__", message)
        assert placeholder is not None
        return f"Polished text with {placeholder.group(0)} in context."

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_transform_and_revision_reuse_session_without_exposing_path() -> None:
    attachment = Attachment(
        "image",
        "/private/secret screenshot.png",
        "/cache/image.png",
        id="1234567890abcdef",
    )
    draft = Draft(text=f"messy {attachment.editor_token} text", attachments=[attachment])
    session = RewriteSession(
        draft,
        RewriteOptions(translate=True, tidy=True, target_language="French"),
    )
    fake_rpc = FakeRpc()
    session.rpc = fake_rpc  # type: ignore[assignment]

    first = await session.transform(draft.text)
    revised = await session.revise(first, "Use a more direct tone")
    await session.close()

    assert attachment.editor_token in first
    assert attachment.editor_token in revised
    assert "/private/secret screenshot.png" not in "\n".join(fake_rpc.prompts)
    assert "secret screenshot.png" not in "\n".join(fake_rpc.prompts)
    assert len(fake_rpc.prompts) == 2
    assert "never add a heading to a short or single-section draft" in fake_rpc.prompts[0]
    assert fake_rpc.closed


@pytest.mark.asyncio
async def test_custom_prompt_receives_language_and_protected_text() -> None:
    attachment = Attachment("file", "/private/notes.md", "/private/notes.md", id="abcdef1234567890")
    draft = Draft(text=f"bonjour {attachment.editor_token}", attachments=[attachment])
    session = RewriteSession(
        draft,
        RewriteOptions(
            target_language="English",
            instructions="Use a formal tone.",
            prompt="Translate into {target_language}:\n{instructions}\n{text}",
        ),
    )
    fake_rpc = FakeRpc()
    session.rpc = fake_rpc  # type: ignore[assignment]

    await session.transform(draft.text)
    await session.close()

    assert fake_rpc.prompts[0].startswith("Translate into English:")
    assert "Use a formal tone." in fake_rpc.prompts[0]
    assert attachment.editor_token not in fake_rpc.prompts[0]
