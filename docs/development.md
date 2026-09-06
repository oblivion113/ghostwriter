# Development

This repository is both a Python application and a Pi package. Python provides the Textual TUI; TypeScript provides the Pi extension.

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- Pi 0.84.4 or a compatible release exposing the APIs documented in [`pi-bridge.md`](pi-bridge.md)
- A terminal with mouse reporting and bracketed paste support; Ghostty is the primary target
- Optional: `fd` for ignored-aware indexing and `fzf` for fuzzy `@` ranking

macOS uses Finder through `osascript` for file selection. Other platforms use Python's Tk file dialog when available. Missing `fd` or `fzf` automatically uses the native Python search fallback.

## One-command setup

```bash
./scripts/setup
```

The setup script intentionally changes user-level state. It:

1. creates or updates `.venv` with Python runtime and development dependencies;
2. installs locked TypeScript development dependencies with `npm ci`;
3. compiles the extension and builds the Python wheel and source distribution;
4. installs the `ghostwriter` command as an editable uv tool;
5. registers this repository as a local Pi package with `pi install <repository>`;
6. removes the legacy direct extension symlink if one exists.

Restart Pi or run `/reload` afterward.

## Manual setup

Contributors who do not want user-level installation can use only the project environments:

```bash
uv sync --dev
npm ci
./scripts/check
uv run ghostwriter
```

To load the extension temporarily in a separate Pi process:

```bash
pi -e ./extensions/ghostwriter.ts
```

To register the repository through Pi's package manager:

```bash
./scripts/install-pi-extension
```

## Build and verification

```bash
./scripts/check
./scripts/build
```

`check` runs:

- TypeScript strict type checking without emit;
- Ruff over the Python tree;
- the complete pytest suite.

`build` produces:

- `build/pi/ghostwriter.js` and its source map;
- Python wheel and source archive under `dist/`.

Generated artifacts and dependency directories are ignored by Git. The extension source under `extensions/` remains the canonical Pi package resource because Pi supports TypeScript extensions directly.

Individual commands are also available:

```bash
npm run check
npm run build
uv run ruff check .
uv run pytest
uv build
npm pack --dry-run
```

## Pi package metadata

`package.json` serves three purposes:

- declares `extensions/ghostwriter.ts` in the `pi.extensions` manifest;
- records Pi core as a peer dependency, as required for Pi packages;
- provides a reproducible local TypeScript toolchain for contributors and CI.

Pi core is a peer dependency because the running Pi host supplies it. It is also an exact development dependency so local type checks are reproducible. Runtime third-party extension dependencies, if introduced later, belong in `dependencies`, not `devDependencies`.

A local install stores the resolved repository path in Pi's user settings. Git and npm installations use the same package manifest. See [`pi-bridge.md`](pi-bridge.md) for lifecycle and protocol details.

## Testing strategy

- `tests/test_app.py`: Textual interactions, autocomplete integration, attachments, previews, responsive layout, and real geometry changes from divider drags
- `tests/test_completions.py`: inline grammar, slash routing, and name filtering
- `tests/test_files.py`: path parsing, indexing, file completion, and preview bounds
- `tests/test_model.py`: draft migration and attachment-marker behavior
- `tests/test_pi.py`: serialization, target metadata, discovery, stale cleanup, and socket exchange
- `tests/test_storage.py`: atomic draft persistence and legacy cache cleanup
- `tests/rewrite/`: RPC framing, placeholder integrity, service prompts, and modal controls

Tests use temporary state paths. New tests should not depend on the user's live draft, Pi registry, or cache.

## Debugging

### Pi target is absent

1. Confirm the package is listed with `pi list`.
2. Restart Pi or run `/reload`.
3. Run `/ghostwriter-status` in Pi.
4. Check `<Pi agent dir>/run/ghostwriter/` for a registry JSON file.
5. Confirm the corresponding socket exists under `/tmp/ghostwriter-<uid>/`.
6. Press `Ctrl+R` in Ghostwriter.

The extension starts its socket only for interactive TUI sessions.

### Injection is rejected

Refresh targets after `/new`, `/resume`, a working-directory change, or Pi restart. The bridge intentionally rejects session and directory mismatches. Revision reuse with different content is also rejected.

### Rewrite fails

Run `pi --mode rpc` independently to verify the installed Pi supports RPC mode and the selected provider/model is authenticated. Rewrite stderr is retained as a short in-memory tail and included when the child process exits unexpectedly.

### Mouse behavior differs by terminal

Textual requires terminal mouse reporting. Divider widgets own mouse capture directly; tests verify that drag events change actual widget geometry. Terminal multiplexers must pass mouse events through.

## Changing protocol or persistence

- Bump `PROTOCOL_VERSION` in Python and TypeScript together.
- Update request validation and tests on both sides.
- Document wire changes in `pi-bridge.md`.
- Bump the draft schema version when persisted fields or marker representation changes.
- Add migration coverage before changing existing state.

## Release checklist

1. Update versions in `pyproject.toml` and `package.json` together.
2. Update `CHANGELOG.md` once the project begins publishing tagged releases.
3. Run `./scripts/check` and `./scripts/build`.
4. Inspect `npm pack --dry-run` and the wheel contents.
5. Test setup from a clean checkout and a fresh Pi session.
6. Tag the commit only after both the Python package and Pi extension are reproducible.

## Uninstall

```bash
./scripts/uninstall-pi-extension
uv tool uninstall ghostwriter
```

Project development environments can be removed separately with `rm -rf .venv node_modules build dist`.
