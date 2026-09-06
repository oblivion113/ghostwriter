# Changelog

All notable changes to Ghostwriter will be documented here. The project follows semantic versioning once releases are tagged.

## Unreleased

- Prevented the horizontal split from pushing the side pane beyond the viewport, removed the redundant app-name header, and renamed **Reload config** to **Refresh**; the broader command also refreshes targets, Skills, and file indexes.
- Expanded `@` completion to the operating system's file index, with selected-project matches first plus debounced, bounded, and cancellable background searches.
- Added configurable attachment path display: compact names inside Pi's working directory and absolute paths outside by default, or full paths everywhere.
- Fixed crashes from incomplete `~` path expressions and restored additional `@` completions on the same prompt line.
- Added folder attachments with trailing-slash markers to `@` completion and kept Git-locally-excluded paths searchable.
- Persisted Theme palette choices through a validated `ui.theme` configuration field.
- Replaced the auto-loaded `AGENTS.md` with an opt-in agent reference page.
- Added target-aware `/skill:<name>` completion anywhere in the prompt, with Tab insertion, one-line descriptions, and highlighted skill tokens.
- Reserved visible space for prompt actions in compact and stacked layouts.
- Consolidated Pi target identity into one concise scrollable list.
- Added unified JSON configuration for provider/model rewrite agents, languages, extra instructions, RPC warm-up, and custom prompts, with default-editor and live-reload controls.
- Kept one isolated rewrite RPC process warm across workflows while resetting conversation state and cleaning it up on exit.
- Prevented the default rewrite prompt from adding headings to short, single-section drafts.
- Added optional `fd` indexing and `fzf` fuzzy ranking for `@` completion, with configurable exclusions and a hidden/cache-free Python fallback.
- Fixed duplicate terminal paste and speech-recognition insertion caused by re-running Textual's default handlers.
- Soft-wrapped prompt text without horizontal scrolling and replaced the expanded Pi target list with a dropdown that has no selectable empty entry.
- Removed SVG screenshot export, limited themes to comfortable dark palettes, kept prompt prose white, and highlighted attachment markers in the editor.
- Forced a full Pi repaint after injection so changed line prefixes and wrapping no longer leave stale editor cells.
- Kept attachment markers highlighted on the active line and added natural wrapping for mixed CJK prose without changing the saved text.
- Replaced the clock and subtitle header with a compact Settings command menu; configuration actions join the original Theme, Keys, Quit, and layout commands.

## 0.2.0 - 2026-08-29

- Added protected translation and tidying through isolated Pi RPC sessions.
- Unified drag, native picker, and `@` autocomplete attachment workflows.
- Added raw text and image previews with atomic attachment removal.
- Added responsive, scrollable panes with independent mouse-draggable dividers.
- Replaced the generic adapter layer with a focused Pi bridge client and extension.
- Added reproducible Python and TypeScript builds, Pi package metadata, setup automation, and contributor documentation.

## 0.1.0 - 2026-08-28

- Added the initial Textual composer, persistent drafts, Pi target discovery, and non-submitting editor injection.
