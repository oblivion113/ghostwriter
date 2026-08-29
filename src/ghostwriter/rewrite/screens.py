from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static, TextArea

from .service import RewriteOptions


class RewriteConfigScreen(ModalScreen[RewriteOptions | None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, defaults: RewriteOptions) -> None:
        super().__init__()
        self.defaults = defaults

    def compose(self) -> ComposeResult:
        with Vertical(id="rewrite-config-dialog"):
            yield Label("TRANSLATE / TIDY", classes="dialog-title")
            yield Static(
                "Attachments stay local. Only opaque placeholders are sent to the selected Pi model.",
                classes="dialog-help",
            )
            with Horizontal(classes="checkbox-row"):
                yield Checkbox("Translate", self.defaults.translate, id="rewrite-translate")
                yield Checkbox("Tidy and structure", self.defaults.tidy, id="rewrite-tidy")
            yield Label("Source language")
            yield Input(self.defaults.source_language, id="rewrite-source")
            yield Label("Target language")
            yield Input(self.defaults.target_language, id="rewrite-target")
            yield Label("Provider (optional)")
            yield Input(self.defaults.provider, placeholder="anthropic", id="rewrite-provider")
            yield Label("Model (blank uses Pi default)")
            yield Input(
                self.defaults.model,
                placeholder="provider/model-id or model-id",
                id="rewrite-model",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button("Start", id="rewrite-start", variant="success")
                yield Button("Cancel", id="rewrite-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#rewrite-start")
    def start(self) -> None:
        options = RewriteOptions(
            translate=self.query_one("#rewrite-translate", Checkbox).value,
            tidy=self.query_one("#rewrite-tidy", Checkbox).value,
            source_language=self.query_one("#rewrite-source", Input).value.strip(),
            target_language=self.query_one("#rewrite-target", Input).value.strip(),
            provider=self.query_one("#rewrite-provider", Input).value.strip(),
            model=self.query_one("#rewrite-model", Input).value.strip(),
        )
        try:
            options.validate()
        except ValueError as error:
            self.notify(str(error), severity="warning")
            return
        self.dismiss(options)

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
                yield Button("Accept", id="review-accept", variant="success")
                yield Button("Revise", id="review-revise", variant="primary")
                yield Button("Reject", id="review-reject", variant="error")

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
