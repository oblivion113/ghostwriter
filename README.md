# Ghostwriter

A standalone terminal prompt composer that replaces the unsent editor text in a running Pi TUI. It never submits the prompt: final review, editing, and submission stay inside Pi.

The name is literal and a Ghostty nod: it writes into another terminal editor without impersonating keyboard input.

## Why Python + TypeScript

The composer uses Python and [Textual](https://textual.textualize.io/) because its editor already provides reliable mouse cursor placement, drag selection, clipboard operations, undo/redo, and responsive terminal layout. Rebuilding that interaction layer in Rust would add substantial terminal-specific code without improving the local Unix-socket bridge.

The Pi bridge is TypeScript because Pi extensions run natively in TypeScript. Runtime work is deliberately small: the app does no per-keystroke disk writes, target discovery reads a tiny registry, image hashing streams in 1 MiB chunks, and injection is one asynchronous local socket exchange.

The project has its own uv-managed `.venv`; it does not use the base Python environment.

## Features

- Mouse editing and drag selection in a multiline prompt editor
- Normal copy, cut, paste, undo, and redo
- Unified attachments from drag-and-drop, the native picker, or `@` autocomplete
- Compact `@filename` markers regardless of how a file was attached
- Raw text preview for source code, Markdown, scripts, and other UTF-8 files
- Ghostty-compatible image preview with Unicode fallback
- Translation, tidying, and iterative revision through an isolated Pi RPC session
- Strict local placeholder restoration that keeps attachment details away from the rewrite model
- Persistent draft and content-addressed image cache
- Discovery of multiple running Pi instances
- Whole-editor replacement with revision and target validation
- No synthetic typing or automatic submission
- A deliberately Pi-only bridge with no unused adapter abstraction

## Setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js/npm, and Pi 0.84.4 or a compatible release.

```bash
git clone <repository-url> ghostwriter
cd ghostwriter
./scripts/setup
```

The setup script installs locked Python and TypeScript dependencies, builds both packages, installs the `ghostwriter` command, and registers this repository through Pi's package manager. Restart Pi or run `/reload` afterward.

Start the composer in another terminal pane:

```bash
ghostwriter
```

The Pi command `/ghostwriter-status` shows that session's name, working directory, model, thinking level, and PID.

Contributors who do not want user-level installation can instead run:

```bash
uv sync --dev
npm ci
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
| `Ctrl+O` | Choose one or more files |
| `Ctrl+R` | Refresh targets |
| `Ctrl+S` | Save draft |
| `F4` | Translate / tidy the draft with Pi RPC |
| `Ctrl+Q` | Quit |

Text editing, selection, clipboard, and history keys come from Textual's `TextArea`. While an `@` completion menu is open, use Up/Down to choose, Tab to attach, and Escape to close it.

## Attachments

File references are serialized using Pi's conventions:

```text
@src/example.ts
@"directory with spaces/example.ts"
```

Ghostwriter presents every file through the same attachment interface. Internally, image formats are validated and copied once to a content-addressed cache so Pi receives the same persistent image paths as before. The draft is stored under the platform state directory; cached images are under the platform cache directory.

Drag files directly into the prompt, select **Attach** to open the native multi-file picker, or type `@` to search the selected Pi session's working directory recursively. Absolute paths and `~` paths are also completed. Every route inserts the same compact `@filename` marker and adds the same filename-only row to Attachments. Pi serialization replaces the display marker in place with Pi's actual file or image reference.

Selecting an attachment previews images visually and displays UTF-8 files—including source code, scripts, tests, and Markdown—as raw text. Binary and oversized files are handled safely; large text previews are truncated.

Deleting a marker from the prompt removes its unreferenced attachment automatically. Selecting an attachment and choosing **Remove** performs the inverse atomic operation: it removes the attachment and every matching marker from the prompt.

## Translation and tidying

Press `F4` to open the rewrite configuration. Select Translate, Tidy, or both, then choose **Run** or press `Ctrl+Enter` to start the tool-free Pi RPC process. Ghostwriter protects inline attachments with opaque placeholders and returns the result to a review dialog. You may accept, reject, directly edit, or provide revision feedback while the same RPC conversation remains alive.

The accepted result returns to Ghostwriter—not Pi's visible editor. Attachment mappings, paths, and content remain local. Every placeholder is validated before restoration. The temporary cached RPC session is deleted by default when the review workflow ends.

See [`docs/rewrite.md`](docs/rewrite.md) for protocol and privacy details.

## Layout

Ghostwriter selects a side-by-side or stacked layout from both terminal width and aspect ratio. Two mouse-draggable dividers resize the prompt independently: the outer divider changes editor width (or pane height when stacked), while the divider below the prompt changes its height. The prompt supports vertical and horizontal scrolling.

## Architecture

```text
Textual UI ── PiBridgeClient ── Unix socket ── Pi extension
     └────── RewriteSession ── isolated Pi RPC process
```

`src/ghostwriter/pi.py` owns Pi target discovery, attachment serialization, and injection. `extensions/ghostwriter.ts` owns the Pi-side session registry and editor replacement.

Developer references:

- [`docs/architecture.md`](docs/architecture.md) — components, state, and end-to-end flows
- [`docs/pi-bridge.md`](docs/pi-bridge.md) — self-contained Pi APIs, lifecycle, registry, and wire protocol
- [`docs/rewrite.md`](docs/rewrite.md) — isolated RPC transformation and placeholder integrity
- [`docs/development.md`](docs/development.md) — setup, build, tests, debugging, and releases
- [`AGENTS.md`](AGENTS.md) — concise operational guidance for coding Agents

## Development

```bash
./scripts/check
./scripts/build
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting changes.

Uninstall with:

```bash
./scripts/uninstall-pi-extension
uv tool uninstall ghostwriter
```
