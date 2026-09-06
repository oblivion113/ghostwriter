from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from rich.style import Style
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from .prompt_templates import PromptTemplate

PromptAction = Literal["insert", "expand"]
PromptFolderOpener = Callable[[Path], None]


@dataclass(frozen=True, slots=True)
class PromptDecision:
    action: PromptAction
    template: PromptTemplate | None = None


class PromptTemplateScreen(ModalScreen[PromptDecision | None]):
    """Select a Prompt template without changing the draft until confirmation."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("f3", "expand", "Expand", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        templates: list[PromptTemplate],
        directory: Path,
        *,
        open_folder: PromptFolderOpener,
    ) -> None:
        super().__init__()
        self.templates = list(templates)
        self.directory = directory
        self._open_folder_callback = open_folder

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-template-dialog"):
            yield Label("PROMPTS", classes="dialog-title")
            yield Static(
                "Select a template to insert its reusable reference at the cursor.",
                classes="dialog-help",
            )
            yield OptionList(id="prompt-template-list", markup=False, compact=True)
            yield Static(
                "No Prompt templates found. Open the folder to add one, then refresh.",
                id="prompt-template-empty",
                markup=False,
            )
            with Horizontal(classes="dialog-actions prompt-template-actions"):
                yield Button(
                    "Insert",
                    id="prompt-template-insert",
                    classes="tool-button primary-action",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Expand",
                    id="prompt-template-expand",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Open folder",
                    id="prompt-template-open-folder",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Cancel",
                    id="prompt-template-cancel",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )

    def on_mount(self) -> None:
        self._populate_templates()

    @staticmethod
    def _template_prompt(template: PromptTemplate) -> Text:
        prompt = Text(no_wrap=True, overflow="ellipsis")
        prompt.append(template.name, style=Style(bold=True))
        prompt.append("\n")
        prompt.append(
            " ".join(template.description.split()) or " ",
            style=Style(color="#9199a6"),
        )
        return prompt

    def _populate_templates(self) -> None:
        options = self.query_one("#prompt-template-list", OptionList)
        highlighted = options.highlighted_option
        previous_name = str(highlighted.id) if highlighted is not None else None
        options.clear_options()
        options.add_options(
            Option(self._template_prompt(template), id=template.name)
            for template in self.templates
        )
        empty = not self.templates
        options.display = not empty
        self.query_one("#prompt-template-empty", Static).display = empty
        self.query_one("#prompt-template-insert", Button).disabled = empty
        if empty:
            self.query_one("#prompt-template-open-folder", Button).focus()
            return
        names = [template.name for template in self.templates]
        options.highlighted = names.index(previous_name) if previous_name in names else 0
        options.focus()

    def _selected_template(self) -> PromptTemplate | None:
        options = self.query_one("#prompt-template-list", OptionList)
        index = options.highlighted
        if index is None or index < 0 or index >= len(self.templates):
            return None
        return self.templates[index]

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_expand(self) -> None:
        self.dismiss(PromptDecision("expand"))

    def _insert_selected(self) -> None:
        template = self._selected_template()
        if template is None:
            self.notify("Select a Prompt template first", severity="warning")
            return
        self.dismiss(PromptDecision("insert", template))

    @on(Button.Pressed)
    def button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "prompt-template-insert":
                self._insert_selected()
            case "prompt-template-expand":
                self.action_expand()
            case "prompt-template-open-folder":
                try:
                    self._open_folder_callback(self.directory)
                except OSError as error:
                    self.notify(f"Could not open Prompt folder: {error}", severity="error")
                else:
                    self.notify(
                        "Prompt folder opened. Use Settings → Refresh after making changes."
                    )
            case "prompt-template-cancel":
                self.action_cancel()
