from pathlib import Path

from ghostwriter.model import Attachment, Draft
from ghostwriter.storage import DraftStore, clear_legacy_image_cache


def test_draft_store_round_trip(tmp_path: Path) -> None:
    store = DraftStore(tmp_path / "state" / "draft.json")
    draft = Draft(
        text="hello",
        attachments=[Attachment("file", "/tmp/source")],
        revision=4,
    )

    store.save(draft)
    restored = store.load()

    assert restored.to_dict() == draft.to_dict()


def test_version_one_draft_migrates_verbose_attachment_marker() -> None:
    attachment = Attachment(
        "file",
        "/tmp/context.md",
        id="abcdef1234567890",
    )
    restored = Draft.from_dict(
        {
            "version": 1,
            "text": f"Review {attachment.legacy_editor_token}",
            "attachments": [attachment.to_dict()],
        }
    )

    assert restored.text == "Review @context.md"
    assert restored.attachments[0].editor_token == "@context.md"


def test_legacy_image_cache_is_removed(tmp_path: Path) -> None:
    cache = tmp_path / "images"
    cache.mkdir()
    (cache / "large-image.png").write_bytes(b"cached")

    clear_legacy_image_cache(cache)

    assert not cache.exists()


def test_version_two_draft_discards_staged_attachment_path() -> None:
    restored = Draft.from_dict(
        {
            "version": 2,
            "attachments": [
                {
                    "kind": "image",
                    "source_path": "/private/source.png",
                    "injected_path": "/cache/hash.png",
                    "id": "abcdef1234567890",
                }
            ],
        }
    )

    assert restored.to_dict()["version"] == 3
    assert restored.attachments[0].source == Path("/private/source.png")
    assert "injected_path" not in restored.attachments[0].to_dict()
