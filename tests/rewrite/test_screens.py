from __future__ import annotations

from pathlib import Path

import pytest

from ghostwriter.app import GhostwriterApp
from ghostwriter.config import RewriteAgent, RewriteConfig
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


@pytest.mark.asyncio
async def test_rewrite_config_selects_configured_language_and_agent(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="Rewrite me")
    app.store = DraftStore(tmp_path / "draft.json")
    config = RewriteConfig(
        agents=(
            RewriteAgent(),
            RewriteAgent("anthropic", "claude-haiku"),
        ),
        target_languages=("English", "French"),
    )

    async with app.run_test(size=(80, 28)) as pilot:
        results: list[RewriteOptions | None] = []
        screen = RewriteConfigScreen(RewriteOptions(), config)
        app.push_screen(screen, callback=results.append)
        await pilot.pause()
        screen.query_one("#rewrite-target").value = "French"
        screen.query_one("#rewrite-agent").value = "anthropic/claude-haiku"
        screen._start()
        await pilot.pause()

        assert results[0] is not None
        assert results[0].target_language == "French"
        assert results[0].agent == "anthropic/claude-haiku"
        assert results[0].provider == "anthropic"
        assert results[0].model == "claude-haiku"


@pytest.mark.asyncio
async def test_rewrite_config_can_open_and_reload_edited_choices(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="Rewrite me")
    app.store = DraftStore(tmp_path / "draft.json")
    initial = RewriteConfig(
        agents=(RewriteAgent("anthropic", "claude-haiku"),),
        target_languages=("French",),
        default_target_language="French",
    )
    edited = RewriteConfig(
        agents=(RewriteAgent("openai", "gpt-test"),),
        target_languages=("Japanese",),
        default_target_language="Japanese",
        instructions="Keep it concise.",
        prompt="Write in {target_language}.\n{instructions}\n{text}",
    )
    opened: list[bool] = []

    async with app.run_test(size=(88, 30)) as pilot:
        screen = RewriteConfigScreen(
            RewriteOptions(agent="anthropic/claude-haiku", target_language="French"),
            initial,
            tmp_path / "config.json",
            open_config=lambda: opened.append(True),
            reload_config=lambda: edited,
        )
        app.push_screen(screen)
        await pilot.pause()

        screen.open_config_button()
        screen.reload_config_button()
        await pilot.pause()

        assert opened == [True]
        assert screen.query_one("#rewrite-target").value == "Japanese"
        assert screen.query_one("#rewrite-agent").value == "openai/gpt-test"
        assert screen.query_one("#rewrite-open-config").region.y < screen.size.height
        assert screen.query_one("#rewrite-reload-config").region.y < screen.size.height
