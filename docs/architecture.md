# Architecture

Ghostwriter is one local application with two integration processes:

```text
┌──────────────────────── Python / Textual ────────────────────────┐
│ Prompt editor ─ Draft/Attachments ─ PiBridgeClient               │
│        │                                 ├─ target skill metadata│
│        └─ RewriteSession ─── Pi RPC child  └─ Unix socket        │
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
| `src/ghostwriter/config.py` | Unified JSON UI, file-search, and rewrite settings with validation |
| `src/ghostwriter/files.py` | Path parsing, project indexing and ranking, native picker, and safe previews |
| `src/ghostwriter/system_search.py` | Bounded, cancellable access to Spotlight or `locate` |
| `src/ghostwriter/wrapping.py` | Incremental CJK-aware soft wrapping that preserves source text |
| `src/ghostwriter/storage.py` | Atomic draft persistence and legacy image-cache cleanup |
| `src/ghostwriter/pi.py` | Pi registry and skill-metadata discovery, Pi attachment syntax, and socket exchange |
| `src/ghostwriter/rewrite/` | Pi RPC process, rewrite prompts, review screens, and placeholder validation |
| `extensions/ghostwriter.ts` | Pi package entry point, session and skill registry, socket server, and status command |
| `tests/` | UI behavior, persistence, serialization, protocol, and rewrite tests |

The project is intentionally Pi-specific. `PiBridgeClient` is a concrete boundary rather than a generic adapter framework.

## Main injection flow

1. `GhostwriterApp` loads a versioned draft from `DraftStore`.
2. Files enter through drag-and-drop, the native picker, startup arguments, or `@` completion; folders enter through pasted paths, startup arguments, or `@` completion. Skill invocations enter as ordinary `/skill:<name>` text through target-aware completion.
3. The editor displays styled attachment markers. Auto path display uses a basename inside the selected working directory and an absolute path outside it; `Attachment` retains that editor path and the original source, while skill invocations deliberately create no separate draft state.
4. The selected `PiTarget` supplies the target working directory, socket, and Pi's loaded skill metadata.
5. `serialize_draft()` replaces every display marker with the same Pi file-reference syntax: `@relative/path`, `@"path with spaces"`, or an absolute reference when the source is outside Pi's working directory.
6. `PiBridgeClient.inject()` sends one bounded newline-delimited JSON request.
7. The extension validates protocol version, session ID, working directory, draft revision, and request size.
8. `ctx.ui.setEditorText()` replaces Pi's unsent input and the extension requests a full repaint. It then returns a SHA-256 acknowledgement.
9. The user reviews and submits from Pi. Ghostwriter never submits automatically.

## Attachment state

`Attachment` separates three representations:

- **Display:** a configured editor path, defaulting to `@filename` inside Pi's working directory and an absolute `@/path` outside it
- **Local metadata:** original source path, editor path, preview kind, and ID in the persisted draft
- **Pi representation:** a relative or absolute reference to that original source

The UI intentionally does not ask users to distinguish files, folders, and images. A suffix-based kind is recorded only for local preview selection; folders have no local preview, while Pi can inspect the referenced path with its tools. Display markers are recalculated when the selected target or `pathDisplay` mode changes. Duplicate source paths and duplicate display markers are rejected because each marker must be unambiguous.

Deleting the final display marker removes its attachment metadata. Removing an attachment from the table performs the inverse operation and deletes every matching marker.

### Completion

The selected Pi session's working directory is the project root. `files.py` prefers `fd` for a bounded 20,000-path project index containing files and folders. VCS ignore rules are bypassed so paths listed only in `.git/info/exclude` remain available; explicit configured ignore files and common cache, dependency, and build-directory exclusions still apply. The retained project index consists only of relative path strings, with a trailing slash marking folders; absolute `Path` objects are created for the small result set.

After three filename characters and a 120 ms debounce, a thread worker queries the operating system's existing file index: Spotlight through `mdfind` on macOS or `locate` on other Unix systems. Search output is streamed with a 20,000-path cap instead of being captured without a bound. Results inside the project are removed, skipped and hidden directory policy is applied, and the candidate set is passed through the same ranker. Project candidates are displayed immediately and remain ahead of system candidates. New input cancels stale workers and terminates their index processes; a bounded session cache makes backspacing instant.

`fzf --filter` performs path-aware fuzzy ranking for both candidate sources, with a bounded-memory Python fallback for the project when unavailable. Global fzf options are inherited unless disabled in `fileSearch`. Queries beginning with `/` or a valid `~` expression use direct filesystem completion; incomplete expressions remain ordinary editable queries instead of raising from `Path.expanduser()`.

The Pi extension obtains loaded skills from `pi.getCommands()` and publishes only each name and description in the target registry. Ghostwriter filters that small in-memory list when `/skill` or `/skill:<partial-name>` appears immediately before the cursor after whitespace, including in the middle of a larger prompt. Descriptions are normalized for a one-line secondary label; no skill document is opened. Tab accepts the highlighted file or skill candidate.

## Rewrite flow

Rewrite is separate from visible Pi injection:

1. `ConfigStore` supplies file-search policy, ordered provider/model agents, target languages, extra instructions, warm-up policy, and the prompt template.
2. `RewriteConfigScreen` returns validated `RewriteOptions` from configured dropdowns.
3. `PiRpcSession.prepare()` launches an isolated process on demand and selects its configured model. Warm mode instead prewarms one process and starts a fresh Pi session for every workflow after the first.
4. `AttachmentProtector` replaces every local marker occurrence with a random opaque token.
5. Responses are checked so every expected placeholder occurs exactly once. One repair request is allowed if integrity fails.
6. The review screen supports acceptance, rejection, direct edits, and revision feedback in the same RPC conversation.
7. With the default on-demand mode, cleanup happens after each workflow. Warm mode retains the shared child until app shutdown. Both paths remove their private session directory.

No attachment path, filename, or content is sent to the rewrite model.

## UI and concurrency

Textual owns terminal rendering and input. Important custom behavior includes:

- `PromptTextArea`: intercepts bracketed paste and Tab completion without re-running Textual's default handlers, soft-wraps prose, keeps it white across themes, and styles attachment and `/skill:<name>` markers without changing their text;
- `DragHandle`: captures mouse events directly for independent width and height resizing;
- `Select`: shows only the current Pi target until its dropdown is opened and uses a disabled sentinel only when no target exists;
- `VerticalScroll`: keeps the side pane reachable in constrained layouts;
- thread workers: run blocking native file pickers and debounced system-index searches without freezing Textual;
- curated theme registration: exposes only comfortable dark choices in Textual's theme picker and persists the selected theme through `ui.theme`;
- filtered system commands: removes Textual's SVG screenshot export from the command palette;
- async workers: perform socket injection and Pi RPC communication.

The app switches between side-by-side and stacked layouts using terminal width and aspect ratio. TextArea supplies clipboard handling, history, selection, soft wrapping, and vertical scrolling.

## Persistence and runtime files

Paths use `platformdirs`, so exact locations vary by operating system:

- config: `user_config_path("ghostwriter")/config.json`
- state: `user_state_path("ghostwriter")/draft.json`
- rewrite sessions: `user_cache_path("ghostwriter")/rewrite-sessions/`
- legacy attachment cache: `user_cache_path("ghostwriter")/images/` (removed in a background startup task and never recreated)
- Pi registry: `<Pi agent dir>/run/ghostwriter/*.json`
- sockets: `/tmp/ghostwriter-<uid>/*.sock`

Draft and registry writes use temporary files followed by atomic rename. Sensitive local files and sockets use user-only permissions where the platform supports them.

## Compatibility boundaries

Changes at these boundaries require coordinated tests and documentation:

- draft schema version in `model.py`;
- socket protocol version in both `pi.py` and `extensions/ghostwriter.ts`;
- Pi RPC event and command names in `rewrite/pi_rpc.py`;
- Pi extension APIs described in `docs/pi-bridge.md`.
