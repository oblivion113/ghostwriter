from __future__ import annotations

from pathlib import Path

from .model import Attachment, Draft


def _display_path(path: Path, cwd: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(cwd.expanduser().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def format_file_reference(path: Path, cwd: Path) -> str:
    value = _display_path(path, cwd)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"Pi file references cannot safely represent this path: {value!r}")
    return f'@"{value}"' if any(character.isspace() for character in value) else f"@{value}"


def _serialize_attachment(attachment: Attachment, cwd: Path) -> str:
    if attachment.kind == "file":
        return format_file_reference(attachment.injected, cwd)
    return attachment.injected.expanduser().resolve().as_posix()


def serialize_draft(draft: Draft, cwd: Path) -> str:
    text = draft.text.rstrip()
    orphaned_references: list[str] = []
    for attachment in draft.attachments:
        reference = _serialize_attachment(attachment, cwd)
        if attachment.editor_token in text:
            text = text.replace(attachment.editor_token, reference)
        else:
            orphaned_references.append(reference)

    if not orphaned_references:
        return text

    attachment_block = "Referenced attachments:\n" + "\n".join(
        f"- {reference}" for reference in orphaned_references
    )
    return f"{text}\n\n{attachment_block}" if text else attachment_block
