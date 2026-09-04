from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from platformdirs import user_cache_path, user_state_path

from .model import Draft


def clear_legacy_image_cache(directory: Path | None = None) -> None:
    """Remove image copies created by draft schema versions before version 3."""
    cache_directory = directory or user_cache_path("ghostwriter") / "images"
    shutil.rmtree(cache_directory, ignore_errors=True)


class DraftStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_state_path("ghostwriter") / "draft.json"

    def load(self) -> Draft:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError("Draft root must be an object")
            return Draft.from_dict(data)
        except FileNotFoundError:
            return Draft()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            broken = self.path.with_suffix(f".broken-{os.getpid()}.json")
            try:
                self.path.replace(broken)
            except OSError:
                pass
            return Draft()

    def save(self, draft: Draft) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(
            json.dumps(draft.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
