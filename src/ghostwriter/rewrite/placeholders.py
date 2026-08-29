from __future__ import annotations

import re
import secrets
from collections import Counter
from dataclasses import dataclass

from ghostwriter.model import Attachment


class PlaceholderIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlaceholderBinding:
    placeholder: str
    editor_token: str


class AttachmentProtector:
    def __init__(
        self,
        text: str,
        attachments: list[Attachment],
        *,
        nonce: str | None = None,
    ) -> None:
        self.nonce = nonce or secrets.token_hex(8).upper()
        bindings: list[PlaceholderBinding] = []
        index = 0
        for attachment in attachments:
            for _ in range(text.count(attachment.editor_token)):
                placeholder = f"__GW_{self.nonce}_ATTACHMENT_{index:04d}__"
                bindings.append(PlaceholderBinding(placeholder, attachment.editor_token))
                index += 1
        self.bindings = bindings
        self._placeholder_pattern = re.compile(
            rf"__GW_{re.escape(self.nonce)}_ATTACHMENT_\d{{4}}__"
        )

    def protect(self, text: str) -> str:
        protected = text
        grouped: dict[str, list[str]] = {}
        for binding in self.bindings:
            grouped.setdefault(binding.editor_token, []).append(binding.placeholder)

        for editor_token, placeholders in grouped.items():
            if protected.count(editor_token) != len(placeholders):
                raise PlaceholderIntegrityError(
                    f"Attachment marker count changed for {editor_token}. "
                    "Restore the missing marker or remove the attachment."
                )
            for placeholder in placeholders:
                protected = protected.replace(editor_token, placeholder, 1)
        return protected

    def restore(self, protected: str) -> str:
        expected = {binding.placeholder for binding in self.bindings}
        found = self._placeholder_pattern.findall(protected)
        counts = Counter(found)
        if len(found) != len(expected) or set(found) != expected:
            missing = sorted(expected - counts.keys())
            duplicated = sorted(item for item, count in counts.items() if count > 1)
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if duplicated:
                details.append(f"duplicated {', '.join(duplicated)}")
            if not details:
                details.append("unexpected placeholder token")
            raise PlaceholderIntegrityError(
                "The model changed protected attachment placeholders: " + "; ".join(details)
            )

        restored = protected
        for binding in self.bindings:
            restored = restored.replace(binding.placeholder, binding.editor_token)
        return restored
