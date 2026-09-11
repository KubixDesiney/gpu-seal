import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { access } from "node:fs/promises";
import { resolve } from "node:path";

const origin = "http://127.0.0.1:4173";

async function waitForServer(server: ChildProcess): Promise<void> {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`production server exited with code ${server.exitCode}`);
    }
    try {
      const response = await fetch(`${origin}/`);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  throw new Error("timed out waiting for the production server");
}

function stopServer(server: ChildProcess): void {
  if (server.exitCode !== null || server.pid === undefined) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(server.pid), "/t", "/f"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    server.kill("SIGTERM");
  }
}

export default async function globalSetup(): Promise<() => void> {
  const cli = resolve(process.cwd(), "node_modules/vinext/dist/cli.js");
  await access(cli);
  const server = spawn(
    process.execPath,
    [cli, "start", "--port", "4173", "--hostname", "127.0.0.1"],
    { cwd: process.cwd(), stdio: "ignore", windowsHide: true },
  );
  try {
    await waitForServer(server);
  } catch (error) {
    stopServer(server);
    throw error;
  }
  return () => stopServer(server);
}
