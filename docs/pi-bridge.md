# Pi bridge

Ghostwriter is intentionally Pi-specific. The integration has two parts:

- `src/ghostwriter/pi.py` discovers Pi sessions, serializes attachments using Pi syntax, and sends drafts.
- `pi-extension.ts` publishes live session metadata and replaces Pi's unsent editor text.

## Session discovery

Each interactive Pi session writes a permission-restricted registry record containing:

- session ID and optional session name;
- working directory;
- provider, model, and thinking level;
- process ID;
- Unix socket path;
- stable start time and latest metadata update time.

Ghostwriter removes stale records when their process or socket no longer exists. The target selector uses the session name, project directory, model, and shortened session ID; the detail panel shows the full working directory, provider/model, thinking level, and PID.

Run `/ghostwriter-status` inside Pi to display the same identifying information for the current session.

## Injection protocol

The bridge uses newline-delimited JSON over a user-only Unix socket. Every request includes the target session and working directory, a draft ID, a monotonic revision, and the serialized text.

The Pi extension:

1. rejects oversized, malformed, stale, or mismatched requests;
2. replaces only the unsent editor content;
3. never submits the prompt or mutates session history;
4. acknowledges the applied revision and SHA-256 digest;
5. removes its socket and registry record during normal shutdown.

The socket path stays under `/tmp/ghostwriter-<uid>` to remain below macOS's Unix-socket path limit. Registry records live under Pi's agent runtime directory.
