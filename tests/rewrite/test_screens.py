from __future__ import annotations

from pathlib import Path

import pytest

from ghostwriter.app import GhostwriterApp
from ghostwriter.model import Draft
from ghostwriter.rewrite.screens import RewriteConfigScreen
from ghostwriter.rewrite.service import RewriteOptions
from ghostwriter.storage import DraftStore


@pytest.mark.asyncio
async def test_rewrite_config_keeps_compact_run_control_visible(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="Rewrite me")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(80, 28)) as pilot:
        results: list[RewriteOptions | None] = []
        screen = RewriteConfigScreen(RewriteOptions(translate=True, tidy=True))
        app.push_screen(screen, callback=results.append)
        await pilot.pause()

        assert screen.query_one("#rewrite-translate").size.height == 1
        assert screen.query_one("#rewrite-tidy").size.height == 1
        assert screen.query_one("#rewrite-start").region.height == 1
        assert screen.query_one("#rewrite-start").region.y < screen.size.height

        screen._start()
        await pilot.pause()

        assert results and results[0] is not None
        assert results[0].translate and results[0].tidy
