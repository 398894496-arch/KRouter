#!/usr/bin/env node
/**
 * Spawn KRouter. No vector store. Read-only routes only.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ALLOWED = new Set([
  "status",
  "preference",
  "correction",
  "memory",
  "project",
  "search",
  "suggest",
]);

const HERE = dirname(fileURLToPath(import.meta.url));

function isForeignLiveRouter(path) {
  return String(path).includes("obsidian-knowledge-router");
}

export function resolveRouter(explicit) {
  const bundled = resolve(
    HERE,
    "../../../skill/krouter/scripts/route_knowledge.sh",
  );
  const bundledPy = resolve(
    HERE,
    "../../../skill/krouter/scripts/route_knowledge.py",
  );
  const installed = join(
    homedir(),
    ".agents/skills/krouter/scripts/route_knowledge.sh",
  );
  const installedPy = join(
    homedir(),
    ".agents/skills/krouter/scripts/route_knowledge.py",
  );
  // 2.0 以前的安装目录（升级后是指向新目录的链接）
  const legacy = join(homedir(), ".agents/skills/krouter-obsidian/scripts/route_knowledge.sh");
  const legacyPy = join(homedir(), ".agents/skills/krouter-obsidian/scripts/route_knowledge.py");
  const preferPy = platform() === "win32";
  const candidates = (
    preferPy
      ? [explicit, process.env.KROUTER_ROUTER, bundledPy, installedPy, bundled, installed, legacyPy, legacy]
      : [explicit, process.env.KROUTER_ROUTER, bundled, installed, bundledPy, installedPy, legacy, legacyPy]
  ).filter(Boolean);
  for (const path of candidates) {
    if (isForeignLiveRouter(path)) continue;
    if (existsSync(path)) return path;
  }
  return null;
}

function pythonArgv(script, args) {
  const exe = process.env.PYTHON || process.env.KROUTER_PYTHON || "";
  if (exe) return [exe, [script, ...args]];
  if (platform() === "win32") return ["py", ["-3", script, ...args]];
  return ["python3", [script, ...args]];
}

export function resolveVault(explicit) {
  return explicit || process.env.KROUTER_VAULT || process.env.OBSIDIAN_VAULT || "";
}

export function runRoute({ route, query = "", vault, router, timeoutMs = 20000 } = {}) {
  if (!ALLOWED.has(route)) {
    return {
      ok: false,
      code: 2,
      stdout: "",
      stderr: `refused route: ${route}. read-only: ${[...ALLOWED].join("|")}\n`,
    };
  }
  const vaultRoot = resolveVault(vault);
  if (!vaultRoot) {
    return { ok: false, code: 2, stdout: "", stderr: "set KROUTER_VAULT (or OBSIDIAN_VAULT) or vaultPath\n" };
  }
  const script = resolveRouter(router);
  if (!script) {
    return {
      ok: false,
      code: 2,
      stdout: "",
      stderr: "route_knowledge.sh not found. run ./scripts/install.sh or set KROUTER_ROUTER\n",
    };
  }
  const args = [route];
  if (query) args.push(query);
  const isPy = String(script).endsWith(".py");
  const result = isPy
    ? spawnSync(...pythonArgv(script, args), {
        encoding: "utf8",
        timeout: timeoutMs,
        cwd: dirname(script),
        env: { ...process.env, KROUTER_VAULT: vaultRoot, OBSIDIAN_VAULT: vaultRoot },
      })
    : spawnSync(script, args, {
        encoding: "utf8",
        timeout: timeoutMs,
        env: { ...process.env, KROUTER_VAULT: vaultRoot, OBSIDIAN_VAULT: vaultRoot },
      });
  return {
    ok: result.status === 0,
    code: result.status ?? 1,
    stdout: result.stdout || "",
    stderr: result.stderr || (result.error ? String(result.error) : ""),
  };
}

export function parseReceipt(text) {
  const fields = {};
  for (const line of text.split("\n")) {
    const idx = line.indexOf(":");
    if (idx < 1) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (key && !(key in fields)) fields[key] = value;
  }
  return fields;
}
