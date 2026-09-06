from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual import events
from textual._cells import cell_len
from textual.command import CommandPalette
from textual.containers import VerticalScroll
from textual.widgets import Select
from textual.widgets._select import InvalidSelectValueError

from ghostwriter.app import CurrentThemeProvider, GhostwriterApp
from ghostwriter.config import ConfigStore, GhostwriterConfig, PromptTemplateConfig
from ghostwriter.model import Draft
from ghostwriter.pi import PiSkill, PiTarget
from ghostwriter.prompt_screens import PromptTemplateScreen
from ghostwriter.storage import DraftStore


@pytest.mark.asyncio
async def test_adding_file_inserts_marker_at_cursor(tmp_path: Path) -> None:
    source = tmp_path / "context.md"
    source.write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="before after")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._project_root = lambda: tmp_path
        editor = app.query_one("#prompt-editor")
        editor.cursor_location = (0, 6)
        app._add_attachment(source)
        await pilot.pause()

        attachment = app.draft.attachments[0]
        assert attachment.editor_token in editor.text
        assert editor.text.startswith("before")
        rendered_line = editor.get_line(0)
        attachment_spans = [
            span
            for span in rendered_line.spans
            if rendered_line.plain[span.start : span.end] == attachment.editor_token
        ]
        assert attachment_spans
        assert attachment_spans[0].style.bold
        assert attachment_spans[0].style.color is not None

        editor.cursor_location = (0, 0)
        active_line = editor.render_line(0)
        assert any(
            attachment.editor_token in segment.text
            and segment.style is not None
            and segment.style.color == attachment_spans[0].style.color
            for segment in active_line
        )


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
        assert attachment.editor_token == f"@{source.as_posix()}"


