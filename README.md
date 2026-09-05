# Ghostwriter

### A comfortable drafting space for Pi

Ghostwriter gives you a mouse-friendly terminal editor for prompts that are awkward to compose directly in Pi: long instructions, several attachments, inline Skill references, or prose that needs a quick translation or cleanup.

When the draft is ready, Ghostwriter replaces the unsent text in the Pi session you choose. **It never submits the prompt.** You still review it and press Enter in Pi.

```text
Compose in Ghostwriter  ── Ctrl+Enter ──▶  Review in Pi  ── Enter ──▶  Agent
```

| Compose comfortably | Bring the right context | Stay in control |
| --- | --- | --- |
| Mouse editing, selection, clipboard, undo/redo, soft wrapping, and persistent drafts | Drag files, preview images and text, search files or folders with `@`, and complete `/skill:<name>` anywhere | Local socket injection replaces only unsent editor text; no synthetic typing and no automatic submission |

## Quick start

Ghostwriter requires Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js/npm, and Pi 0.84.4 or a compatible release.

```bash
git clone https://github.com/oblivion113/ghostwriter.git
cd ghostwriter
./scripts/setup
```

`setup` installs the local command and registers the Pi extension, so it changes your user-level Pi settings. Restart Pi or run `/reload`, then open Ghostwriter in another terminal pane:

```bash
ghostwriter
```

Choose a running Pi session, write your prompt, and press `Ctrl+Enter`. Ghostwriter transfers the draft to Pi for final review.

You can also start with attachments:

```bash
ghostwriter ./spec.md ./screenshot.png
```

For a development-only checkout that does not install the command or modify Pi settings, follow [`docs/development.md`](docs/development.md).

## Writing with context

### Attachments

Drag files into the editor, choose **Attach**, paste a local path, or type `@` to search the selected Pi project's files and folders. `@` search includes paths hidden by Git's local excludes, which keeps untracked local context selectable. Every route creates the same compact marker, such as `@design.md` or `@notes/`.

Ghostwriter keeps the original path in place rather than copying it. Text and images can be previewed locally; at injection time the marker becomes Pi's normal path syntax:

```text
@src/example.ts
@"notes/design brief.md"
```

Deleting the final marker removes the attachment automatically. You can also select it in the Attachments pane and choose **Remove**.

`fd` and `fzf` improve indexing and fuzzy ranking when installed, but neither is required. A bounded Python fallback is always available.

### Skills

Type `/skill` or `/skill:<partial-name>` after whitespace anywhere in your draft. Ghostwriter shows the Skills loaded by the selected Pi session, including a short description, and lets you complete the highlighted result with Tab or a click.

```text
First review the architecture, then use /skill:teaching for the explanation.
```

The inserted `/skill:<name>` remains ordinary prompt text and is highlighted for readability. There is no separate checkbox or preview. If Pi's Skills change, press `Ctrl+R` to refresh the selected target's metadata.

Pi expands a Skill command normally when it begins the submitted input and Skill commands are enabled. When it appears later in a sentence, the explicit syntax remains visible to the Agent so it can select the matching Skill instructions.

## Rewrite before you send

Press `F4` to translate, tidy, or revise the current draft with an isolated Pi RPC process. You can review the result, edit it directly, request another revision in the same workflow, or reject it and keep the original.

Attachments stay private during rewriting. Ghostwriter replaces every attachment marker with an opaque placeholder, verifies that the model preserved each placeholder exactly once, and only then restores the local markers. Paths, filenames, and attachment contents are not sent to the rewrite model.

The accepted rewrite returns to Ghostwriter. It reaches Pi only when you explicitly choose **Inject**.

See [`docs/rewrite.md`](docs/rewrite.md) for isolation, placeholder integrity, and RPC lifecycle details.

## Keyboard guide

| Key | Action |
| --- | --- |
| `Ctrl+Enter` | Replace the selected Pi session's unsent editor text |
| `Ctrl+O` | Choose one or more attachments |
| `Ctrl+R` | Refresh Pi targets and their Skills |
| `Ctrl+S` | Save the current draft |
| `F4` | Open Translate / Tidy |
| `Ctrl+Q` | Quit |
| `Up` / `Down` | Move through an open completion list |
| `Tab` | Accept the highlighted `@` or `/skill:` completion |
| `Escape` | Close the completion list |

Text editing, selection, clipboard, and history shortcuts come from Textual's `TextArea`.

## Safety by design

Ghostwriter has a deliberately narrow job: prepare a prompt and place it in Pi's editor.

- **Review stays mandatory.** Injection never submits or starts an Agent turn.
- **Communication stays local.** The bridge uses a user-only Unix socket, not a TCP port.
- **Attachments stay zero-copy.** Ghostwriter references original files and does not upload, hash, or duplicate them.
- **Targets are validated.** Session ID, working directory, revision, and request size are checked before replacement.
- **Rewriting is isolated.** The RPC process has tools, extensions, Skills, prompt templates, and project context disabled.

## Configuration

Choose **Settings → Open config** to edit Ghostwriter's generated JSON configuration. It controls the persistent theme, file search, rewrite models, target languages, standing instructions, custom prompts, and optional RPC warm-up. Theme choices are saved immediately; reload other manual edits from Ghostwriter after saving.

See [`docs/configuration.md`](docs/configuration.md) for the configuration format and examples.

## Project guide

| Document | Use it for |
| --- | --- |
| [`docs/configuration.md`](docs/configuration.md) | File search and rewrite settings |
| [`docs/rewrite.md`](docs/rewrite.md) | Rewrite privacy, validation, and RPC behavior |
| [`docs/architecture.md`](docs/architecture.md) | Components, state, and end-to-end data flow |
| [`docs/pi-bridge.md`](docs/pi-bridge.md) | Pi APIs, runtime registry, and wire protocol |
| [`docs/development.md`](docs/development.md) | Local setup, tests, debugging, releases, and uninstalling |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Contribution workflow and project invariants |
| [`docs/agent-reference.md`](docs/agent-reference.md) | Compact codebase orientation for coding agents |

## For Agents

Use [`docs/agent-reference.md`](docs/agent-reference.md) when an agent needs a compact repository map, verification commands, and design constraints. It is intentionally a normal reference page rather than an automatically loaded `AGENTS.md`. Read `docs/pi-bridge.md` before changing Pi integration and `docs/architecture.md` before moving responsibilities between modules.

The short version: preserve Ghostwriter's Pi-only scope, keep attachment data local during rewrites, and never turn editor replacement into submission.

## Development

```bash
./scripts/check
./scripts/build
```

`check` runs TypeScript type checking, Ruff, and the full pytest suite. The Python UI lives under `src/ghostwriter/`; the Pi extension is `extensions/ghostwriter.ts`.

Ghostwriter is licensed under the [MIT License](LICENSE).
