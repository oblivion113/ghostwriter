from __future__ import annotations

import argparse
from pathlib import Path

from .app import GhostwriterApp

__all__ = ["GhostwriterApp", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ghostwriter",
        description="Compose rich drafts and replace the input box of a running Pi TUI.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or images to attach when the composer opens",
    )
    args = parser.parse_args()
    GhostwriterApp(initial_paths=args.paths).run()
