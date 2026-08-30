from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static, TextArea

from ghostwriter.config import RewriteConfig

from .service import RewriteOptions


class RewriteConfigScreen(ModalScreen[RewriteOptions | None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+enter", "start", "Run rewrite", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        defaults: RewriteOptions,
        config: RewriteConfig | None = None,
        config_path: Path | None = None,
        *,
        open_config: Callable[[], None] | None = None,
        reload_config: Callable[[], RewriteConfig] | None = None,
    ) -> None:
        super().__init__()
        self.defaults = defaults
        self.config = config or RewriteConfig()
        self.config_path = config_path
        self.open_config = open_config
        self.reload_config = reload_config

    def compose(self) -> ComposeResult:
        target_language = (
            self.defaults.target_language
            if self.defaults.target_language in self.config.target_languages
            else self.config.default_target_language
        )
        agent_name = (
            self.defaults.agent
            if self.defaults.agent in {agent.name for agent in self.config.agents}
            else self.config.default_agent
        )
        with VerticalScroll(id="rewrite-config-dialog"):
            yield Label("TRANSLATE / TIDY", classes="dialog-title")
            config_label = str(self.config_path) if self.config_path is not None else "config.json"
            yield Static(
                f"Choose Translate, Tidy, or both. Choices come from {config_label}. "
                "After editing, reload before running. Attachments stay local.",
                classes="dialog-help",
            )
            with Horizontal(classes="checkbox-row"):
                yield Checkbox(
                    "Translate",
                    self.defaults.translate,
                    id="rewrite-translate",
                    compact=True,
                )
                yield Checkbox(
                    "Tidy and structure",
                    self.defaults.tidy,
                    id="rewrite-tidy",
                    compact=True,
                )
            yield Label("Source language")
            yield Input(self.defaults.source_language, id="rewrite-source")
            yield Label("Target language")
            yield Select(
                [(language, language) for language in self.config.target_languages],
                value=target_language,
                allow_blank=False,
                id="rewrite-target",
            )
            yield Label("Rewrite agent")
            yield Select(
                [(agent.name, agent.name) for agent in self.config.agents],
                value=agent_name,
                allow_blank=False,
                id="rewrite-agent",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button(
                    "Run",
                    id="rewrite-start",
                    classes="tool-button primary-action",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Open config",
                    id="rewrite-open-config",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                    disabled=self.open_config is None,
                )
                yield Button(
                    "Reload config",
                    id="rewrite-reload-config",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                    disabled=self.reload_config is None,
                )
                yield Button(
                    "Cancel",
                    id="rewrite-cancel",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_start(self) -> None:
        self._start()

    @on(Button.Pressed, "#rewrite-start")
    def start_button(self) -> None:
        self._start()

    def _start(self) -> None:
        target_value = self.query_one("#rewrite-target", Select).value
        agent_value = self.query_one("#rewrite-agent", Select).value
        target_language = "" if target_value is Select.NULL else str(target_value)
        agent_name = self.config.default_agent if agent_value is Select.NULL else str(agent_value)
        agent = self.config.agent(agent_name)
        options = RewriteOptions(
            translate=self.query_one("#rewrite-translate", Checkbox).value,
            tidy=self.query_one("#rewrite-tidy", Checkbox).value,
            source_language=self.query_one("#rewrite-source", Input).value.strip(),
            target_language=target_language,
            provider=agent.provider,
            model=agent.model,
            agent=agent.name,
            prompt=self.config.prompt,
        )
        try:
            options.validate()
        except ValueError as error:
            self.notify(str(error), severity="warning")
            return
        self.dismiss(options)

    @on(Button.Pressed, "#rewrite-open-config")
    def open_config_button(self) -> None:
        if self.open_config is None:
            return
        try:
            self.open_config()
        except OSError as error:
            self.notify(f"Could not open config: {error}", severity="error")
            return
        self.notify("Config opened. Save it, then select Reload config.")

    @on(Button.Pressed, "#rewrite-reload-config")
    def reload_config_button(self) -> None:
        if self.reload_config is None:
            return
        try:
            config = self.reload_config()
        except (OSError, TypeError, ValueError) as error:
            self.notify(f"Could not reload config: {error}", severity="error")
            return

        target = self.query_one("#rewrite-target", Select)
        agent = self.query_one("#rewrite-agent", Select)
        current_target = None if target.value is Select.NULL else str(target.value)
        current_agent = None if agent.value is Select.NULL else str(agent.value)
        self.config = config
        target.set_options((language, language) for language in config.target_languages)
        agent.set_options((item.name, item.name) for item in config.agents)
        target.value = (
            current_target
            if current_target in config.target_languages
            else config.default_target_language
        )
        agent_names = {item.name for item in config.agents}
        agent.value = current_agent if current_agent in agent_names else config.default_agent
        self.notify("Config reloaded")

    @on(Button.Pressed, "#rewrite-cancel")
    def cancel_button(self) -> None:
        self.dismiss(None)


ReviewAction = Literal["accept", "revise", "reject"]


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    action: ReviewAction
    text: str
    feedback: str = ""


class RewriteReviewScreen(ModalScreen[ReviewDecision]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "reject", "Reject")]

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="rewrite-review-dialog"):
            yield Label("REVIEW MODEL RESULT", classes="dialog-title")
            yield Static(
                "Edit directly, accept it, or describe a revision while the same Pi RPC session remains alive.",
                classes="dialog-help",
            )
            yield TextArea(self.text, id="rewrite-result", soft_wrap=True)
            yield Input(
                placeholder="Revision feedback (for example: preserve the original tone)",
                id="rewrite-feedback",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button(
                    "Accept",
                    id="review-accept",
                    classes="tool-button primary-action",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Revise",
                    id="review-revise",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )
                yield Button(
                    "Reject",
                    id="review-reject",
                    classes="tool-button",
                    compact=True,
                    flat=True,
                )

    def _current_text(self) -> str:
        return self.query_one("#rewrite-result", TextArea).text

    def action_reject(self) -> None:
        self.dismiss(ReviewDecision("reject", self._current_text()))

    @on(Button.Pressed, "#review-accept")
    def accept(self) -> None:
        self.dismiss(ReviewDecision("accept", self._current_text()))

    @on(Button.Pressed, "#review-revise")
    def revise(self) -> None:
        feedback = self.query_one("#rewrite-feedback", Input).value.strip()
        if not feedback:
            self.notify("Enter revision feedback first", severity="warning")
            return
        self.dismiss(ReviewDecision("revise", self._current_text(), feedback))

    @on(Button.Pressed, "#review-reject")
    def reject(self) -> None:
        self.action_reject()
