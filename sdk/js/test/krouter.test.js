// The JS client against KRouter's real server: over stdio (it starts one) and over Streamable HTTP (a team server).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { cpSync, mkdtempSync, writeFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { KRouter, Answer } from "../index.js";

const REPO = resolve(import.meta.dirname, "..", "..", "..");
const SERVER = join(REPO, "skill", "krouter-obsidian", "scripts", "mcp_server.py");
const PY = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const TOKEN = "js-test-token-0123456789abcdef";
let dir, vault, http, url;

before(async () => {
  dir = mkdtempSync(join(tmpdir(), "krouter-js-"));
  vault = join(dir, "vault");
  cpSync(join(REPO, "template"), vault, { recursive: true });
  writeFileSync(join(vault, "02 经验与方法", "API port.md"),
    "---\ntitle: API port\nstatus: active\nhow: The local API listens on 8080.\n---\n\n# API port\n\nThe local API listens on 8080.\n");
  Object.assign(process.env, { KROUTER_CACHE_DIR: join(dir, "cache"), KROUTER_STATE_DIR: join(dir, "state"),
    KROUTER_NO_QUERY_LOG: "1" });
  const tokenFile = join(dir, "token");
  writeFileSync(tokenFile, TOKEN);
  chmodSync(tokenFile, 0o600);
  http = spawn(PY, [SERVER, "--http", "127.0.0.1:0", "--vault", vault, "--token-file", tokenFile],
    { stdio: ["ignore", "ignore", "pipe"] });
  url = await new Promise((ok, fail) => {
    const rl = createInterface({ input: http.stderr });
    rl.on("line", (l) => { if (l.startsWith("{") && l.includes("listening")) ok(JSON.parse(l).listening); });
    http.on("exit", () => fail(new Error("server exited")));
  });
});

after(() => { http?.kill(); });

async function checks(kr) {
  assert.ok((await kr.tools()).includes("krouter_ask"));
  const a = await kr.ask("what port does the local api listen on");
  assert.ok(a instanceof Answer);
  assert.equal(a.refused, false);
  assert.match(a.page, /API port\.md$/);
  assert.match(a.how, /8080/);
  const none = await kr.ask("which espresso grinder setting do we use");
  assert.equal(none.refused, true);
  assert.equal(none.page, "");
  assert.equal(none.how, "");
}

test("local, over stdio", async () => {
  const kr = KRouter.local({ vault, python: PY, server: SERVER });
  try { await checks(kr); } finally { await kr.close(); }
});

test("team server, over Streamable HTTP with a token", async () => {
  await checks(KRouter.remote(url, { token: TOKEN }));
});

test("a wrong token is refused", async () => {
  await assert.rejects(KRouter.remote(url, { token: "wrong-token-0123456789" }).ask("x"), /HTTP 401/);
});
