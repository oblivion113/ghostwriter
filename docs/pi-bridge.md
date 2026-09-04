# Pi integration and bridge protocol

This document contains the Pi-specific information needed to maintain Ghostwriter without access to Pi's full documentation.

Ghostwriter is intentionally Pi-specific. The integration has two parts:

- `src/ghostwriter/pi.py` discovers Pi sessions, serializes attachments using Pi syntax, and sends drafts.
- `extensions/ghostwriter.ts` runs inside Pi, publishes session metadata, and replaces Pi's unsent editor text.

## How Pi loads the extension

The repository is a Pi package because `package.json` contains:

```json
{
  "pi": {
    "extensions": ["./extensions/ghostwriter.ts"]
  }
}
```

Pi supports TypeScript extension entry points directly. `pi install /absolute/path/to/ghostwriter` adds the resolved local package path to Pi's user settings; it does not copy the repository. A project-local install uses `pi install -l <source>`. `pi remove <source>` reverses the corresponding installation.

For a one-process test without changing settings:

```bash
pi -e ./extensions/ghostwriter.ts
```

Extensions run with the user's full permissions. Pi supplies its core packages at runtime, so `@earendil-works/pi-coding-agent` is a peer dependency rather than a bundled runtime dependency.

## Pi APIs used by Ghostwriter

The extension exports one default factory:

```ts
export default function ghostwriterBridge(pi: ExtensionAPI): void
```

Only the following Pi surface is required:

| API | Purpose |
| --- | --- |
| `getAgentDir()` | Resolve Pi's agent configuration/runtime root |
| `pi.on("session_start", handler)` | Start registry and socket resources for an interactive session |
| `pi.on("session_shutdown", handler)` | Close the server and remove runtime files |
| `pi.on("session_info_changed", handler)` | Refresh the optional session display name |
| `pi.on("model_select", handler)` | Refresh provider and model metadata |
| `pi.on("thinking_level_select", handler)` | Refresh thinking-level metadata |
| `pi.registerCommand(name, definition)` | Register `/ghostwriter-status` |
| `ctx.mode` | Restrict the bridge to interactive `"tui"` sessions |
| `ctx.cwd` | Identify the session working directory |
| `ctx.model` | Read active provider and model IDs |
| `ctx.thinkingLevel` | Read active thinking level |
| `ctx.sessionManager.getSessionId()` | Bind requests to the current session |
| `ctx.sessionManager.getSessionName()` | Publish a user-readable session name |
| `ctx.ui.setEditorText(text)` | Replace the unsent Pi editor content |
| `ctx.ui.setWidget(key, factory)` | Install an invisible component that captures the TUI render requester |
| `tui.requestRender(true)` | Fully repaint editor cells after an external socket callback |
| `ctx.ui.notify(message, level)` | Display `/ghostwriter-status` output |

Long-lived resources must not start in the extension factory. Ghostwriter creates them during `session_start` and performs idempotent cleanup during `session_shutdown`. Session switches, forks, reloads, and normal exit all pass through these lifecycle events.

The project currently type-checks against Pi `0.84.4`. The peer range is `*` because the host supplies Pi, but changes to any API above should be treated as compatibility changes and tested before release.

## Runtime topology

For each interactive Pi session, the extension creates:

```text
<Pi agent dir>/run/ghostwriter/pi-<pid>-<session>.json
/tmp/ghostwriter-<uid>/pi-<pid>-<session>.sock
```

The short `/tmp` socket location is required because macOS limits Unix-domain socket paths to roughly 104 bytes. Runtime directories are mode `0700`; registry files and sockets are mode `0600` where supported.

One Pi process may change sessions. On every `session_start`, the extension stops any old server, creates paths using the new session ID, starts a fresh server, and writes current metadata. Cleanup tolerates missing files so reload and shutdown remain idempotent.

## Registry schema

Registry files are local discovery records, not a remote API. A representative record is:

```json
{
  "version": 1,
  "pid": 31005,
  "sessionId": "01a04b54-7ca0-...",
  "sessionName": "Refactor Ghostwriter",
  "cwd": "/Users/example/code/ghostwriter",
  "socketPath": "/tmp/ghostwriter-501/pi-31005-01a04b547c.sock",
  "modelProvider": "openai-codex",
  "modelId": "gpt-5.6-sol",
  "thinkingLevel": "high",
  "startedAt": "2026-08-29T00:00:00.000Z",
  "updatedAt": "2026-08-29T00:05:00.000Z"
}
```

`startedAt` remains stable for sorting. `updatedAt` changes when session metadata is rewritten. Writes use a temporary file followed by atomic rename.

