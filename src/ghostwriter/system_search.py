from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence


def search_system_file_index(
    query: str,
    *,
    limit: int,
    timeout: float,
    cancelled: Callable[[], bool] | None = None,
) -> list[str]:
    """Query the platform file index and return bounded, NUL-safe paths."""
    if sys.platform == "darwin" and (mdfind := shutil.which("mdfind")) is not None:
        command = [mdfind, "-0", "-onlyin", "/", "-name", query]
    elif os.name != "nt" and (locate := shutil.which("locate")) is not None:
        command = [locate, "-0", "-i", "--", query]
    else:
        return []
    return read_null_delimited_process(
        command,
        limit=limit,
        timeout=timeout,
        cancelled=cancelled,
    )


def read_null_delimited_process(
    command: Sequence[str],
    *,
    limit: int,
    timeout: float,
    cancelled: Callable[[], bool] | None = None,
) -> list[str]:
    """Read bounded search output and terminate promptly when completion becomes stale."""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return []
    if process.stdout is None:
        process.kill()
        return []

    deadline = time.monotonic() + timeout
    buffer = bytearray()
    paths: list[str] = []
    stopped_early = False
    reached_eof = False
    was_cancelled = False
    try:
        while len(paths) < limit:
            if cancelled is not None and cancelled():
                was_cancelled = True
                stopped_early = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stopped_early = True
                break
            readable, _, _ = select.select(
                [process.stdout],
                [],
                [],
                min(0.05, remaining),
            )
            if not readable:
                continue
            chunk = os.read(process.stdout.fileno(), 64 * 1024)
            if not chunk:
                reached_eof = True
                break
            buffer.extend(chunk)
            items = bytes(buffer).split(b"\0")
            buffer = bytearray(items.pop())
            remaining_slots = limit - len(paths)
            paths.extend(os.fsdecode(item) for item in items[:remaining_slots] if item)
        if len(paths) >= limit:
            stopped_early = True
    except (OSError, ValueError):
        return []
    finally:
        if process.poll() is None:
            if was_cancelled:
                process.kill()
            elif reached_eof:
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    process.terminate()
            else:
                process.terminate()
            if process.poll() is None:
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    if was_cancelled or (not stopped_early and process.returncode):
        return []
    return paths
