from __future__ import annotations

import shlex
from pathlib import Path
from typing import ClassVar
from urllib.parse import unquote, urlparse

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)
from textual_image.widget import Image

from .adapters import AdapterRegistry, InjectionRequest, InjectionTarget
from .model import Attachment, AttachmentKind
from .rewrite import PiRpcError, PlaceholderIntegrityError, RewriteOptions, RewriteSession
from .rewrite.screens import RewriteConfigScreen, RewriteReviewScreen
from .storage import DraftStore, ImageCache


class GhostwriterApp(App[None]):
    TITLE = "Ghostwriter"
    SUB_TITLE = "Compose here. Submit in Pi."
    CSS_PATH = "ghostwriter.tcss"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+enter", "inject", "Inject into Pi", priority=True),
        Binding("ctrl+o", "focus_path", "Attach path"),
        Binding("ctrl+r", "refresh_targets", "Refresh Pi targets"),
        Binding("ctrl+s", "save", "Save draft"),
        Binding("f4", "rewrite", "Translate / tidy"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, initial_paths: list[Path] | None = None) -> None:
        super().__init__()
        self.store = DraftStore()
        self.image_cache = ImageCache()
        self.draft = self.store.load()
        self.adapters = AdapterRegistry()
        self.targets: dict[str, InjectionTarget] = {}
        self.selected_attachment_id: str | None = None
        self.initial_paths = initial_paths or []
        self.rewrite_defaults = RewriteOptions()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="editor-pane"):
                yield Label("PROMPT", classes="section-title")
                yield TextArea(
                    self.draft.text,
                    id="prompt-editor",
                    soft_wrap=True,
                    show_line_numbers=False,
                    placeholder="Compose the prompt that Pi should receive…",
                )
                with Horizontal(id="path-row"):
                    yield Input(
                        placeholder="Type or drag a file path here",
                        id="attachment-path",
                    )
                    yield Button("Add file", id="add-file")
                    yield Button("Add image", id="add-image")
                with Horizontal(id="actions"):
                    yield Button("Inject into Pi", id="inject", variant="success")
                    yield Button("Translate / tidy", id="rewrite", variant="primary")
                    yield Button("Save draft", id="save")
            with Vertical(id="side-pane"):
                yield Label("PI TARGET", classes="section-title")
                yield Select([], prompt="No Pi bridge found", id="target", allow_blank=True)
                yield Button("Refresh targets", id="refresh-targets")
                yield Label("ATTACHMENTS", classes="section-title")
                yield DataTable(id="attachments", cursor_type="row", zebra_stripes=True)
                yield Button("Remove selected", id="remove-attachment", variant="error")
                yield Label("PREVIEW", classes="section-title")
                yield Static("Select an image attachment", id="preview-message")
                yield Image(None, id="image-preview")
        yield Static("Ready", id="status")
        yield Footer()

    def on_resize(self, event: Resize) -> None:
        self.screen.set_class(event.size.width < 95, "narrow")

    def on_mount(self) -> None:
        table = self.query_one("#attachments", DataTable)
        table.add_columns("Kind", "Path")
        self.query_one("#image-preview", Image).display = False
        self._refresh_attachment_table()
        self.action_refresh_targets()
        for path in self.initial_paths:
            try:
                self._add_attachment(path, "image" if self._looks_like_image(path) else "file")
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error")
        self.query_one("#prompt-editor", TextArea).focus()

    def on_unmount(self) -> None:
        self.store.save(self.draft)

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
            table.add_row(
                attachment.kind.upper(),
                str(attachment.source),
                key=attachment.id,
            )

    @staticmethod
    def _looks_like_image(path: Path) -> bool:
        return path.suffix.lower() in {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}

    @staticmethod
    def _parse_paths(value: str) -> list[Path]:
        value = value.strip()
        if not value:
            return []
        try:
            parts = shlex.split(value)
        except ValueError:
            parts = [value]
        paths: list[Path] = []
        for part in parts:
            if part.startswith("file://"):
                parsed = urlparse(part)
                part = unquote(parsed.path)
            paths.append(Path(part).expanduser())
        return paths

    def _add_attachment(self, path: Path, kind: AttachmentKind) -> None:
        source = path.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError(f"Not a file: {source}")
        if any(item.kind == kind and item.source == source for item in self.draft.attachments):
            raise ValueError(f"Already attached: {source}")

        injected = self.image_cache.stage(source) if kind == "image" else source
        attachment = Attachment(kind=kind, source_path=str(source), injected_path=str(injected))
        self.draft.attachments.append(attachment)
        editor = self.query_one("#prompt-editor", TextArea)
        prefix = "" if editor.cursor_at_start_of_text else " "
        editor.insert(f"{prefix}{attachment.editor_token} ")
        self._refresh_attachment_table()
        self.store.save(self.draft)
        self._set_status(f"Added {kind}: {source.name}")

    def _add_paths_from_input(self, kind: AttachmentKind) -> None:
        path_input = self.query_one("#attachment-path", Input)
        paths = self._parse_paths(path_input.value)
        if not paths:
            self.notify("Enter or drag a file path first", severity="warning")
            path_input.focus()
            return
        failures: list[str] = []
        for path in paths:
            try:
                self._add_attachment(path, kind)
            except (OSError, ValueError) as error:
                failures.append(str(error))
        if failures:
            self.notify("\n".join(failures), severity="error")
        else:
            path_input.value = ""
            self.query_one("#prompt-editor", TextArea).focus()

    def _selected_target(self) -> InjectionTarget | None:
        value = self.query_one("#target", Select).value
        if value is Select.NULL:
            return None
        return self.targets.get(str(value))

    async def _inject(self) -> None:
        target = self._selected_target()
        if target is None:
            self.notify(
                "No Pi bridge is available. Start Pi with the Ghostwriter extension loaded.",
                severity="warning",
            )
            return

        self._capture_text()
        try:
            serialized = self.adapters.serialize(self.draft, target)
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
            response = await self.adapters.inject(
                target,
                InjectionRequest(
                    text=serialized,
                    draft_id=self.draft.id,
                    revision=self.draft.revision,
                ),
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

        target = self._selected_target()
        defaults = self.rewrite_defaults
        if target is not None and not defaults.model:
            defaults = RewriteOptions(
                translate=defaults.translate,
                tidy=defaults.tidy,
                source_language=defaults.source_language,
                target_language=defaults.target_language,
                provider=str(target.metadata.get("modelProvider", "")),
                model=str(target.metadata.get("modelId", "")),
            )
        options = await self.push_screen_wait(RewriteConfigScreen(defaults))
        if options is None:
            return
        self.rewrite_defaults = options

        button = self.query_one("#rewrite", Button)
        button.disabled = True
        session = RewriteSession(self.draft, options)
        try:
            model_label = options.model or "Pi default model"
            self._set_status(f"Transforming with {model_label}…")
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
            button.disabled = False

    def action_focus_path(self) -> None:
        self.query_one("#attachment-path", Input).focus()

    def action_refresh_targets(self) -> None:
        select = self.query_one("#target", Select)
        previous = None if select.value is Select.NULL else str(select.value)
        found = self.adapters.discover_targets()
        self.targets = {target.selection_id: target for target in found}
        select.set_options((target.label, key) for key, target in self.targets.items())
        if previous in self.targets:
            select.value = previous
        elif self.targets:
            select.value = next(iter(self.targets))
        select.disabled = not bool(self.targets)
        select.prompt = "Choose a Pi instance" if self.targets else "No Pi bridge found"
        count = len(self.targets)
        self._set_status(f"Found {count} Pi target{'s' if count != 1 else ''}")

    def action_save(self) -> None:
        self._save()

    @on(TextArea.Changed, "#prompt-editor")
    def prompt_changed(self, event: TextArea.Changed) -> None:
        self.draft.text = event.text_area.text
        self._set_status("Draft modified")

    @on(Input.Submitted, "#attachment-path")
    def path_submitted(self) -> None:
        paths = self._parse_paths(self.query_one("#attachment-path", Input).value)
        kind: AttachmentKind = "image" if paths and all(self._looks_like_image(path) for path in paths) else "file"
        self._add_paths_from_input(kind)

    @on(DataTable.RowHighlighted, "#attachments")
    def attachment_highlighted(self, event: DataTable.RowHighlighted) -> None:
        attachment_id = str(event.row_key.value)
        self.selected_attachment_id = attachment_id
        attachment = next(
            (item for item in self.draft.attachments if item.id == attachment_id),
            None,
        )
        image = self.query_one("#image-preview", Image)
        message = self.query_one("#preview-message", Static)
        if attachment is not None and attachment.kind == "image" and attachment.injected.exists():
            image.image = attachment.injected
            image.display = True
            message.display = False
        else:
            image.display = False
            message.display = True
            message.update(str(attachment.source) if attachment else "Select an image attachment")

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "add-file":
                self._add_paths_from_input("file")
            case "add-image":
                self._add_paths_from_input("image")
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
        if removed is not None:
            editor = self.query_one("#prompt-editor", TextArea)
            editor.load_text(editor.text.replace(removed.editor_token, ""))
        self.selected_attachment_id = None
        self._refresh_attachment_table()
        self.query_one("#image-preview", Image).display = False
        message = self.query_one("#preview-message", Static)
        message.display = True
        message.update("Select an image attachment")
        self.store.save(self.draft)
        self._set_status("Attachment removed")