`PiBridgeClient.discover_targets()` validates that the PID is alive and the socket exists. Invalid or stale registry records are removed. It removes a stale socket only when it is a Unix socket inside the expected user-specific socket directory and has the expected `pi-` prefix.

## Injection wire protocol

Transport is one newline-delimited JSON request and one newline-delimited JSON response over the discovered Unix socket. Protocol version is currently `1` on both sides.

### Request

```json
{
  "version": 1,
  "target": {
    "sessionId": "01a04b54-7ca0-...",
    "cwd": "/Users/example/code/ghostwriter"
  },
  "draftId": "stable-ghostwriter-draft-id",
  "revision": 7,
  "text": "Serialized prompt text"
}
```

Validation rules:

- payload is at most 4 MiB including JSON framing;
- version must match exactly;
- target session ID and working directory must match the live context;
- draft ID must be non-empty;
- revision must be a non-negative safe integer;
- an older revision than the latest applied revision is rejected;
- the same revision may be retried only with identical text.

The revision map is process-local and keyed by draft ID. It prevents stale Ghostwriter windows from overwriting newer content while allowing an identical retry.

### Success response

```json
{
  "ok": true,
  "revision": 7,
  "sha256": "hex digest of serialized text",
  "sessionId": "01a04b54-7ca0-..."
}
```

### Error response

```json
{
  "ok": false,
  "error": "Human-readable rejection reason"
}
```

The Python client uses a three-second exchange timeout. The extension uses a five-second socket timeout and stops reading after the first complete request.

## Editor replacement behavior

After successful validation, the extension replaces the editor text and requests a full TUI repaint:

```ts
ctx.ui.setEditorText(request.text);
forceEditorRender?.();
```

`setEditorText` updates only Pi's unsent input. It does not submit, append a conversation message, or start an agent turn. Socket callbacks occur outside Pi's normal keyboard event path, and an incremental render can leave stale cells when the replacement changes line prefixes or wrapping. During `session_start`, Ghostwriter installs a zero-line widget factory to capture the supported TUI object; `forceEditorRender` calls `tui.requestRender(true)`. The hook is removed during shutdown and never adds visible content.

This render workaround is intentionally isolated in the extension. If a future Pi release makes `setEditorText` schedule a full repaint itself, remove the hook only after an interactive regression test.

## Attachment serialization

The editor marker is local Ghostwriter state. Before injection, Python emits Pi-compatible text:

- a regular file under Pi's working directory becomes `@relative/path`;
- a path containing whitespace becomes `@"relative/path with spaces"`;
- a file outside the working directory becomes an absolute `@path` reference;
- an image becomes the absolute path of its validated content-addressed cache copy.

Paths containing quotes or line breaks are rejected because they cannot be represented safely by the current Pi file-reference syntax.

## Status command

`/ghostwriter-status` reports the current session name/ID, working directory, provider/model, thinking level, and PID. This is the easiest way to match one visible Pi window with a Ghostwriter target.

## Security properties

- No TCP port is opened.
- Runtime files are user-only.
- Request size and socket lifetime are bounded.
- Session ID and working directory prevent accidental cross-session injection.
- Revisions prevent stale replacement.
- The extension never submits prompts.
- Registry data contains local paths and model metadata, so it must not be copied to logs or remote services by default.

## Rewrite RPC lifecycle

The rewrite child is separate from the visible TUI bridge. Ghostwriter starts `pi --mode rpc` with tools, extensions, skills, prompt templates, and project context disabled. Pi RPC is a persistent stdin/stdout protocol: keeping the subprocess alive is sufficient to keep its model runtime warm.

Ghostwriter uses these documented RPC commands:

| Command | Purpose |
| --- | --- |
| `get_state` | Confirm startup and remember Pi's default provider/model |
| `new_session` | Clear conversation state between independent rewrite workflows |
| `set_model` | Select the named agent from Ghostwriter's configuration |
| `prompt` | Start a transform or review revision |
| `get_last_assistant_text` | Retrieve the settled result |

The default app-lifetime process still uses a private persistent session directory because Pi's RPC session replacement API is being used. All session files are deleted with that directory during normal Ghostwriter shutdown. Setting `rewrite.keepRpcWarm` to `false` restores per-workflow process cleanup.

## Coordinated changes

When changing the bridge or rewrite RPC integration:

1. update protocol constants and message fields in Python and TypeScript together;
2. preserve request bounds and target validation;
3. update `tests/test_pi.py` with success, rejection, and stale-runtime behavior;
4. run `npm run check` and the Python test suite;
5. update this document so contributors and Agents do not need external Pi documentation.