@pytest.mark.asyncio
async def test_plain_paste_is_inserted_once(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app.post_message(events.Paste("Audio transcription"))
        await pilot.pause()

        assert app.query_one("#prompt-editor").text == "Audio transcription"


@pytest.mark.asyncio
async def test_unsaved_prompt_is_persisted_on_unmount(tmp_path: Path) -> None:
    store = DraftStore(tmp_path / "draft.json")
    app = GhostwriterApp()
    app.draft = Draft(text="before")
    app.store = store

    async with app.run_test(size=(120, 40)):
        app.query_one("#prompt-editor").load_text("edited without saving")

    assert store.load().text == "edited without saving"


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
async def test_target_sessions_use_a_collapsed_select(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")
    targets = [
        PiTarget(
            pid=pid,
            session_id=f"abcdef{pid}",
            session_name=name,
            cwd=tmp_path / name.lower(),
            socket_path=tmp_path / f"{pid}.sock",
            provider="anthropic",
            model_id="claude-sonnet",
            thinking_level="high",
        )
        for pid, name in ((42, "Refactor"), (43, "Review"))
    ]
    app.pi.discover_targets = lambda: targets  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        target_select = app.query_one("#target", Select)

        assert target_select.value == targets[0].selection_id
        assert not target_select.expanded
        assert app._selected_target() == targets[0]
        with pytest.raises(InvalidSelectValueError):
            target_select.value = Select.NULL

        target_select.value = targets[1].selection_id
        await pilot.pause()
        assert app._selected_target() == targets[1]


@pytest.mark.asyncio
async def test_target_select_has_a_disabled_empty_state(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")
    app.pi.discover_targets = list  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        target_select = app.query_one("#target", Select)

        assert target_select.disabled
        assert target_select.value == app.NO_TARGET_ID
        assert app._selected_target() is None
        with pytest.raises(InvalidSelectValueError):
            target_select.value = Select.NULL


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
async def test_skill_completion_works_mid_prompt_and_styles_inserted_token(tmp_path: Path) -> None:
    target = PiTarget(
        pid=42,
        session_id="abcdef123456",
        cwd=tmp_path,
        socket_path=tmp_path / "pi.sock",
        skills=(
            PiSkill("blueprint", "Explains why a codebase works well.\nUse for analysis."),
            PiSkill("teaching", "Explains concepts for beginners."),
        ),
    )
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")
    app.pi.discover_targets = lambda: [target]  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        editor = app.query_one("#prompt-editor")
        editor.load_text("Explain this first, then /skill:blue")
        editor.cursor_location = (0, len(editor.text))
        app._update_completions()

        options = app.query_one("#prompt-completions")
        assert options.display
        assert options.option_count == 1
        assert options.options[0].prompt.plain == (
            "/skill:blueprint\nExplains why a codebase works well. Use for analysis."
        )
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "Explain this first, then /skill:blueprint "
        rendered_line = editor.get_line(0)
        skill_spans = [
            span
            for span in rendered_line.spans
            if rendered_line.plain[span.start : span.end] == "/skill:blueprint"
        ]
        assert skill_spans
        assert skill_spans[0].style.bold
        assert skill_spans[0].style.color is not None


@pytest.mark.asyncio
async def test_prompt_template_completion_adds_reference_then_f3_expands_it(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "review.md").write_text(
        "---\nname: review\ndescription: Review the selected area\n---\n"
        "First pass.\n\nSecond pass.",
        encoding="utf-8",
    )
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.save(
        GhostwriterConfig(
            prompt_templates=PromptTemplateConfig(directory=prompts)
        )
    )
    app = GhostwriterApp(config_store=config_store)
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        editor = app.query_one("#prompt-editor")
        editor.load_text("Before /prompt:rev after")
        editor.cursor_location = (0, len("Before /prompt:rev"))
        app._update_completions()

        options = app.query_one("#prompt-completions")
        assert options.display
        assert options.option_count == 1
        assert options.options[0].prompt.plain == (
            "/prompt:review\nReview the selected area"
        )
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "Before /prompt:review after"
        rendered_line = editor.get_line(0)
        assert any(
            rendered_line.plain[span.start : span.end] == "/prompt:review"
            for span in rendered_line.spans
        )

        await pilot.press("f3")
        await pilot.pause()

        assert editor.text == "Before First pass.\n\nSecond pass. after"


@pytest.mark.asyncio
async def test_prompt_picker_inserts_and_expands_without_changing_slash_completion(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "concise.md").write_text(
        "---\nname: concise\ndescription:\n---\nKeep the answer short.",
        encoding="utf-8",
    )
    (prompts / "review.md").write_text(
        "---\nname: review\ndescription: Review carefully\n---\nReview the implementation.",
        encoding="utf-8",
    )
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.save(
        GhostwriterConfig(
            prompt_templates=PromptTemplateConfig(directory=prompts)
        )
    )
    app = GhostwriterApp(config_store=config_store)
    app.draft = Draft(text="Existing draft")
    app.store = DraftStore(tmp_path / "draft.json")
    opened: list[Path] = []
    app._open_prompt_template_directory = opened.append  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        editor = app.query_one("#prompt-editor")
        editor.cursor_location = (0, len(editor.text))
        await pilot.click("#prompts")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PromptTemplateScreen)
        options = screen.query_one("#prompt-template-list")
        assert [option.prompt.plain for option in options.options] == [
            "concise\n ",
            "review\nReview carefully",
        ]
        name_span, description_span = options.options[1].prompt.spans
        assert name_span.style.bold
        assert not description_span.style.bold

        await pilot.click("#prompt-template-open-folder")
        await pilot.pause()
        assert opened == [prompts]
        assert app.screen is screen

        actions = [
            screen.query_one(f"#prompt-template-{name}")
            for name in ("insert", "expand", "open-folder", "cancel")
        ]
        assert len({button.region.y for button in actions}) == 1
        assert not screen.query("#prompt-template-replace")
        assert not screen.query("#prompt-template-refresh")

        options.highlighted = 1
        await pilot.click("#prompt-template-insert")
        await pilot.pause()
        assert editor.text == "Existing draft /prompt:review "

        await pilot.click("#prompts")
        await pilot.pause()
        await pilot.click("#prompt-template-expand")
        await pilot.pause()
        assert editor.text == "Existing draft Review the implementation. "

        before_cancel = editor.text
        await pilot.click("#prompts")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert editor.text == before_cancel


@pytest.mark.asyncio
async def test_prompt_picker_has_a_safe_empty_state(tmp_path: Path) -> None:
    app = GhostwriterApp(config_store=ConfigStore(tmp_path / "config.json"))
    app.draft = Draft(text="Unchanged")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#prompts")
        await pilot.pause()

        screen = app.screen
        assert isinstance(screen, PromptTemplateScreen)
        assert not screen.query_one("#prompt-template-list").display
        assert screen.query_one("#prompt-template-empty").display
        assert screen.query_one("#prompt-template-insert").disabled
        assert not screen.query("#prompt-template-replace")
        assert not screen.query("#prompt-template-refresh")

        await pilot.press("escape")
        await pilot.pause()
        assert app.query_one("#prompt-editor").text == "Unchanged"


@pytest.mark.asyncio
async def test_settings_refresh_updates_added_and_deleted_prompt_templates(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    old_template = prompts / "old.md"
    old_template.write_text(
        "---\nname: old\ndescription: Old\n---\nOld body",
        encoding="utf-8",
    )
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.save(
        GhostwriterConfig(
            prompt_templates=PromptTemplateConfig(directory=prompts)
        )
    )
    app = GhostwriterApp(config_store=config_store)
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        old_template.unlink()
        (prompts / "new.md").write_text(
            "---\nname: new\ndescription: New\n---\nNew body",
            encoding="utf-8",
        )

        commands = {command.title: command for command in app.get_system_commands(app.screen)}
        commands["Refresh"].callback()
        assert [template.name for template in app.prompt_templates] == ["new"]

        await pilot.click("#prompts")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PromptTemplateScreen)
        options = screen.query_one("#prompt-template-list")
        assert [option.id for option in options.options] == ["new"]


@pytest.mark.asyncio
async def test_prompt_refresh_discovers_templates_created_after_launch(
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    config_store = ConfigStore(tmp_path / "config.json")
    config_store.save(
        GhostwriterConfig(
            prompt_templates=PromptTemplateConfig(directory=prompts)
        )
    )
    app = GhostwriterApp(config_store=config_store)
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)):
        assert app.prompt_templates == []
        (prompts / "new.md").write_text(
            "---\nname: new\ndescription: New Prompt\n---\nNew prompt",
            encoding="utf-8",
        )

        app.action_refresh_targets()

        assert [template.name for template in app.prompt_templates] == ["new"]


@pytest.mark.asyncio
async def test_at_completion_attaches_project_file_with_relative_marker(tmp_path: Path) -> None:
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

        assert app.query_one("#prompt-completions").display
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "Review @src/context.md "
        assert app.draft.attachments[0].source == source.resolve()
        assert app.query_one("#attachments").row_count == 1


@pytest.mark.asyncio
async def test_same_filename_in_different_project_folders_stays_unambiguous(
    tmp_path: Path,
) -> None:
    first = tmp_path / "one" / "context.md"
    second = tmp_path / "two" / "context.md"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)):
        app._project_root = lambda: tmp_path
        app._add_attachment(first)
        app._add_attachment(second)

        assert [attachment.display_path for attachment in app.draft.attachments] == [
            "one/context.md",
            "two/context.md",
        ]
        assert "@one/context.md" in app.query_one("#prompt-editor").text
        assert "@two/context.md" in app.query_one("#prompt-editor").text


