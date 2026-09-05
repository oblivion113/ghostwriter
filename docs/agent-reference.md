# Agent Reference

This page gives coding agents a compact orientation to Ghostwriter. It is a reference document rather than an automatically loaded harness context file.

Ghostwriter is a Pi-only terminal prompt composer: it composes locally, transforms through an isolated Pi RPC process when requested, and replaces—but never submits—the unsent editor text in a selected Pi TUI.

## Repository map

- `src/ghostwriter/app.py`: Textual UI and interaction orchestration
- `src/ghostwriter/model.py`: persisted draft and attachment model
- `src/ghostwriter/files.py`: path discovery, completion, native picker, and text previews
- `src/ghostwriter/pi.py`: Pi target discovery, serialization, and Unix-socket client
- `src/ghostwriter/rewrite/`: isolated Pi RPC rewrite workflow and placeholder integrity
- `extensions/ghostwriter.ts`: Pi extension, target registry, and editor injection server
- `tests/`: Python behavior and protocol tests
- `docs/architecture.md`: data flow and design rationale
- `docs/pi-bridge.md`: self-contained Pi API and wire-protocol reference

## Verification

```bash
./scripts/check   # TypeScript check, Ruff, and pytest
./scripts/build   # Pi extension JavaScript plus Python wheel/sdist
```

`./scripts/setup` performs a full local installation and changes the user's Pi settings. It is only needed when installation behavior is under test.

## Design constraints

Changes should retain these properties:

- Injection replaces Pi's unsent editor text and never submits it.
- The Python client and TypeScript extension use the same protocol version and validation rules.
- Attachment display markers remain local UI state; Pi-specific paths are produced only during serialization.
- Rewrite models receive opaque attachment placeholders, never local paths or attachment names.
- Registry files and sockets remain user-only, bounded, and disposable after crashes.
- Long-lived extension resources start on `session_start` and stop on `session_shutdown`.
- Ghostwriter remains Pi-specific; a generic adapter layer is only useful when backed by a concrete requirement.

Changes to Pi integration should also update `docs/pi-bridge.md`, which keeps the integration understandable without private harness documentation.
