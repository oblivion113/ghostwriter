from __future__ import annotations

from pathlib import Path

import pytest

from ghostwriter.app import GhostwriterApp
from ghostwriter.model import Draft
from ghostwriter.storage import DraftStore


@pytest.mark.asyncio
async def test_adding_file_inserts_marker_at_cursor(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="before after")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        editor = app.query_one("#prompt-editor")
        editor.cursor_location = (0, 6)
        app._add_attachment(source, "file")
        await pilot.pause()

        attachment = app.draft.attachments[0]
        assert attachment.editor_token in editor.text
        assert editor.text.startswith("before")
