from pathlib import Path

from ghostwriter.model import Attachment, Draft
from ghostwriter.storage import DraftStore, clear_legacy_image_cache


def test_draft_store_round_trip(tmp_path: Path) -> None:
    store = DraftStore(tmp_path / "state" / "draft.json")
    draft = Draft(
        text="hello",
        attachments=[Attachment("file", "/tmp/source", editor_path="/tmp/source")],
        revision=4,
    )

    store.save(draft)
    restored = store.load()

    assert restored.to_dict() == draft.to_dict()


def test_legacy_image_cache_is_removed(tmp_path: Path) -> None:
    cache = tmp_path / "images"
    cache.mkdir()
    (cache / "large-image.png").write_bytes(b"cached")

    clear_legacy_image_cache(cache)

    assert not cache.exists()
