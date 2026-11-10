#!/usr/bin/env node
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseReceipt, resolveRouter, runRoute } from "./lib/route.js";

// Tests are not the host's traffic: the nightly learning reads the query log.
process.env.KROUTER_NO_QUERY_LOG = "1";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const VAULT = join(ROOT, "template");
const ROUTER = join(ROOT, "skill/krouter/scripts/route_knowledge.sh");

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) {
    console.log(`ok ${name}`);
    return;
  }
  failed += 1;
  console.error(`FAIL ${name}${detail ? `\n${detail}` : ""}`);
}

const status = runRoute({ route: "status", vault: VAULT, router: ROUTER });
check("status exit 0", status.ok, status.stderr);
check(
  "status home page",
  status.stdout.includes("Agent第二大脑.md"),
  status.stdout,
);
check(
  "status host_action",
  status.stdout.includes("host_action:"),
  status.stdout,
);

const home = runRoute({ route: "search", query: "home", vault: VAULT, router: ROUTER });
const homeFields = parseReceipt(home.stdout);
check("search home exit 0", home.ok, home.stderr);
check("search home Q01", homeFields.canonical_id === "Q01", home.stdout);
check("search home match true", homeFields.canonical_match === "true", home.stdout);

const correction = runRoute({
  route: "correction",
  query: "correction",
  vault: VAULT,
  router: ROUTER,
});
check("correction Q05", parseReceipt(correction.stdout).canonical_id === "Q05", correction.stdout);

const memory = runRoute({ route: "memory", query: "memory", vault: VAULT, router: ROUTER });
check("memory Q07", parseReceipt(memory.stdout).canonical_id === "Q07", memory.stdout);

const suggest = runRoute({ route: "suggest", query: "homz", vault: VAULT, router: ROUTER });
check("suggest homz mentions Q01", suggest.stdout.includes("Q01"), suggest.stdout);
check(
  "suggest is not a hit",
  !suggest.stdout.includes("canonical_match: true"),
  suggest.stdout,
);

const write = runRoute({ route: "rm", query: "/", vault: VAULT, router: ROUTER });
check("refuse non-route", !write.ok && write.stderr.includes("refused route"), write.stderr);

const savedRouter = process.env.KROUTER_ROUTER;
process.env.KROUTER_ROUTER = join(
  homedir(),
  ".agents/skills/obsidian-knowledge-router/scripts/route_knowledge.sh",
);
const pinned = resolveRouter();
if (savedRouter !== undefined) process.env.KROUTER_ROUTER = savedRouter;
else delete process.env.KROUTER_ROUTER;
check(
  "skip live foreign router",
  Boolean(pinned) && !String(pinned).includes("obsidian-knowledge-router"),
  pinned,
);

const savedVault = process.env.OBSIDIAN_VAULT;
const savedAlt = process.env.KROUTER_VAULT;
delete process.env.OBSIDIAN_VAULT;
delete process.env.KROUTER_VAULT;
const missing = runRoute({ route: "status", router: ROUTER });
if (savedVault !== undefined) process.env.OBSIDIAN_VAULT = savedVault;
if (savedAlt !== undefined) process.env.KROUTER_VAULT = savedAlt;
check("missing vault fails", !missing.ok, missing.stderr);

if (failed) {
  console.error(`\n${failed} failed`);
  process.exit(1);
}
console.log("\nDSH bridge tests passed on template vault");
