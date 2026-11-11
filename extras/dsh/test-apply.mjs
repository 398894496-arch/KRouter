#!/usr/bin/env node
/**
 * Register + execute against the template vault. Does not import DSH peers
 * and does not call `dsh plugin add`.
 */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { KROUTER_TOOL_NAMES, registerKrouterTools } from "./lib/register.js";

// Tests are not the host's traffic: the nightly learning reads the query log.
process.env.KROUTER_NO_QUERY_LOG = "1";

const HERE = dirname(fileURLToPath(import.meta.url));
const registered = [];
registerKrouterTools(
  {
    tools: {
      register(tool) {
        registered.push(tool);
      },
    },
  },
  {
    vaultPath: join(HERE, "../../template"),
    routerScript: join(HERE, "../../skill/krouter/scripts/route_knowledge.sh"),
  },
  (spec) => spec,
);

const names = registered.map((t) => t.name);
if (names.join() !== KROUTER_TOOL_NAMES.join()) {
  console.error("FAIL tool names", names);
  process.exit(1);
}

const search = registered.find((t) => t.name === "krouter_search");
const out = await Promise.resolve(search.execute({ query: "home" }));
if (!out.ok || out.canonical_id !== "Q01" || out.canonical_match !== "true") {
  console.error("FAIL execute search home", out);
  process.exit(1);
}

const correction = registered.find((t) => t.name === "krouter_correction");
const corr = await Promise.resolve(correction.execute({ query: "correction" }));
if (!corr.ok || corr.canonical_id !== "Q05" || corr.canonical_match !== "true") {
  console.error("FAIL execute correction", corr);
  process.exit(1);
}

const memory = registered.find((t) => t.name === "krouter_memory");
const mem = await Promise.resolve(memory.execute({ query: "memory" }));
if (!mem.ok || mem.canonical_id !== "Q07" || mem.canonical_match !== "true") {
  console.error("FAIL execute memory", mem);
  process.exit(1);
}

const suggest = registered.find((t) => t.name === "krouter_suggest");
const hint = await Promise.resolve(suggest.execute({ query: "homz" }));
if (!hint.text.includes("Q01") || hint.canonical_match === "true") {
  console.error("FAIL execute suggest", hint);
  process.exit(1);
}

console.log("ok register + execute memory-system routes on template");
