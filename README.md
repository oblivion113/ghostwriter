# Ghostwriter

A standalone terminal prompt composer that replaces the unsent editor text in a running Pi TUI. It never submits the prompt: final review, editing, and submission stay inside Pi.

The name is literal and a Ghostty nod: it writes into another terminal editor without impersonating keyboard input.

## Why Python + TypeScript

The composer uses Python and [Textual](https://textual.textualize.io/) because its editor already provides reliable mouse cursor placement, drag selection, clipboard operations, undo/redo, and responsive terminal layout. Rebuilding that interaction layer in Rust would add substantial terminal-specific code without improving the local Unix-socket bridge.

The Pi bridge is TypeScript because Pi extensions run natively in TypeScript. Runtime work is deliberately small: the app does no per-keystroke disk writes, target discovery reads a tiny registry, attachments keep their original paths, and injection is one asynchronous local socket exchange.

The project has its own uv-managed `.venv`; it does not use the base Python environment.

## Features

- Mouse editing and drag selection in a multiline prompt editor
- Normal copy, cut, paste, undo, and redo
- Unified attachments from drag-and-drop, the native picker, or `@` autocomplete
- Compact `@filename` markers regardless of how a file was attached
- Raw text preview for source code, Markdown, scripts, and other UTF-8 files
- Ghostty-compatible image preview with Unicode fallback
- Translation, tidying, and iterative revision through one isolated, app-lifetime Pi RPC process
- JSON-configured rewrite agents, target languages, warm-up behavior, and prompt template
- Strict local placeholder restoration that keeps attachment details away from the rewrite model
- Persistent draft with zero-copy attachments
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

Ghostwriter presents every file through the same attachment interface and keeps only its original path. Files and images are never copied or hashed. Both are injected as Pi `@` references, and Pi's `read` tool identifies supported images from their content when it opens them. Ghostwriter still records whether a path looks like an image only to choose its local preview widget. The draft is stored under the platform state directory.

Versions using draft schemas 1 and 2 created persistent image copies under the platform cache directory. The current app removes that legacy `images` directory in a background startup task; it does not create a replacement attachment cache.

Drag files directly into the prompt, select **Attach** to open the native multi-file picker, or type `@` to search the selected Pi session's working directory recursively. Absolute paths and `~` paths are also completed. Every route inserts the same compact `@filename` marker and adds the same filename-only row to Attachments. Pi serialization replaces the display marker in place with Pi's actual file or image reference.

When available, `fd` builds the bounded project index and `fzf` ranks fuzzy matches without opening a second terminal UI. Both tools remain optional: the Python fallback excludes hidden files and common cache, dependency, and build directories. Project ignore files are respected by `fd`, and additional exclusions are configurable.

Selecting an attachment previews images visually and displays UTF-8 files—including source code, scripts, tests, and Markdown—as raw text. Plain prompt text stays white across every available theme, while attached `@filename` markers use a distinct blue style. Binary and oversized files are handled safely; large text previews are truncated.

Deleting a marker from the prompt removes its unreferenced attachment automatically. Selecting an attachment and choosing **Remove** performs the inverse atomic operation: it removes the attachment and every matching marker from the prompt.

## Translation and tidying

Press `F4` to open the rewrite configuration. Select Translate, Tidy, a target language, and a configured rewrite agent, then choose **Run** or press `Ctrl+Enter`. Ghostwriter protects inline attachments with opaque placeholders and returns the result to a review dialog. You may accept, reject, directly edit, or provide revision feedback in the same RPC conversation.

By default, Ghostwriter starts one tool-free Pi RPC process in the background and keeps it warm for the app's lifetime. Each new rewrite receives a fresh Pi session, while revisions retain the current conversation. On exit, Ghostwriter terminates the process and deletes its private session directory. Set `rewrite.keepRpcWarm` to `false` to use one process per workflow instead.

The accepted result returns to Ghostwriter—not Pi's visible editor. Attachment mappings, paths, and content remain local. Every placeholder is validated before restoration.

### Configuration

Ghostwriter creates one `config.json` in the platform user configuration directory on first start (on macOS, `~/Library/Application Support/ghostwriter/config.json`). It controls file search and rewrite choices:

```json
{
  "version": 1,
  "fileSearch": {
    "includeHidden": false,
    "useGlobalFzfOptions": true,
    "ignoreFiles": [],
    "fzfOptions": []
  },
  "rewrite": {
    "keepRpcWarm": true,
    "agents": [
      { "provider": "agent-plan", "model": "ark-code-latest" },
      { "provider": "anthropic", "model": "claude-haiku-4-5" }
    ],
    "targetLanguages": ["English", "Chinese (Simplified)", "French"],
    "defaultTargetLanguage": "English",
    "instructions": "",
    "prompt": "Transform the draft under these requirements:\\n{instructions}\\n\\nDRAFT START\\n{text}\\nDRAFT END"
  }
}
```

Select **Open config** in the Rewrite dialog to launch this file with the desktop's default associated editor. Save your edits, return to Ghostwriter, and select **Reload config** before running the rewrite. Ghostwriter also reloads the file automatically whenever the Rewrite dialog opens, so changes made while the dialog was closed are immediately available.

Customization rules:

- `fileSearch.includeHidden` defaults to `false`. `skipDirectories` contains the generated/cache directory names omitted by both `fd` and Python indexing; edit the generated list to tune it.
- `fileSearch.ignoreFiles` accepts extra gitignore-format files for `fd`. `useGlobalFzfOptions` inherits `FZF_DEFAULT_OPTS` and `FZF_DEFAULT_OPTS_FILE`; set it to `false` for app-only behavior, then place individual CLI arguments in `fzfOptions`.
- Each agent is identified directly as `provider/model`; there is no separate name. Set both values to IDs recognized by Pi (`pi --list-models`), or leave both blank to offer Pi's default. The first array entry is the default agent.
- `defaultTargetLanguage` must appear in `targetLanguages`.
- Type extra standing rewrite directions in `instructions`; leave it as `""` when none are needed. `{instructions}` expands to the built-in Translate/Tidy rules followed by this value—no external prompt file is involved.
- `{text}` is required in `prompt`. `{source_language}` and `{target_language}` expand to the chosen language values.
- Keep the attachment-placeholder instruction when replacing the default prompt. Ghostwriter still validates placeholders locally, but clear model instructions avoid unnecessary repair requests.
- JSON does not support comments. Use the field descriptions here rather than adding `//` or `#` lines to the file.

An invalid manual reload is reported without overwriting the file, allowing you to correct it in the editor. An invalid file encountered during app startup is moved to `config.broken-<pid>.json` and replaced with safe defaults. The generated default prompt tells the model not to add headings to short, single-section drafts.

See [`docs/rewrite.md`](docs/rewrite.md) for protocol and privacy details.

## Layout

Ghostwriter selects a side-by-side or stacked layout from both terminal width and aspect ratio. Its initial split always reserves space for the editor actions. Two mouse-draggable dividers resize the prompt independently: the outer divider changes editor width (or pane height when stacked), while the divider below the prompt changes its height. The current Pi session appears in a compact dropdown, which expands only when choosing another target. When no session is available, the control shows a disabled **No active Pi session** state rather than a selectable option. Prompt text soft-wraps to the available width and scrolls vertically without a horizontal scrollbar.

The command palette deliberately omits Textual's SVG screenshot command. Theme selection is limited to six comfortable dark themes: Textual Dark, Nord, Gruvbox, Catppuccin Mocha, Tokyo Night, and Rosé Pine Moon.

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
