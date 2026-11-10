"""`krouter why "<question>"`: how a lookup came out, in words a person can read.

It asks the same modules `krouter ask` asks (the alias lock, then the ranked recall with its associative path and its
old-versus-new tie-break) and, from what they return, says: what matched first (which alias, which words), why each
page sits where it does (the words it matched, its tier, the boosts), why the confidence is the one it is, which pages
came along an edge and from where, which page replaced which, whether an experience card goes with the question, and,
when the memory does not know, which word it could not find and which check said no.

Read only: no page is written, no query log line is appended (a `why` is not a question the nightly job should learn
from), nothing is sent anywhere. The only thing refreshed is the recall cache, outside the memory folder, as with `ask`.

`explain()` returns the structure; `blocks()` turns it into a list of `{"t": "h"|"p"|"li", "x": text, "page": rel}`
that the command line prints as text and `krouter view` shows as HTML, so both say the same thing; `render()` is the
text. Output follows the memory's language (a memory whose zones file says `@lang|en` is English, else Chinese) unless
asked otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

from .viewdata import Store, head_of, mods

# ---------------------------------------------------------------------------------------------- the words

TEXT = {
    "en": {
        "h_question": "Question",
        "h_lock": "1. The alias lock",
        "h_words": "2. The words of the question",
        "h_pages": "3. The pages, in order",
        "h_pages_ref": "3. The pages the ranked search would give (the lock answered first and skipped it)",
        "h_pages_none": "3. The closest pages (found, but not offered: the memory refused)",
        "h_conf": "4. Why this confidence",
        "h_assoc": "5. Pages that came along a connection",
        "h_conflict": "6. Old and new",
        "h_cards": "7. Experience cards",
        "v_locked": "Answered by an alias lock: the question names a page the alias table points at.",
        "v_answer": "Answered by the ranked search. Confidence: {conf}.",
        "v_partial": "Found pages, but only one word of the question matched them. Confidence: low; they may be about something else.",
        "v_none": "The memory does not know this: no page covers enough of the question, so nothing is offered.",
        "lock_hit": "The question {how} the alias “{alias}”, which the alias table lists for {page}. A lock answers at once, so the ranked search did not decide this.",
        "how_exact": "is exactly",
        "how_inside": "contains, and is mostly about,",
        "how_part": "is most of",
        "how_token": "has as one of its words the whole alias",
        "lock_how": "The one-line answer on file for that alias: {how}",
        "lock_tie": "No lock: the question matches two different pages equally well ({left} → {lp}; {right} → {rp}). A lock does not guess between them.",
        "lock_dead": "No lock: the alias “{alias}” matches, but its page {page} is no longer in force (replaced, retired or expired), so the lock does not claim it.",
        "lock_gone": "No lock: the alias “{alias}” matches, but its page {page} is not in the memory any more.",
        "lock_none": "No lock: no alias in the alias table matches the question closely enough.",
        "lock_near": "Closest aliases (hints only, never an answer): {list}.",
        "words_used": "Words used to rank: {words}.",
        "words_absent": "Words of the question that no page contains: {words}.",
        "words_none": "Nothing is left of the question once function words are dropped, so there is nothing to look up.",
        "page_head": "#{n} {rel}: {title} (tier {tier}{status}, score {score})",
        "page_matched": "matched the question's words {words}",
        "page_where": "{word} in the {where}",
        "where_title": "title",
        "where_trigger": "aliases or triggers",
        "where_body": "text",
        "page_nomatch": "no word of the question is in this page by itself (it is listed for another reason, below)",
        "page_score": "score {score} = text relevance {base} × {boosts}",
        "page_score_plain": "score {score}",
        "boost_tier": "{tier} ×{f}",
        "boost_topic_named": "the question names this topic ×{f}",
        "boost_topic_unnamed": "a topic page the question does not name ×{f}",
        "boost_title": "the question is this page's name ×{f}",
        "tier_rule": "rule page (decisions, preferences, corrections)",
        "tier_topic": "topic page",
        "tier_project": "project page",
        "tier_other": "ordinary page",
        "tier_log": "daily-log page",
        "tier_dead": "page out of play (replaced, retired or machine-written)",
        "page_rank_first": "highest score of the pages that matched",
        "page_rank_after": "{ratio}% of the top score",
        "page_how": "one-line answer (from the page): {how}",
        "page_replaced": "this page was replaced by {pages}: shown so you can see what changed, never offered as the answer",
        "page_replaces": "this page replaces {pages}",
        "page_conflict_newer": "the newer of two pages that say different things about this (see section 6)",
        "page_conflict_older": "the older of two pages that say different things about this (see section 6)",
        "page_conflict_possible": "one of two pages that may disagree (see section 6)",
        "page_reordered": "moved to first place because it is the newer one",
        "slots": "A lookup gives {n} pages: the first {k} are always the question's own matches, the rest go to connected pages when there are any.",
        "conf_high": "high: the top page scores at least 1.5× the second ({margin}×), it is a rule or topic page, and the question's words matched it well.",
        "conf_medium_margin": "medium: the top page scores {margin}× the second, enough to prefer it, not enough for high (high needs 1.5× and a rule or topic page).",
        "conf_medium_tier": "medium: the top page leads clearly ({margin}×) but it is a {tier} rather than a rule or topic page, which high requires.",
        "conf_low_close": "low: the top two pages score close together ({margin}× apart): the question does not single one out.",
        "conf_low_partial": "low: only one word of the question matched the top page, so it may be about something else.",
        "conf_low_clipped": "low (capped): every page found is a clipped web page, reference someone else wrote, not your own notes.",
        "conf_none": "none: the memory refused. Reasons below.",
        "r_nothing": "no page contains the question's words ({words})",
        "r_no_words": "the question has only function words, nothing to match",
        "r_unnamed": "the question names {names}, which no page in the memory mentions at all",
        "r_unknown": "the question's central word never appears in the memory ({words}); the pages found only share side words",
        "r_off_vault": "most of the question's real words ({n}) appear nowhere in the memory, more than the best page matched ({m}): it asks about something else",
        "r_alien": "the question has characters the memory has never used ({n}) and the best page matched only one real word",
        "r_no_strong": "the best page matches none of the question's words that count as real words",
        "r_one_word": "the best page matched only {n} real word(s) and its score ({score}) is under the bar for a one-word match ({bar})",
        "r_score": "the best page's score ({score}) is under the minimum ({bar})",
        "r_clipped": "every page found is a clipped web page and the question has a word the memory never mentions ({words})",
        "r_unknown_reason": "the check that refused could not be reproduced here; run `krouter ask` for the raw receipt",
        "assoc_intro": "These pages are connected to the pages above but the question did not name them; read one only if the pages above leave part of it open.",
        "assoc_none": "None. Either nothing is connected strongly enough, or the lookup was refused (a refusal stays a refusal).",
        "assoc_head": "{rel}: {title} (tier {tier}, association {score})",
        "via_link": "linked with {src}",
        "via_supersedes": "replaces or is replaced by {src}",
        "via_session": "same session as {src}",
        "via_day": "same day as {src}",
        "via_cocite": "cited together with {src} in earlier lookups",
        "via_words": "shares rare words with {src}{words}",
        "conflict_sure": "{new} ({nd}) changes what {old} ({od}) says. The newer page is listed first; answer from it and say it was changed.",
        "conflict_possible": "{a} ({ad}) and {b} ({bd}) are both about this and may disagree. They carry the same date, so which is newer cannot be told; the order was not changed. Read both.",
        "conflict_none": "No two of the top pages look like the same thing said twice at different dates.",
        "replaced_list": "Replaced pages among those shown: {list}.",
        "cards_digest": "Cards are not matched to a question: the agent is handed the whole digest ({n} card(s), at most {k}) when a session starts and judges the situation itself.",
        "cards_none_on": "No experience cards in this memory.",
        "cards_off": "Experience cards are switched off (KROUTER_EXPERIENCE=0).",
        "cards_overlap": "Cards whose situation shares words with this question (a hint, not a rule): ",
        "card_line": "〔{id}〕 {lesson} (shares: {words})",
        "cards_source": "Cards taken from a page shown above: ",
        "cards_nothing": "No card's situation reads like this question.",
        "none": "none",
    },
    "zh": {
        "h_question": "问题",
        "h_lock": "一、别名锁",
        "h_words": "二、问题里的词",
        "h_pages": "三、页面和顺序",
        "h_pages_ref": "三、排序搜索会给出的页面（锁先答了，没走这一步）",
        "h_pages_none": "三、最接近的页（找到了，但没有给出：库里没有）",
        "h_conf": "四、为什么是这个置信度",
        "h_assoc": "五、沿联想带出来的页",
        "h_conflict": "六、新旧冲突",
        "h_cards": "七、经验卡",
        "v_locked": "别名锁直接答了：问题点到了别名表里指向的那一页。",
        "v_answer": "排序搜索答了，置信度：{conf}。",
        "v_partial": "找到了页面，但问题里只有一个词对上，置信度 low：它们可能说的是别的事。",
        "v_none": "库里没有：没有哪一页覆盖了足够多的问题，所以什么也不给。",
        "lock_hit": "问题{how}别名「{alias}」，别名表把它列在 {page} 名下。锁是直接答，这一题没走排序。",
        "how_exact": "就是",
        "how_inside": "包含并且主要在问",
        "how_part": "占了大半个",
        "how_token": "里有一个词正好是整个别名",
        "lock_how": "这个别名登记的一句话答案：{how}",
        "lock_tie": "没有锁：问题同样好地对上了两个不同的页（{left} → {lp}；{right} → {rp}）。锁不在两者之间猜。",
        "lock_dead": "没有锁：别名「{alias}」对上了，但它的页 {page} 已经不生效（被取代、退役或过期），锁不认领它。",
        "lock_gone": "没有锁：别名「{alias}」对上了，但它的页 {page} 已经不在库里。",
        "lock_none": "没有锁：别名表里没有哪个别名和问题够接近。",
        "lock_near": "最接近的别名（只是提示，不当答案）：{list}。",
        "words_used": "用来排序的词：{words}。",
        "words_absent": "问题里整个库都没有页面含有的词：{words}。",
        "words_none": "去掉虚词以后问题里什么都不剩，没有可查的。",
        "page_head": "第{n}：{rel}：{title}（层级 {tier}{status}，得分 {score}）",
        "page_matched": "对上了问题里的词 {words}",
        "page_where": "{word}（在{where}里）",
        "where_title": "标题",
        "where_trigger": "别名或触发词",
        "where_body": "正文",
        "page_nomatch": "问题里的词没有哪个单独出现在这一页（它因为别的原因列在这里，见下）",
        "page_score": "得分 {score} = 正文相关度 {base} × {boosts}",
        "page_score_plain": "得分 {score}",
        "boost_tier": "{tier} ×{f}",
        "boost_topic_named": "问题点了这个主题 ×{f}",
        "boost_topic_unnamed": "问题没点名的主题档案 ×{f}",
        "boost_title": "问题就是这一页的名字 ×{f}",
        "tier_rule": "规则页（决定、偏好、纠错）",
        "tier_topic": "主题档案",
        "tier_project": "项目页",
        "tier_other": "普通页",
        "tier_log": "时间日志页",
        "tier_dead": "不参与作答的页（已取代、退役或机器生成）",
        "page_rank_first": "命中的页里得分最高",
        "page_rank_after": "得分是第一名的 {ratio}%",
        "page_how": "一句话答案（取自这一页）：{how}",
        "page_replaced": "这一页已被 {pages} 取代：列出来是让你看到改了什么，不会当答案给",
        "page_replaces": "这一页取代了 {pages}",
        "page_conflict_newer": "两个说法不同的页里较新的一页（见第六节）",
        "page_conflict_older": "两个说法不同的页里较早的一页（见第六节）",
        "page_conflict_possible": "可能互相矛盾的两页之一（见第六节）",
        "page_reordered": "因为它是较新的一页，被挪到了第一位",
        "slots": "一次查询给 {n} 页：前 {k} 页永远是问题自己的命中，后面的位置有联想页就给联想页。",
        "conf_high": "high：第一名得分至少是第二名的 1.5 倍（{margin} 倍），它是规则页或主题档案，问题的词对得上。",
        "conf_medium_margin": "medium：第一名是第二名的 {margin} 倍，够优先它，但不到 high（high 要 1.5 倍并且是规则页或主题档案）。",
        "conf_medium_tier": "medium：第一名明显领先（{margin} 倍），但它是{tier}，不是 high 要求的规则页或主题档案。",
        "conf_low_close": "low：前两名得分很接近（只差 {margin} 倍）：问题没有单点出哪一页。",
        "conf_low_partial": "low：问题里只有一个词对上了第一名，它可能说的是别的事。",
        "conf_low_clipped": "low（封顶）：找到的全是网页剪藏，是别人写的参考材料，不是你自己的笔记。",
        "conf_none": "none：库里没有。原因见下。",
        "r_nothing": "没有哪一页含有问题里的词（{words}）",
        "r_no_words": "问题里只有虚词，没有可匹配的内容",
        "r_unnamed": "问题点了 {names}，整个库里没有哪一页提过",
        "r_unknown": "问题的核心词在库里一次都没出现（{words}），找到的页只是沾了边角词",
        "r_off_vault": "问题里的真词有 {n} 个整库都没有，比最好的一页对上的（{m} 个）还多：问的是库外的事",
        "r_alien": "问题里有 {n} 个库里从没用过的汉字，而最好的一页只对上了一个真词",
        "r_no_strong": "最好的一页没有对上问题里任何一个算得上真词的词",
        "r_one_word": "最好的一页只对上 {n} 个真词，得分（{score}）也没达到单词命中的门槛（{bar}）",
        "r_score": "最好的一页得分（{score}）低于下限（{bar}）",
        "r_clipped": "找到的全是网页剪藏，而且问题里有库里从没提过的词（{words}）",
        "r_unknown_reason": "拒答是哪一道检查拦的，这里没能复现；用 `krouter ask` 看原始回执",
        "assoc_intro": "这些页和上面的页相连，但问题没有点到它们；只有上面的页没把问题答全时才值得读。",
        "assoc_none": "没有。要么没有哪一页连得足够紧，要么这次查询被拒答了（拒答就是拒答，联想不会把没有变成有）。",
        "assoc_head": "{rel}：{title}（层级 {tier}，联想分 {score}）",
        "via_link": "和 {src} 互相链接",
        "via_supersedes": "取代或被取代，对方是 {src}",
        "via_session": "和 {src} 同一次会话",
        "via_day": "和 {src} 同一天",
        "via_cocite": "以前的查询里和 {src} 一起被引用过",
        "via_words": "和 {src} 共有少见的词{words}",
        "conflict_sure": "{new}（{nd}）改了 {old}（{od}）说的事。较新的页排在前面，按它回答并说明改过。",
        "conflict_possible": "{a}（{ad}）和 {b}（{bd}）都在说这件事，可能互相矛盾。两页日期相同，分不出谁新，顺序没动。两页都读。",
        "conflict_none": "前几名里没有两页像是「同一件事在不同日期说了两次」。",
        "replaced_list": "显示的页里已被取代的：{list}。",
        "cards_digest": "经验卡不按问题匹配：会话开始时把整份摘要（{n} 张，最多 {k} 条）交给 agent，由它自己判断处境像不像。",
        "cards_none_on": "这个库里没有经验卡。",
        "cards_off": "经验卡功能关着（KROUTER_EXPERIENCE=0）。",
        "cards_overlap": "处境和这个问题共有词的卡（提示，不是规则）：",
        "card_line": "〔{id}〕{lesson}（共有：{words}）",
        "cards_source": "出处是上面某一页的卡：",
        "cards_nothing": "没有哪张卡的处境读起来像这个问题。",
        "none": "无",
    },
}

CONF_ORDER = ("none", "low", "medium", "high")


def t(lang: str, key: str, **kw) -> str:
    return TEXT[lang][key].format(**kw) if kw else TEXT[lang][key]


def _status(lang: str, s: str) -> str:
    return (f", status {s}" if lang == "en" else f"，状态 {s}") if s else ""


# ---------------------------------------------------------------------------------------------- the facts


def _lock(m, vault: Path, q: str) -> dict:
    """What the alias lock did with the question, and why."""
    cl = m.cl
    out: dict = {"state": "none", "near": []}
    map_path = cl.map_for(vault)
    if not q or not map_path.is_file():
        return out
    rows = cl.load_rows(map_path)
    hit = cl.lookup(q, rows, vault=vault)
    if hit is not None:
        case_id, relative, anchor = hit
        if not (vault / relative).is_file():
            return {**out, "state": "gone", "alias": "", "page": relative}
        alias, kind = _winning_alias(cl, q, next(r for r in rows if r[0] == case_id))
        how = anchor
        try:
            import route_knowledge

            how = route_knowledge.how_for(vault, case_id, anchor)[0]
        except Exception:  # noqa: BLE001
            pass
        return {**out, "state": "locked", "id": case_id, "alias": alias, "kind": kind, "page": relative,
                "how": m.redact.redact(how)}
    tie = cl.query_conflict(q, rows, vault=vault)
    if tie:
        l, r = tie["left"], tie["right"]
        return {**out, "state": "tie", "left": f"{l[1]}", "lp": l[2], "right": f"{r[1]}", "rp": r[2]}
    live = {r[0] for r in cl.live_rows(rows, vault)}
    blocked = cl.scores_for(q, [r for r in rows if r[0] not in live])
    if blocked:
        cid = max(blocked, key=blocked.get)
        row = next(r for r in rows if r[0] == cid)
        alias, _k = _winning_alias(cl, q, row)
        state = "gone" if not (vault / row[2]).is_file() else "dead"
        return {**out, "state": state, "alias": alias, "page": row[2]}
    out["near"] = [{"alias": a, "page": s, "score": sc} for sc, _cid, a, s in cl.suggestions(q, rows, 3, vault=vault)
                   if sc >= 60]  # a prefix or phrase in common; a stray shared letter says nothing
    return out


def _winning_alias(cl, q: str, row) -> tuple[str, str]:
    """(the alias of this row that the question matched best, how it matched: exact / inside / part / token)."""
    best, best_alias, tokens = 0, "", False
    for alias in row[1]:
        s = cl.alias_score(q, alias)
        if s > best:
            best, best_alias = s, alias
    if best < cl.LOCK_BAND:  # the token fallback: one whole alias among the question's words
        for alias in row[1]:
            if any(cl.alias_score(tok, alias) >= 500 for tok in q.split()):
                best_alias, tokens = alias, True
                break
    if tokens:
        return best_alias, "token"
    kind = "exact" if best >= 1000 else "inside" if best >= 500 else "part"
    return best_alias, kind


def _words(m, con, q: str) -> tuple[list[str], dict]:
    """(the question's words as recall ranks with them, their document counts): recall's own reduction."""
    ri = m.ri
    raw: list[str] = []
    for tok in ri.tokens(q):
        if len(tok) == 1 and ri.CJK_RE.fullmatch(tok):
            continue
        if tok not in ri.QUERY_STOP and tok not in raw:
            raw.append(tok)
    raw = [tok for tok in raw if tok not in ri.EN_FUNCTION] or raw
    if not raw:
        return [], {}
    df = ri.term_df(con, raw + [c for tok in raw if ri.is_cjk_bigram(tok) for c in tok]
                    + [f for tok in raw if not ri.is_cjk_bigram(tok) for f in ri.latin_forms(tok)])
    return raw, df


def _refusal(m, con, vault: Path, q: str, raw: list[str], df: dict, opened: dict) -> list[tuple[str, dict]]:
    """Which of recall's refusal checks said no, as (code, params). Recomputed from recall's own helpers on the ranking
    it would have given with the gate off; a test keeps this and `recall` in step."""
    ri = m.ri
    if not raw:
        return [("r_no_words", {})]
    absent = [tok for tok in raw if df.get(tok, 0) == 0]
    hits = opened.get("hits") or []
    if not hits:
        return [("r_nothing", {"absent": absent})]
    present = [tok for tok in raw if df.get(tok, 0) > 0]
    bigrams = [tok for tok in present if ri.is_cjk_bigram(tok)]
    titled = ri.phrase_terms(con, bigrams, ("title",))
    n_docs = con.execute("SELECT count(*) FROM files").fetchone()[0] or 1
    rid = con.execute("SELECT rid FROM files WHERE rel=?", (hits[0]["rel"],)).fetchone()[0]
    top, strong = hits[0]["score"], opened.get("strong", 0)
    scale = min(1.0, n_docs / 1000)
    need = min(ri.MIN_STRONG_MATCH, ri.query_content_terms(raw, df, titled))
    unknown = ri.unknown_content_terms(raw, df)
    alien = ri.alien_chars(raw, df)
    absent_words, top_words = ri.outside_words(con, rid, raw, df)
    off_vault = absent_words >= 2 and absent_words > top_words
    unnamed = ri.absent_names(q, df)
    single = ri.is_single_concept(q)
    why: list[tuple[str, dict]] = []
    if unnamed:
        why.append(("r_unnamed", {"names": ", ".join("“" + n + "”" for n in unnamed)}))
    if unknown:
        why.append(("r_unknown", {"words": ", ".join(absent[:4]) or "?"}))
    if off_vault and not single:
        why.append(("r_off_vault", {"n": absent_words, "m": top_words}))
    if not single and strong < need and alien >= ri.ALIEN_MIN:
        why.append(("r_alien", {"n": alien}))
    if single:
        if top < ri.SCORE_MIN * scale * 0.5:
            why.append(("r_score", {"score": round(top, 1), "bar": round(ri.SCORE_MIN * scale * 0.5, 1)}))
    else:
        if strong == 0:
            why.append(("r_no_strong", {}))
        elif strong < need and top < ri.SINGLE_TERM_SCORE * scale:
            why.append(("r_one_word", {"n": strong, "score": round(top, 1), "bar": round(ri.SINGLE_TERM_SCORE * scale, 1)}))
        if top < ri.SCORE_MIN * scale:
            why.append(("r_score", {"score": round(top, 1), "bar": round(ri.SCORE_MIN * scale, 1)}))
    if opened.get("clipped") and ri.absent_stems(con, raw, df):
        why.append(("r_clipped", {"words": ", ".join(ri.absent_stems(con, raw, df)[:3])}))
    for code, params in why:
        params.setdefault("absent", absent)
    return why or [("r_unknown_reason", {})]


def _page_facts(m, con, vault: Path, rel: str, qtok: list[str], qset: set, qname: str, score: float, top: float) -> dict:
    """Why one page scored what it scored: the question words it holds (and where), the weights applied."""
    ri = m.ri
    row = con.execute("SELECT f.rid, d.tier, d.status, d.title, d.name, d.how FROM files f JOIN docs d ON d.rowid=f.rid "
                      "WHERE f.rel=?", (rel,)).fetchone()
    info: dict = {"rel": rel, "score": score, "title": "", "tier": "", "status": "", "matched": [], "boosts": [], "base": None}
    if not row:
        return info
    rid, tier, status, title_tokens, name, how = row
    info.update({"tier": tier, "status": status, "how": how or ""})
    meta, body = head_of(vault / rel, 3000)
    info["title"] = meta.get("title") or next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), "") \
        or Path(rel).stem
    if qtok:
        marks = ",".join("?" * len(qtok))
        by: dict[str, list[str]] = {}
        for term, col in con.execute(f"SELECT DISTINCT term, col FROM vinst WHERE doc=? AND term IN ({marks}) "
                                     "AND col IN ('title','triggers','body')", [rid] + qtok):
            by.setdefault(term, []).append({"title": "title", "triggers": "trigger", "body": "body"}[col])
        order = {w: i for i, w in enumerate(qtok)}
        info["matched"] = [{"word": w, "where": sorted(set(v), key=["title", "trigger", "body"].index)}
                           for w, v in sorted(by.items(), key=lambda kv: order.get(kv[0], 99))]
        match = "{title triggers body} : (" + " OR ".join('"' + w.replace('"', "") + '"' for w in qtok) + ")"
        got = con.execute("SELECT bm25(docs, 0, 4.0, 4.0, 1.0, 0, 0, 0, 0, 0) FROM docs WHERE docs MATCH ? AND rowid=?",
                          (match, rid)).fetchone()
        if got:
            info["base"] = round(-got[0], 3)
    factor = ri.TIER_BOOST.get(tier, 1.0)
    info["boosts"].append({"code": "tier", "tier": tier, "f": factor})
    if tier == "topic":
        named = bool(set((title_tokens or "").split()) & qset)
        f = ri.TOPIC_NAMED if named else ri.TOPIC_UNNAMED
        info["boosts"].append({"code": "topic_named" if named else "topic_unnamed", "f": f})
        factor *= f
    if qname and len(qname) >= 2 and qname in (name or ""):
        info["boosts"].append({"code": "title", "f": ri.TITLE_HIT})
        factor *= ri.TITLE_HIT
    # the weights only explain the number when they reproduce it; otherwise the score is shown plain
    info["explained"] = info["base"] is not None and abs(round(info["base"] * factor, 3) - score) < 0.002
    info["ratio"] = round(100 * score / top) if top else 100
    return info


def explain(vault, question: str, lang: str | None = None, refresh: bool = True, store: Store | None = None) -> dict:
    """The structured explanation of one lookup. See the module doc; `blocks()` and `render()` make it readable."""
    m = mods()
    vault = Path(vault).expanduser()
    q = " ".join((question or "").split())
    vlang = m.zones.lang(vault)
    lang = lang if lang in ("en", "zh") else vlang
    ri, assoc = m.ri, m.associate
    out: dict = {"question": q, "lang": lang, "vault_lang": vlang, "vault": str(vault)}
    out["lock"] = _lock(m, vault, q)
    res = ri.recall(vault, q, refresh_first=refresh) if q else {"hits": [], "confidence": "none", "margin": 0.0,
                                                                  "query_tokens": [], "stats": {}}
    conf = res.get("confidence", "none")
    out["confidence"] = conf
    out["margin"] = res.get("margin", 0.0)
    out["partial"] = bool(res.get("partial"))
    out["clipped"] = bool(res.get("clipped"))
    st = store or Store(vault)
    con = ri.connect(ri.cache_path(vault))
    try:
        raw, df = _words(m, con, q) if q else ([], {})
        out["words"] = {"raw": raw, "used": list(res.get("query_tokens") or []),
                        "absent": [w for w in raw if df.get(w, 0) == 0]}
        qset, qname = set(raw), ri.compact(q)
        qtok = list(res.get("query_tokens") or [])
        hits = res.get("hits") or []
        top = max([h["score"] for h in hits] or [0.0]) or (hits[0]["score"] if hits else 0.0)
        out["pages"] = []
        conflict = res.get("conflict")
        for n, h in enumerate(hits, 1):
            info = _page_facts(m, con, vault, h["rel"], qtok, qset, qname, h["score"], top)
            info["n"] = n
            info["conflict"] = h.get("conflict", "")
            sides = st.supersede_sides(con, h["rel"])
            info["replaced_by"], info["replaces"] = sides["replaced_by"], sides["replaces"]
            info["reordered"] = bool(conflict and conflict.get("reorder") and h["rel"] == conflict.get("newer") and n == 1)
            out["pages"].append(info)
        out["assoc"] = []
        for n, a in enumerate(res.get("assoc") or [], 1):
            out["assoc"].append({"n": n, "rel": a["rel"], "tier": a["tier"], "status": a["status"], "how": a.get("how", ""),
                                 "score": a["score"], "title": st.title_of(a["rel"]),
                                 "via": a["via"]})
        out["conflict"] = conflict
        out["slots"] = {"n": ri.PAGES, "k": ri.DIRECT_FIRST}
        if conf == "none":
            opened = ri.recall(vault, q, refresh_first=False, gate=False, conflict=False, assoc=False) if q else {}
            out["refusal"] = [{"code": c, **p} for c, p in _refusal(m, con, vault, q, raw, df, opened)] if q else \
                [{"code": "r_no_words"}]
        else:
            out["refusal"] = []
    finally:
        con.close()
    out["cards"] = _cards(m, vault, q, [p["rel"] for p in out["pages"]])
    out["verdict"] = ("locked" if out["lock"]["state"] == "locked" else "none" if conf == "none"
                      else "partial" if out["partial"] else "answer")
    return out


def _cards(m, vault: Path, q: str, shown: list[str]) -> dict:
    exp = m.experience
    out: dict = {"on": exp.digest_on(), "total": 0, "digest_max": exp.DIGEST_MAX_LINES, "overlap": [], "from_pages": []}
    try:
        cards = exp.load_cards(vault)
    except Exception:  # noqa: BLE001
        cards = []
    out["total"] = len(cards)
    if not cards or not out["on"]:
        return out
    qw = exp.words(q)
    for c in exp.suggest(vault, q, limit=3, cards=cards):
        shared = [w for w in exp.words(c["matched"]) if w in qw]
        out["overlap"].append({"id": c["id"], "rel": c["rel"], "lesson": c["lesson"] or c["title"], "words": shared})
    stems = {Path(r).stem: r for r in shown}
    for c in cards:
        src = c["source"] or ""
        for stem, rel in stems.items():
            if stem and stem in src:
                out["from_pages"].append({"id": c["id"], "rel": c["rel"], "lesson": c["lesson"] or c["title"], "page": rel})
                break
    return out


# ---------------------------------------------------------------------------------------------- the telling


def _via(lang: str, v: dict) -> str:
    words = ""
    if v.get("words"):
        words = " (" + ", ".join(v["words"]) + ")" if lang == "en" else "（" + "、".join(v["words"]) + "）"
    return t(lang, "via_" + v["kind"], src=v["from"], words=words) if ("via_" + v["kind"]) in TEXT[lang] else v["kind"]


def blocks(e: dict) -> list[dict]:
    """The explanation as `{"t": "h"|"p"|"li", "x": text, "page": rel, "lvl": n}` blocks."""
    L = e["lang"]
    out: list[dict] = []

    def h(x):
        out.append({"t": "h", "x": x})

    def p(x):
        out.append({"t": "p", "x": x})

    def li(x, lvl=0, page=""):
        out.append({"t": "li", "x": x, "lvl": lvl, "page": page})

    h(t(L, "h_question"))
    p(e["question"] or "(empty)")
    verdict = e["verdict"]
    p({"locked": t(L, "v_locked"), "none": t(L, "v_none"), "partial": t(L, "v_partial"),
       "answer": t(L, "v_answer", conf=e["confidence"])}[verdict])

    lock = e["lock"]
    h(t(L, "h_lock"))
    st = lock["state"]
    if st == "locked":
        how = t(L, {"exact": "how_exact", "inside": "how_inside", "part": "how_part", "token": "how_token"}[lock["kind"]])
        li(t(L, "lock_hit", how=how, alias=lock["alias"], page=lock["page"]), page=lock["page"])
        if lock.get("how"):
            li(t(L, "lock_how", how=lock["how"]), 1)
    elif st == "tie":
        li(t(L, "lock_tie", left=lock["left"], lp=lock["lp"], right=lock["right"], rp=lock["rp"]))
    elif st in ("dead", "gone"):
        li(t(L, "lock_dead" if st == "dead" else "lock_gone", alias=lock["alias"], page=lock["page"]), page=lock["page"])
    else:
        li(t(L, "lock_none"))
        if lock.get("near"):
            sep = "; " if L == "en" else "；"
            li(t(L, "lock_near", list=sep.join(f"“{n['alias']}” → {n['page']}" for n in lock["near"])), 1)

    w = e["words"]
    h(t(L, "h_words"))
    if not w["raw"]:
        li(t(L, "words_none"))
    else:
        sep = ", " if L == "en" else "、"
        li(t(L, "words_used", words=sep.join(w["used"] or w["raw"])))
        if w["absent"]:
            li(t(L, "words_absent", words=sep.join(w["absent"][:10])))

    h(t(L, "h_pages_ref" if verdict == "locked" else "h_pages_none" if verdict == "none" else "h_pages"))
    if not e["pages"]:
        li(t(L, "none"))
    for pg in e["pages"]:
        tier = pg["tier"] or "other"
        li(t(L, "page_head", n=pg["n"], rel=pg["rel"], title=pg["title"], tier=tier, status=_status(L, pg["status"]),
             score=pg["score"]), 0, pg["rel"])
        if pg["matched"]:
            parts = [t(L, "page_where", word=x["word"], where=" + ".join(t(L, "where_" + wh) for wh in x["where"]))
                     for x in pg["matched"]]
            li(t(L, "page_matched", words=("; " if L == "en" else "；").join(parts)), 1)
        else:
            li(t(L, "page_nomatch"), 1)
        if pg.get("explained"):
            boosts = " × ".join(_boost(L, b) for b in pg["boosts"])
            li(t(L, "page_score", score=pg["score"], base=pg["base"], boosts=boosts) + (
                "; " if L == "en" else "；") + (t(L, "page_rank_first") if pg["n"] == 1 or pg["ratio"] >= 100
                                                else t(L, "page_rank_after", ratio=pg["ratio"])), 1)
        else:
            li(t(L, "page_score_plain", score=pg["score"]), 1)
        if pg.get("reordered"):
            li(t(L, "page_reordered"), 1)
        if pg["conflict"]:
            li(t(L, {"newer": "page_conflict_newer", "older": "page_conflict_older"}.get(pg["conflict"],
                                                                                     "page_conflict_possible")), 1)
        if pg.get("replaced_by"):
            li(t(L, "page_replaced", pages=", ".join(pg["replaced_by"])), 1)
        if pg.get("replaces"):
            li(t(L, "page_replaces", pages=", ".join(pg["replaces"])), 1)
        if pg.get("how"):
            li(t(L, "page_how", how=pg["how"]), 1)
    if e["pages"] and verdict != "none":
        p(t(L, "slots", **e["slots"]))

    h(t(L, "h_conf"))
    conf, margin = e["confidence"], e["margin"]
    if conf == "none":
        li(t(L, "conf_none"))
        for r in e["refusal"]:
            params = {k: v for k, v in r.items() if k not in ("code", "absent")}
            if r["code"] == "r_nothing":
                params["words"] = ", ".join((r.get("absent") or e["words"]["raw"])[:8])
            li(t(L, r["code"], **params), 1)
    elif e["clipped"]:
        li(t(L, "conf_low_clipped"))
    elif e["partial"]:
        li(t(L, "conf_low_partial"))
    elif conf == "high":
        li(t(L, "conf_high", margin=margin))
    elif conf == "medium":
        top = e["pages"][0] if e["pages"] else {}
        if top.get("tier") in ("rule", "topic") or margin < 1.5:
            li(t(L, "conf_medium_margin", margin=margin))
        else:
            li(t(L, "conf_medium_tier", margin=margin, tier=t(L, "tier_" + (top.get("tier") or "other"))))
    else:
        li(t(L, "conf_low_close", margin=margin))

    h(t(L, "h_assoc"))
    if not e["assoc"]:
        li(t(L, "assoc_none"))
    else:
        p(t(L, "assoc_intro"))
        for a in e["assoc"]:
            li(t(L, "assoc_head", rel=a["rel"], title=a["title"], tier=a["tier"] or "other", score=a["score"]), 0, a["rel"])
            for v in a["via"]:
                li(_via(L, v), 1, v["from"])

    h(t(L, "h_conflict"))
    c = e["conflict"]
    if c:
        if c["sure"]:
            li(t(L, "conflict_sure", new=c["newer"], nd=c["newer_day"], old=c["older"], od=c["older_day"]), 0, c["newer"])
        else:
            li(t(L, "conflict_possible", a=c["newer"], ad=c["newer_day"], b=c["older"], bd=c["older_day"]), 0, c["newer"])
    else:
        li(t(L, "conflict_none"))
    dead = [pg["rel"] for pg in e["pages"] if pg["tier"] == "dead" or pg["status"] in ("superseded", "retired")]
    if dead:
        li(t(L, "replaced_list", list=", ".join(dead)))

    h(t(L, "h_cards"))
    cd = e["cards"]
    if not cd["on"]:
        li(t(L, "cards_off"))
    elif not cd["total"]:
        li(t(L, "cards_none_on"))
    else:
        li(t(L, "cards_digest", n=cd["total"], k=cd["digest_max"]))
        sep = ", " if L == "en" else "、"
        for c in cd["overlap"]:
            li(t(L, "cards_overlap") + t(L, "card_line", id=c["id"], lesson=c["lesson"], words=sep.join(c["words"])), 1, c["rel"])
        for c in cd["from_pages"]:
            li(t(L, "cards_source") + f"〔{c['id']}〕 {c['lesson']} ← {c['page']}", 1, c["rel"])
        if not cd["overlap"] and not cd["from_pages"]:
            li(t(L, "cards_nothing"), 1)
    return out


def _boost(lang: str, b: dict) -> str:
    if b["code"] == "tier":
        return t(lang, "boost_tier", tier=t(lang, "tier_" + b["tier"]) if ("tier_" + b["tier"]) in TEXT[lang] else b["tier"],
                 f=b["f"])
    return t(lang, "boost_" + b["code"], f=b["f"])


def pages_in(e: dict) -> list[str]:
    """Every page path the explanation mentions, longest first (the viewer turns them into links)."""
    found: set[str] = set()
    lock = e.get("lock") or {}
    found.update(x for x in (lock.get("page"), lock.get("lp"), lock.get("rp")) if x)
    for pg in e.get("pages", []):
        found.add(pg["rel"])
        found.update(pg.get("replaced_by") or [])
        found.update(pg.get("replaces") or [])
    for a in e.get("assoc", []):
        found.add(a["rel"])
        found.update(v["from"] for v in a["via"])
    c = e.get("conflict") or {}
    found.update(x for x in (c.get("newer"), c.get("older")) if x)
    cards = e.get("cards") or {}
    found.update(x["rel"] for x in cards.get("overlap", []) + cards.get("from_pages", []))
    found.update(x["page"] for x in cards.get("from_pages", []))
    return sorted(found, key=lambda r: (-len(r), r))


def render(e: dict) -> str:
    """The explanation as plain text."""
    lines: list[str] = []
    for b in blocks(e):
        if b["t"] == "h":
            lines += ["", b["x"], ""] if lines else [b["x"], ""]
        elif b["t"] == "p":
            lines.append(b["x"])
        else:
            lines.append("  " * (b.get("lvl") or 0) + "- " + b["x"])
    return "\n".join(lines).strip() + "\n"


def run(vault, question: str, lang: str | None = None, as_json: bool = False) -> int:
    import json

    e = explain(vault, question, lang)
    if as_json:
        print(json.dumps(e, ensure_ascii=False, indent=1, default=list))
    else:
        print(render(e), end="")
    return 0
