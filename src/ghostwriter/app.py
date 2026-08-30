from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Resize
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    OptionList,
    Select,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option
from textual_image.widget import Image

from .config import ConfigStore, RewriteConfig, open_config_file
from .files import (
    FileCompletion,
    build_file_index,
    choose_native_paths,
    existing_paths,
    find_file_completions,
    looks_like_image,
    read_text_preview,
)
from .model import Attachment
from .pi import PiBridgeClient, PiTarget
from .rewrite import (
    PiRpcError,
    PiRpcSession,
    PlaceholderIntegrityError,
    RewriteOptions,
    RewriteSession,
)
from .rewrite.screens import RewriteConfigScreen, RewriteReviewScreen
from .storage import DraftStore, ImageCache


class DragHandle(Static):
    class Dragged(Message):
        def __init__(self, handle: DragHandle, screen_x: float, screen_y: float) -> None:
            super().__init__()
            self.handle = handle
            self.screen_x = screen_x
            self.screen_y = screen_y

        @property
        def control(self) -> DragHandle:
            return self.handle

    def __init__(self, *, id: str) -> None:
        super().__init__("", id=id)
        self._dragging = False

    def render(self) -> str:
        horizontal = self.id == "height-handle" or self.screen.has_class("stacked")
        if horizontal:
            return "─" * self.size.width
        return "\n".join("│" for _ in range(self.size.height))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            return
        self._dragging = True
        self.capture_mouse()
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        self.post_message(self.Dragged(self, event.screen_x, event.screen_y))
        event.stop()
        event.prevent_default()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.release_mouse()
        event.stop()
        event.prevent_default()


class PromptTextArea(TextArea):
    COMPONENT_CLASSES = TextArea.COMPONENT_CLASSES | {"prompt-attachment"}

    def get_line(self, line_index: int) -> Text:
        line = super().get_line(line_index)
        app = self.app
        if not isinstance(app, GhostwriterApp):
            return line
        attachment_style = self.get_component_rich_style("prompt-attachment")
        for attachment in app.draft.attachments:
            token = attachment.editor_token
            start = 0
            while (index := line.plain.find(token, start)) >= 0:
                line.stylize(attachment_style, index, index + len(token))
                start = index + len(token)
        return line

    def _on_paste(self, event: events.Paste) -> None:
        app = self.app
        if isinstance(app, GhostwriterApp) and app._attach_pasted_paths(event.text):
            event.stop()
            event.prevent_default()

    def _on_key(self, event: events.Key) -> None:
        app = self.app
        if isinstance(app, GhostwriterApp) and app._handle_completion_key(event.key):
            event.stop()
            event.prevent_default()


