# Ghostwriter Agent Guide

Ghostwriter is a Pi-only terminal prompt composer. Agents should preserve its narrow purpose: compose locally, transform through an isolated Pi RPC process when requested, and replace—but never submit—the unsent editor text in a selected Pi TUI.

## Repository map

- `src/ghostwriter/app.py`: Textual UI and interaction orchestration
- `src/ghostwriter/model.py`: persisted draft and attachment model
- `src/ghostwriter/files.py`: file discovery, completion, native picker, and text previews
- `src/ghostwriter/pi.py`: Pi target discovery, serialization, and Unix-socket client
- `src/ghostwriter/rewrite/`: isolated Pi RPC rewrite workflow and placeholder integrity
- `extensions/ghostwriter.ts`: Pi extension, target registry, and editor injection server
- `tests/`: Python behavior and protocol tests
- `docs/architecture.md`: data flow and design rationale
- `docs/pi-bridge.md`: self-contained Pi API and wire-protocol reference

## Commands

```bash
./scripts/setup   # full local installation; changes the user's Pi settings
./scripts/check   # TypeScript check, Ruff, and pytest
./scripts/build   # Pi extension JavaScript plus Python wheel/sdist
```

Agents should run `./scripts/check` after code changes. Setup is unnecessary unless installation behavior changes and should not be run casually because it installs a user-level command and Pi package.

## Invariants

- Injection replaces Pi's unsent editor text and never submits it.
- The Python client and TypeScript extension must agree on protocol version and validation.
- Attachment display markers remain local UI state; Pi-specific paths are produced only during serialization.
- Rewrite models receive opaque attachment placeholders, never local paths or attachment filenames.
- Registry files and sockets remain user-only, bounded, and disposable after crashes.
- Long-lived extension resources start on `session_start` and stop on `session_shutdown`.
- Ghostwriter remains Pi-specific; generic adapter layers should not be reintroduced without a concrete requirement.

When changing Pi integration, Agents should update `docs/pi-bridge.md` in the same change so contributors do not need private harness documentation.
