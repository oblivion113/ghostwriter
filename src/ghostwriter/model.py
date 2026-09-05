from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

AttachmentKind = Literal["file", "image", "directory"]


@dataclass(slots=True)
class Attachment:
    kind: AttachmentKind
    source_path: str
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def source(self) -> Path:
        return Path(self.source_path)

    @property
    def display_name(self) -> str:
        suffix = "/" if self.kind == "directory" else ""
        return f"{self.source.name}{suffix}"

    @property
    def editor_token(self) -> str:
        return f"@{self.display_name}"

    @property
    def legacy_editor_token(self) -> str:
        safe_name = self.source.name.replace("[", "(").replace("]", ")")
        return f"[[GW:{self.kind}:{self.id[:12]}:{safe_name}]]"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Attachment:
        kind = data.get("kind")
        source_path = data["source_path"]
        if kind == "file" and Path(source_path).is_dir():
            kind = "directory"
        if kind not in {"file", "image", "directory"}:
            raise ValueError(f"Unsupported attachment kind: {kind!r}")
        return cls(
            kind=kind,
            source_path=source_path,
            id=data.get("id") or uuid4().hex,
        )


@dataclass(slots=True)
class Draft:
    text: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)
    revision: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 4,
            "id": self.id,
            "revision": self.revision,
            "text": self.text,
            "attachments": [attachment.to_dict() for attachment in self.attachments],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Draft:
        raw_attachments = data.get("attachments", [])
        attachments = [
            Attachment.from_dict(item)
            for item in raw_attachments
            if isinstance(item, dict)
        ]
        text = str(data.get("text", ""))
        version = int(data.get("version", 1))
        if version < 2:
            for attachment in attachments:
                text = text.replace(attachment.legacy_editor_token, attachment.editor_token)
        if 2 <= version < 4:
            for attachment in attachments:
                if attachment.kind == "directory" and attachment.editor_token not in text:
                    text = text.replace(f"@{attachment.source.name}", attachment.editor_token)
        return cls(
            text=text,
            attachments=attachments,
            id=str(data.get("id") or uuid4().hex),
            revision=int(data.get("revision", 0)),
        )
