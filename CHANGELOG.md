# Changelog

All notable changes to Ghostwriter will be documented here. The project follows semantic versioning once releases are tagged.

## Unreleased

- Reserved visible space for prompt actions in compact and stacked layouts.
- Consolidated Pi target identity into one concise scrollable list.
- Added unified JSON configuration for provider/model rewrite agents, languages, extra instructions, RPC warm-up, and custom prompts, with default-editor and live-reload controls.
- Kept one isolated rewrite RPC process warm across workflows while resetting conversation state and cleaning it up on exit.
- Prevented the default rewrite prompt from adding headings to short, single-section drafts.
- Added optional `fd` indexing and `fzf` fuzzy ranking for `@` completion, with configurable exclusions and a hidden/cache-free Python fallback.
- Fixed duplicate terminal paste and speech-recognition insertion caused by re-running Textual's default handlers.
- Soft-wrapped prompt text without horizontal scrolling and replaced the expanded Pi target list with a dropdown that has no selectable empty entry.
- Removed SVG screenshot export, limited themes to comfortable dark palettes, kept prompt prose white, and highlighted attachment markers in the editor.

## 0.2.0 - 2026-08-29

- Added protected translation and tidying through isolated Pi RPC sessions.
- Unified drag, native picker, and `@` autocomplete attachment workflows.
- Added raw text and image previews with atomic attachment removal.
- Added responsive, scrollable panes with independent mouse-draggable dividers.
- Replaced the generic adapter layer with a focused Pi bridge client and extension.
- Added reproducible Python and TypeScript builds, Pi package metadata, setup automation, and contributor documentation.

## 0.1.0 - 2026-08-28

- Added the initial Textual composer, persistent drafts, Pi target discovery, and non-submitting editor injection.