class GhostwriterApp(App[None]):
    TITLE = "Ghostwriter"
    SUB_TITLE = "Compose here. Submit in Pi."
    NO_TARGET_ID = "__no-active-pi-session__"
    NO_TARGET_LABEL = "No active Pi session"
    CSS_PATH = "ghostwriter.tcss"
    COMFORTABLE_THEMES = frozenset(
        {
            "textual-dark",
            "nord",
            "gruvbox",
            "catppuccin-mocha",
            "tokyo-night",
            "rose-pine-moon",
        }
    )

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+enter", "inject", "Inject into Pi", priority=True),
        Binding("ctrl+o", "choose_file", "Attach files"),
        Binding("ctrl+r", "refresh_targets", "Refresh Pi targets"),
        Binding("ctrl+s", "save", "Save draft"),
        Binding("f4", "rewrite", "Translate / tidy"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, initial_paths: list[Path] | None = None) -> None:
        super().__init__()
        if self.theme not in self.COMFORTABLE_THEMES:
            self.theme = "textual-dark"
        for theme_name in set(self.available_themes) - self.COMFORTABLE_THEMES:
            self.unregister_theme(theme_name)
        self.store = DraftStore()
        self.config_store = ConfigStore()
        self.image_cache = ImageCache()
        self.draft = self.store.load()
        self.config = self.config_store.load()
        self.pi = PiBridgeClient()
        self.targets: dict[str, PiTarget] = {}
        self.selected_target_id: str | None = None
        self.selected_attachment_id: str | None = None
        self.initial_paths = initial_paths or []
        rewrite_config = self.config.rewrite
        default_agent = rewrite_config.default_agent
        self.rewrite_defaults = RewriteOptions(
            target_language=rewrite_config.default_target_language,
            provider=default_agent.provider,
            model=default_agent.model,
            agent=default_agent.label,
            instructions=rewrite_config.instructions,
            prompt=rewrite_config.prompt,
        )
        self.rewrite_rpc = PiRpcSession()
        self._completion_candidates: list[FileCompletion] = []
        self._file_index_root: Path | None = None
        self._file_index: list[Path] = []
        self._stacked = False
        self._horizontal_split = 0.74
        self._vertical_split = 0.52
        self._prompt_split = 0.8

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Keep Textual's useful commands, excluding SVG screenshot export."""
        yield from (
            command
            for command in super().get_system_commands(screen)
            if command.title != "Screenshot"
        )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="editor-pane"):
                yield Label("PROMPT", classes="section-title")
                with Vertical(id="prompt-region"):
                    yield PromptTextArea(
                        self.draft.text,
                        id="prompt-editor",
                        soft_wrap=True,
                        show_line_numbers=False,
                        placeholder="Compose here, drag files, or type @ to attach…",
                    )
                    yield OptionList(id="file-completions", markup=False, compact=True)
                yield DragHandle(id="height-handle")
                with Horizontal(id="actions"):
                    yield Button(
                        "Attach",
                        id="add-attachment",
                        classes="tool-button",
                        compact=True,
                        flat=True,
                        tooltip="Choose one or more files (Ctrl+O)",
                    )
                    yield Button(
                        "Inject",
                        id="inject",
                        classes="tool-button primary-action",
                        compact=True,
                        flat=True,
                        tooltip="Inject into Pi (Ctrl+Enter)",
                    )
                    yield Button(
                        "Rewrite",
                        id="rewrite",
                        classes="tool-button",
                        compact=True,
                        flat=True,
                        tooltip="Translate or tidy (F4)",
                    )
                    yield Button(
                        "Save",
                        id="save",
                        classes="tool-button",
                        compact=True,
                        flat=True,
                        tooltip="Save draft (Ctrl+S)",
                    )
            yield DragHandle(id="width-handle")
            with VerticalScroll(id="side-pane"):
                yield Label("PI TARGET", classes="section-title")
                with Horizontal(id="target-row"):
                    yield Select(
                        [(self.NO_TARGET_LABEL, self.NO_TARGET_ID)],
                        value=self.NO_TARGET_ID,
                        allow_blank=False,
                        id="target",
                        compact=True,
                        disabled=True,
                    )
                    yield Button(
                        "↻",
                        id="refresh-targets",
                        classes="tool-button icon-button",
                        compact=True,
                        flat=True,
                        tooltip="Refresh Pi targets (Ctrl+R)",
                    )
                yield Label("ATTACHMENTS", classes="section-title")
                yield DataTable(id="attachments", cursor_type="row")
                yield Button(
                    "Remove",
                    id="remove-attachment",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                    tooltip="Remove selected attachment",
                )
                yield Label("PREVIEW", classes="section-title")
                yield Static("", id="preview-path", markup=False)
                yield Static("Select an attachment", id="preview-message", markup=False)
                yield TextArea(
                    "",
                    id="text-preview",
                    read_only=True,
                    soft_wrap=False,
                    show_line_numbers=False,
                )
                yield Image(None, id="image-preview")
        yield Static("Ready", id="status")
        yield Footer()

    def on_resize(self, event: Resize) -> None:
        stacked = event.size.width < 95 or event.size.width < event.size.height * 1.8
        if stacked != self._stacked:
            self._stacked = stacked
            self.screen.set_class(stacked, "stacked")
        self._apply_split()
        self.call_after_refresh(self._apply_split)

    def on_mount(self) -> None:
        table = self.query_one("#attachments", DataTable)
        table.add_column("Attachment")
        self.query_one("#file-completions", OptionList).display = False
        self.query_one("#image-preview", Image).display = False
        self.query_one("#text-preview", TextArea).display = False
        self.query_one("#preview-path", Static).display = False
        self.call_after_refresh(self._apply_split)
        if self.config_store.recovered_path is not None:
            self.notify(
                f"Invalid config was moved to {self.config_store.recovered_path}",
                severity="warning",
            )
        if self._reconcile_attachments(self.draft.text):
            self.store.save(self.draft)
        else:
            self._refresh_attachment_table()
        self.action_refresh_targets()
        if self.config.rewrite.keep_rpc_warm and not self.is_headless:
            self.run_worker(self._warm_rewrite_rpc(), exclusive=True, group="rewrite-warmup")
        for path in self.initial_paths:
            try:
                self._add_attachment(path)
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error")
        self.query_one("#prompt-editor", TextArea).focus()

    async def on_unmount(self) -> None:
        self.store.save(self.draft)
        await self.rewrite_rpc.close()

    async def _warm_rewrite_rpc(self) -> None:
        try:
            await self.rewrite_rpc.start()
        except (OSError, PiRpcError, TimeoutError) as error:
            self.notify(f"Rewrite RPC warm-up failed: {error}", severity="warning")

    def _open_config(self) -> None:
        open_config_file(self.config_store.path)

    def _reload_config(self) -> RewriteConfig:
        previous_rewrite = self.config.rewrite
        previous_file_search = self.config.file_search
        config = self.config_store.reload()
        self.config = config
        rewrite = config.rewrite
        current = self.rewrite_defaults
        agent_labels = {agent.label for agent in rewrite.agents}
        agent = rewrite.agent(
            current.agent if current.agent in agent_labels else rewrite.default_agent.label
        )
        target_language = (
            current.target_language
            if current.target_language in rewrite.target_languages
            else rewrite.default_target_language
        )
        self.rewrite_defaults = RewriteOptions(
            translate=current.translate,
            tidy=current.tidy,
            source_language=current.source_language,
            target_language=target_language,
            provider=agent.provider,
            model=agent.model,
            agent=agent.label,
            instructions=rewrite.instructions,
            prompt=rewrite.prompt,
        )
        if config.file_search != previous_file_search:
            self._file_index_root = None
        if rewrite.keep_rpc_warm and not previous_rewrite.keep_rpc_warm and not self.is_headless:
            self.run_worker(self._warm_rewrite_rpc(), exclusive=True, group="rewrite-warmup")
        return rewrite

    def _capture_text(self) -> None:
        self.draft.text = self.query_one("#prompt-editor", TextArea).text

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _save(self) -> None:
        self._capture_text()
        self.store.save(self.draft)
        self._set_status("Draft saved")

    def _refresh_attachment_table(self) -> None:
        table = self.query_one("#attachments", DataTable)
        table.clear()
        for attachment in self.draft.attachments:
            table.add_row(attachment.source.name, key=attachment.id)

    def _add_attachment(self, path: Path) -> None:
        source = path.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"Not a file: {source}")
        if any(item.source == source for item in self.draft.attachments):
            raise ValueError(f"Already attached: {source}")

        kind = "image" if looks_like_image(source) else "file"
        injected = self.image_cache.stage(source) if kind == "image" else source
        attachment = Attachment(kind=kind, source_path=str(source), injected_path=str(injected))
        if any(item.editor_token == attachment.editor_token for item in self.draft.attachments):
            raise ValueError(f"An attachment named {source.name!r} is already present")

        self.draft.attachments.append(attachment)
        editor = self.query_one("#prompt-editor", TextArea)
        row, column = editor.cursor_location
        line = editor.text.split("\n")[row]
        prefix = "" if column == 0 or line[column - 1].isspace() else " "
        suffix = "" if column < len(line) and line[column].isspace() else " "
        editor.insert(f"{prefix}{attachment.editor_token}{suffix}")
        self._refresh_attachment_table()
        self.store.save(self.draft)
        self._set_status(f"Attached {source.name}")

    def _add_paths(self, paths: list[Path]) -> None:
        failures: list[str] = []
        for path in paths:
            try:
                self._add_attachment(path)
            except (OSError, ValueError) as error:
                failures.append(str(error))
        if failures:
            self.notify("\n".join(failures), severity="error")
        self.query_one("#prompt-editor", TextArea).focus()

    def _attach_pasted_paths(self, value: str) -> bool:
        paths = existing_paths(value)
        if not paths:
            return False
        editor = self.query_one("#prompt-editor", TextArea)
        if not editor.selection.is_empty:
            result = editor.replace("", *editor.selection, maintain_selection_offset=False)
            editor.move_cursor(result.end_location)
        self._add_paths(paths)
        return True

    def _open_file_picker(self) -> None:
        def choose() -> None:
            try:
                paths = choose_native_paths()
            except OSError as error:
                self.call_from_thread(self.notify, str(error), severity="error")
                return
            if paths:
                self.call_from_thread(self._add_paths, paths)

        self.run_worker(choose, thread=True, exclusive=True, group="file-picker")

    def _project_root(self) -> Path:
        target = self._selected_target()
        root = target.cwd if target is not None else Path.cwd()
        return root.expanduser().resolve()

    def _completion_context(self) -> tuple[str, tuple[int, int], tuple[int, int]] | None:
        editor = self.query_one("#prompt-editor", TextArea)
        row, column = editor.cursor_location
        lines = editor.text.split("\n")
        if row >= len(lines):
            return None
        before_cursor = lines[row][:column]
        match = re.search(r"(?<!\S)@(.*)$", before_cursor)
        if match is None:
            return None
        return match.group(1), (row, match.start()), (row, column)

    def _update_file_completions(self) -> None:
        context = self._completion_context()
        if context is None:
            self._hide_file_completions()
            return
        query, _, _ = context
        if any(attachment.editor_token == f"@{query}" for attachment in self.draft.attachments):
            self._hide_file_completions()
            return

        root = self._project_root()
        search = self.config.file_search
        if self._file_index_root != root:
            self._file_index_root = root
            self._file_index = build_file_index(
                root,
                include_hidden=search.include_hidden,
                skipped_directories=search.skipped_directories,
                ignore_files=search.ignore_files,
            )
        candidates = find_file_completions(
            root,
            query,
            self._file_index,
            include_hidden=search.include_hidden,
            fzf_options=search.fzf_options,
            use_global_fzf_options=search.use_global_fzf_options,
        )
        if not candidates:
            self._hide_file_completions()
            return

        self._completion_candidates = candidates
        options = self.query_one("#file-completions", OptionList)
        options.clear_options()
        options.add_options(Option(candidate.label, id=str(index)) for index, candidate in enumerate(candidates))
        options.highlighted = 0
        options.display = True

    def _hide_file_completions(self) -> None:
        self._completion_candidates = []
        self.query_one("#file-completions", OptionList).display = False

    def _handle_completion_key(self, key: str) -> bool:
        options = self.query_one("#file-completions", OptionList)
        if not options.display or not self._completion_candidates:
            return False
        if key == "tab":
            self._accept_file_completion(options.highlighted or 0)
        elif key == "down":
            current = options.highlighted or 0
            options.highlighted = (current + 1) % len(self._completion_candidates)
        elif key == "up":
            current = options.highlighted or 0
            options.highlighted = (current - 1) % len(self._completion_candidates)
        elif key == "escape":
            self._hide_file_completions()
        else:
            return False
        return True

    def _accept_file_completion(self, index: int) -> None:
        if index < 0 or index >= len(self._completion_candidates):
            return
        context = self._completion_context()
        if context is None:
            self._hide_file_completions()
            return
        _, start, end = context
        candidate = self._completion_candidates[index]
        editor = self.query_one("#prompt-editor", TextArea)
        replacement = f"@{candidate.label}" if candidate.is_directory else ""
        result = editor.replace(replacement, start, end, maintain_selection_offset=False)
        editor.move_cursor(result.end_location)
        if candidate.is_directory:
            self._update_file_completions()
        else:
            self._hide_file_completions()
            try:
                self._add_attachment(candidate.path)
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error")
        editor.focus()

    def _apply_split(self) -> None:
        editor = self.query_one("#editor-pane", Vertical)
        prompt = self.query_one("#prompt-region", Vertical)
        side = self.query_one("#side-pane", VerticalScroll)
        if editor.size.height:
            desired_prompt_height = round(editor.size.height * self._prompt_split)
            prompt.styles.height = min(desired_prompt_height, max(8, editor.size.height - 4))
        else:
            prompt.styles.height = f"{self._prompt_split * 100:.1f}%"
        if self._stacked:
            editor.styles.width = "1fr"
            editor.styles.height = f"{self._vertical_split * 100:.1f}%"
            side.styles.width = "1fr"
            side.styles.height = "1fr"
        else:
            editor.styles.width = f"{self._horizontal_split * 100:.1f}%"
            editor.styles.height = "1fr"
            side.styles.width = "1fr"
            side.styles.height = "1fr"

    def _selected_target(self) -> PiTarget | None:
        if self.selected_target_id is None:
            return None
        return self.targets.get(self.selected_target_id)

    async def _inject(self) -> None:
        target = self._selected_target()
        if target is None:
            self.notify(
                "No active Pi session is available. Start Pi with the Ghostwriter extension loaded.",
                severity="warning",
            )
            return

        self._capture_text()
        try:
            serialized = self.pi.serialize(self.draft, target)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error")
            return
        if not serialized.strip():
            self.notify("The draft is empty", severity="warning")
            return

        self.draft.revision += 1
        self.store.save(self.draft)
        self._set_status(f"Injecting revision {self.draft.revision}…")
        try:
            response = await self.pi.inject(
                target,
                text=serialized,
                draft_id=self.draft.id,
                revision=self.draft.revision,
            )
        except (ConnectionError, OSError, TimeoutError, ValueError) as error:
            self._set_status("Injection failed")
            self.notify(str(error), severity="error")
            self.action_refresh_targets()
            return

        digest = str(response.get("sha256", ""))[:8]
        self._set_status(f"Injected revision {self.draft.revision} · {digest}")
        self.notify("Pi's input box was replaced. Review and submit it in Pi.")

    def action_inject(self) -> None:
        self.run_worker(self._inject(), exclusive=True, group="inject")

    def action_rewrite(self) -> None:
        self.run_worker(self._rewrite(), exclusive=True, group="rewrite")

    async def _rewrite(self) -> None:
        self._capture_text()
        if not self.draft.text.strip():
            self.notify("The draft is empty", severity="warning")
            return

        try:
            self._reload_config()
        except (OSError, TypeError, ValueError) as error:
            self.notify(f"Could not reload config: {error}", severity="warning")
        options = await self.push_screen_wait(
            RewriteConfigScreen(
                self.rewrite_defaults,
                self.config.rewrite,
                self.config_store.path,
                open_config=self._open_config,
                reload_config=self._reload_config,
            )
        )
        if options is None:
            return
        self.rewrite_defaults = options

        button = self.query_one("#rewrite", Button)
        button.disabled = True
        session = RewriteSession(self.draft, options, rpc=self.rewrite_rpc)
        try:
            self._set_status(f"Preparing {options.agent}…")
            await self.rewrite_rpc.prepare(provider=options.provider, model=options.model)
            self._set_status(f"Transforming with {options.agent}…")
            candidate = await session.transform(self.draft.text)
            while True:
                decision = await self.push_screen_wait(RewriteReviewScreen(candidate))
                if decision.action == "reject":
                    self._set_status("Model result rejected; original draft preserved")
                    return
                if decision.action == "accept":
                    try:
                        session.protector.protect(decision.text)
                    except PlaceholderIntegrityError as error:
                        self.notify(str(error), severity="error")
                        candidate = decision.text
                        continue
                    editor = self.query_one("#prompt-editor", TextArea)
                    editor.load_text(decision.text)
                    self.draft.text = decision.text
                    self.store.save(self.draft)
                    self._set_status("Translated / tidied result accepted")
                    self.notify("The transformed draft is back in Ghostwriter. It was not sent to Pi's editor.")
                    return

                self._set_status("Applying revision feedback in the same RPC session…")
                try:
                    candidate = await session.revise(decision.text, decision.feedback)
                except PlaceholderIntegrityError as error:
                    self.notify(str(error), severity="error")
                    candidate = decision.text
        except (OSError, PiRpcError, PlaceholderIntegrityError, TimeoutError, ValueError) as error:
            self._set_status("Translation / tidy failed")
            self.notify(str(error), severity="error")
        finally:
            await session.close()
            if not self.config.rewrite.keep_rpc_warm:
                await self.rewrite_rpc.close()
            button.disabled = False

    def action_choose_file(self) -> None:
        self._open_file_picker()

    def action_refresh_targets(self) -> None:
        self._file_index_root = None
        target_select = self.query_one("#target", Select)
        previous = self.selected_target_id
        found = self.pi.discover_targets()
        self.targets = {target.selection_id: target for target in found}
        options = (
            [
                (target.summary, selection_id)
                for selection_id, target in self.targets.items()
            ]
            if self.targets
            else [(self.NO_TARGET_LABEL, self.NO_TARGET_ID)]
        )
        target_select.set_options(options)
        if self.targets:
            self.selected_target_id = (
                previous if previous in self.targets else next(iter(self.targets))
            )
            target_select.disabled = False
            target_select.value = self.selected_target_id
        else:
            target_select.value = self.NO_TARGET_ID
            target_select.disabled = True
            self.selected_target_id = None
        count = len(self.targets)
        self._set_status(f"Found {count} Pi target{'s' if count != 1 else ''}")

    def action_save(self) -> None:
        self._save()

    @on(DragHandle.Dragged)
    def divider_dragged(self, event: DragHandle.Dragged) -> None:
        workspace = self.query_one("#workspace", Horizontal)
        editor = self.query_one("#editor-pane", Vertical)
        if event.handle.id == "height-handle":
            available = max(1, editor.size.height - 3)
            position = event.screen_y - editor.region.y - 1
            self._prompt_split = min(0.97, max(0.25, position / available))
        elif self._stacked:
            position = event.screen_y - workspace.region.y
            self._vertical_split = min(0.8, max(0.35, position / workspace.size.height))
        else:
            position = event.screen_x - workspace.region.x
            self._horizontal_split = min(0.82, max(0.5, position / workspace.size.width))
        self._apply_split()

    @on(TextArea.Changed, "#prompt-editor")
    def prompt_changed(self, event: TextArea.Changed) -> None:
        self.draft.text = event.text_area.text
        removed = self._reconcile_attachments(self.draft.text)
        if removed:
            count = len(removed)
            self._set_status(f"Removed {count} unreferenced attachment{'s' if count != 1 else ''}")
        else:
            self._set_status("Draft modified")
        self._update_file_completions()

    @on(OptionList.OptionSelected, "#file-completions")
    def file_completion_selected(self, event: OptionList.OptionSelected) -> None:
        self._accept_file_completion(event.option_index)

    @on(Select.Changed, "#target")
    def target_changed(self, event: Select.Changed) -> None:
        target_id = None if event.value is Select.NULL else str(event.value)
        self.selected_target_id = target_id if target_id in self.targets else None
        self._file_index_root = None

    @on(DataTable.RowHighlighted, "#attachments")
    def attachment_highlighted(self, event: DataTable.RowHighlighted) -> None:
        attachment_id = str(event.row_key.value)
        self.selected_attachment_id = attachment_id
        attachment = next(
            (item for item in self.draft.attachments if item.id == attachment_id),
            None,
        )
        self._show_attachment_preview(attachment)

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "add-attachment":
                self._open_file_picker()
            case "inject":
                self.action_inject()
            case "rewrite":
                self.action_rewrite()
            case "save":
                self.action_save()
            case "refresh-targets":
                self.action_refresh_targets()
            case "remove-attachment":
                self._remove_selected_attachment()

    def _show_attachment_preview(self, attachment: Attachment | None) -> None:
        image = self.query_one("#image-preview", Image)
        text_preview = self.query_one("#text-preview", TextArea)
        path = self.query_one("#preview-path", Static)
        message = self.query_one("#preview-message", Static)
        image.display = False
        text_preview.display = False

        if attachment is None:
            path.display = False
            message.display = True
            message.update("Select an attachment")
            return

        path.display = True
        path.update(str(attachment.source))
        if attachment.kind == "image" and attachment.injected.exists():
            image.image = attachment.injected
            image.display = True
            message.display = False
            return

        try:
            preview = read_text_preview(attachment.source)
        except OSError as error:
            preview = None
            unavailable = str(error)
        else:
            unavailable = "Binary file preview unavailable"

        if preview is not None:
            text_preview.load_text(preview)
            text_preview.display = True
            message.display = False
        else:
            message.display = True
            message.update(unavailable)

    def _reset_attachment_preview(self) -> None:
        self._show_attachment_preview(None)

    def _reconcile_attachments(self, text: str) -> list[Attachment]:
        removed = [item for item in self.draft.attachments if item.editor_token not in text]
        if not removed:
            return []
        removed_ids = {item.id for item in removed}
        self.draft.attachments = [
            item for item in self.draft.attachments if item.id not in removed_ids
        ]
        if self.selected_attachment_id in removed_ids:
            self.selected_attachment_id = None
            self._reset_attachment_preview()
        self._refresh_attachment_table()
        return removed

    def _remove_selected_attachment(self) -> None:
        if self.selected_attachment_id is None:
            self.notify("Select an attachment first", severity="warning")
            return
        removed = next(
            (item for item in self.draft.attachments if item.id == self.selected_attachment_id),
            None,
        )
        if removed is None:
            return

        self.draft.attachments = [
            item for item in self.draft.attachments if item.id != self.selected_attachment_id
        ]
        editor = self.query_one("#prompt-editor", TextArea)
        text = editor.text.replace(removed.editor_token, "")
        self.draft.text = text
        editor.load_text(text)
        self.selected_attachment_id = None
        self._refresh_attachment_table()
        self._reset_attachment_preview()
        self.store.save(self.draft)
        self._set_status("Attachment and all of its prompt markers removed")