@pytest.mark.asyncio
async def test_second_at_completion_works_on_the_same_line(tmp_path: Path) -> None:
    first = tmp_path / "first-context.md"
    second = tmp_path / "second-context.md"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._project_root = lambda: tmp_path
        app._add_attachment(first)
        editor = app.query_one("#prompt-editor")
        editor.insert("and @second")
        app._update_file_completions()

        assert app.query_one("#prompt-completions").display
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "@first-context.md and @second-context.md "
        assert [attachment.source for attachment in app.draft.attachments] == [
            first.resolve(),
            second.resolve(),
        ]


@pytest.mark.asyncio
async def test_system_file_search_is_debounced_while_typing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def find_system(_root: Path, query: str, **_kwargs: object) -> list[object]:
        calls.append(query)
        return []

    monkeypatch.setattr("ghostwriter.app.SYSTEM_COMPLETION_DEBOUNCE", 0.01)
    monkeypatch.setattr("ghostwriter.app.find_system_file_completions", find_system)
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)):
        app._project_root = lambda: tmp_path
        app._file_index_root = tmp_path
        editor = app.query_one("#prompt-editor")
        for query in ("bug", "bug1"):
            editor.load_text(f"@{query}")
            editor.cursor_location = (0, len(query) + 1)
            app._update_file_completions()
        await asyncio.sleep(0.05)

        assert calls == ["bug1"]


