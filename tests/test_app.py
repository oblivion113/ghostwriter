from __future__ import annotations

from pathlib import Path

import pytest
from textual import events
from textual.containers import VerticalScroll
from textual.widgets import OptionList

from ghostwriter.app import GhostwriterApp
from ghostwriter.model import Draft
from ghostwriter.pi import PiTarget
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
        app._add_attachment(source)
        await pilot.pause()

        attachment = app.draft.attachments[0]
        assert attachment.editor_token in editor.text
        assert editor.text.startswith("before")


@pytest.mark.asyncio
async def test_pasting_file_path_into_prompt_creates_attachment(tmp_path: Path) -> None:
    source = tmp_path / "context notes.md"
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="Review: ")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        editor = app.query_one("#prompt-editor")
        editor.cursor_location = (0, len(editor.text))
        editor.post_message(events.Paste(str(source)))
        await pilot.pause()

        assert len(app.draft.attachments) == 1
        attachment = app.draft.attachments[0]
        assert attachment.kind == "file"
        assert attachment.editor_token in editor.text
        assert str(source) not in editor.text


@pytest.mark.asyncio
async def test_deleting_last_marker_removes_unreferenced_attachment(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="Review: ")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._add_attachment(source)
        editor = app.query_one("#prompt-editor")
        editor.load_text("Review: ")
        await pilot.pause()

        assert app.draft.attachments == []
        assert app.query_one("#attachments").row_count == 0


@pytest.mark.asyncio
async def test_removing_attachment_deletes_all_matching_markers(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._add_attachment(source)
        attachment = app.draft.attachments[0]
        editor = app.query_one("#prompt-editor")
        editor.load_text(f"Before {attachment.editor_token} and {attachment.editor_token} after")
        await pilot.pause()

        app.selected_attachment_id = attachment.id
        app._remove_selected_attachment()
        await pilot.pause()

        assert attachment.editor_token not in editor.text
        assert app.draft.attachments == []


@pytest.mark.asyncio
async def test_code_attachment_has_raw_text_preview(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._add_attachment(source)
        app._show_attachment_preview(app.draft.attachments[0])
        await pilot.pause()

        preview = app.query_one("#text-preview")
        assert preview.display
        assert preview.text == "def answer():\n    return 42\n"


@pytest.mark.asyncio
async def test_target_sessions_are_concise_in_one_scrollable_list(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")
    target = PiTarget(
        pid=42,
        session_id="abcdef123456",
        session_name="Refactor",
        cwd=tmp_path / "ghostwriter",
        socket_path=tmp_path / "pi.sock",
        provider="anthropic",
        model_id="claude-sonnet",
        thinking_level="high",
    )
    app.pi.discover_targets = lambda: [target]  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        target_list = app.query_one("#target", OptionList)

        assert target_list.option_count == 1
        assert app._selected_target() == target
        assert "Refactor" in str(target_list.get_option_at_index(0).prompt)
        assert not app.query("#target-details")


@pytest.mark.asyncio
async def test_narrow_side_pane_scrolls_to_hidden_controls(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        side_pane = app.query_one("#side-pane", VerticalScroll)

        assert app.screen.has_class("stacked")
        assert side_pane.max_scroll_y > 0
        actions = app.query_one("#actions")
        editor = app.query_one("#editor-pane")
        assert actions.region.bottom <= editor.region.bottom


@pytest.mark.asyncio
async def test_at_completion_attaches_project_file_with_compact_marker(tmp_path: Path) -> None:
    source = tmp_path / "src" / "context.md"
    source.parent.mkdir()
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._project_root = lambda: tmp_path
        editor = app.query_one("#prompt-editor")
        editor.load_text("Review @cont")
        editor.cursor_location = (0, len(editor.text))
        app._update_file_completions()

        assert app.query_one("#file-completions").display
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "Review @context.md "
        assert app.draft.attachments[0].source == source.resolve()
        assert app.query_one("#attachments").row_count == 1


@pytest.mark.asyncio
async def test_layout_uses_aspect_ratio_and_splitter_is_draggable(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        assert not app.screen.has_class("stacked")
        original_width = app._horizontal_split
        original_height = app._prompt_split
        original_editor_cells = app.query_one("#editor-pane").size.width
        original_prompt_cells = app.query_one("#prompt-region").size.height

        await pilot.mouse_down("#width-handle")
        await pilot.hover("#workspace", offset=(70, 10))
        await pilot.mouse_up("#width-handle")
        await pilot.pause()
        assert app._horizontal_split < original_width
        assert app.query_one("#editor-pane").size.width < original_editor_cells

        await pilot.mouse_down("#height-handle")
        await pilot.hover("#editor-pane", offset=(20, 20))
        await pilot.mouse_up("#height-handle")
        await pilot.pause()
        assert app._prompt_split < original_height
        assert app.query_one("#prompt-region").size.height < original_prompt_cells

    tall_app = GhostwriterApp()
    tall_app.draft = Draft(text="")
    tall_app.store = DraftStore(tmp_path / "tall-draft.json")
    async with tall_app.run_test(size=(100, 70)):
        assert tall_app.screen.has_class("stacked")
