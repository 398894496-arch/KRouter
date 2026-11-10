/* KRouter view: a read-only page. It only ever GETs /api/... from the address it was served from. */
(function () {
  "use strict";

  var I18N = {
    en: {
      readonly: "read only", tab_memory: "Memory", tab_graph: "Connections", tab_experience: "Experience", tab_nightly: "Last night", tab_why: "Try a sentence",
      pages: "pages", search_ph: "Search pages by path, title or words", all_tiers: "All tiers", all_status: "All statuses", sort_path: "By path", sort_recent: "Recently changed",
      col_page: "Page", col_tier: "Tier", col_status: "Status", col_date: "Date", prev: "Previous", next: "Next", range: "{a}–{b} of {n}", range_cap: "{a}–{b} of at least {n}",
      none: "Nothing here.", loading: "Loading…", failed: "Could not load: {e}", pick_page: "Pick a page on the left to read it.",
      replaced_by: "Replaced by", replaces: "Replaces", secret: "This is a secret page: KRouter shows its path only, never its text.",
      truncated: "The page is longer than what is shown here.", connects: "Connects to", open_graph: "Show connections", no_links: "No connections yet.",
      modified: "Modified", size: "Size", path: "Path", meta: "Front matter",
      graph_for: "Connections around", graph_pick: "Pick the centre page: search, then choose.", graph_note: "Strength is the number recall's associative path would add from this page, before its hub split and the question's weight. Pages on the same day are listed but do not count in ranking.",
      col_conn: "Connected page", col_why: "Why connected", col_strength: "Strength", more_edges: "{n} more connections are not shown.",
      k_link: "link", k_supersedes: "replaces", k_session: "same session", k_day: "same day", k_cocite: "cited together", k_words: "shared words",
      d_out: "this page links to it", d_in: "it links to this page", d_replaces: "this page replaces it", d_replaced_by: "it replaces this page",
      exp_cards: "Experience cards", exp_off: "Experience cards are switched off (KROUTER_EXPERIENCE=0).", exp_none: "No experience cards yet. They come from sessions the agent distils, or from krouter_learn.",
      col_card: "Card", col_lesson: "Lesson", col_offered: "Offered", col_adopted: "Adopted", col_again: "Met again", col_last: "Last", in_digest: "in the digest", out_digest: "not in the digest",
      exp_rank: "Cards are listed in the order the session-start digest gives them (the first {n} fit in it).", exp_events: "Recent use", exp_drafts: "Skill drafts", exp_skills: "Skills", exp_skills_none: "No skill drafts or skills yet.",
      night_none: "The nightly job has not written a report yet.", night_last: "Last report", night_steps: "Steps", col_step: "Step", col_result: "Result", col_calls: "Model calls / sent", col_sec: "s", col_reason: "Reason",
      night_off: "Not switched on, and why", night_hist: "Earlier nights", night_runs: "What the runs changed", night_corr: "Corrections made to hold", night_learned: "Learned triggers", night_learned_n: "{n} learned so far; newest first.",
      night_pending: "{n} correction candidate(s) wait to be judged at the next distill.", night_nogit: "The memory folder is not a git repository, so earlier reports are not kept.", night_added: "added", night_superseded: "replaced", night_removed: "removed",
      why_ph: "Ask a question the way you would ask the agent", why_go: "Explain", why_hint: "Shows what `krouter why` shows: how the answer came out, page by page. Nothing is written and nothing is logged.", why_empty: "Type a sentence above.",
      theme: "Theme", ok: "ok", state: "state", lane: "lane", lock: "alias lock", sample: "sample memory", ev_offered: "offered", ev_adopted: "adopted", ev_again: "met again", demo_note: "(demo, deleted when you stop it)",
    },
    zh: {
      readonly: "只读", tab_memory: "记忆", tab_graph: "关联", tab_experience: "经验", tab_nightly: "昨晚", tab_why: "试一句",
      pages: "页", search_ph: "按路径、标题或词搜索页面", all_tiers: "全部层级", all_status: "全部状态", sort_path: "按路径", sort_recent: "最近改动",
      col_page: "页面", col_tier: "层级", col_status: "状态", col_date: "日期", prev: "上一页", next: "下一页", range: "第 {a}–{b} 条，共 {n}", range_cap: "第 {a}–{b} 条，至少 {n}",
      none: "这里没有内容。", loading: "加载中…", failed: "加载失败：{e}", pick_page: "在左边选一页来读。",
      replaced_by: "被取代于", replaces: "取代了", secret: "这是机密页：KRouter 只显示路径，不显示正文。",
      truncated: "这一页比这里显示的更长。", connects: "连着", open_graph: "看关联", no_links: "还没有连着的页。",
      modified: "修改时间", size: "大小", path: "路径", meta: "头部信息",
      graph_for: "以这一页为中心的关联", graph_pick: "选中心页：先搜索，再点选。", graph_note: "强度是联想通路从这一页出发会给这条边加的数，没有计枢纽页分摊和问题的权重。同一天的页会列出来，但不参与排序。",
      col_conn: "相连的页", col_why: "为什么相连", col_strength: "强度", more_edges: "还有 {n} 条关联没有显示。",
      k_link: "链接", k_supersedes: "取代", k_session: "同一次会话", k_day: "同一天", k_cocite: "一起被引用", k_words: "共有的词",
      d_out: "这一页链接到它", d_in: "它链接到这一页", d_replaces: "这一页取代了它", d_replaced_by: "它取代了这一页",
      exp_cards: "经验卡", exp_off: "经验卡功能关着（KROUTER_EXPERIENCE=0）。", exp_none: "还没有经验卡。它们来自 agent 提炼的会话，或 krouter_learn。",
      col_card: "卡", col_lesson: "通用说法", col_offered: "被提出", col_adopted: "被采纳", col_again: "又遇到", col_last: "最近", in_digest: "在摘要里", out_digest: "不在摘要里",
      exp_rank: "按会话开始时摘要给出的顺序排列（前 {n} 张放得进摘要）。", exp_events: "最近的使用记录", exp_drafts: "技能草稿", exp_skills: "技能", exp_skills_none: "还没有技能草稿或技能。",
      night_none: "夜间任务还没有写出报告。", night_last: "最近一次报告", night_steps: "各步骤", col_step: "步骤", col_result: "结果", col_calls: "模型调用 / 发出", col_sec: "秒", col_reason: "原因",
      night_off: "没开的功能，和原因", night_hist: "之前几晚", night_runs: "各轮改了什么", night_corr: "当场落实的纠正", night_learned: "学到的触发词", night_learned_n: "已学到 {n} 条，新的在前。",
      night_pending: "有 {n} 条纠正候选等下次提炼时判定。", night_nogit: "记忆文件夹不是 git 仓库，所以没有保留更早的报告。", night_added: "新增", night_superseded: "取代", night_removed: "删除",
      why_ph: "像问 agent 那样问一句", why_go: "解释", why_hint: "显示和 `krouter why` 一样的内容：答案是怎么来的，一页一页讲。不写入任何东西，也不记查询日志。", why_empty: "在上面输入一句话。",
      theme: "主题", ok: "正常", state: "状态", lane: "通道", lock: "别名锁", sample: "示例记忆库", ev_offered: "被提出", ev_adopted: "被采纳", ev_again: "又遇到", demo_note: "（演示，停掉就删）",
    },
  };

  var state = { lang: "en", cfg: null, theme: "" };
  try { state.theme = localStorage.getItem("krouter-theme") || ""; } catch (e) { /* storage may be blocked */ }
  var asked = /[?&]theme=(light|dark)\b/.exec(location.search);  // /?theme=light, for a link or a screenshot
  if (asked) state.theme = asked[1];
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var main = $("#main");

  function t(k, v) {
    var s = (I18N[state.lang] && I18N[state.lang][k]) || I18N.en[k] || k;
    if (v) Object.keys(v).forEach(function (n) { s = s.split("{" + n + "}").join(v[n]); });
    return s;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function qs(o) { var p = []; Object.keys(o).forEach(function (k) { if (o[k] !== "" && o[k] != null) p.push(encodeURIComponent(k) + "=" + encodeURIComponent(o[k])); }); return p.join("&"); }
  function get(path, params) {
    return fetch("/api/" + path + (params ? "?" + qs(params) : ""), { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); });
  }
  function pageHref(rel) { return "#/page?" + qs({ rel: rel }); }
  function graphHref(rel) { return "#/graph?" + qs({ rel: rel }); }
  function chip(text, cls) { return '<span class="chip ' + esc(cls || text) + '">' + esc(text) + "</span>"; }
  function setHTML(html) { main.innerHTML = html; }
  function fail(e) { setHTML('<p class="err">' + esc(t("failed", { e: e && e.message ? e.message : e })) + "</p>"); }

  /* ---- minimal Markdown: escaped first, then a few safe constructs; no external image, no external link ---- */
  function inline(s, links) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
    s = s.replace(/\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|([^\]]*))?\]\]/g, function (m, target, label) {
      var rel = links && links[target.replace(/&amp;/g, "&")];
      var text = label || target;
      return rel ? '<a href="' + esc(pageHref(rel)) + '">' + text + "</a>" : "<span>" + text + "</span>";
    });
    s = s.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\[([^\]]+)\]\(([^)]*)\)/g, function (m, label, url) {
      return label + (/^https?:/i.test(url) ? ' <span class="muted">(' + url + ")</span>" : "");
    });
    return s;
  }
  function markdown(text, links, title) {
    var out = [], lines = String(text || "").replace(/\r\n/g, "\n").split("\n"), i = 0, para = [], list = null;
    var flush = function () { if (para.length) { out.push("<p>" + inline(para.join(" "), links) + "</p>"); para = []; } };
    var endList = function () { if (list) { out.push("<ul>" + list.join("") + "</ul>"); list = null; } };
    if (lines[0] === "---") { var e = lines.indexOf("---", 1); if (e > 0) i = e + 1; }
    for (; i < lines.length; i++) {
      var ln = lines[i], m;
      if (/^```/.test(ln)) { flush(); endList(); var code = []; i++; while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]); out.push("<pre>" + esc(code.join("\n")) + "</pre>"); continue; }
      if ((m = /^(#{1,6})\s+(.*)$/.exec(ln))) { flush(); endList(); if (title && m[1] === "#" && m[2].trim() === title) continue; var n = Math.min(3, m[1].length); out.push("<h" + n + ">" + inline(m[2], links) + "</h" + n + ">"); continue; }
      if ((m = /^\s*[-*+]\s+(.*)$/.exec(ln)) || (m = /^\s*\d+\.\s+(.*)$/.exec(ln))) { flush(); (list = list || []).push("<li>" + inline(m[1], links) + "</li>"); continue; }
      if (/^>\s?/.test(ln)) { flush(); endList(); out.push("<blockquote>" + inline(ln.replace(/^>\s?/, ""), links) + "</blockquote>"); continue; }
      if (!ln.trim()) { flush(); endList(); continue; }
      endList(); para.push(ln.trim());
    }
    flush(); endList();
    return out.join("");
  }

  /* ---- routing ---- */
  function route() {
    var h = location.hash.replace(/^#/, "") || "/memory", q = h.indexOf("?"), name = (q < 0 ? h : h.slice(0, q)).replace(/^\//, "").split("/")[0] || "memory";
    var params = {};
    if (q >= 0) h.slice(q + 1).split("&").forEach(function (kv) { if (kv) { var p = kv.split("="); params[decodeURIComponent(p[0])] = decodeURIComponent((p[1] || "").replace(/\+/g, " ")); } });
    var tab = name === "page" ? "memory" : name;
    document.querySelectorAll("#tabs a").forEach(function (a) { a.classList.toggle("on", a.getAttribute("data-tab") === tab); });
    setHTML('<p class="muted">' + esc(t("loading")) + "</p>");
    ({ memory: viewMemory, page: viewMemory, graph: viewGraph, experience: viewExperience, nightly: viewNightly, why: viewWhy }[name] || viewMemory)(params, name);
  }
  function go(base, params) { location.hash = "#/" + base + (qs(params || {}) ? "?" + qs(params) : ""); }

  /* ---- memory ---- */
  var LIMIT = 40;
  function viewMemory(p, name) {
    var offset = parseInt(p.offset || "0", 10) || 0;
    var f = { q: p.q || "", tier: p.tier || "", status: p.status || "", sort: p.sort || "path" };
    var head = '<h1>' + esc(t("tab_memory")) + ' <span class="muted small" id="total"></span></h1>' +
      '<form class="row card" id="flt" role="search"><input class="grow" type="search" name="q" maxlength="200" placeholder="' + esc(t("search_ph")) + '" value="' + esc(f.q) + '">' +
      '<select name="tier"><option value="">' + esc(t("all_tiers")) + "</option>" + ["rule", "topic", "project", "other", "log", "dead"].map(function (x) { return '<option' + (f.tier === x ? " selected" : "") + ">" + x + "</option>"; }).join("") + "</select>" +
      '<select name="status"><option value="">' + esc(t("all_status")) + "</option>" + ["active", "provisional", "superseded", "generated", "-"].map(function (x) { return '<option value="' + x + '"' + (f.status === x ? " selected" : "") + ">" + (x === "-" ? "(none)" : x) + "</option>"; }).join("") + "</select>" +
      '<select name="sort"><option value="path"' + (f.sort === "path" ? " selected" : "") + ">" + esc(t("sort_path")) + '</option><option value="recent"' + (f.sort === "recent" ? " selected" : "") + ">" + esc(t("sort_recent")) + "</option></select></form>" +
      '<div class="split"><div><div class="card scroll" id="list"></div></div><div id="detail"></div></div>';
    setHTML(head);
    $("#flt").addEventListener("submit", function (ev) { ev.preventDefault(); var d = new FormData(ev.target); go("memory", { q: d.get("q"), tier: d.get("tier"), status: d.get("status"), sort: d.get("sort") }); });
    ["tier", "status", "sort"].forEach(function (n) { $("#flt [name=" + n + "]").addEventListener("change", function () { $("#flt").dispatchEvent(new Event("submit", { cancelable: true })); }); });
    get("pages", { q: f.q, tier: f.tier, status: f.status, sort: f.sort, offset: offset, limit: LIMIT }).then(function (r) {
      $("#total").textContent = r.total + " " + t("pages") + (r.capped ? "+" : "");
      if (!r.items.length) { $("#list").innerHTML = '<p class="empty">' + esc(t("none")) + "</p>"; return; }
      var rows = r.items.map(function (it) {
        return '<tr data-rel="' + esc(it.rel) + '"' + (it.rel === p.rel ? ' class="sel"' : "") + '><td><a class="title" href="' + esc(pageHref(it.rel)) + '">' + esc(it.title) + '</a><div class="path">' + esc(it.rel) + "</div></td><td>" + chip(it.tier) + (it.status ? chip(it.status) : "") + "</td></tr>";
      }).join("");
      var a = r.offset + 1, b = r.offset + r.items.length;
      var base = { q: f.q, tier: f.tier, status: f.status, sort: f.sort };
      $("#list").innerHTML = "<table><thead><tr><th>" + esc(t("col_page")) + "</th><th>" + esc(t("col_tier")) + "</th></tr></thead><tbody>" + rows + "</tbody></table>" +
        '<div class="pager"><button type="button" id="prev"' + (offset <= 0 ? " disabled" : "") + ">← " + esc(t("prev")) + '</button><span class="muted small">' + esc(t(r.capped ? "range_cap" : "range", { a: a, b: b, n: r.total })) +
        '</span><button type="button" id="next"' + (b >= r.total ? " disabled" : "") + ">" + esc(t("next")) + " →</button></div>";
      $("#prev").addEventListener("click", function () { go("memory", Object.assign({}, base, { offset: Math.max(0, offset - LIMIT) || "" })); });
      $("#next").addEventListener("click", function () { go("memory", Object.assign({}, base, { offset: offset + LIMIT })); });
    }).catch(function (e) { $("#list").innerHTML = '<p class="err">' + esc(t("failed", { e: e.message })) + "</p>"; });
    if (p.rel) showPage(p.rel); else $("#detail").innerHTML = '<p class="empty">' + esc(t("pick_page")) + "</p>";
  }
  function relList(label, arr) {
    if (!arr || !arr.length) return "";
    return "<h3>" + esc(label) + "</h3><ul>" + arr.map(function (x) { return '<li><a href="' + esc(pageHref(x.rel)) + '">' + esc(x.title) + '</a> <span class="path">' + esc(x.rel) + "</span> " + (x.status ? chip(x.status) : "") + "</li>"; }).join("") + "</ul>";
  }
  function showPage(rel) {
    var box = $("#detail");
    box.innerHTML = '<p class="muted">' + esc(t("loading")) + "</p>";
    Promise.all([get("page", { rel: rel }), get("graph", { rel: rel }).catch(function () { return null; })]).then(function (res) {
      var pg = res[0], g = res[1];
      var meta = Object.keys(pg.meta || {}).map(function (k) { return "<dt>" + esc(k) + "</dt><dd>" + esc(pg.meta[k]) + "</dd>"; }).join("");
      var conn = "";
      if (g) {
        conn = "<h3>" + esc(t("connects")) + ' <a class="small" href="' + esc(graphHref(rel)) + '">' + esc(t("open_graph")) + " →</a></h3>";
        conn += g.neighbors.length ? "<ul>" + g.neighbors.slice(0, 8).map(function (n) {
          return '<li><a href="' + esc(pageHref(n.rel)) + '">' + esc(n.title) + "</a> " + n.edges.map(function (e) { return '<span class="k ' + esc(e.kind) + '">' + esc(t("k_" + e.kind)) + "</span>"; }).join("") + "</li>";
        }).join("") + "</ul>" : '<p class="muted small">' + esc(t("no_links")) + "</p>";
      }
      box.innerHTML = '<div class="card"><h1 class="mt0">' + esc(pg.title) + "</h1>" + chip(pg.tier) + (pg.status ? chip(pg.status) : "") + (pg.date ? chip(pg.date, "date") : "") +
        '<div class="path">' + esc(pg.rel) + "</div>" + relList(t("replaced_by"), pg.replaced_by) + relList(t("replaces"), pg.replaces) + conn +
        (pg.secret ? '<p class="muted">' + esc(t("secret")) + "</p>" : '<hr class="rule"><div class="body">' + markdown(pg.body, pg.links, pg.title) + "</div>") +
        (pg.truncated ? '<p class="muted small">' + esc(t("truncated")) + "</p>" : "") +
        '<dl class="meta"><dt>' + esc(t("modified")) + "</dt><dd>" + esc(pg.modified) + "</dd><dt>" + esc(t("size")) + "</dt><dd>" + pg.size + " B</dd>" + meta + "</dl></div>";
    }).catch(function (e) { box.innerHTML = '<p class="err">' + esc(t("failed", { e: e.message })) + "</p>"; });
  }

  /* ---- connections ---- */
  function viewGraph(p) {
    var form = '<h1>' + esc(t("tab_graph")) + '</h1><form class="row card" id="gp"><input class="grow" type="search" name="q" maxlength="200" placeholder="' + esc(t("search_ph")) + '"><button class="primary" type="submit">' + esc(t("search_ph").split(" ")[0]) + '</button></form><div id="gbody"></div>';
    setHTML(form);
    $("#gp").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var q = new FormData(ev.target).get("q");
      get("pages", { q: q, limit: 8 }).then(function (r) {
        $("#gbody").innerHTML = '<div class="card"><ul>' + r.items.map(function (it) { return '<li><a href="' + esc(graphHref(it.rel)) + '">' + esc(it.title) + '</a> <span class="path">' + esc(it.rel) + "</span></li>"; }).join("") + "</ul></div>";
      }).catch(fail);
    });
    if (!p.rel) {
      get("pages", { sort: "recent", limit: 8 }).then(function (r) {
        $("#gbody").innerHTML = '<p class="muted">' + esc(t("graph_pick")) + '</p><div class="card"><ul>' + r.items.map(function (it) { return '<li><a href="' + esc(graphHref(it.rel)) + '">' + esc(it.title) + '</a> <span class="path">' + esc(it.rel) + "</span></li>"; }).join("") + "</ul></div>";
      }).catch(fail);
      return;
    }
    get("graph", { rel: p.rel }).then(function (g) {
      var kinds = {};
      g.neighbors.forEach(function (n) { n.edges.forEach(function (e) { kinds[e.kind] = 1; }); });
      var legend = '<div class="legend">' + Object.keys(kinds).map(function (k) { return '<span class="k ' + k + '">' + esc(t("k_" + k)) + "</span>"; }).join("") + "</div>";
      var rows = g.neighbors.map(function (n) {
        return "<tr><td><a href=\"" + esc(graphHref(n.rel)) + '" class="title">' + esc(n.title) + '</a> <a class="small" href="' + esc(pageHref(n.rel)) + '">↗</a><div class="path">' + esc(n.rel) + "</div></td><td>" +
          n.edges.map(function (e) {
            var d = e.direction ? " — " + t("d_" + e.direction) : "", det = e.detail ? " (" + e.detail + ")" : "";
            return '<div><span class="k ' + esc(e.kind) + '">' + esc(t("k_" + e.kind)) + "</span>" + esc(d + det) + "</div>";
          }).join("") + '</td><td class="num"><span class="bar w' + Math.max(1, Math.round(Math.min(1, n.strength) * 10)) + '"></span> ' + n.strength + "</td></tr>";
      }).join("");
      $("#gbody").innerHTML = "<h2>" + esc(t("graph_for")) + ' <a href="' + esc(pageHref(p.rel)) + '">' + esc(g.center.title) + "</a></h2>" + legend +
        (g.neighbors.length ? svgGraph(g) : '<p class="empty">' + esc(t("no_links")) + "</p>") +
        '<div class="card scroll mt12"><table><thead><tr><th>' + esc(t("col_conn")) + "</th><th>" + esc(t("col_why")) + '</th><th class="num">' + esc(t("col_strength")) + "</th></tr></thead><tbody>" + rows + "</tbody></table>" +
        (g.capped ? '<p class="muted small">' + esc(t("more_edges", { n: g.total - g.neighbors.length })) + "</p>" : "") + '<p class="muted small">' + esc(t("graph_note")) + "</p></div>";
    }).catch(fail);
  }
  function short(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function svgGraph(g) {
    var W = 720, H = 460, cx = W / 2, cy = H / 2, ns = g.neighbors.slice(0, 16), out = [];
    var rx = W / 2 - 110, ry = H / 2 - 50;
    ns.forEach(function (n, i) {
      var a = (2 * Math.PI * i) / ns.length - Math.PI / 2, x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
      var main = n.edges.slice().sort(function (p, q) { return q.strength - p.strength; })[0];
      var mx = cx + (x - cx) * 0.62, my = cy + (y - cy) * 0.62;
      var lab = n.edges.map(function (e) { return t("k_" + e.kind); }).join(" · ");
      out.push('<line class="e-' + esc(main.kind) + '" x1="' + cx + '" y1="' + cy + '" x2="' + x.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke-width="' + (1 + 4 * Math.min(1, n.strength)).toFixed(1) + '" opacity="0.8"/><text class="elab" x="' + mx.toFixed(1) + '" y="' + (my - 4).toFixed(1) + '" text-anchor="middle">' + esc(short(lab, 46)) + "</text>");
      var anchor = Math.cos(a) > 0.2 ? "start" : Math.cos(a) < -0.2 ? "end" : "middle", dx = anchor === "start" ? 12 : anchor === "end" ? -12 : 0, dy = Math.abs(Math.cos(a)) <= 0.2 ? (Math.sin(a) > 0 ? 22 : -14) : 4;
      out.push('<a href="' + esc(graphHref(n.rel)) + '" class="node"><circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="8"/><text x="' + (x + dx).toFixed(1) + '" y="' + (y + dy).toFixed(1) + '" text-anchor="' + anchor + '">' + esc(short(n.title, 24)) + "</text><title>" + esc(n.rel) + "</title></a>");
    });
    out.push('<g class="center"><circle cx="' + cx + '" cy="' + cy + '" r="12"/><text x="' + cx + '" y="' + (cy + 34) + '" text-anchor="middle">' + esc(short(g.center.title, 30)) + "</text><title>" + esc(g.center.rel) + "</title></g>");
    return '<svg class="graph" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(g.center.title) + '">' + out.join("") + "</svg>";
  }

  /* ---- experience ---- */
  function viewExperience() {
    get("experience").then(function (x) {
      var cards = x.cards.length ? '<div class="card scroll"><table><thead><tr><th>' + esc(t("col_card")) + "</th><th>" + esc(t("col_lesson")) + '</th><th class="num">' + esc(t("col_offered")) + '</th><th class="num">' + esc(t("col_adopted")) + '</th><th class="num">' + esc(t("col_again")) + "</th><th>" + esc(t("col_last")) + "</th></tr></thead><tbody>" +
        x.cards.map(function (c) {
          var last = [c.last_adopted, c.last_again, c.last_offered].sort().pop();
          return "<tr><td><a href=\"" + esc(pageHref(c.rel)) + '">' + esc(c.id) + "</a><div>" + chip(c.status || "—") + chip(t(c.in_digest ? "in_digest" : "out_digest"), c.in_digest ? "ok" : "off") + '</div></td><td><div class="title">' + esc(c.lesson || c.title) + "</div>" +
            (c.when.length ? '<div class="muted small">' + esc(c.when.join(" · ")) + "</div>" : "") + '</td><td class="num">' + c.offered + '</td><td class="num">' + c.adopted + '</td><td class="num">' + c.again + "</td><td class=\"small muted\">" + esc(last || "") + "</td></tr>";
        }).join("") + "</tbody></table></div>" + '<p class="muted small">' + esc(t("exp_rank", { n: x.digest_max })) + "</p>"
        : '<p class="empty">' + esc(t("exp_none")) + "</p>";
      var ev = x.events.length ? "<h2>" + esc(t("exp_events")) + '</h2><div class="card scroll"><table><tbody>' + x.events.slice(0, 12).map(function (e) { return "<tr><td class=\"small muted\">" + esc(e.at) + "</td><td>" + esc(e.card) + "</td><td>" + chip(t("ev_" + e.kind), e.kind === "adopted" ? "ok" : "off") + '</td><td class="small muted">' + esc(e.why) + "</td></tr>"; }).join("") + "</tbody></table></div>" : "";
      var sk = function (label, arr) { return arr.length ? "<h3>" + esc(label) + "</h3><ul>" + arr.map(function (a) { return '<li><a href="' + esc(pageHref(a.rel)) + '">' + esc(a.title) + '</a> <span class="path">' + esc(a.rel) + "</span> " + chip(a.status || "draft") + "</li>"; }).join("") + "</ul>" : ""; };
      var skills = (x.drafts.length || x.skills.length) ? sk(t("exp_drafts"), x.drafts) + sk(t("exp_skills"), x.skills) : '<p class="muted small">' + esc(t("exp_skills_none")) + "</p>";
      setHTML("<h1>" + esc(t("exp_cards")) + "</h1>" + (x.on ? "" : '<p class="muted">' + esc(t("exp_off")) + "</p>") + cards + ev + '<h2>' + esc(t("exp_skills")) + '</h2><div class="card">' + skills + "</div>");
    }).catch(fail);
  }

  /* ---- last night ---- */
  function stepRows(steps) {
    return steps.map(function (s) { return "<tr><td>" + esc(s.step) + "</td><td>" + chip(s.state) + '</td><td class="small muted">' + esc(s.calls) + '</td><td class="num small muted">' + esc(s.seconds) + '</td><td class="small">' + esc(s.reason) + "</td></tr>"; }).join("");
  }
  function viewNightly() {
    get("nightly", { lang: state.lang }).then(function (n) {
      var h = "<h1>" + esc(t("tab_nightly")) + "</h1>";
      if (!n.report) h += '<p class="empty">' + esc(t("night_none")) + "</p>";
      else {
        var r = n.report;
        h += '<div class="card"><h3 class="mt0">' + esc(t("night_last")) + "</h3><p>" + chip(r.state || "?") + ' <span class="muted small">' + esc(r.at) + " · " + esc(t("lane")) + ": " + esc(r.lane) + "</span></p>" +
          '<div class="scroll"><table><thead><tr><th>' + esc(t("col_step")) + "</th><th>" + esc(t("col_result")) + "</th><th>" + esc(t("col_calls")) + '</th><th class="num">' + esc(t("col_sec")) + "</th><th>" + esc(t("col_reason")) + "</th></tr></thead><tbody>" + stepRows(r.steps) + "</tbody></table></div>" +
          (r.notes.length ? "<ul>" + r.notes.map(function (x) { return '<li class="small">' + esc(x) + "</li>"; }).join("") + "</ul>" : "") + "</div>";
        if (n.off.length) h += "<h2>" + esc(t("night_off")) + '</h2><div class="card"><ul>' + n.off.map(function (o) { return "<li><strong>" + esc(o.step) + "</strong> " + chip(o.state) + " " + esc(o.reason) + "</li>"; }).join("") + "</ul></div>";
      }
      if (n.history.length) h += "<h2>" + esc(t("night_hist")) + '</h2><div class="card">' + n.history.map(function (o) { return "<p>" + chip(o.state || "?") + ' <span class="small muted">' + esc(o.at) + "</span> " + o.steps.map(function (s) { return '<span class="chip ' + esc(s.state) + '">' + esc(s.step) + " " + esc(s.state) + "</span>"; }).join("") + "</p>"; }).join("") + "</div>";
      else if (n.report && !n.git) h += '<p class="muted small">' + esc(t("night_nogit")) + "</p>";
      if (n.runs.length) h += "<h2>" + esc(t("night_runs")) + "</h2>" + n.runs.map(function (r) {
        return '<div class="card"><strong>' + esc(r.title) + '</strong> <span class="muted small">' + esc(r.at) + "</span><div>" + chip(t("night_added") + " " + r.added, "ok") + chip(t("night_superseded") + " " + r.superseded, r.superseded ? "warn" : "off") + chip(t("night_removed") + " " + r.removed, "off") + "</div><ul>" +
          r.lines.slice(0, 14).map(function (l) { return '<li class="small' + (/^\s{2}/.test(l) ? " muted" : "") + '">' + esc(l.replace(/^\s*-\s*/, "")) + "</li>"; }).join("") + "</ul></div>";
      }).join("");
      if (n.corrections.length) h += "<h2>" + esc(t("night_corr")) + '</h2><div class="card"><ul>' + n.corrections.map(function (c) { return '<li class="small">' + esc(c.replace(/^-\s*/, "")) + "</li>"; }).join("") + "</ul></div>";
      h += "<h2>" + esc(t("night_learned")) + '</h2><div class="card"><p class="muted small">' + esc(t("night_learned_n", { n: n.learned.count })) + "</p>" + (n.learned.recent.length ? "<ul>" + n.learned.recent.map(function (l) { return "<li>" + esc(l.query) + ' → <a href="' + esc(pageHref(l.page)) + '">' + esc(l.page) + "</a></li>"; }).join("") + "</ul>" : "") + "</div>";
      if (n.pending_candidates) h += '<p class="muted">' + esc(t("night_pending", { n: n.pending_candidates })) + "</p>";
      setHTML(h);
    }).catch(fail);
  }

  /* ---- try a sentence ---- */
  function viewWhy(p) {
    setHTML("<h1>" + esc(t("tab_why")) + '</h1><form class="row card" id="wf"><input class="grow" type="search" name="q" maxlength="500" placeholder="' + esc(t("why_ph")) + '" value="' + esc(p.q || "") + '"><button class="primary" type="submit">' + esc(t("why_go")) + '</button></form><p class="muted small">' + esc(t("why_hint")) + '</p><div id="wout" class="card why-out"></div>');
    $("#wf").addEventListener("submit", function (ev) { ev.preventDefault(); go("why", { q: new FormData(ev.target).get("q") }); });
    var out = $("#wout");
    if (!p.q) { out.innerHTML = '<p class="muted">' + esc(t("why_empty")) + "</p>"; return; }
    out.innerHTML = '<p class="muted">' + esc(t("loading")) + "</p>";
    get("why", { q: p.q, lang: state.lang }).then(function (r) {
      known = knownRe(r.pages);
      var html = [], inList = false, first = true;
      r.blocks.forEach(function (b) {
        if (b.t !== "li" && inList) { html.push("</ul>"); inList = false; }
        if (b.t === "h") html.push("<h3>" + esc(b.x) + "</h3>");
        else if (b.t === "p") { html.push('<p class="' + (first ? "" : "") + '">' + link(b.x) + "</p>"); }
        else { if (!inList) { html.push("<ul>"); inList = true; } html.push('<li class="l' + (b.lvl || 0) + '">' + link(b.x, b.page) + "</li>"); }
        first = false;
      });
      if (inList) html.push("</ul>");
      out.innerHTML = html.join("");
      var vd = out.querySelectorAll("p")[1]; if (vd) vd.classList.add("verdict");
    }).catch(function (e) { out.innerHTML = '<p class="err">' + esc(t("failed", { e: e.message })) + "</p>"; });
  }
  var known = null;
  function link(text) {
    var s = esc(text);
    if (!known) return s;
    return s.replace(known, function (m) {
      var rel = m.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">");
      return '<a class="pg" href="' + esc(pageHref(rel)) + '">' + m + "</a>";
    });
  }
  function knownRe(pages) {
    if (!pages || !pages.length) return null;
    return new RegExp(pages.map(function (r) { return esc(r).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("|"), "g");
  }

  /* ---- chrome: language, theme, config ---- */
  function applyLang() {
    if (state.cfg) $("#vaultline").textContent = (state.demo ? t("sample") + " " + t("demo_note") : state.vaultPath) + "  ·  KRouter " + state.cfg.version;
    document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
    document.querySelectorAll("[data-i18n]").forEach(function (el) { el.textContent = t(el.getAttribute("data-i18n")); });
    $("#lang").textContent = state.lang === "zh" ? "EN" : "中文";
    $("#lang").setAttribute("aria-label", state.lang === "zh" ? "English" : "中文");
  }
  function applyTheme() {
    if (state.theme) document.documentElement.setAttribute("data-theme", state.theme); else document.documentElement.removeAttribute("data-theme");
  }
  $("#lang").addEventListener("click", function () {
    state.lang = state.lang === "zh" ? "en" : "zh";
    try { localStorage.setItem("krouter-lang", state.lang); } catch (e) { /* ignore */ }
    applyLang(); route();
  });
  $("#theme").addEventListener("click", function () {
    var dark = state.theme ? state.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    state.theme = dark ? "light" : "dark";
    try { localStorage.setItem("krouter-theme", state.theme); } catch (e) { /* ignore */ }
    applyTheme();
  });
  window.addEventListener("hashchange", route);
  applyTheme();
  get("config").then(function (c) {
    state.cfg = c;
    var saved = ""; try { saved = localStorage.getItem("krouter-lang") || ""; } catch (e) { /* ignore */ }
    state.lang = saved === "zh" || saved === "en" ? saved : c.lang;
    state.demo = !!c.demo; state.vaultPath = c.vault;
    applyLang(); route();
  }).catch(fail);
})();
