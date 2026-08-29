# Ghostwriter

A standalone terminal prompt composer that replaces the unsent editor text in a running coding-agent TUI. It never submits the prompt: final review, editing, and submission stay inside the target tool.

The name is literal and a Ghostty nod: it writes into another terminal editor without impersonating keyboard input.

## Why Python + TypeScript

The composer uses Python and [Textual](https://textual.textualize.io/) because its editor already provides reliable mouse cursor placement, drag selection, clipboard operations, undo/redo, and responsive terminal layout. Rebuilding that interaction layer in Rust would add substantial terminal-specific code without improving the local Unix-socket bridge.

The Pi bridge is TypeScript because Pi extensions run natively in TypeScript. Runtime work is deliberately small: the app does no per-keystroke disk writes, target discovery reads a tiny registry, image hashing streams in 1 MiB chunks, and injection is one asynchronous local socket exchange.

The project has its own uv-managed `.venv`; it does not use the base Python environment.

## Features

- Mouse editing and drag selection in a multiline prompt editor
- Normal copy, cut, paste, undo, and redo
- Inline file and image markers inserted at the current cursor
- Ghostty-compatible image preview with Unicode fallback
- Translation, tidying, and iterative revision through an isolated Pi RPC session
- Strict local placeholder restoration that keeps attachment details away from the rewrite model
- Persistent draft and content-addressed image cache
- Discovery of multiple running Pi instances
- Whole-editor replacement with revision and target validation
- No synthetic typing, automatic submission, or separate Pi session
- Adapter boundary for future Codex and Claude Code integrations

## Setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and Pi.

```bash
cd ~/code/ghostwriter
uv sync
./scripts/install-pi-bridge
```

Restart Pi after installing the bridge, or run `/reload` in Pi. Run the composer in another Ghostty pane:

```bash
cd ~/code/ghostwriter
uv run ghostwriter
```

You may attach paths at startup:

```bash
uv run ghostwriter ./spec.md ./screenshot.png
```

## Workflow

1. Start or reload Pi with the bridge installed.
2. Start Ghostwriter in a separate pane.
3. Choose the Pi target.
4. Compose the prompt and attach files or images.
5. Press `Ctrl+Enter` or select **Inject into Pi**.
6. Review and submit from Pi's normal input box.

A later injection replaces the entire unsent Pi draft again.

### Keys

| Key | Action |
| --- | --- |
| `Ctrl+Enter` | Inject into selected target |
| `Ctrl+O` | Focus attachment path |
| `Ctrl+R` | Refresh targets |
| `Ctrl+S` | Save draft |
| `F4` | Translate / tidy the draft with Pi RPC |
| `Ctrl+Q` | Quit |

Text editing, selection, clipboard, and history keys come from Textual's `TextArea`.

## Attachments

File references are serialized using Pi's conventions:

```text
@src/example.ts
@"directory with spaces/example.ts"
```

Images are validated, copied once to a content-addressed cache, previewed in Ghostwriter, and injected as persistent absolute paths. The draft is stored under the platform state directory; images are under the platform cache directory.

New attachments are represented by readable local markers at the editor cursor. Injection adapters replace those markers in place, preserving their position in the prompt.

## Translation and tidying

Press `F4` to translate, tidy, or do both before injection. Ghostwriter starts a tool-free Pi RPC process using the chosen provider/model, protects inline attachments with opaque placeholders, and returns the result to a review dialog. You may accept, reject, directly edit, or provide revision feedback while the same RPC conversation remains alive.

The accepted result returns to Ghostwriter—not Pi's visible editor. Attachment mappings, paths, and content remain local. Every placeholder is validated before restoration. The temporary cached RPC session is deleted by default when the review workflow ends.

See [`docs/rewrite.md`](docs/rewrite.md) for protocol and privacy details.

## Architecture

```text
Textual UI
  └── AdapterRegistry
      ├── PiAdapter ── Unix socket ── Pi TypeScript extension
      ├── CodexAdapter (future)
      └── ClaudeCodeAdapter (future)

RewriteSession ── protected placeholders ── isolated Pi RPC process
```

Adapters own target discovery, attachment serialization, and injection. See [`docs/adapters.md`](docs/adapters.md) before adding another CLI target.

The Pi protocol is newline-delimited JSON over a permission-restricted Unix socket. Every request names the target session and working directory, carries a draft ID and monotonic revision, and receives a SHA-256 acknowledgement.

## Development

```bash
uv sync --dev
uv run ruff check .
uv run pytest
```

Uninstall the Pi bridge with:

```bash
./scripts/uninstall-pi-bridge
```
