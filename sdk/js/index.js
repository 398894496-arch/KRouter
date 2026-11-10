// KRouter from JavaScript / TypeScript. No dependencies: it speaks MCP (JSON-RPC) to KRouter's own server, either a
// local one it starts over stdio, or a team server over Streamable HTTP.
//
//   import { KRouter } from "krouter";
//   const kr = KRouter.local();                                  // the vault the one-line install recorded
//   const a = await kr.ask("how do we ship a release?");
//   a.page, a.how, a.refused                                     // source page, one-line answer, true = not in the vault
//   await kr.close();
//
//   const team = KRouter.remote("https://krouter.example/mcp/team", { token: process.env.KROUTER_TOKEN });
import { spawn } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";

const PROTOCOL = "2025-06-18";
const DEFAULT_SERVER = join(homedir(), ".agents", "skills", "krouter-obsidian", "scripts", "mcp_server.py");

/** One receipt, read the same way as the Python SDK's `Answer`. */
export class Answer {
  constructor(text, isError = false) {
    this.text = text;
    this.isError = isError;
    this.fields = {};
    for (const line of text.split("\n")) {
      const i = line.indexOf(": ");
      if (i > 0 && !/^[ \-|]/.test(line)) {
        const k = line.slice(0, i).trim();
        if (!(k in this.fields)) this.fields[k] = line.slice(i + 2).trim();
      }
    }
  }

  /** Pages recall listed, best first: {page, tier, status, how}. A replaced page can be listed; it is never the answer. */
  get hits() {
    const out = [];
    let inside = false;
    for (const line of this.text.split("\n")) {
      if (line.startsWith("recall:")) { inside = line.trim() === "recall:"; continue; }
      if (!inside) continue;
      if (line.startsWith("- ")) {
        const body = line.slice(2);
        const at = body.indexOf(" tier=");
        const meta = {};
        if (at >= 0) for (const kv of ("tier=" + body.slice(at + 6)).split(/\s+/)) {
          const j = kv.indexOf("=");
          if (j > 0) meta[kv.slice(0, j)] = kv.slice(j + 1);
        }
        out.push({ page: (at >= 0 ? body.slice(0, at) : body).trim(), tier: meta.tier || "", status: meta.status || "", how: "" });
      } else if (line.startsWith("  how: ") && out.length) {
        out[out.length - 1].how = line.slice(7).trim();
      } else if (!line.startsWith(" ")) {
        inside = false;
      }
    }
    return out;
  }

  get refused() { return (this.fields.recall || "").startsWith("none"); }
  get confidence() { return this.fields.recall_confidence || ""; }

  #top() { return this.hits.find((h) => h.tier !== "dead" && h.status !== "superseded") || {}; }

  /** The page the answer comes from: the locked page on an exact match, else recall's best live page. */
  get page() {
    if (this.fields.canonical_match === "true") return this.fields.source || "";
    return this.refused ? "" : this.#top().page || "";
  }

  /** The one line that answers it; empty when the memory does not know. */
  get how() { return this.refused ? "" : this.#top().how || this.fields.how || ""; }

  toString() { return this.text; }
}

class StdioTransport {
  constructor(command, args, env) {
    this.proc = spawn(command, args, { env: { ...process.env, ...env }, stdio: ["pipe", "pipe", "ignore"] });
    this.waiting = new Map();
    createInterface({ input: this.proc.stdout }).on("line", (line) => {
      let msg;
      try { msg = JSON.parse(line); } catch { return; }
      const w = this.waiting.get(msg.id);
      if (w) { this.waiting.delete(msg.id); w(msg); }
    });
    this.proc.on("exit", () => {
      for (const w of this.waiting.values()) w({ error: { message: "KRouter server exited" } });
      this.waiting.clear();
    });
  }

  send(msg) {
    return new Promise((resolve) => {
      if ("id" in msg) this.waiting.set(msg.id, resolve);
      this.proc.stdin.write(JSON.stringify(msg) + "\n");
      if (!("id" in msg)) resolve(null);
    });
  }

  async close() { this.proc.stdin.end(); this.proc.kill(); }
}

class HttpTransport {
  constructor(url, token) { this.url = url; this.token = token; this.session = ""; }

  async send(msg) {
    const headers = { "Content-Type": "application/json", Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": PROTOCOL };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    if (this.session) headers["Mcp-Session-Id"] = this.session;
    const res = await fetch(this.url, { method: "POST", headers, body: JSON.stringify(msg) });
    this.session = res.headers.get("mcp-session-id") || this.session;
    if (!("id" in msg)) return null;
    const body = await res.text();
    if (!res.ok) return { error: { message: `HTTP ${res.status}: ${body.slice(0, 300)}` } };
    if ((res.headers.get("content-type") || "").includes("text/event-stream")) {
      const data = body.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim());
      return JSON.parse(data[data.length - 1]);
    }
    return JSON.parse(body);
  }

  async close() {}
}

export class KRouter {
  /** A local KRouter: starts its MCP server over stdio. `vault` defaults to the one the install recorded. */
  static local({ vault, python = process.platform === "win32" ? "python" : "python3", server = DEFAULT_SERVER } = {}) {
    return new KRouter(new StdioTransport(python, [server], vault ? { KROUTER_VAULT: String(vault), OBSIDIAN_VAULT: String(vault) } : {}));
  }

  /** A team server over Streamable HTTP, e.g. https://krouter.example/mcp/team. */
  static remote(url, { token } = {}) { return new KRouter(new HttpTransport(url, token)); }

  constructor(transport) { this.t = transport; this.nextId = 1; this.ready = null; }

  async #call(method, params) {
    const reply = await this.t.send({ jsonrpc: "2.0", id: this.nextId++, method, params });
    if (reply.error) throw new Error(reply.error.message || "KRouter error");
    return reply.result;
  }

  #init() {
    this.ready ??= (async () => {
      const r = await this.#call("initialize", { protocolVersion: PROTOCOL, capabilities: {},
        clientInfo: { name: "krouter-js", version: "1.3.0" } });
      await this.t.send({ jsonrpc: "2.0", method: "notifications/initialized" });
      return r;
    })();
    return this.ready;
  }

  async #tool(name, args) {
    await this.#init();
    const r = await this.#call("tools/call", { name, arguments: args });
    return new Answer((r.content || []).map((c) => c.text || "").join("\n"), Boolean(r.isError));
  }

  /** Ask the memory one question. `route`: search (default), preference, correction, memory, project, suggest. */
  ask(query, { route = "search" } = {}) { return this.#tool("krouter_ask", { query, route }); }

  status() { return this.#tool("krouter_status", {}); }

  /** One line into the memory (a local server, or a team server started with --allow-write). */
  async note(text, { kind = "note" } = {}) { return (await this.#tool("krouter_note", { text, kind })).text; }

  async tools() { await this.#init(); return (await this.#call("tools/list", {})).tools.map((t) => t.name); }

  close() { return this.t.close(); }
}
