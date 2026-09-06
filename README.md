# Ghostwriter

### A comfortable drafting space for Pi

Ghostwriter gives you a mouse-friendly terminal editor for prompts that are awkward to compose directly in Pi: long instructions, several attachments, inline Skill references, or prose that needs a quick translation or cleanup.

When the draft is ready, Ghostwriter replaces the unsent text in the Pi session you choose. **It never submits the prompt.** You still review it and press Enter in Pi.

```text
Compose in Ghostwriter  ── Ctrl+Enter ──▶  Review in Pi  ── Enter ──▶  Agent
```

| Compose comfortably | Bring the right context | Stay in control |
| --- | --- | --- |
| Mouse editing, selection, clipboard, undo/redo, soft wrapping, persistent drafts, and reusable Prompt templates | Drag files, preview images and text, search files or folders with `@`, and complete `/skill:<name>` anywhere | Local socket injection replaces only unsent editor text; no synthetic typing and no automatic submission |

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

Drag files into the editor, choose **Attach**, paste a local path, or type `@` to search the selected Pi project immediately. After three filename characters, Ghostwriter also searches the operating system's indexed files and folders, so typing `@bug1` can find `~/Desktop/bug1-2.png` without a full path. Project matches always appear first, including paths hidden by Git's local excludes.

By default, an attached path inside Pi's working directory is shown relative to that directory, such as `@docs/design.md` or `@notes/`; a path outside it shows its absolute path. Set `fileSearch.pathDisplay` to `full` to show absolute paths for both. Ghostwriter keeps the original path in place rather than copying it. Text and images can be previewed locally; at injection time the marker becomes Pi's normal path syntax:

```text
@src/example.ts
@"notes/design brief.md"
```

Deleting the final marker removes the attachment automatically. You can also select it in the Attachments pane and choose **Remove**.

`fd` and `fzf` improve project indexing and fuzzy ranking when installed, but neither is required. A bounded Python fallback handles project search. Whole-computer name search uses the macOS Spotlight index or `locate` on other Unix systems when available.

### Prompt templates

Ghostwriter reads simple Markdown Prompt templates from the directory configured at `promptTemplates.directory`. The default is Ghostwriter's own `prompts` directory beside `config.json`, so it does not collide with Pi's default. You may point it at `~/.pi/agent/prompts`. Each template needs a single-line `name`; `description` is optional and may be blank:

```markdown
---
name: review
description: Review the current draft
---
Review this carefully.

Preserve important details.
```

Choose **Prompts** to browse templates by bold name and description. **Insert** adds a highlighted `/prompt:<name>` reference such as `/prompt:review` at the cursor, **Expand** replaces every inserted reference in place, and **Open folder** opens the configured template directory. Use **Settings → Refresh** after adding or deleting templates; `F3` performs expansion directly.

Inline completion starts with `/`, which lists the Prompt and Skill routes. Type `/p` and press Tab to complete `/prompt:` and open the template list; then type part of a template name and press Tab again, or click a match, to insert `/prompt:<name>`. You can also type the full `/prompt:` prefix directly. Add as many references as needed and arrange them within the draft before expanding them. Body line breaks and surrounding draft text are preserved.

Template bodies are inserted literally. Ghostwriter deliberately does not interpret Pi argument placeholders such as `$1` or `${@:2}` because Pi has no supported extension hook that exposes its post-expansion text without starting an Agent turn. Discovery is non-recursive.

### Skills

Type `/` after whitespace anywhere in your draft to see the Prompt and Skill routes. Type `/s` and press Tab to complete `/skill:` and open the selected Pi session's Skill list. Continue with part of a Skill name, then press Tab again or click a match. You can also type `/skill:<partial-name>` directly. Each Skill includes a short description.

```text
First review the architecture, then use /skill:teaching for the explanation.
```

The inserted `/skill:<name>` remains ordinary prompt text and is highlighted for readability. There is no separate checkbox or preview. Press `Ctrl+R` after changing Prompt templates, Pi Skills, or working-directory files.

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
| `Ctrl+R` | Refresh Pi targets, Prompt templates, Skills, and the project file index |
| `Ctrl+S` | Save the current draft |
| `F3` | Expand all Prompt-template references directly |
| `F4` | Open Translate / Tidy |
| `Ctrl+Q` | Quit |
| `Up` / `Down` | Move through an open completion list |
| `Tab` | Accept the highlighted route, `@` path, Prompt, or Skill completion |
| `Escape` | Close the completion list or cancel a dialog |


Text editing, selection, clipboard, and history shortcuts come from Textual's `TextArea`.

## Safety by design

Ghostwriter has a deliberately narrow job: prepare a prompt and place it in Pi's editor.

- **Review stays mandatory.** Injection never submits or starts an Agent turn.
- **Communication stays local.** The bridge uses a user-only Unix socket, not a TCP port.
- **Attachments stay zero-copy.** Ghostwriter references original files and does not upload, hash, or duplicate them.
- **Targets are validated.** Session ID, working directory, revision, and request size are checked before replacement.
- **Rewriting is isolated.** The RPC process has tools, extensions, Skills, prompt templates, and project context disabled.

## Configuration

Choose **Settings → Open config** to edit Ghostwriter's generated JSON configuration. It controls the persistent theme, Prompt-template directory, file search, rewrite models, target languages, standing instructions, custom rewrite prompts, and optional RPC warm-up. Theme choices are saved immediately. **Refresh** applies other manual edits and refreshes Pi targets, Prompt templates, Skills, and file-search indexes.

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
