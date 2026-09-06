from __future__ import annotations

import sys

from ghostwriter.system_search import read_null_delimited_process


def test_process_reader_preserves_null_delimited_paths_and_limit() -> None:
    paths = read_null_delimited_process(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(b'first\\0second\\0third\\0')",
        ],
        limit=2,
        timeout=1,
    )

    assert paths == ["first", "second"]
