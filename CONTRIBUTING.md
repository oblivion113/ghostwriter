# Contributing

Thanks for improving Ghostwriter. The project is intentionally small, local, and Pi-specific.

## Start here

1. Read [`docs/architecture.md`](docs/architecture.md) for component and data flow.
2. Read [`docs/pi-bridge.md`](docs/pi-bridge.md) before changing Pi integration.
3. Follow [`docs/development.md`](docs/development.md) for setup, tests, debugging, and releases.

For a development-only checkout:

```bash
uv sync --dev
npm ci
./scripts/check
```

`./scripts/setup` performs a full user installation and changes Pi's user settings, so contributors should run it only when they want to test installation behavior.

## Change guidelines

- Keep injection reviewable: Ghostwriter may replace Pi's unsent editor but must never submit it.
- Prefer direct Pi-specific code over speculative abstraction.
- Preserve attachment placeholder integrity and local-path privacy during rewrites.
- Add regression coverage for user-visible behavior and protocol changes.
- Keep Python and TypeScript protocol changes synchronized.
- Update relevant documentation in the same change.

## Before submitting a change

```bash
./scripts/check
./scripts/build
```

Confirm the working tree contains no generated artifacts. For installation changes, test from a clean checkout and verify `pi list`, `/reload`, `/ghostwriter-status`, target discovery, and one non-submitting editor injection.
