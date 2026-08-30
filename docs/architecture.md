# Architecture

Ghostwriter is one local application with two integration processes:

```text
┌──────────────────────── Python / Textual ────────────────────────┐
│ Prompt editor ─ Draft/Attachments ─ PiBridgeClient               │
│        │                  │                 │                     │
│        └─ RewriteSession ─┴─ Pi RPC child   └─ Unix socket       │
└───────────────────────────────────────────────────────┬───────────┘
                                                        │
                                           TypeScript Pi extension
                                                        │
                                                Pi unsent editor
```

The Python application owns composition and local state. The TypeScript extension is deliberately small: it advertises live Pi sessions and applies validated editor replacements.

## Source layout

| Path | Responsibility |
| --- | --- |
| `src/ghostwriter/app.py` | Textual widgets, responsive layout, actions, workers, and screen orchestration |
| `src/ghostwriter/model.py` | Versioned `Draft` and `Attachment` serialization |
| `src/ghostwriter/config.py` | Unified JSON rewrite settings, defaults, and prompt validation |
| `src/ghostwriter/files.py` | Dragged-path parsing, native picker, recursive `@` index, and safe previews |
| `src/ghostwriter/storage.py` | Atomic draft persistence and content-addressed image cache |
| `src/ghostwriter/pi.py` | Pi registry discovery, Pi attachment syntax, and socket exchange |
| `src/ghostwriter/rewrite/` | Pi RPC process, rewrite prompts, review screens, and placeholder validation |
| `extensions/ghostwriter.ts` | Pi package entry point, session registry, socket server, and status command |
| `tests/` | UI behavior, persistence, serialization, protocol, and rewrite tests |

The project is intentionally Pi-specific. `PiBridgeClient` is a concrete boundary rather than a generic adapter framework.

## Main injection flow

1. `GhostwriterApp` loads a versioned draft from `DraftStore`.
2. Files enter through drag-and-drop, the native picker, startup arguments, or `@` completion.
3. The editor displays a compact `@filename` marker while `Attachment` retains the source path, staged path, kind, and stable ID.
4. The selected `PiTarget` supplies the target working directory and socket.
5. `serialize_draft()` replaces display markers with Pi syntax:
   - files become `@relative/path` or `@"path with spaces"` when representable relative to Pi's working directory;
   - images become persistent absolute cache paths.
6. `PiBridgeClient.inject()` sends one bounded newline-delimited JSON request.
7. The extension validates protocol version, session ID, working directory, draft revision, and request size.
8. `ctx.ui.setEditorText()` replaces Pi's unsent input. The extension returns a SHA-256 acknowledgement.
9. The user reviews and submits from Pi. Ghostwriter never submits automatically.

## Attachment state

`Attachment` separates three representations:

- **Display:** `@filename` inside the Textual editor
- **Local metadata:** source path, staged path, kind, and ID in the persisted draft
- **Pi representation:** relative file reference or cached absolute image path

The UI intentionally does not ask users to distinguish files from images. Image detection and validation happen internally when the attachment is added. Duplicate source files and duplicate display filenames are rejected because an unambiguous display marker is required.

Deleting the final display marker removes its attachment metadata. Removing an attachment from the table performs the inverse operation and deletes every matching marker.

### File completion

The selected Pi session's working directory is the project root. `files.py` indexes up to 20,000 files while skipping `.git`, `.venv`, `node_modules`, and `__pycache__`. Relative queries are ranked by filename and path match. Queries beginning with `/` or `~` use direct filesystem completion. Tab accepts the highlighted candidate.

## Rewrite flow

Rewrite is separate from visible Pi injection:

1. `ConfigStore` supplies named agents, target languages, warm-up policy, and the prompt template.
2. App startup normally launches `PiRpcSession` once with tools and project resources disabled.
3. `RewriteConfigScreen` returns validated `RewriteOptions` from configured dropdowns.
4. `PiRpcSession.prepare()` starts a fresh Pi session for every workflow after the first and selects its configured model.
5. `AttachmentProtector` replaces every local marker occurrence with a random opaque token.
6. Responses are checked so every expected placeholder occurs exactly once. One repair request is allowed if integrity fails.
7. The review screen supports acceptance, rejection, direct edits, and revision feedback in the same RPC conversation.
8. App shutdown terminates the shared child and removes its private session directory. With warm mode disabled, cleanup instead happens after each workflow.

No attachment path, filename, or content is sent to the rewrite model.

## UI and concurrency

Textual owns terminal rendering and input. Important custom behavior includes:

- `PromptTextArea`: intercepts bracketed paste and Tab completion;
- `DragHandle`: captures mouse events directly for independent width and height resizing;
- `OptionList`: presents complete, concise Pi target identity in one scrollable box;
- `VerticalScroll`: keeps the side pane reachable in constrained layouts;
- thread worker: runs blocking native file pickers without freezing Textual;
- async workers: perform socket injection and Pi RPC communication.

The app switches between side-by-side and stacked layouts using terminal width and aspect ratio. TextArea supplies clipboard handling, history, selection, and both scroll axes.

## Persistence and runtime files

Paths use `platformdirs`, so exact locations vary by operating system:

- config: `user_config_path("ghostwriter")/config.json`
- state: `user_state_path("ghostwriter")/draft.json`
- cache: `user_cache_path("ghostwriter")/images/`
- rewrite sessions: `user_cache_path("ghostwriter")/rewrite-sessions/`
- Pi registry: `<Pi agent dir>/run/ghostwriter/*.json`
- sockets: `/tmp/ghostwriter-<uid>/*.sock`

Draft and registry writes use temporary files followed by atomic rename. Sensitive local files and sockets use user-only permissions where the platform supports them.

## Compatibility boundaries

Changes at these boundaries require coordinated tests and documentation:

- draft schema version in `model.py`;
- socket protocol version in both `pi.py` and `extensions/ghostwriter.ts`;
- Pi RPC event and command names in `rewrite/pi_rpc.py`;
- Pi extension APIs described in `docs/pi-bridge.md`.
