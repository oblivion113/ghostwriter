# Injection adapters

Ghostwriter keeps editor concerns separate from target-tool behavior. A target adapter implements the `InjectionAdapter` protocol in `src/ghostwriter/adapters/base.py`.

## Responsibilities

An adapter owns three operations:

1. `discover_targets()` returns currently reachable `InjectionTarget` values.
2. `serialize(draft, target)` converts the structured draft and attachments to text understood by that CLI.
3. `inject(target, request)` replaces the target's unsent input and returns an acknowledgement.

The UI only talks to `AdapterRegistry`; it has no Pi-specific branches.

## Adding a target

Create `src/ghostwriter/adapters/<tool>.py`:

```python
class ExampleAdapter:
    id = "example"
    display_name = "Example CLI"

    def discover_targets(self) -> list[InjectionTarget]:
        ...

    def serialize(self, draft: Draft, target: InjectionTarget) -> str:
        ...

    async def inject(
        self,
        target: InjectionTarget,
        request: InjectionRequest,
    ) -> dict[str, object]:
        ...
```

Register one instance in `AdapterRegistry`. Keep tool-specific bridge code under `bridges/<tool>/` and protocol tests under `tests/adapters/`.

## Integration standard

Prefer, in order:

1. A documented extension/plugin API that replaces unsent editor content
2. A documented local IPC or control API
3. A small, version-pinned bridge that uses stable public APIs

Do not silently fall back to terminal keystroke simulation or clipboard typing. If a target cannot safely replace its unsent editor, report it as unsupported. Injection must not submit, start a new session, or mutate the target's history.

Each bridge should:

- use authenticated or permission-restricted local transport;
- identify its process, session, and working directory;
- reject stale revisions and mismatched targets;
- bound request size and parsing work;
- acknowledge the applied content hash;
- remove discovery records during normal shutdown;
- tolerate stale discovery records after crashes.

Serialization belongs to the adapter because file and image syntax differs between tools. Rich attachment state remains in Ghostwriter.