@pytest.mark.asyncio
async def test_at_completion_attaches_project_directory(tmp_path: Path) -> None:
    source = tmp_path / "reference-notes"
    source.mkdir()
    (source / "context.md").write_text("context", encoding="utf-8")
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        app._project_root = lambda: tmp_path
        editor = app.query_one("#prompt-editor")
        editor.load_text("Review @reference")
        editor.cursor_location = (0, len(editor.text))
        app._update_file_completions()

        assert app.query_one("#prompt-completions").display
        assert app._handle_completion_key("tab")
        await pilot.pause()

        assert editor.text == "Review @reference-notes/ "
        assert app.draft.attachments[0].source == source.resolve()
        assert app.draft.attachments[0].kind == "directory"
        app._show_attachment_preview(app.draft.attachments[0])
        assert app.query_one("#preview-message").render().plain == (
            "Directory preview unavailable"
        )


def test_command_palette_omits_screenshot_and_only_offers_comfortable_themes() -> None:
    app = GhostwriterApp()

    command_titles = {
        command.title for command in app.get_system_commands(app.get_default_screen())
    }

    assert "Screenshot" not in command_titles
    assert {"Open config", "Refresh", "Theme", "Quit", "Keys"} <= command_titles
    assert set(app.available_themes) == set(app.COMFORTABLE_THEMES)
    assert all(theme.dark for theme in app.available_themes.values())


@pytest.mark.asyncio
async def test_theme_palette_opens_on_current_theme(tmp_path: Path) -> None:
    app = GhostwriterApp(config_store=ConfigStore(tmp_path / "config.json"))
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test():
        app.theme = "nord"
        provider = CurrentThemeProvider(app.screen)

        assert provider.commands[0][0] == "nord"


@pytest.mark.asyncio
async def test_selected_theme_is_saved_and_restored(tmp_path: Path) -> None:
    config_store = ConfigStore(tmp_path / "config.json")
    app = GhostwriterApp(config_store=config_store)
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test() as pilot:
        app.theme = "rose-pine-moon"
        await pilot.pause()

    assert config_store.reload().ui.theme == "rose-pine-moon"
    restored = GhostwriterApp(config_store=config_store)
    assert restored.theme == "rose-pine-moon"


@pytest.mark.asyncio
async def test_prompt_soft_wraps_without_horizontal_scrolling(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="word " * 100)
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(80, 30)):
        editor = app.query_one("#prompt-editor")

        assert editor.soft_wrap
        assert editor.styles.overflow_x == "hidden"
        assert editor.max_scroll_x == 0


