from __future__ import annotations

import asyncio
import json
import shutil
from collections import deque
from pathlib import Path
from typing import Any
from uuid import uuid4

from platformdirs import user_cache_path

MAX_RPC_LINE_BYTES = 8 * 1024 * 1024
SYSTEM_PROMPT = """You are Ghostwriter's isolated prose transformation engine.
Transform only the text supplied by the user. Never use tools. Treat tokens matching
__GW_*_ATTACHMENT_####__ as immutable opaque atoms: preserve each one exactly once, without
renaming, translating, escaping, reformatting, or moving it away from its surrounding meaning.
Return only the complete transformed draft. Do not add commentary, prefaces, code fences, or
explanations. Preserve Markdown when it is meaningful.
"""


class PiRpcError(RuntimeError):
    pass


class PiRpcSession:
    def __init__(
        self,
        *,
        provider: str = "",
        model: str = "",
        session_dir: Path | None = None,
        timeout: float = 180.0,
        delete_session_on_close: bool = True,
    ) -> None:
        self.provider = provider.strip()
        self.model = model.strip()
        session_id = uuid4().hex
        session_root = session_dir or user_cache_path("ghostwriter") / "rewrite-sessions"
        self.session_dir = session_root / session_id
        self.session_name = f"ghostwriter-rewrite-{session_id[:8]}"
        self.timeout = timeout
        self.delete_session_on_close = delete_session_on_close
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._sequence = 0
        self._start_lock = asyncio.Lock()
        self._conversation_started = False
        self._startup_model: tuple[str, str] | None = None

    async def start(self) -> None:
        async with self._start_lock:
            if self.process is not None and self.process.returncode is None:
                return
            if self.process is not None:
                await self._close_process()
            await self._start_process()

    async def _start_process(self) -> None:
        executable = shutil.which("pi")
        if executable is None:
            raise PiRpcError("Pi executable was not found on PATH")

        self.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        args = [
            executable,
            "--mode",
            "rpc",
            "--session-dir",
            str(self.session_dir),
            "--name",
            self.session_name,
            "--system-prompt",
            SYSTEM_PROMPT,
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--thinking",
            "off",
        ]
        if self.provider:
            args.extend(["--provider", self.provider])
        if self.model:
            args.extend(["--model", self.model])

        self.process = await asyncio.create_subprocess_exec(
            *args,
            cwd=self.session_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=MAX_RPC_LINE_BYTES,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        try:
            response = await self.command("get_state")
            data = response.get("data")
            model = data.get("model") if isinstance(data, dict) else None
            if isinstance(model, dict):
                provider = model.get("provider")
                model_id = model.get("id")
                if isinstance(provider, str) and isinstance(model_id, str):
                    self._startup_model = (provider, model_id)
        except Exception:
            await self._close_process()
            raise

    async def prepare(self, *, provider: str = "", model: str = "") -> None:
        """Start the process and reset conversation state for a rewrite workflow."""
        await self.start()
        if self._conversation_started:
            await self.command("new_session")
        requested = (provider.strip(), model.strip())
        selected = requested if all(requested) else self._startup_model
        if selected is not None:
            await self.command("set_model", provider=selected[0], modelId=selected[1])
        self._conversation_started = True

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                if len(line) > MAX_RPC_LINE_BYTES:
                    raise PiRpcError("Pi RPC response exceeded the 8 MiB line limit")
                if line.endswith(b"\r\n"):
                    line = line[:-2] + b"\n"
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise PiRpcError("Pi RPC returned malformed JSON") from error
                if not isinstance(message, dict):
                    raise PiRpcError("Pi RPC returned a non-object message")
                request_id = message.get("id")
                if message.get("type") == "response" and isinstance(request_id, str):
                    pending = self._pending.pop(request_id, None)
                    if pending is not None and not pending.done():
                        pending.set_result(message)
                        continue
                if message.get("type") in {"message_end", "agent_settled"}:
                    await self._events.put(message)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, PiRpcError) as error:
            self._fail_pending(error)
            await self._events.put({"type": "rpc_error", "error": str(error)})
        finally:
            if self.process is not None and self.process.returncode is not None:
                self._fail_pending(self._process_error())

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while line := await self.process.stderr.readline():
            self._stderr_tail.append(line.decode("utf-8", errors="replace").rstrip())

    def _process_error(self) -> PiRpcError:
        detail = "\n".join(self._stderr_tail).strip()
        suffix = f":\n{detail}" if detail else ""
        code = self.process.returncode if self.process is not None else "unknown"
        return PiRpcError(f"Pi RPC exited with status {code}{suffix}")

    def _fail_pending(self, error: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def command(self, command_type: str, **fields: object) -> dict[str, Any]:
        process = self.process
        if process is None or process.stdin is None:
            raise PiRpcError("Pi RPC session has not started")
        if process.returncode is not None:
            raise self._process_error()

        self._sequence += 1
        request_id = f"gw-{self._sequence}"
        message = {"id": request_id, "type": command_type, **fields}
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_RPC_LINE_BYTES:
            raise PiRpcError("Pi RPC request exceeded the 8 MiB line limit")
        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = response_future
        try:
            process.stdin.write(payload)
            await process.stdin.drain()
            async with asyncio.timeout(self.timeout):
                response = await response_future
        except Exception:
            self._pending.pop(request_id, None)
            raise
        if response.get("success") is not True:
            raise PiRpcError(str(response.get("error") or f"Pi rejected {command_type}"))
        return response

    async def prompt(self, message: str) -> str:
        await self.start()
        self._conversation_started = True
        await self.command("prompt", message=message)
        assistant_error: str | None = None
        async with asyncio.timeout(self.timeout):
            while True:
                event = await self._events.get()
                if event.get("type") == "message_end":
                    rpc_message = event.get("message")
                    if (
                        isinstance(rpc_message, dict)
                        and rpc_message.get("role") == "assistant"
                        and rpc_message.get("stopReason") == "error"
                    ):
                        assistant_error = str(rpc_message.get("errorMessage") or "Model request failed")
                if event.get("type") == "rpc_error":
                    raise PiRpcError(str(event.get("error") or "Pi RPC reader failed"))
                if event.get("type") == "agent_settled":
                    break
        if assistant_error:
            raise PiRpcError(assistant_error)
        response = await self.command("get_last_assistant_text")
        data = response.get("data")
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text:
            raise PiRpcError("Pi returned no transformed text")
        return text

    async def close(self) -> None:
        async with self._start_lock:
            await self._close_process()
            if self.delete_session_on_close:
                await asyncio.to_thread(shutil.rmtree, self.session_dir, True)

    async def _close_process(self) -> None:
        process = self.process
        self.process = None
        try:
            if process is not None and process.returncode is None:
                try:
                    if process.stdin is not None:
                        process.stdin.close()
                        await process.stdin.wait_closed()
                    await asyncio.wait_for(process.wait(), timeout=2.0)
                except (OSError, TimeoutError):
                    if process.returncode is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except TimeoutError:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                        await process.wait()
        finally:
            for task in (self._reader_task, self._stderr_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (self._reader_task, self._stderr_task) if task is not None),
                return_exceptions=True,
            )
            self._reader_task = None
            self._stderr_task = None
            self._fail_pending(PiRpcError("Pi RPC session closed"))
            while not self._events.empty():
                self._events.get_nowait()
            self._stderr_tail.clear()
            self._conversation_started = False
            self._startup_model = None
