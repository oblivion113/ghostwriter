import { createHash } from "node:crypto";
import { mkdir, chmod, rename, rm, writeFile } from "node:fs/promises";
import { createServer, type Server, type Socket } from "node:net";
import { join } from "node:path";
import {
  getAgentDir,
  type ExtensionAPI,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";

const PROTOCOL_VERSION = 1;
const MAX_REQUEST_BYTES = 4 * 1024 * 1024;
const RUNTIME_DIR = join(getAgentDir(), "run", "ghostwriter");
// Keep the socket path short enough for macOS's 104-byte AF_UNIX limit.
const SOCKET_DIR = join("/tmp", `ghostwriter-${process.getuid?.() ?? process.pid}`);

type DraftRequest = {
  version: number;
  target: { sessionId: string; cwd: string };
  draftId: string;
  revision: number;
  text: string;
};

type AppliedRevision = { revision: number; sha256: string };

function reply(socket: Socket, message: object): void {
  if (!socket.destroyed) socket.end(`${JSON.stringify(message)}\n`);
}

function parseRequest(value: unknown): DraftRequest {
  if (!value || typeof value !== "object") throw new Error("Request must be an object");
  const request = value as Partial<DraftRequest>;
  if (request.version !== PROTOCOL_VERSION) {
    throw new Error(`Unsupported protocol version: ${String(request.version)}`);
  }
  if (!request.target || typeof request.target !== "object") {
    throw new Error("Missing target");
  }
  if (typeof request.target.sessionId !== "string" || typeof request.target.cwd !== "string") {
    throw new Error("Invalid target");
  }
  if (typeof request.draftId !== "string" || request.draftId.length === 0) {
    throw new Error("Missing draftId");
  }
  if (!Number.isSafeInteger(request.revision) || (request.revision ?? -1) < 0) {
    throw new Error("revision must be a non-negative integer");
  }
  if (typeof request.text !== "string") throw new Error("text must be a string");
  return request as DraftRequest;
}

export default function ghostwriterBridge(pi: ExtensionAPI): void {
  let server: Server | undefined;
  let socketPath: string | undefined;
  let registryPath: string | undefined;
  let activeContext: ExtensionContext | undefined;
  const applied = new Map<string, AppliedRevision>();

  async function removeRuntimeFiles(): Promise<void> {
    await Promise.all([
      socketPath ? rm(socketPath, { force: true }).catch(() => undefined) : undefined,
      registryPath ? rm(registryPath, { force: true }).catch(() => undefined) : undefined,
    ]);
  }

  async function stop(): Promise<void> {
    activeContext = undefined;
    const current = server;
    server = undefined;
    if (current) {
      await new Promise<void>((resolve) => current.close(() => resolve()));
    }
    await removeRuntimeFiles();
    socketPath = undefined;
    registryPath = undefined;
  }

  async function writeRegistry(ctx: ExtensionContext): Promise<void> {
    if (!socketPath || !registryPath) return;
    const registry = {
      version: PROTOCOL_VERSION,
      pid: process.pid,
      sessionId: ctx.sessionManager.getSessionId(),
      sessionName: ctx.sessionManager.getSessionName(),
      cwd: ctx.cwd,
      socketPath,
      modelProvider: ctx.model?.provider,
      modelId: ctx.model?.id,
      thinkingLevel: ctx.thinkingLevel,
      startedAt: new Date().toISOString(),
    };
    const temporary = `${registryPath}.tmp-${process.pid}`;
    await writeFile(temporary, `${JSON.stringify(registry, null, 2)}\n`, { mode: 0o600 });
    await rename(temporary, registryPath);
  }

  function handleConnection(socket: Socket): void {
    let bytes = 0;
    let buffer = "";
    let handled = false;
    socket.setEncoding("utf8");
    socket.setTimeout(5_000, () => socket.destroy());

    socket.on("data", (chunk: string) => {
      if (handled) return;
      bytes += Buffer.byteLength(chunk);
      if (bytes > MAX_REQUEST_BYTES) {
        handled = true;
        reply(socket, { ok: false, error: "Draft exceeds the 4 MiB bridge limit" });
        return;
      }
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline < 0) return;
      handled = true;

      try {
        const request = parseRequest(JSON.parse(buffer.slice(0, newline)));
        const ctx = activeContext;
        if (!ctx) throw new Error("Pi session is shutting down");
        if (request.target.sessionId !== ctx.sessionManager.getSessionId()) {
          throw new Error("Target session changed; refresh targets in Ghostwriter");
        }
        if (request.target.cwd !== ctx.cwd) {
          throw new Error("Target working directory changed; refresh targets in Ghostwriter");
        }

        const sha256 = createHash("sha256").update(request.text).digest("hex");
        const previous = applied.get(request.draftId);
        if (previous && request.revision < previous.revision) {
          throw new Error(`Stale draft revision ${request.revision}; latest is ${previous.revision}`);
        }
        if (
          previous &&
          request.revision === previous.revision &&
          previous.sha256 !== sha256
        ) {
          throw new Error("A revision may not be reused with different content");
        }

        ctx.ui.setEditorText(request.text);
        applied.set(request.draftId, { revision: request.revision, sha256 });
        reply(socket, {
          ok: true,
          revision: request.revision,
          sha256,
          sessionId: ctx.sessionManager.getSessionId(),
        });
      } catch (error) {
        reply(socket, {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    });

    socket.on("error", () => undefined);
  }

  pi.on("session_start", async (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    await stop();
    activeContext = ctx;
    await mkdir(RUNTIME_DIR, { recursive: true, mode: 0o700 });
    await mkdir(SOCKET_DIR, { recursive: true, mode: 0o700 });
    await chmod(RUNTIME_DIR, 0o700);
    await chmod(SOCKET_DIR, 0o700);

    const shortSession = ctx.sessionManager.getSessionId().replace(/[^a-zA-Z0-9]/g, "").slice(0, 10);
    const baseName = `pi-${process.pid}-${shortSession}`;
    socketPath = join(SOCKET_DIR, `${baseName}.sock`);
    registryPath = join(RUNTIME_DIR, `${baseName}.json`);
    await removeRuntimeFiles();

    server = createServer(handleConnection);
    await new Promise<void>((resolve, reject) => {
      const current = server!;
      const onError = (error: Error) => reject(error);
      current.once("error", onError);
      current.listen(socketPath!, () => {
        current.off("error", onError);
        resolve();
      });
    });
    await chmod(socketPath, 0o600);
    await writeRegistry(ctx);
  });

  pi.on("session_info_changed", async (_event, ctx) => {
    await writeRegistry(ctx);
  });

  pi.on("model_select", async (_event, ctx) => {
    await writeRegistry(ctx);
  });

  pi.on("thinking_level_select", async (_event, ctx) => {
    await writeRegistry(ctx);
  });

  pi.on("session_shutdown", async () => {
    await stop();
  });
}