@pytest.mark.asyncio
async def test_prompt_wraps_mixed_cjk_text_without_a_phantom_newline(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(80, 30)):
        editor = app.query_one("#prompt-editor")
        width = editor.wrap_width
        prefix = "a " * ((width - 8) // 2)
        text = prefix + "english这是一段测试中文"
        editor.load_text(text)
        sections = editor.wrapped_document.get_sections(0)

        assert "".join(sections) == text
        assert "\n" not in editor.text
        assert len(sections) == 2
        assert cell_len(sections[0]) >= width - 2

        editor.cursor_location = (0, len(text))
        editor.insert("继续")
        assert "".join(editor.wrapped_document.get_sections(0)) == text + "继续"


@pytest.mark.asyncio
async def test_header_only_shows_settings_menu(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.store = DraftStore(tmp_path / "draft.json")
    opened: list[bool] = []
    reloaded: list[bool] = []
    refreshed: list[bool] = []
    app._open_config = lambda: opened.append(True)  # type: ignore[method-assign]
    app._reload_config = lambda: reloaded.append(True)  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)) as pilot:
        top_bar = app.query_one("#top-bar")
        settings = app.query_one("#settings-menu")

        assert settings.label.plain == "Settings"
        assert settings.region.x == top_bar.region.x
        assert not app.query("#app-title")
        assert not app.query("Header")

        app.action_refresh_targets = lambda: refreshed.append(True)  # type: ignore[method-assign]
        commands = {command.title: command for command in app.get_system_commands(app.screen)}
        commands["Open config"].callback()
        commands["Refresh"].callback()
        assert opened == [True]
        assert reloaded == [True]
        assert refreshed == [True]

        await pilot.click("#settings-menu")
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


@pytest.mark.asyncio
async def test_refresh_command_rebuilds_file_index(tmp_path: Path) -> None:
    app = GhostwriterApp(config_store=ConfigStore(tmp_path / "config.json"))
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")
    app.pi.discover_targets = list  # type: ignore[method-assign]

    async with app.run_test(size=(120, 40)):
        app._project_root = lambda: tmp_path
        app._file_index_root = tmp_path
        app._file_index = []
        added = tmp_path / "added-after-launch.md"
        added.touch()

        app._reload_config_command()
        editor = app.query_one("#prompt-editor")
        editor.load_text("@added-after")
        editor.cursor_location = (0, len(editor.text))
        app._update_file_completions()

        options = app.query_one("#prompt-completions")
        assert options.display
        assert options.options[0].prompt == "added-after-launch.md"


@pytest.mark.asyncio
async def test_prompt_text_stays_white_across_themes(tmp_path: Path) -> None:
    app = GhostwriterApp(config_store=ConfigStore(tmp_path / "config.json"))
    app.draft = Draft(text="Plain text")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        editor = app.query_one("#prompt-editor")
        for theme in app.COMFORTABLE_THEMES:
            app.theme = theme
            await pilot.pause()
            assert editor.styles.color.hex == "#FFFFFF"


@pytest.mark.asyncio
async def test_theme_colors_accent_controls_without_tinting_content_panels(tmp_path: Path) -> None:
    app = GhostwriterApp(config_store=ConfigStore(tmp_path / "config.json"))
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        for theme in app.COMFORTABLE_THEMES:
            app.theme = theme
            await pilot.pause()
            primary = app.current_theme.primary

            assert app.query_one(".section-title").styles.color.hex == primary.upper()
            assert app.query_one(".tool-button").styles.background.hex == primary.upper()
            assert app.query_one("#target SelectCurrent").styles.background.a == 0
            assert app.query_one("#attachments").styles.background.a == 0


@pytest.mark.asyncio
async def test_layout_uses_aspect_ratio_and_splitter_is_draggable(tmp_path: Path) -> None:
    app = GhostwriterApp()
    app.draft = Draft(text="")
    app.store = DraftStore(tmp_path / "draft.json")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
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

    compact_app = GhostwriterApp()
    compact_app.draft = Draft(text="")
    compact_app.store = DraftStore(tmp_path / "compact-draft.json")
    async with compact_app.run_test(size=(95, 40)) as pilot:
        await pilot.pause()
        workspace = compact_app.query_one("#workspace")
        side_pane = compact_app.query_one("#side-pane")
        refresh = compact_app.query_one("#refresh-targets")

        assert not compact_app.screen.has_class("stacked")
        assert workspace.max_scroll_x == 0
        assert side_pane.region.right <= workspace.content_region.right
        assert refresh.region.right <= workspace.content_region.right

    tall_app = GhostwriterApp()
    tall_app.draft = Draft(text="")
    tall_app.store = DraftStore(tmp_path / "tall-draft.json")
    async with tall_app.run_test(size=(100, 70)):
        assert tall_app.screen.has_class("stacked")
