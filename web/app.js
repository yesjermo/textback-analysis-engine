/* TextBack Analysis Engine web view.
 *
 * Two modes, picked automatically:
 *   - Local server (python3 main.py serve): lists your Python profiles, replies come from
 *     the Python engine, corrections save to disk.
 *   - Browser only (open index.html or any static host): parses a chat export in the
 *     browser, learns the style, replies with the offline retrieval engine, and keeps
 *     profiles in this browser's localStorage. Nothing is uploaded.
 *
 * The parser, analyzer, rules and offline engine mirror tools/*.py.
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------ parsing
  const TIME = String.raw`\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?\s?[Mm]\.?)?`;
  const DATE = String.raw`\d{1,4}[./-]\d{1,2}[./-]\d{1,4}`;
  const WA_BRACKET = new RegExp(String.raw`^\[(${DATE}),?\s+(${TIME})\]\s*([^:]{1,60}):\s?(.*)$`);
  const WA_DASH = new RegExp(String.raw`^(${DATE}),?\s+(${TIME})\s+-\s+([^:]{1,60}):\s?(.*)$`);
  const SIMPLE = /^([^:\[\]\n]{1,40}):\s+(.+)$/;
  const SKIP = ["<media omitted>", "image omitted", "video omitted", "sticker omitted", "audio omitted",
    "gif omitted", "this message was deleted", "you deleted this message",
    "messages and calls are end-to-end encrypted"];

  const keep = (t) => { const l = t.trim().toLowerCase(); return l && !SKIP.some((s) => l.includes(s)); };

  function parseDate(date, time) {
    // Assumes month/day order (US WhatsApp). Only used for reply-delay and active hours.
    const [a, b, c] = date.split(/[./-]/).map(Number);
    let y, m, d;
    if (String(date).match(/^\d{4}/)) [y, m, d] = [a, b, c];
    else { [m, d, y] = a > 12 ? [b, a, c] : [a, b, c]; if (y < 100) y += 2000; }
    const t = time.replace(/\./g, "").toUpperCase().match(/(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?/);
    if (!t) return null;
    let h = Number(t[1]);
    if (t[4] === "PM" && h < 12) h += 12;
    if (t[4] === "AM" && h === 12) h = 0;
    const dt = new Date(y, m - 1, d, h, Number(t[2]), Number(t[3] || 0));
    return isNaN(dt) ? null : dt.toISOString();
  }

  function parseText(raw) {
    const lines = raw.split(/\r?\n/).map((l) => l.replace(/ /g, " ").replace(/[‎﻿]/g, ""));
    const sample = lines.filter((l) => l.trim()).slice(0, 200);
    const score = (re) => sample.filter((l) => re.test(l)).length;
    let pattern = score(WA_BRACKET) >= score(WA_DASH) ? WA_BRACKET : WA_DASH;
    if (score(pattern) === 0) pattern = SIMPLE;
    const out = [];
    for (const line of lines) {
      const m = line.match(pattern);
      if (m) {
        out.push(pattern === SIMPLE
          ? { sender: m[1].trim(), text: m[2].trim(), timestamp: null }
          : { sender: m[3].trim(), text: m[4].trim(), timestamp: parseDate(m[1], m[2]) });
      } else if (out.length && line.trim()) {
        out[out.length - 1].text += "\n" + line.trim();
      }
    }
    return out.filter((m) => keep(m.text));
  }

  const pick = (row, keys) => {
    const low = Object.fromEntries(Object.entries(row).map(([k, v]) => [k.toLowerCase().trim(), v]));
    for (const k of keys) if (low[k] != null && low[k] !== "") return low[k];
    return null;
  };
  const textValue = (v) => Array.isArray(v) ? v.map((p) => (typeof p === "string" ? p : p.text || "")).join("") : (v == null ? "" : String(v));

  function rowsToMessages(rows) {
    return rows.map((r) => ({
      sender: pick(r, ["sender", "from", "author", "name", "sender_name", "contact", "who"]),
      text: textValue(pick(r, ["text", "message", "body", "content", "msg"])).trim(),
      timestamp: pick(r, ["timestamp", "date", "time", "datetime", "sent_at", "created_at"]),
    })).filter((m) => m.sender && keep(m.text)).map((m) => ({ ...m, sender: String(m.sender).trim() }));
  }

  function parseCSV(raw) {
    const rows = [];
    let row = [], field = "", quoted = false;
    for (let i = 0; i < raw.length; i++) {
      const ch = raw[i];
      if (quoted) {
        if (ch === '"' && raw[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ",") { row.push(field); field = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && raw[i + 1] === "\n") i++;
        row.push(field); rows.push(row); row = []; field = "";
      } else field += ch;
    }
    if (field || row.length) { row.push(field); rows.push(row); }
    const [head, ...body] = rows;
    if (!head) return [];
    return rowsToMessages(body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]]))));
  }

  function parseFile(name, raw) {
    const lower = name.toLowerCase();
    if (lower.endsWith(".csv")) return { messages: parseCSV(raw) };
    if (lower.endsWith(".json")) {
      const data = JSON.parse(raw);
      if (data && data.format && /^(textback|textprint)-profile/.test(String(data.format))) return { bundle: data };
      return { messages: rowsToMessages(Array.isArray(data) ? data : data.messages || []) };
    }
    return { messages: parseText(raw) };
  }

  // ------------------------------------------------------------------ analysis
  const EMOJI = /\p{Extended_Pictographic}/u;
  const EMOJI_G = /\p{Extended_Pictographic}/gu;
  const WORD = /[A-Za-z][A-Za-z']*/g;
  const SLANG = new Set("lol lmao lmfao rofl u ur k kk tbh idk ngl omg btw pls plz thx ty np rn imo fr bruh haha hahaha hehe ok okay yep yup nah ya yea yeah gonna wanna gotta asap fyi eod eta wfh sry srsly bc cuz tho ikr smh wyd hbu omw w mtg cal def prob tmrw".split(" "));
  const NO_APOSTROPHE = new Set("dont cant wont im thats lets youre didnt isnt ive whats doesnt theyre wasnt couldnt shouldnt".split(" "));
  const STOP = new Set("the a an and or but to of in on at for is it i you me my we be that this so do are was with have just not if can i'm it's your what will about up get as all no yes from there they he she them our were been has had did don't how when then too out by".split(" "));
  const LAUGHS = ["haha", "hahaha", "lol", "lmao", "hehe", "😂", "🤣", "💀"]; // taste-skill-ignore: data the analyzer matches, not UI

  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const round = (n, d = 2) => Math.round(n * 10 ** d) / 10 ** d;
  const top = (counter, n) => [...counter.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
  const bump = (map, k, by = 1) => map.set(k, (map.get(k) || 0) + by);

  function textStats(msgs) {
    const texts = msgs.map((m) => m.text.trim()).filter(Boolean);
    const n = texts.length;
    if (!n) return { count: 0 };
    const words = texts.map((t) => t.match(WORD) || []);
    const lens = words.map((w) => w.length);
    const lettered = texts.filter((t) => /[A-Za-z]/.test(t));
    const ends = new Map(), wc = new Map(), bi = new Map(), emo = new Map(), laughs = new Map();
    texts.forEach((t, i) => {
      const last = [...t].pop();
      if (t.endsWith("..") || t.endsWith("…")) bump(ends, "ellipsis");
      else if (".!?".includes(last)) bump(ends, last);
      else if (EMOJI.test(last)) bump(ends, "emoji");
      else bump(ends, "none");
      const low = words[i].map((w) => w.toLowerCase());
      low.forEach((w) => bump(wc, w));
      for (let j = 0; j < low.length - 1; j++) {
        if (!(STOP.has(low[j]) && STOP.has(low[j + 1]))) bump(bi, low[j] + " " + low[j + 1]);
      }
      (t.match(EMOJI_G) || []).forEach((e) => bump(emo, e));
      const lt = t.toLowerCase();
      const laugh = LAUGHS.find((l) => lt.includes(l));
      if (laugh) bump(laughs, laugh);
    });
    const rate = (c, total = n) => round(c / Math.max(total, 1), 3);
    const allWords = words.flat().map((w) => w.toLowerCase());
    const noApos = allWords.filter((w) => NO_APOSTROPHE.has(w)).length;
    const withApos = allWords.filter((w) => w.includes("'") && NO_APOSTROPHE.has(w.replace(/'/g, ""))).length;
    const endRates = Object.fromEntries(top(ends, 10).map(([k, v]) => [k, rate(v)]));
    return {
      count: n,
      avg_words: round(mean(lens)),
      median_words: median(lens),
      lowercase_rate: rate(lettered.filter((t) => t === t.toLowerCase()).length, lettered.length),
      capitalized_start_rate: rate(lettered.filter((t) => /^[A-Z]/.test(t)).length, lettered.length),
      ending_punctuation: endRates,
      apostrophe_drop_rate: noApos + withApos ? rate(noApos, noApos + withApos) : 0,
      question_rate: rate(texts.filter((t) => t.includes("?")).length),
      exclaim_rate: rate(texts.filter((t) => t.includes("!")).length),
      emoji_rate: rate(texts.filter((t) => EMOJI.test(t)).length),
      top_emojis: top(emo, 8).map(([e]) => e),
      laugh_style: laughs.size ? top(laughs, 1)[0][0] : null,
      slang: top(new Map([...wc].filter(([w]) => SLANG.has(w))), 10).map(([w]) => w),
      top_words: top(new Map([...wc].filter(([w]) => !STOP.has(w) && !SLANG.has(w) && w.length > 2)), 25).map(([w]) => w),
      top_phrases: top(bi, 40).filter(([, c]) => c > 1).slice(0, 15).map(([p]) => p),
    };
  }

  function analyze(messages, target, me) {
    const turns = [];
    const SILENCE = 3 * 3600 * 1000; // a gap this long starts a new conversation
    for (const m of messages) {
      const last = turns[turns.length - 1];
      const gap = last ? Date.parse(m.timestamp) - Date.parse(last.messages[last.messages.length - 1].timestamp) : 0;
      if (last && last.sender === m.sender && !(gap > SILENCE)) last.messages.push(m);
      else turns.push({ sender: m.sender, messages: [m] });
    }
    const them = textStats(messages.filter((m) => m.sender === target));
    const you = textStats(messages.filter((m) => (me ? m.sender === me : m.sender !== target)));
    const theirTurns = turns.filter((t) => t.sender === target);
    // Phrases like "after 3" / "by fri" first: they work as answers, a bare "9:30" usually doesn't.
    const timeCounts = countOf(messages.filter((m) => m.sender === target).flatMap((m) => extractTimes(m.text).map((t) => t.toLowerCase())));
    them.time_phrases = [...timeCounts].sort((x, y) => (PREP_START.test(y[0]) - PREP_START.test(x[0])) || (y[1] - x[1])).slice(0, 8).map(([t]) => t);
    them.msgs_per_turn = theirTurns.length ? round(mean(theirTurns.map((t) => t.messages.length))) : 1;
    const latencies = [], examples = [], starters = [];
    turns.forEach((t, i) => {
      if (t.sender !== target) return;
      const reply = t.messages.map((m) => m.text);
      const prev = turns[i - 1];
      if (!prev || prev.sender === target) { starters.push(reply); return; }
      const a = Date.parse(prev.messages[prev.messages.length - 1].timestamp);
      const b = Date.parse(t.messages[0].timestamp);
      if (!isNaN(a) && !isNaN(b)) {
        const gap = (b - a) / 1000;
        if (gap >= 0 && gap < SILENCE / 1000) latencies.push(gap);
        else if (gap >= SILENCE / 1000) starters.push(reply);
      }
      examples.push({ context: prev.messages.slice(-3).map((m) => m.text).join(" / "), reply });
    });
    them.median_reply_seconds = latencies.length ? Math.round(median(latencies)) : null;
    // Who starts conversations: the first turn after a long silence (or the very first turn).
    const starts = turns.filter((t, i) => {
      if (i === 0) return true;
      const prev = turns[i - 1];
      return Date.parse(t.messages[0].timestamp) - Date.parse(prev.messages[prev.messages.length - 1].timestamp) > SILENCE;
    }).map((t) => t.sender);
    them.initiation_rate = starts.length >= 3 ? round(starts.filter((s) => s === target).length / starts.length) : null;
    return {
      style: { target, me, message_count: messages.length, them, you, starters: starters.slice(-30) },
      examples: examples.slice(-400),
    };
  }

  // Mirrors tools/persona_builder.py::style_rules
  function styleRules(style) {
    const s = (style && style.them) || {};
    if (!s.count) return ["Not enough messages yet. Import more chat history."];
    const r = [];
    const avg = s.avg_words || 0;
    if (avg <= 4) r.push(`Very short texts: about ${avg} words each. One-word answers are normal.`);
    else if (avg <= 12) r.push(`Short, casual texts: about ${avg} words each.`);
    else r.push(`Writes full, longer messages: about ${avg} words each.`);
    r.push(s.msgs_per_turn >= 1.6
      ? `Sends bursts: about ${s.msgs_per_turn} separate texts per turn instead of one long one.`
      : "Usually sends one text per turn.");
    if (s.lowercase_rate >= 0.6) r.push("Types almost entirely in lowercase.");
    else if (s.capitalized_start_rate >= 0.7) r.push("Starts messages with a capital letter, like proper writing.");
    const ends = s.ending_punctuation || {};
    if ((ends.none || 0) >= 0.5) r.push("Usually leaves the final punctuation off.");
    if ((ends["."] || 0) >= 0.3) r.push("Often ends texts with a period, which reads as formal or curt.");
    if (s.exclaim_rate >= 0.25) r.push("Uses exclamation marks a lot!");
    if ((ends.ellipsis || 0) >= 0.1) r.push("Trails off with '...' fairly often.");
    if (s.emoji_rate >= 0.2 && s.top_emojis.length) r.push(`Uses emoji in about ${Math.round(s.emoji_rate * 100)}% of texts, mostly ${s.top_emojis.slice(0, 4).join(" ")}.`);
    else if (s.emoji_rate < 0.05) r.push("Almost never uses emoji.");
    if (s.laugh_style) r.push(`Laughs with "${s.laugh_style}".`);
    if (s.slang && s.slang.length) r.push(`Slang and shorthand: ${s.slang.slice(0, 8).join(", ")}.`);
    if (s.top_phrases && s.top_phrases.length) r.push(`Signature phrases: ${s.top_phrases.slice(0, 6).map((p) => `'${p}'`).join(", ")}.`);
    if (s.initiation_rate != null) {
      if (s.initiation_rate >= 0.6) r.push(`Usually texts first: starts ${Math.round(s.initiation_rate * 100)}% of your conversations.`);
      else if (s.initiation_rate <= 0.3) r.push(`Rarely texts first: starts only ${Math.round(s.initiation_rate * 100)}% of conversations; you usually reach out.`);
    }
    if (s.median_reply_seconds != null) {
      const mins = s.median_reply_seconds / 60;
      r.push(`Typical reply delay: ${mins < 1 ? "under a minute" : `about ${Math.round(mins)} min`}.`);
    }
    const you = style.you || {};
    if (you.count && s.avg_words) {
      const ratio = s.avg_words / Math.max(you.avg_words || 1, 0.1);
      r.push(ratio < 0.6 ? "Replies to you much more briefly than you write to them."
        : ratio > 1.6 ? "Writes back at greater length than you do." : "Roughly matches your message length.");
    }
    return r;
  }

  // ------------------------------------------------------------------ understanding texts (mirrors tools/intents.py)
  // Patterns, synonyms and templates come from tools/reply_data.json via reply_data.js.
  const D = window.TEXTBACK_DATA;
  const INTENTS = D.intents.map(([n, p]) => [n, new RegExp(p, "i")]);
  const BY_NAME = Object.fromEntries(INTENTS);
  const WH_START = new RegExp(D.wh_start, "i");
  const WH_FIRST = D.wh_first.map((n) => [n, BY_NAME[n]]);
  const NOUN_HEADS = new Set(D.noun_heads), GENERIC = new Set(D.generic_nouns), ADJECTIVES = new Set(D.adjectives);
  const FACT_INTENTS = new Set(D.fact_intents), LABELS = D.intent_labels, FAMILY_ONLY = D.family_only;
  const CONTEXTLESS = new Set(D.contextless_intents); // "ok", "lol": a real reply to these depends on the moment
  const LAUGH_WORD = /\b(lol|lmao+|lmfao|haha(ha)*)\b/gi;
  const oneTextWriter = (them) => (them.avg_words || 0) >= 6 && (them.msgs_per_turn || 1) < 1.4;
  const FAMILY_NAMES = { work: "work", personal: "friends & family", ex: "ex", talking_stage: "talking-stage" };
  const DEADLINE_HINT = new RegExp(D.deadline_hint, "i"), DEADLINE_TIMES = new RegExp(D.deadline_times, "i");
  const SWAPS = D.slang_swaps.map(([p, r, n]) => [new RegExp(p, "gi"), r, n]);
  const DAYS = "(?:mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)(?:day)?";
  const WORD_TIME = `(?:noon|lunch|eod|tomorrow|tmrw|tonight|next week|this week|later today|end of (?:the )?day|${DAYS})`;
  const CLOCK = String.raw`\d{1,2}(?::\d{2})?\s?(?:am|pm)|\d{1,2}:\d{2}`;
  const PREP = String.raw`(?:after|by|before|at|around|until|till)\s+(?:${CLOCK}|\d{1,2}\b|${WORD_TIME})`;
  const TIME_SRC = String.raw`\b(?:${PREP}|${CLOCK}|${WORD_TIME})\b`;
  const TIME_ONLY = new RegExp(`^(?:${TIME_SRC})$`, "i");
  const TOPIC_RE = /\b(?:the|my|our|this|that|your|ur)\s+([a-z][a-z0-9'-]*(?:\s+[a-z][a-z0-9'-]*){0,2})/g;
  const PREP_START = /^(after|by|before|at|around|until|till)\s+/i;

  // Which reply style a relationship uses: work, ex, talking_stage, or personal.
  function family(rel) {
    const r = String(rel || "").toLowerCase().replace(/[-_]/g, " ");
    for (const [fam, members] of Object.entries(D.families)) if (members.includes(r)) return fam;
    return "personal";
  }
  const lastMessage = (c) => c.split(" / ").pop();
  const extractTimes = (t) => [...t.matchAll(new RegExp(TIME_SRC, "gi"))].map((m) => m[0].trim());
  const countOf = (arr) => { const m = new Map(); arr.forEach((w) => bump(m, w)); return m; };

  function detectIntent(text, fam = null) {
    const t = text.toLowerCase().trim();
    // "where can I find..." is a where-question, not a permission request.
    const order = WH_START.test(t) ? [...WH_FIRST, ...INTENTS] : INTENTS;
    for (const [name, rx] of order) {
      if (fam && FAMILY_ONLY[name] && !FAMILY_ONLY[name].includes(fam)) continue; // no "relationship talks" with your boss
      if (!rx.test(t)) continue;
      if (name === "done" && t.endsWith("?")) return "yesno";
      if (name === "request" && /^(did|have|has|do|does) (you|u|they|we|he|she)\b/.test(t)) return "yesno"; // "did you send it?"
      return name;
    }
    return "statement";
  }

  function extractTopic(text) {
    for (const m of text.toLowerCase().matchAll(TOPIC_RE)) {
      let words = m[1].split(/\s+/);
      if (ADJECTIVES.has(words[0]) && words.length > 1) words = words.slice(1);
      const first = words[0];
      if (STOP.has(first) || GENERIC.has(first) || TIME_ONLY.test(first)) continue;
      const topic = [first];
      for (const w of words.slice(1)) { if (!NOUN_HEADS.has(w)) break; topic.push(w); }
      return topic.join(" ");
    }
    return null;
  }

  function tokenize(text, keepStop = false) {
    const out = [];
    for (let w of text.toLowerCase().match(/[a-z0-9']+/g) || []) {
      w = D.synonyms[w] || w;
      if (STOP.has(w) && !keepStop) continue;
      if (w.length > 4) for (const suf of ["ing", "ed", "es", "s"]) if (w.endsWith(suf)) { w = w.slice(0, -suf.length); break; }
      out.push(D.synonyms[w] || w);
    }
    return out;
  }

  // TF-IDF cosine: rare shared words ("budget", "dentist") count more than common ones.
  function makeIndex(contexts) {
    const msgs = contexts.map(lastMessage);
    const n = msgs.length;
    const norm = (v) => Math.sqrt([...v.values()].reduce((a, x) => a + x * x, 0));
    // Two views: content words only, and every word (for texts like "what are we?").
    const views = [false, true].map((keep) => {
      const docs = msgs.map((m) => countOf(tokenize(m, keep)));
      const df = new Map();
      docs.forEach((d) => d.forEach((_, w) => bump(df, w)));
      const idf = (w) => Math.log((n + 1) / ((df.get(w) || 0) + 1)) + 1;
      const vec = (counts) => { const v = new Map(); counts.forEach((c, w) => v.set(w, c * idf(w))); return v; };
      return { vec, vecs: docs.map(vec) };
    });
    return {
      cosine(query, i) {
        const keep = tokenize(query).length === 0; // nothing but common words: compare every word
        const view = views[keep ? 1 : 0];
        const q = view.vec(countOf(tokenize(query, keep))), d = view.vecs[i];
        let dot = 0;
        q.forEach((x, w) => { dot += x * (d.get(w) || 0); });
        return dot ? dot / (norm(q) * norm(d)) : 0;
      },
    };
  }

  function personalize(text, them) {
    const used = new Set([...(them.slang || []), ...(them.top_words || [])]);
    for (const [rx, repl, needs] of SWAPS) if (used.has(needs)) text = text.replace(rx, repl);
    if ((them.apostrophe_drop_rate || 0) >= 0.5) text = text.replace(/'/g, "");
    if (them.laugh_style) text = text.replace(LAUGH_WORD, them.laugh_style); // laugh the way they do
    return text;
  }

  // ------------------------------------------------------------------ offline engine (mirrors tools/reply_engine.py)
  const WEIGHTS = { correction: 1.6, approved: 1.25, history: 1.0, reference: 0.75 };
  const TIME_INTENTS = new Set(["q_when", "schedule", "q_status"]);
  const REUSE_SCORE = 0.6, NEAR_COSINE = 0.25;
  const asList = (v) => (Array.isArray(v) ? v : [v]);
  const choice = (a) => a[Math.floor(Math.random() * a.length)];
  const timesWord = (n) => (n === 1 ? "once" : `${n} times`);
  const isShort = (text, intent) => text.trim().split(/\s+/).length <= 5 && (TIME_INTENTS.has(intent) || !/\d/.test(text));

  function memory(b, fam) {
    const useRef = b.meta.use_reference !== false;
    return [
      ...b.examples.map((e) => ({ ...e, source: "history" })),
      ...(b.corrections || []).map((c) => ({ context: c.context, reply: asList(c.good), source: "correction" })),
      ...(b.approved || []).map((a) => ({ context: a.context, reply: asList(a.reply), source: "approved" })),
      ...(useRef ? (D.reference[fam] || []).map((r) => ({ ...r, source: "reference" })) : []),
    ].map((r) => ({ ...r, reply: asList(r.reply), intent: detectIntent(lastMessage(r.context), fam) }));
  }

  function rank(rows, message, intent) {
    if (!rows.length) return [];
    const idx = makeIndex(rows.map((r) => r.context));
    return rows.map((r, i) => {
      const cos = idx.cosine(message, i);
      return [(0.65 * cos + 0.35 * (r.intent === intent ? 1 : 0)) * WEIGHTS[r.source], cos, r];
    }).sort((a, b) => b[0] - a[0]);
  }

  function stylize(text, them, composed = false, intent = "") {
    let t = text.trim();
    if (composed) {
      t = personalize(t, them);
      if ((them.capitalized_start_rate || 0) >= 0.7 && /^[a-z]/.test(t)) t = t[0].toUpperCase() + t.slice(1);
    }
    if ((them.lowercase_rate || 0) >= 0.6) t = t.toLowerCase();
    const ends = them.ending_punctuation || {};
    if ((ends.none || 0) >= 0.5) t = t.replace(/\.+$/, "");
    else if (composed && t && !/[.!?]$/.test(t) && !EMOJI.test([...t].pop())) {
      if ((them.exclaim_rate || 0) >= 0.25 && ["news", "thanks", "greeting", "done"].includes(intent)) t += "!";
      else if ((ends["."] || 0) >= 0.3) t += ".";
    }
    const em = them.top_emojis || [];
    if (em.length && !EMOJI.test(t) && Math.random() < (them.emoji_rate || 0) * 0.6) t += " " + choice(em.slice(0, 3));
    return t;
  }

  function reactionBank(rows, intent) {
    const bank = new Map();
    for (const r of rows) {
      if (CONTEXTLESS.has(intent) && (r.reply[0] || "").trim().split(/\s+/).length > 2) continue; // only "ok" / "lol" travel
      if (r.source !== "reference" && r.intent === intent && r.reply.length && isShort(r.reply[0], intent)) bump(bank, r.reply[0], r.source !== "history" ? 2 : 1);
    }
    return bank;
  }

  function pickTime(message, them, fam) {
    const mentioned = extractTimes(message);
    if (mentioned.length) return [mentioned[0], "the time you mentioned"];
    let phrases = them.time_phrases || [];
    if (DEADLINE_HINT.test(message)) { // deadlines get days ("by fri"), not clock times
      phrases = phrases.filter((p) => DEADLINE_TIMES.test(p));
      if (!phrases.length) return [choice(["by eod", "by fri", "end of the week"]), "a default deadline"];
    }
    if (phrases.length) return [choice(phrases.slice(0, 4)), "a time phrase they often use"];
    return [choice(D.default_times[fam]), "a default time"];
  }

  function fill(template, topic, time, bare) {
    if (template.includes("{topic}") && !topic) return null;
    const when = /(^|\b(until|till|by|at|after|before|around|do)\s+)\{time\}/.test(template) ? bare : time;
    return template.replace("{topic}", topic || "").replace("{time}", when).trim();
  }

  function offlineReply(b, message, recent) {
    const them = b.style.them || {};
    const fam = family(b.meta.relationship);
    const rows = memory(b, fam);
    const intent = detectIntent(message, fam);
    const topic = extractTopic(message);
    const why = { intent, read_as: LABELS[intent] || intent, topic };
    const everything = rank(rows, message, intent).filter(([, , r]) => !recent.includes(r.reply.join(" ")));
    const ranked = everything.filter(([, , r]) => r.source !== "reference");
    const references = everything.filter(([, , r]) => r.source === "reference");
    let near = null;

    // 1. A near-identical situation already happened (or you taught one): send that reply.
    if (ranked.length) {
      const [score, cos, row] = ranked[0];
      const taught = row.source !== "history";
      if ((row.intent === intent && score >= REUSE_SCORE) || (taught && cos >= 0.5)) {
        const source = `${taught ? "you taught this reply" : "their real reply"} to "${lastMessage(row.context)}"`;
        const mine = new Set(tokenize(message));
        // Later bubbles can carry details from that other day ("standup moved to 9:30").
        const offTopic = row.reply.slice(1).filter((x) => (/\d/.test(x) || extractTimes(x).length) && !tokenize(x).some((w) => mine.has(w)));
        const extraOk = taught || cos >= 0.8 || !offTopic.length;
        if (extraOk) {
          Object.assign(why, { strategy: "reused", because: `${source} (${Math.round(cos * 100)}% similar wording)` });
          return { replies: row.reply.map((t) => stylize(t, them)), why };
        }
        near = ranked[0];
      }
    }

    // 2. Compose: their reaction + a follow-up about your topic, in their style.
    const tpl = D.templates[fam][intent] || D.templates[fam].statement;
    const [time, timeSrc] = pickTime(message, them, fam);
    const bare = time.replace(PREP_START, "");
    const nearMin = CONTEXTLESS.has(intent) ? 0.5 : NEAR_COSINE;
    near = near || ranked.slice(0, 5).find(([, c, r]) => r.intent === intent && c >= nearMin) || null;
    let bank = reactionBank(rows, intent);
    if (FACT_INTENTS.has(intent)) { // "why/who/what/how" answers are facts about one situation
      bank = new Map();
      if (near && near[1] < 0.45) near = null;
    }
    if (extractTimes(message).length) { // you named a time: don't open by proposing a different one
      bank = new Map([...bank].filter(([k]) => !extractTimes(k).length));
      if (near && extractTimes(near[2].reply[0]).length) near = null;
    }

    const target = Math.max(1, Math.min(3, Math.round(them.msgs_per_turn || 1)));
    const strongRef = references.slice(0, 5).find(([, c, r]) => r.intent === intent && c >= 0.6);
    const ref = strongRef || references.slice(0, 5).find(([, c, r]) => r.intent === intent && c >= (FACT_INTENTS.has(intent) ? 0.45 : 0.3));
    if (ref && !(near && isShort(near[2].reply[0], intent)) && (strongRef || !bank.size)) {
      // Their own chat has nothing like this: borrow a generic reply's shape, in their style.
      Object.assign(why, { strategy: "reference",
        because: `the built-in ${FAMILY_NAMES[fam]} reference reply to "${ref[2].context}", rewritten in their style (your chat had nothing similar)` });
      const trailing = /\s*\p{Extended_Pictographic}+\s*$/u;
      const parts = ref[2].reply.map((x) => stylize(x, them, true, intent)).map((p, i, all) => (i < all.length - 1 ? p.replace(trailing, "") || p : p));
      const long = oneTextWriter(them); // they write one fuller message
      return { replies: long ? [parts.map((p, i) => (i && /[.!?]$/.test(parts[i - 1]) ? p[0].toUpperCase() + p.slice(1) : p) + (i < parts.length - 1 && !/[.!?]$/.test(p) ? "." : "")).join(" ")] : parts.slice(0, target), why };
    }

    let reaction, composed = false;
    if (near && isShort(near[2].reply[0], intent)) {
      reaction = near[2].reply[0];
      why.reaction_from = `their reply when you said "${lastMessage(near[2].context)}"`;
    } else if (bank.size) {
      const options = top(bank, 4);
      let x = Math.random() * options.reduce((a, [, c]) => a + c, 0);
      reaction = (options.find(([, c]) => (x -= c) < 0) || options[0])[0];
      const total = [...bank.values()].reduce((a, c) => a + c, 0);
      why.reaction_from = `how they usually react to ${why.read_as} (${timesWord(total)} in your chat)`;
    } else {
      reaction = choice(tpl.react.map((t) => fill(t, topic, time, bare)).filter(Boolean));
      composed = true;
      why.reaction_from = `a typical ${FAMILY_NAMES[fam]} reaction to ${why.read_as}, rewritten in their style`;
    }

    let bubbles = [stylize(reaction, them, composed, intent)];
    const longWriter = oneTextWriter(them); // one fuller text, not several
    const follows = tpl.follow.map((t) => fill(t, topic, time, bare)).filter(Boolean);
    for (let i = follows.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [follows[i], follows[j]] = [follows[j], follows[i]]; }
    const relevant = (f) => (topic && f.includes(topic)) || f.includes(bare);
    follows.sort((a, b) => relevant(b) - relevant(a));
    for (const f of follows) {
      if (bubbles.length >= (longWriter ? ((them.avg_words || 0) >= 10 ? 3 : 2) : target)) break;
      const styled = stylize(f, them, true, intent);
      if (!bubbles.some((x) => x.toLowerCase() === styled.toLowerCase())) bubbles.push(styled);
    }
    if (longWriter && bubbles.length > 1) {
      const out = [];
      bubbles = bubbles.map((p, i) => (i < bubbles.length - 1 ? p.replace(/\s*\p{Extended_Pictographic}+\s*$/u, "") || p : p));
      for (let p of bubbles) {
        p = p.trim();
        const last = out[out.length - 1];
        if (last && !/[.!?]$/.test(last) && !EMOJI.test([...last].pop())) out[out.length - 1] += ".";
        out.push(out.length && /[.!?]$/.test(out[out.length - 1]) ? p[0].toUpperCase() + p.slice(1) : p);
      }
      bubbles = [out.join(" ")];
    }
    why.strategy = "composed";
    if (bubbles.some((x) => x.includes(bare))) why.time = `"${time}" (${timeSrc})`;
    return { replies: bubbles, why };
  }

  function explain(why) {
    if (!why) return "";
    const parts = [`read your text as ${why.read_as}` + (why.topic ? ` about "${why.topic}"` : "")];
    if (why.strategy === "reused") parts.push(`reused ${why.because}`);
    else if (why.strategy === "reference") parts.push(`used ${why.because}`);
    else {
      parts.push(`opened with ${why.reaction_from}`);
      if (why.time) parts.push(`used ${why.time}`);
    }
    return parts.join("; ");
  }

  function offlineOpener(b) {
    const starters = (b.style.starters && b.style.starters.length) ? b.style.starters : b.examples.slice(0, 20).map((e) => e.reply);
    return {
      replies: (choice(starters) || ["hey"]).map((t) => stylize(t, b.style.them || {})),
      explanation: "how they opened a conversation after a long silence in your chat",
    };
  }

  // ------------------------------------------------------------------ text features (mirrors tools/features.py)
  const LENGTH_BINS = [["0", 0, 0], ["1", 1, 1], ["2-3", 2, 3], ["4-6", 4, 6], ["7-12", 7, 12], ["13-25", 13, 25], ["26+", 26, Infinity]];
  const POSITIVE = new Set(D.sentiment.positive), NEGATIVE = new Set(D.sentiment.negative);
  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const pct1 = (part, whole) => (whole ? round((100 * part) / whole, 1) : 0);
  const quantile = (v, q) => { if (!v.length) return null; const s = [...v].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(q * (s.length - 1) + 0.5))]; };
  const tsOf = (m) => { const t = Date.parse(m.timestamp); return isNaN(t) ? null : new Date(t); };
  const FEATURE_SILENCE = 3 * 3600 * 1000;
  const gapExceeds = (a, b) => { const x = tsOf(a), y = tsOf(b); return !!(x && y && y - x > FEATURE_SILENCE); };

  function turnsOf(messages) {
    const turns = [];
    for (const m of messages) {
      const last = turns[turns.length - 1];
      if (last && last.sender === m.sender && !gapExceeds(last.messages[last.messages.length - 1], m)) last.messages.push(m);
      else turns.push({ sender: m.sender, messages: [m] });
    }
    return turns;
  }

  function mattr(words, win = 50) {
    if (words.length < win) return words.length ? round(new Set(words).size / words.length, 3) : null;
    let sum = 0;
    for (let i = 0; i + win <= words.length; i++) sum += new Set(words.slice(i, i + win)).size / win;
    return round(sum / (words.length - win + 1), 3);
  }

  function sideFeatures(msgs, turns, sender, fam) {
    const texts = msgs.map((m) => m.text.trim()).filter(Boolean);
    const n = texts.length;
    if (!n) return { messages: 0 };
    const wl = texts.map((t) => t.match(WORD) || []);
    const words = wl.flat().map((w) => w.toLowerCase());
    const lens = wl.map((w) => w.length);
    const lettered = texts.filter((t) => /[A-Za-z]/.test(t));
    const ends = { ".": 0, "!": 0, "?": 0, "...": 0, emoji: 0, none: 0 };
    for (const t of texts) {
      const last = [...t].pop();
      if (t.endsWith("..") || t.endsWith("…")) ends["..."]++;
      else if (".!?".includes(last)) ends[last]++;
      else if (EMOJI.test(last)) ends.emoji++;
      else ends.none++;
    }
    const emojis = texts.flatMap((t) => t.match(EMOJI_G) || []);
    const emojiCounts = countOf(emojis);
    const content = countOf(words.filter((w) => !STOP.has(w) && !SLANG.has(w) && w.length > 2));
    const bi = new Map();
    for (const ws of wl) {
      const low = ws.map((w) => w.toLowerCase());
      for (let j = 0; j < low.length - 1; j++) if (!(STOP.has(low[j]) && STOP.has(low[j + 1]))) bump(bi, `${low[j]} ${low[j + 1]}`);
    }
    const laughs = new Map();
    for (const t of texts) { const l = t.toLowerCase(); const hit = LAUGHS.find((x) => l.includes(x)); if (hit) bump(laughs, hit); }
    const sizes = turns.filter((t) => t.sender === sender).map((t) => t.messages.length);
    const hours = Array(24).fill(0), weekdays = Array(7).fill(0);
    for (const m of msgs) { const d = tsOf(m); if (d) { hours[d.getHours()]++; weekdays[(d.getDay() + 6) % 7]++; } }
    const lowercase = pct1(lettered.filter((t) => t === t.toLowerCase()).length, lettered.length);
    const capital = pct1(lettered.filter((t) => /^[A-Z]/.test(t)).length, lettered.length);
    const slang = pct1(words.filter((w) => SLANG.has(w)).length, words.length);
    const punctEnd = 100 - pct1(ends.none + ends.emoji, n);
    const avgWordLen = words.length ? round(mean(words.map((w) => w.length)), 2) : 0;
    const formality = Math.round(mean([capital, punctEnd, 100 - lowercase, Math.max(0, 100 - slang * 5), Math.min(100, Math.max(0, (avgWordLen - 3) * 50))]));
    const kinds = top(countOf(texts.map((t) => detectIntent(t, fam))), 10);
    const hasWord = (set) => wl.filter((ws) => ws.some((w) => set.has(w.toLowerCase()))).length;
    return {
      messages: n, words: words.length, chars: texts.reduce((a, t) => a + [...t].length, 0), // characters, not UTF-16 units
      avg_words: round(mean(lens)), median_words: median(lens), p90_words: quantile(lens, 0.9),
      avg_chars: round(mean(texts.map((t) => [...t].length)), 1),
      length_bins: Object.fromEntries(LENGTH_BINS.map(([k, lo, hi]) => [k, pct1(lens.filter((x) => x >= lo && x <= hi).length, n)])),
      texts_per_turn: sizes.length ? round(mean(sizes)) : 1, max_burst: sizes.length ? Math.max(...sizes) : 1,
      burst_share: pct1(sizes.filter((s) => s >= 2).length, sizes.length),
      lowercase_pct: lowercase, capital_start_pct: capital,
      caps_word_pct: pct1(wl.flat().filter((w) => w.length > 2 && w === w.toUpperCase() && /[A-Z]/.test(w)).length, words.length),
      endings_pct: Object.fromEntries(Object.entries(ends).map(([k, v]) => [k, pct1(v, n)])),
      question_pct: pct1(texts.filter((t) => t.includes("?")).length, n), exclaim_pct: pct1(texts.filter((t) => t.includes("!")).length, n),
      multi_exclaim_pct: pct1(texts.filter((t) => t.includes("!!")).length, n), formality,
      emoji_pct: pct1(texts.filter((t) => EMOJI.test(t)).length, n),
      emoji_per_100_words: words.length ? round((100 * emojis.length) / words.length, 1) : 0,
      distinct_emojis: emojiCounts.size, top_emojis: top(emojiCounts, 6).map(([e]) => e),
      vocab_size: new Set(words).size, mattr: mattr(words), avg_word_len: avgWordLen, slang_pct: slang,
      top_words: top(content, 12).map(([w]) => w), top_phrases: top(bi, 30).filter(([, c]) => c > 1).slice(0, 8).map(([p]) => p),
      laugh_style: laughs.size ? top(laughs, 1)[0][0] : null, laugh_pct: pct1([...laughs.values()].reduce((a, b) => a + b, 0), n),
      positive_pct: pct1(hasWord(POSITIVE), n), negative_pct: pct1(hasWord(NEGATIVE), n),
      hours, weekdays, kinds: Object.fromEntries(kinds),
    };
  }

  function replyDelays(turns, responder) {
    const out = [];
    for (let i = 1; i < turns.length; i++) {
      const prev = turns[i - 1], cur = turns[i];
      if (cur.sender !== responder || prev.sender === responder) continue;
      const a = tsOf(prev.messages[prev.messages.length - 1]), b = tsOf(cur.messages[0]);
      if (a && b && !gapExceeds(prev.messages[prev.messages.length - 1], cur.messages[0]) && b >= a) out.push((b - a) / 1000);
    }
    return out;
  }

  const localDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; // taste-skill-ignore: an ISO date
  function computeFeatures(messages, target, me, relationship) {
    const fam = family(relationship);
    const them = messages.filter((m) => m.sender === target), you = messages.filter((m) => (me ? m.sender === me : m.sender !== target));
    const turns = turnsOf(messages);
    const starts = turns.filter((t, i) => i === 0 || gapExceeds(turns[i - 1].messages[turns[i - 1].messages.length - 1], t.messages[0])).map((t) => t.sender);
    const stamps = messages.map(tsOf).filter(Boolean).sort((a, b) => a - b);
    const days = new Set(stamps.map(localDay));
    const tq = (v, q) => { const x = quantile(v, q); return x == null ? null : Math.round(x); };
    const td = replyDelays(turns, target), yd = replyDelays(turns, me);
    const span = stamps.length ? Math.round((new Date(localDay(stamps[stamps.length - 1])) - new Date(localDay(stamps[0]))) / 86400000) + 1 : null;
    return {
      format: "textback-features/1", target, me, relationship,
      shared: {
        messages: messages.length,
        first: stamps.length ? localDay(stamps[0]) : null, last: stamps.length ? localDay(stamps[stamps.length - 1]) : null,
        days_span: span, active_days: stamps.length ? days.size : null, conversations: starts.length,
        them_share_pct: pct1(them.length, them.length + you.length),
        they_start_pct: starts.length >= 3 ? pct1(starts.filter((s) => s === target).length, starts.length) : null,
        them_reply_median_s: tq(td, 0.5), them_reply_p90_s: tq(td, 0.9), you_reply_median_s: tq(yd, 0.5), you_reply_p90_s: tq(yd, 0.9),
        has_timestamps: stamps.length > 0,
      },
      them: sideFeatures(them, turns, target, fam),
      you: sideFeatures(you, turns, me, fam),
    };
  }

  function flatRow(name, f) {
    const row = { name, relationship: f.relationship, ...f.shared };
    for (const side of ["them", "you"]) {
      for (const [k, v] of Object.entries(f[side])) {
        if (Array.isArray(v)) row[`${side}_${k}`] = k === "hours" || k === "weekdays" ? v.join(";") : v.join(" ");
        else if (v && typeof v === "object") for (const [kk, vv] of Object.entries(v)) row[`${side}_${k}_${kk}`] = vv;
        else row[`${side}_${k}`] = v;
      }
    }
    return row;
  }

  // ------------------------------------------------------------------ screenshots (mirrors tools/screenshot_parser.py)
  // Your bubbles sit on the right, theirs on the left: read the text, then sort lines by position.
  const SHOT = D.screenshot;
  const SHOT_JUNK = SHOT.junk.map((p) => new RegExp(`^(?:${p})$`, "i"));
  const KEEP_SHORT = new Set(SHOT.keep_short);
  const STRIP_PREFIX = new RegExp(SHOT.strip_prefix); // profile-picture circles read as a stray "O"
  const IMAGE_RE = /\.(png|jpe?g|webp|gif|bmp|heic|heif)$/i;
  const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";

  // Fix the usual OCR slips: "|" read for "I", emoji read as stray symbols.
  const cleanOcr = (t) => t.replace(/(^|\s)\|(?=\s|$|')/g, "$1I").replace(/\s*[®©™¢]+\s*$/, "").trim();

  function isJunk(text) {
    const t = text.trim();
    if (!t) return true;
    if (KEEP_SHORT.has(t.toLowerCase())) return false;
    return SHOT_JUNK.some((rx) => rx.test(t));
  }

  function bubblesFromPage(rawLines) {
    const lines = rawLines.map((l) => ({ ...l, text: l.text.trim().replace(STRIP_PREFIX, "") }))
      .filter((l) => SHOT.top <= l.y0 && l.y1 <= SHOT.bottom && !isJunk(l.text))
      .sort((a, b) => (Math.round(a.y0 * 1000) - Math.round(b.y0 * 1000)) || (a.x0 - b.x0));
    if (!lines.length) return [];
    const heights = lines.map((l) => l.y1 - l.y0).sort((a, b) => a - b);
    const lineH = heights[heights.length >> 1] || 0.02;
    const groups = [];
    for (const l of lines) { // stacked, left-aligned lines are one bubble
      const g = groups[groups.length - 1];
      if (g && l.y0 - g.y1 < 0.45 * lineH && Math.abs(l.x0 - g.x0) < 0.03) {
        g.texts.push(l.text.trim()); g.x1 = Math.max(g.x1, l.x1); g.y1 = l.y1;
      } else groups.push({ texts: [l.text.trim()], x0: l.x0, x1: l.x1, y0: l.y0, y1: l.y1 });
    }
    const leftEdge = Math.min(...groups.map((g) => g.x0));
    const rightEdge = Math.max(...groups.map((g) => g.x1));
    const tol = SHOT.align_tolerance;
    const out = [];
    for (const g of groups) {
      const onLeft = g.x0 - leftEdge < tol, onRight = rightEdge - g.x1 < tol;
      let side;
      if (onLeft && !onRight) side = "left";
      else if (onRight && !onLeft) side = "right";
      else if (onLeft && onRight) side = g.x0 < 1 - g.x1 ? "left" : "right"; // spans the screen
      else continue; // centred: date dividers
      const text = cleanOcr(g.texts.join(" "));
      if (text) out.push({ side, text });
    }
    return out;
  }

  const normText = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "");
  function similarity(x, y) { // 1 - edit distance / length, like Python's SequenceMatcher ratio
    const prev = Array.from({ length: y.length + 1 }, (_, j) => j);
    for (let i = 1; i <= x.length; i++) {
      let diag = prev[0]; prev[0] = i;
      for (let j = 1; j <= y.length; j++) {
        const tmp = prev[j];
        prev[j] = Math.min(prev[j] + 1, prev[j - 1] + 1, diag + (x[i - 1] === y[j - 1] ? 0 : 1));
        diag = tmp;
      }
    }
    return 1 - prev[y.length] / Math.max(x.length, y.length, 1);
  }
  // Same sender and nearly the same text: OCR can read one screenshot as "7?" and the next as "77?".
  function sameBubble(a, b) {
    if (a.sender !== b.sender) return false;
    const x = normText(a.text), y = normText(b.text);
    if (x === y) return true;
    if (Math.min(x.length, y.length) < 2) return !!(x && y) && Math.abs(x.length - y.length) <= 1 && (x.includes(y) || y.includes(x)); // "7" vs "77"
    return similarity(x, y) >= 0.6;
  }
  function stitch(existing, add) { // drop bubbles repeated where you scrolled, or screenshots you already added
    if (!add.length) return existing;
    for (let start = Math.max(0, existing.length - 400); start <= existing.length - add.length; start++) {
      if (add.every((m, i) => sameBubble(existing[start + i], m))) return existing;
    }
    for (let k = Math.min(existing.length, add.length); k > 0; k--) {
      if (existing.slice(-k).every((m, i) => sameBubble(m, add[i]))) return existing.concat(add.slice(k));
    }
    return existing.concat(add);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("couldn't load the screenshot reader (are you offline?)"));
      document.head.append(s);
    });
  }

  function brightTextMask(bmp) {
    const canvas = document.createElement("canvas");
    canvas.width = bmp.width; canvas.height = bmp.height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0);
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height), px = img.data;
    for (let i = 0; i < px.length; i += 4) {
      const lum = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
      px[i] = px[i + 1] = px[i + 2] = lum > 200 ? 0 : 255;
    }
    ctx.putImageData(img, 0, 0);
    return canvas;
  }

  let ocrWorker = null;
  async function readScreenshots(files, progress) {
    progress("Loading the screenshot reader…");
    if (!window.Tesseract) await loadScript(TESSERACT_URL);
    if (!ocrWorker) {
      ocrWorker = await window.Tesseract.createWorker("eng");
      await ocrWorker.setParameters({ tessedit_pageseg_mode: "11" }); // sparse text: scattered short bubbles
    }
    const sorted = [...files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    let messages = [];
    for (const [i, f] of sorted.entries()) {
      progress(`Reading screenshot ${i + 1} of ${sorted.length}…`);
      let bmp;
      try { bmp = await createImageBitmap(f); } catch { throw new Error(`${f.name}: this browser can't open that image (convert HEIC to PNG or JPG)`); }
      const W = bmp.width, H = bmp.height;
      // Pass 1 reads dark text on light bubbles. Pass 2 reads bright text (white on blue/purple
      // bubbles, dark mode) after turning bright pixels black and everything else white.
      const toLines = (data) => (data.lines || []).filter((l) => l.text.trim())
        .map((l) => ({ text: l.text.trim(), conf: l.confidence, x0: l.bbox.x0 / W, x1: l.bbox.x1 / W, y0: l.bbox.y0 / H, y1: l.bbox.y1 / H }));
      const pass1 = toLines((await ocrWorker.recognize(f)).data);
      const pass2 = toLines((await ocrWorker.recognize(brightTextMask(bmp))).data);
      if (bmp.close) bmp.close();
      const overlaps = (a, b) => {
        const w = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0), h = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0);
        return w > 0 && h > 0 && w * h > 0.5 * Math.min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0));
      };
      // Where both passes read the same spot, keep the more confident reading.
      const lines = [];
      for (const l of pass1.concat(pass2).sort((a, b) => b.conf - a.conf)) {
        if (l.conf >= 45 && !lines.some((m) => overlaps(l, m))) lines.push(l);
      }
      const bubbles = bubblesFromPage(lines).map((b) => ({ sender: b.side === "left" ? "Them" : "Me", text: b.text, timestamp: null }));
      messages = stitch(messages, bubbles);
    }
    progress("");
    return messages;
  }

  // ------------------------------------------------------------------ storage
  // For a short while the project was called Textprint: move what this browser saved under that name back, once.
  try {
    for (const k of ["profiles.v1", "theme", "showWhy"]) {
      const old = localStorage.getItem(`textprint.${k}`);
      if (old !== null && localStorage.getItem(`textback.${k}`) === null) localStorage.setItem(`textback.${k}`, old);
      if (old !== null) localStorage.removeItem(`textprint.${k}`);
    }
  } catch { /* storage unavailable: nothing to move */ }
  const STORE_KEY = "textback.profiles.v1";
  const loadLocal = () => { try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; } };
  const saveLocal = (all) => { try { localStorage.setItem(STORE_KEY, JSON.stringify(all)); } catch { /* private mode or full: keep in memory */ } };
  const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "contact";

  // ------------------------------------------------------------------ server API
  const api = {
    online: false,
    engine: "offline",
    async probe() {
      if (location.protocol === "file:") return false;
      try {
        const r = await fetch("/api/status", { cache: "no-store" });
        if (!r.ok) return false;
        const s = await r.json();
        this.online = true; this.engine = s.engine;
        return true;
      } catch { return false; }
    },
    async get(path) { const r = await fetch(path); if (!r.ok) throw new Error(r.statusText); return r.json(); },
    async post(path, body) {
      const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
      return r.json();
    },
  };

  // ------------------------------------------------------------------ app state + UI
  const $ = (id) => document.getElementById(id);
  const state = {
    local: loadLocal(),      // slug -> bundle (browser profiles)
    server: [],              // [{slug, name, relationship, version}]
    current: null,           // {source: "local"|"server", bundle}
    history: [],             // [{role: "me"|"them", text}]
    turns: [],               // [{context, replies, el: [li...]}]
    pending: null,           // parsed messages waiting for the setup form
    view: "contacts",        // the list column: "contacts" or "new"
    fast: false,             // the demo skips the typing delay
    practice: false,         // practice mode: work on a copy, save nothing
  };

  // People get a stable hue for their avatar tint (identity, not data).
  function personHue(name) {
    let h = 0;
    for (const ch of String(name || "")) h = (h * 31 + ch.codePointAt(0)) % 360;
    return h;
  }
  function paintAvatar(el, name) {
    el.textContent = name ? [...name][0].toUpperCase() : "?";
    el.classList.toggle("blank", !name);
    if (name) el.style.setProperty("--h", personHue(name)); else el.style.removeProperty("--h");
  }

  // The one habit worth leading with: how they answer you, or who reaches out.
  function finding(style) {
    const rules = styleRules(style);
    const pick = rules.find((r) => /texts first|briefly|greater length/i.test(r)) || rules.find((r) => /short|longer|bursts/i.test(r));
    return pick ? pick.replace(/\.$/, "").replace(/:.*$/, "") : "";
  }

  function renderContacts() {
    const list = $("contactList");
    list.innerHTML = "";
    const q = ($("contactSearch").value || "").trim().toLowerCase();
    const all = [
      ...state.server.map((p) => ({ ...p, source: "server" })),
      ...Object.values(state.local).map((b) => ({
        slug: b.slug, name: b.meta.name, relationship: b.meta.relationship, version: b.meta.version,
        replies: b.examples.length, source: "local",
      })),
    ];
    const items = all.filter((p) => !q || `${p.name} ${p.relationship}`.toLowerCase().includes(q));
    $("contactCount").textContent = all.length;
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = all.length ? `No contacts match "${q}".` : "No contacts yet. Add one from a chat or screenshots.";
      list.append(li);
      return;
    }
    for (const p of items) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "row";
      const active = state.current && state.current.source === p.source && state.current.bundle.slug === p.slug;
      btn.setAttribute("aria-current", String(!!active));
      btn.innerHTML = `<span class="avatar"></span><span class="row-main"><span class="row-name"></span><span class="row-sub"></span></span><span class="row-meta num"></span>`;
      paintAvatar(btn.querySelector(".avatar"), p.name);
      btn.querySelector(".row-name").textContent = p.name;
      btn.querySelector(".row-sub").textContent = p.replies != null
        ? `${p.relationship} · ${p.replies} replies learned` : `${p.relationship} · saved on disk`;
      btn.querySelector(".row-meta").textContent = `v${p.version}`;
      btn.addEventListener("click", () => openContact(p.source, p.slug));
      li.append(btn);
      list.append(li);
    }
  }

  const pct = (v) => (v == null ? null : Math.round(v * 100));
  function renderStyle() {
    const b = state.current && state.current.bundle;
    const grid = $("statsGrid"), rules = $("rulesList"), counts = $("learnCounts"), cmp = $("compare");
    grid.innerHTML = ""; rules.innerHTML = ""; counts.innerHTML = ""; cmp.innerHTML = "";
    const s = (b && b.style.them) || {}, you = (b && b.style.you) || {};

    // KPIs: label over value, a grey dash when there's nothing yet
    const kpi = (label, value, unit = "") => {
      const d = document.createElement("div");
      d.className = "kpi";
      d.innerHTML = "<span></span><b></b>";
      d.querySelector("span").textContent = label;
      const v = d.querySelector("b");
      if (value == null) { v.textContent = "–"; v.classList.add("none"); }
      else { v.textContent = value; if (unit) { const u = document.createElement("small"); u.textContent = unit; v.append(u); } }
      grid.append(d);
    };
    const delay = s.median_reply_seconds;
    kpi("Words per text", s.avg_words != null ? s.avg_words.toFixed(1) : null);
    kpi("Texts per turn", s.msgs_per_turn != null ? s.msgs_per_turn.toFixed(1) : null);
    kpi("With emoji", pct(s.emoji_rate), "%");
    kpi("Reply delay", delay == null ? null : delay < 60 ? "<1" : Math.round(delay / 60), delay == null ? "" : "min");

    // Them vs you: each habit on one scale, their bar in the hue, yours in grey
    const initThem = s.initiation_rate;
    const rows = [
      ["Words per text", s.avg_words, you.avg_words, (v) => v.toFixed(1), null],
      ["Lowercase texts", pct(s.lowercase_rate), pct(you.lowercase_rate), (v) => `${v}%`, 100],
      ["Texts with emoji", pct(s.emoji_rate), pct(you.emoji_rate), (v) => `${v}%`, 100],
      ["Asks questions", pct(s.question_rate), pct(you.question_rate), (v) => `${v}%`, 100],
      ["Texts first", initThem == null ? null : pct(initThem), initThem == null ? null : 100 - pct(initThem), (v) => `${v}%`, 100],
    ].filter(([, a, c]) => a != null && c != null);
    if (!b || !rows.length) {
      const e = document.createElement("p");
      e.className = "empty-box";
      e.textContent = b ? "Not enough messages from both of you to compare yet." : "Open a contact to compare their habits with yours.";
      cmp.append(e);
    }
    for (const [label, them, mine, fmt, max] of rows) {
      const scale = max || Math.max(them, mine, 1) * 1.15;
      const row = document.createElement("div");
      row.className = "cmp";
      const diff = them - mine;
      const note = Math.abs(diff) < (max ? 8 : 0.6) ? "about the same" : diff > 0 ? "they do it more" : "you do it more";
      row.innerHTML = `<div class="cmp-label"><span></span><span></span></div>
        <div class="cmp-bars">
          <div class="cmp-track them"><i></i></div><span class="cmp-val them"></span>
          <div class="cmp-track you"><i></i></div><span class="cmp-val you"></span>
        </div>`;
      const [l1, l2] = row.querySelectorAll(".cmp-label span");
      l1.textContent = label; l2.textContent = note;
      row.querySelector(".cmp-track.them i").style.width = `${Math.min(100, (them / scale) * 100)}%`;
      row.querySelector(".cmp-track.you i").style.width = `${Math.min(100, (mine / scale) * 100)}%`;
      row.querySelector(".cmp-val.them").textContent = fmt(them);
      row.querySelector(".cmp-val.you").textContent = fmt(mine);
      row.setAttribute("aria-label", `${label}: them ${fmt(them)}, you ${fmt(mine)}`);
      cmp.append(row);
    }

    if (!b) { rules.innerHTML = '<li class="muted">Habits appear once you open a contact.</li>'; }
    else for (const r of styleRules(b.style)) { const li = document.createElement("li"); li.textContent = r; rules.append(li); }

    const kv = (label, value) => {
      const d = document.createElement("div");
      d.innerHTML = "<dt></dt><dd class='num'></dd>";
      d.querySelector("dt").textContent = label;
      d.querySelector("dd").textContent = value;
      counts.append(d);
    };
    kv("Real replies learned", b ? b.examples.length : "–");
    kv("Your corrections", b ? (b.corrections || []).length : "–");
    kv("Replies you approved", b ? (b.approved || []).length : "–");
    kv("Profile version", b ? `v${b.meta.version || 1}` : "–");
  }

  function renderHeader() {
    const b = state.current && state.current.bundle;
    paintAvatar($("avatar"), b ? b.meta.name : "");
    $("whoName").textContent = b ? b.meta.name : "No conversation open";
    const lead = b ? finding(b.style) : "";
    $("whoStatus").textContent = b
      ? [b.meta.relationship, lead || `learned from ${b.style.message_count} messages`].join(" · ")
      : "Pick a contact, or add one from a chat or screenshots.";
    for (const id of ["msgInput", "sendBtn", "nudgeBtn", "exportBtn"]) $(id).disabled = !b;
    $("deleteBtn").disabled = !b || state.current.source !== "local";
    $("addMoreBtn").disabled = !b || state.current.source !== "local";
    $("featuresBtn").disabled = !b;
    const badge = $("engineBadge");
    const live = b && state.current.source === "server";
    badge.textContent = live ? `Replies from the local server (${api.engine})` : (api.online ? "Local server connected" : "Replies made in this browser, offline");
    badge.classList.toggle("live", !!(live || api.online));
  }

  function clearThread(hint) {
    state.history = []; state.turns = [];
    const t = $("thread");
    t.innerHTML = "";
    if (!hint) return;
    const li = document.createElement("li");
    li.className = "hint";
    if (typeof hint === "string") li.textContent = hint;
    else {
      const p = document.createElement("p");
      p.innerHTML = "<strong></strong><span></span>";
      p.querySelector("strong").textContent = hint.title;
      p.querySelector("span").textContent = hint.text;
      li.append(p);
      if (hint.action) {
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "btn primary"; btn.textContent = hint.action.label;
        btn.addEventListener("click", hint.action.run);
        li.append(btn);
      }
    }
    t.append(li);
  }

  const startHint = () => ({
    title: "Text someone who isn't here",
    text: "Add your boss, a friend, a talking stage or an ex from a chat export or screenshots. TextBack learns how they text and answers like them.",
    action: { label: "Try a sample person", run: () => { setView("new"); setPane("list"); const first = document.querySelector("#sampleList .row"); if (first) first.focus(); } },
  });

  // ----- the text features view
  const fmt = (v, unit = "") => (v == null ? "–" : `${v}${unit}`);
  const dur = (s) => (s == null ? "–" : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  const KIND_NAME = (k) => (k === "statement" ? "other" : (LABELS[k] || k).replace(/\s*\(.*\)$/, ""));
  let lastFeatures = null;

  async function openFeatures() {
    const { source, bundle } = state.current;
    const name = bundle.meta.name;
    let f;
    try {
      if (source === "server") f = await api.get(`/api/features/${encodeURIComponent(bundle.slug)}`);
      else if (bundle.messages && bundle.messages.length) f = computeFeatures(bundle.messages, bundle.meta.target, bundle.meta.me, bundle.meta.relationship);
      else { alert("This contact was imported without its chat, so its features can't be measured here."); return; }
    } catch (e) { alert("Couldn't measure the features: " + e.message); return; }
    lastFeatures = { name, f };
    renderFeatures(name, f);
    $("featuresDialog").showModal();
  }

  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function renderFeatures(name, f) {
    const t = f.them, y = f.you, s = f.shared, you = f.me || "You";
    $("featuresTitle").textContent = `Text features: ${name}`;
    $("featuresSummary").textContent = s.has_timestamps
      ? `${s.messages} messages from ${s.first} to ${s.last}: ${s.days_span} days, ${s.active_days} with texts, ${s.conversations} conversations`
      : `${s.messages} messages. This export has no timestamps, so timing features are left out.`;
    const body = $("featuresBody");
    body.innerHTML = "";
    const left = el("div", "fx-col"), right = el("div", "fx-col");
    body.append(left, right);
    const block = (col, title, note) => { const b = el("section", "fx-block"); b.append(el("h3", null, title)); if (note) b.append(el("p", "fx-note", note)); col.append(b); return b; };

    // Them vs you, every feature
    const tb = block(left, `${name} vs ${you}`);
    const table = el("table", "fx-table");
    const head = el("thead"); const hr = el("tr");
    hr.append(el("th", null, "Feature"), el("th", "them", name), el("th", null, you)); head.append(hr);
    const tbody = el("tbody");
    const group = (label) => { const r = el("tr", "group"); const c = el("td", null, label); c.colSpan = 3; r.append(c); tbody.append(r); };
    const row = (label, a, b) => { const r = el("tr"); r.append(el("td", null, label), el("td", "them", a), el("td", "you", b)); tbody.append(r); };
    const both = (label, key, unit = "") => row(label, fmt(t[key], unit), fmt(y[key], unit));
    group("Length");
    both("Messages", "messages"); row("Share of the chat", fmt(s.them_share_pct, "%"), fmt(round(100 - s.them_share_pct, 1), "%"));
    both("Words per text", "avg_words"); both("Median words", "median_words"); both("90th percentile", "p90_words"); both("Characters per text", "avg_chars");
    group("Rhythm");
    both("Texts per turn", "texts_per_turn"); both("Longest burst", "max_burst"); both("Turns with 2+ texts", "burst_share", "%");
    if (s.has_timestamps) {
      row("Texts first", fmt(s.they_start_pct, "%"), s.they_start_pct == null ? "–" : `${round(100 - s.they_start_pct, 1)}%`);
      row("Reply delay, median", dur(s.them_reply_median_s), dur(s.you_reply_median_s));
      row("Reply delay, 90th pct", dur(s.them_reply_p90_s), dur(s.you_reply_p90_s));
    }
    group("Style");
    both("All-lowercase texts", "lowercase_pct", "%"); both("Capitalised starts", "capital_start_pct", "%"); both("ALL-CAPS words", "caps_word_pct", "%");
    row("End with a period", fmt(t.endings_pct["."], "%"), fmt(y.endings_pct && y.endings_pct["."], "%"));
    row("End with !", fmt(t.endings_pct["!"], "%"), fmt(y.endings_pct && y.endings_pct["!"], "%"));
    row("End with ?", fmt(t.endings_pct["?"], "%"), fmt(y.endings_pct && y.endings_pct["?"], "%"));
    row("No ending punctuation", fmt(t.endings_pct.none, "%"), fmt(y.endings_pct && y.endings_pct.none, "%"));
    both("Formality, 0 to 100", "formality");
    group("Emoji and words");
    both("Texts with emoji", "emoji_pct", "%"); both("Emoji per 100 words", "emoji_per_100_words"); both("Distinct emoji", "distinct_emojis");
    both("Unique words", "vocab_size"); both("Richness (MATTR), 0 to 1", "mattr"); both("Average word length", "avg_word_len");
    both("Slang, % of words", "slang_pct", "%"); both("Texts with a laugh", "laugh_pct", "%");
    group("Tone, from a word list");
    both("Texts with a positive word", "positive_pct", "%"); both("Texts with a negative word", "negative_pct", "%");
    table.append(head, tbody); tb.append(table);

    // How long their texts are
    const lb = block(right, "How long the texts are", "Share of texts by number of words; \u201cemoji\u201d is texts with no words at all.");
    const legend = el("span", "legend"); legend.innerHTML = '<i class="sw them"></i><span></span> <i class="sw you"></i><span></span>';
    legend.querySelectorAll("span")[0].textContent = name; legend.querySelectorAll("span")[1].textContent = you;
    lb.querySelector("h3").after(legend);
    const bars = el("div", "fx-bars");
    const maxBin = Math.max(1, ...Object.values(t.length_bins), ...Object.values(y.length_bins || {}));
    for (const k of Object.keys(t.length_bins)) {
      const bin = el("div", "fx-bin"); const pair = el("div", "pair");
      const a = el("i", "them"); a.style.height = `${(t.length_bins[k] / maxBin) * 100}%`; a.title = `${name}: ${t.length_bins[k]}%`;
      const b = el("i", "you"); b.style.height = `${((y.length_bins || {})[k] || 0) / maxBin * 100}%`; b.title = `${you}: ${(y.length_bins || {})[k] || 0}%`;
      pair.append(a, b); bin.append(pair, el("span", null, k === "0" ? "emoji" : k)); bars.append(bin);
    }
    lb.append(bars);

    // When they text
    if (s.has_timestamps) {
      const hb = block(right, `When ${name} texts`, "Messages by hour of the day, and by weekday.");
      const hours = el("div", "fx-hours"); const maxH = Math.max(1, ...t.hours);
      t.hours.forEach((v, h) => { const i = el("i", v ? null : "zero"); i.style.height = v ? `${(v / maxH) * 100}%` : "1px"; i.title = `${String(h).padStart(2, "0")}:00 · ${v} messages`; hours.append(i); }); // taste-skill-ignore: a clock time
      const axis = el("div", "fx-axis"); ["0:00", "6:00", "12:00", "18:00", "23:00"].forEach((x) => axis.append(el("span", null, x)));
      const week = el("div", "fx-week");
      t.weekdays.forEach((v, i) => { const d = el("div"); d.append(el("b", null, String(v)), el("span", null, WEEKDAYS[i])); week.append(d); });
      hb.append(hours, axis, week);
    }

    // Favourites
    const fb = block(right, `${name}'s favourites`);
    const kv = el("dl", "fx-kv");
    for (const [k, v] of [["Emoji", t.top_emojis.join(" ")], ["Laugh", t.laugh_style], ["Words", t.top_words.join(", ")], ["Phrases", t.top_phrases.join(", ")]]) {
      kv.append(el("dt", null, k), el("dd", null, v || "–"));
    }
    fb.append(kv);

    // What kinds of texts they send
    const kb = block(right, `What ${name} sends`, "Their texts by kind, as the reply engine reads them.");
    const kinds = el("div", "fx-kinds"); const entries = Object.entries(t.kinds); const maxK = Math.max(1, ...entries.map(([, v]) => v));
    for (const [k, v] of entries.slice(0, 8)) {
      const r = el("div", "fx-kind"); const line = el("div"); line.append(el("span", null, KIND_NAME(k)), el("span", null, String(v)));
      const bar = el("i"); bar.style.width = `${(v / maxK) * 88}%`; r.append(line, bar); kinds.append(r);
    }
    kb.append(kinds);
  }

  function download(name, type, text) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function featuresCsv() {
    const { name, f } = lastFeatures; const row = flatRow(name, f); const cols = Object.keys(row);
    const cell = (v) => { const x = v == null ? "" : String(v); return /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x; };
    download(`${slugify(name)}-features.csv`, "text/csv", `${cols.map(cell).join(",")}\n${cols.map((c) => cell(row[c])).join(",")}\n`);
  }

  // ----- sample people (examples/samples, bundled into sample.js)
  function renderSamples() {
    const list = $("sampleList");
    list.innerHTML = "";
    for (const s of window.TEXTBACK_SAMPLES || []) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "row";
      btn.innerHTML = `<span class="avatar"></span><span class="row-main"><span class="row-name"></span><span class="row-sub"></span></span><span class="row-meta num"></span>`;
      paintAvatar(btn.querySelector(".avatar"), s.name);
      btn.querySelector(".row-name").textContent = s.name;
      btn.querySelector(".row-sub").textContent = `${s.relationship} · ${s.about.replace(/^[^,]+,\s*/, "")}`; // drop the repeated name
      btn.querySelector(".row-meta").textContent = `${s.messages} msgs`;
      btn.setAttribute("aria-label", `${s.name}, ${s.relationship}, ${s.messages} messages. ${s.about}`);
      btn.addEventListener("click", () => loadSample(s));
      li.append(btn);
      list.append(li);
    }
  }

  async function loadSample(s) {
    await handleFile(s.filename, s.text);
    $("targetSelect").value = s.target;
    $("meSelect").value = s.me;
    $("nameInput").value = s.name;
    $("relSelect").value = s.relationship;
    $("setupForm").scrollIntoView({ block: "nearest" });
    $("setupForm").querySelector("button[type=submit]").focus({ preventScroll: true });
  }

  // ----- layout: the list column's two views, and which region shows on a phone
  function setView(view) {
    $("viewContacts").hidden = view !== "contacts";
    $("viewNew").hidden = view !== "new";
    document.querySelectorAll(".rail-btn[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === view)));
    state.view = view;
    syncTabs();
  }
  function setPane(pane) {
    $("app").dataset.pane = pane;
    syncTabs();
  }
  function syncTabs() {
    const pane = $("app").dataset.pane;
    document.querySelectorAll(".tabbar button").forEach((b) => {
      const on = b.dataset.paneGo === pane && (!b.dataset.view || b.dataset.view === state.view);
      b.setAttribute("aria-current", String(on));
    });
  }

  const THEMES = ["auto", "light", "dark"];
  function applyTheme(theme) {
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    const label = { auto: "Theme: match system", light: "Theme: light", dark: "Theme: dark" }[theme];
    $("themeBtn").setAttribute("aria-label", label);
    $("themeBtn").title = label;
    try { localStorage.setItem("textback.theme", theme); } catch { /* per-viewer convenience only */ }
  }

  async function openContact(source, slug) {
    let bundle = source === "local" ? state.local[slug] : await api.get(`/api/profiles/${encodeURIComponent(slug)}`);
    state.current = { source, bundle };
    state.practice = false;
    renderUndo();
    renderContacts(); renderStyle(); renderHeader();
    clearThread({
      title: `Text ${bundle.meta.name} anything`,
      text: "They'll answer the way they really text. Tap any of their replies to fix it or mark it spot-on.",
    });
    setPane("chat");
    $("msgInput").focus();
  }

  function makeBubble(role, text, turn) {
    const li = document.createElement("li");
    li.className = `bubble ${role}`;
    li.textContent = text;
    if (role === "them" && turn) {
      li.title = "Tap to correct or approve";
      li.addEventListener("click", () => openFix(turn));
    }
    return li;
  }

  function bubble(role, text, turn) {
    const t = $("thread");
    const hint = t.querySelector(".hint"); if (hint) hint.remove();
    const li = makeBubble(role, text, turn);
    t.append(li);
    t.scrollTop = t.scrollHeight;
    return li;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  function typingDelay() {
    if (state.fast) return 0;
    const s = state.current.bundle.style.them || {};
    return Math.min(((s.median_reply_seconds || 2) / 30) * 1000, 2200) * (0.5 + Math.random() * 0.5) + 350;
  }

  async function deliver(context, replies, explanation = "") {
    const turn = { context, replies: [...replies], el: [], hist: [], explanation };
    state.turns.push(turn);
    $("typing").hidden = false;
    for (const r of replies) {
      await sleep(typingDelay());
      turn.el.push(bubble("them", r, turn));
      const entry = { role: "them", text: r };
      turn.hist.push(entry);
      state.history.push(entry);
    }
    $("typing").hidden = true;
    if (explanation) {
      const li = document.createElement("li");
      li.className = "why";
      li.textContent = "why: " + explanation;
      $("thread").append(li);
      turn.whyEl = li;
      $("thread").scrollTop = $("thread").scrollHeight;
    }
  }

  async function send(text) {
    const { source, bundle } = state.current;
    const history = [...state.history];
    bubble("me", text);
    state.history.push({ role: "me", text });
    let result;
    try {
      if (source === "server" && !state.practice) result = await api.post("/api/reply", { slug: bundle.slug, history, message: text });
      else {
        const r = offlineReply(bundle, text, history.filter((h) => h.role === "them").slice(-12).map((h) => h.text));
        result = { replies: r.replies, explanation: explain(r.why) };
      }
    } catch (e) {
      const r = offlineReply(bundle, text, []);
      result = { replies: r.replies, explanation: explain(r.why) + " (browser engine; server unreachable)" };
      console.warn("server reply failed, used browser engine", e);
    }
    await deliver(text, result.replies, result.explanation);
  }

  async function nudge() {
    const { source, bundle } = state.current;
    let result;
    try {
      result = source === "server" ? await api.post("/api/nudge", { slug: bundle.slug, history: state.history }) : offlineOpener(bundle);
    } catch { result = offlineOpener(bundle); }
    await deliver("", result.replies, result.explanation);
  }

  // ----- learning loop: corrections + approvals
  let fixing = null;
  function openFix(turn) {
    fixing = turn;
    $("fixWas").textContent = `They said: "${turn.replies.join(" / ")}"` + (turn.context ? ` in reply to "${turn.context}"` : "")
      + (turn.explanation ? `. Why: ${turn.explanation}.` : "");
    $("fixText").value = turn.replies.join("\n");
    $("fixDialog").showModal();
    $("fixText").select();
  }

  async function saveFeedback(kind) {
    const turn = fixing; fixing = null;
    if (!turn) return;
    const { source, bundle } = state.current;
    const saving = !state.practice;
    if (kind === "good") {
      const row = { context: turn.context, reply: turn.replies, at: new Date().toISOString() };
      if (saving && source === "local") snapshot(bundle, `approved reply to "${turn.context.slice(0, 40)}"`);
      if (saving && source === "server") await api.post("/api/approve", { slug: bundle.slug, ...row });
      (bundle.approved = bundle.approved || []).push(row);
    } else {
      const good = $("fixText").value.split("\n").map((s) => s.trim()).filter(Boolean);
      if (!good.length || good.join("\n") === turn.replies.join("\n")) return;
      const row = { context: turn.context, bad: turn.replies, good, at: new Date().toISOString() };
      if (saving && source === "local") snapshot(bundle, `correction to "${turn.context.slice(0, 40)}"`);
      if (saving && source === "server") await api.post("/api/correct", { slug: bundle.slug, ...row });
      (bundle.corrections = bundle.corrections || []).push(row);
      // Swap the bubbles and history entries in place so the conversation continues from the fix.
      const fresh = good.map((g) => { const li = makeBubble("them", g, turn); li.classList.add("fixed"); return li; });
      turn.el[0].before(...fresh);
      turn.el.forEach((li) => li.remove());
      turn.el = fresh;
      const entries = good.map((text) => ({ role: "them", text }));
      const at = state.history.indexOf(turn.hist[0]);
      if (at >= 0) state.history.splice(at, turn.hist.length, ...entries);
      turn.hist = entries;
      turn.replies = good;
      if (turn.whyEl) turn.whyEl.textContent = "why: you corrected this; similar texts will get this reply";
    }
    if (saving && source === "local") { state.local[bundle.slug] = bundle; saveLocal(state.local); }
    if (saving && source === "server") { // the server took a saved copy: pick up its undo list
      try { const fresh = await api.get(`/api/profiles/${encodeURIComponent(bundle.slug)}`); bundle.undo = fresh.undo; bundle.undo_count = fresh.undo_count; } catch { /* keep the old count */ }
    }
    renderStyle(); renderUndo();
  }

  // ----- undo, reset and practice
  // Browser contacts keep their own saved copies: small ones for feedback, full ones when they learn.
  const MAX_SNAPSHOTS = 10;
  const FEEDBACK_KEYS = ["corrections", "approved"];
  const FULL_KEYS = ["meta", "style", "examples", "messages", "corrections", "approved"];
  function snapshot(b, label, full = false) {
    const keys = full ? FULL_KEYS : FEEDBACK_KEYS;
    const data = Object.fromEntries(keys.filter((k) => b[k] !== undefined).map((k) => [k, structuredClone(b[k])]));
    b.snapshots = b.snapshots || [];
    b.snapshots.push({ label, at: new Date().toISOString(), data });
    if (b.snapshots.length > MAX_SNAPSHOTS) b.snapshots.splice(1, b.snapshots.length - MAX_SNAPSHOTS); // keep the first
  }
  const undoInfo = (b) => (state.current.source === "server"
    ? { count: b.undo_count || 0, last: (b.undo || [])[0] }
    : { count: (b.snapshots || []).length, last: (b.snapshots || []).slice(-1)[0] });

  function renderUndo() {
    const b = state.current && state.current.bundle;
    const practice = state.practice;
    const info = b ? undoInfo(b) : { count: 0 };
    const fb = b ? (b.corrections || []).length + (b.approved || []).length : 0;
    $("undoBtn").disabled = !b || practice || !info.count;
    $("resetBtn").disabled = !b || practice || !fb;
    $("startBtn").disabled = !b || practice || !info.count;
    $("practiceMode").disabled = !b;
    $("practiceMode").checked = practice;
    $("undoNote").textContent = !b ? "Open a contact to undo or reset what it learned."
      : practice ? "Practice mode is on: corrections shape this chat only, and are forgotten when you turn it off."
      : info.last ? `Last change: ${info.last.label}. ${info.count} change${info.count === 1 ? "" : "s"} can be undone.`
      : "Nothing to undo yet. Corrections, approvals and new chats you add can each be undone.";
  }

  function afterChange(bundle, message) {
    state.current.bundle = bundle;
    if (state.current.source === "local") { state.local[bundle.slug] = bundle; saveLocal(state.local); }
    renderContacts(); renderStyle(); renderHeader(); renderUndo();
    clearThread({ title: message, text: `Text ${bundle.meta.name} again to see the difference.` });
  }

  async function undoLast() {
    const { source, bundle } = state.current;
    if (source === "server") {
      const r = await api.post("/api/undo", { slug: bundle.slug });
      return afterChange(r.bundle, r.undone ? `Undid: ${r.undone}` : "Nothing to undo");
    }
    const snap = (bundle.snapshots || []).pop();
    if (!snap) return;
    Object.assign(bundle, structuredClone(snap.data));
    afterChange(bundle, `Undid: ${snap.label}`);
  }

  async function resetFeedback() {
    const { source, bundle } = state.current;
    const n = (bundle.corrections || []).length + (bundle.approved || []).length;
    if (!confirm(`Forget ${n} correction${n === 1 ? "" : "s"} and approval${n === 1 ? "" : "s"} for ${bundle.meta.name}? What it learned from your chats is kept, and you can undo this.`)) return;
    if (source === "server") {
      const r = await api.post("/api/reset", { slug: bundle.slug });
      return afterChange(r.bundle, `Cleared your corrections for ${bundle.meta.name}`);
    }
    snapshot(bundle, "reset corrections and approvals");
    bundle.corrections = []; bundle.approved = [];
    afterChange(bundle, `Cleared your corrections for ${bundle.meta.name}`);
  }

  async function resetToStart() {
    const { source, bundle } = state.current;
    if (!confirm(`Return ${bundle.meta.name} to how they were first added? Every later change (corrections, approvals, chats you added) is forgotten. This can't be undone.`)) return;
    if (source === "server") {
      const r = await api.post("/api/reset", { slug: bundle.slug, to_start: true });
      return afterChange(r.bundle, `${bundle.meta.name} is back to how they were first added`);
    }
    const first = (bundle.snapshots || [])[0];
    if (!first) return;
    Object.assign(bundle, structuredClone(first.data));
    bundle.snapshots = [];
    afterChange(bundle, `${bundle.meta.name} is back to how they were first added`);
  }

  async function setPractice(on) {
    const cur = state.current;
    if (!cur) return;
    state.practice = on;
    if (on) {
      cur.saved = cur.bundle;
      cur.bundle = structuredClone(cur.bundle); // corrections land on the copy only
      clearThread({ title: "Practice mode", text: `Fix ${cur.bundle.meta.name}'s replies as much as you like. Nothing is saved; turn it off to throw it all away.` });
    } else {
      cur.bundle = cur.saved || cur.bundle;
      delete cur.saved;
      clearThread({ title: "Practice is over", text: "Nothing from it was saved." });
    }
    renderStyle(); renderHeader(); renderUndo();
  }

  // ----- import
  async function handleFile(name, raw) {
    let parsed;
    try { parsed = parseFile(name, raw); } catch (e) { alert("Couldn't read that file: " + e.message); return; }
    if (parsed.bundle) {
      const b = parsed.bundle;
      state.local[b.slug] = { ...b, corrections: b.corrections || [], approved: b.approved || [] };
      saveLocal(state.local); renderContacts(); openContact("local", b.slug);
      return;
    }
    offerSetup(parsed.messages, name);
  }

  function offerSetup(msgs, source, fromShots = false) {
    if (!msgs.length) { alert("No messages found. See INSTALL.md for supported formats."); return; }
    const counts = new Map(); msgs.forEach((m) => bump(counts, m.sender));
    const people = top(counts, 50);
    if (fromShots) people.sort((a, b) => (b[0] === "Them") - (a[0] === "Them")); // left bubbles are "them"
    state.pending = { messages: msgs, source };
    const label = (p, c) => (fromShots ? `${p === "Them" ? "Left bubbles" : "Right bubbles"} (${c})` : `${p} (${c})`);
    const opts = (sel, skipFirst) => {
      sel.innerHTML = "";
      people.forEach(([p, c], i) => { const o = new Option(label(p, c), p); if (skipFirst ? i === 1 : i === 0) o.selected = true; sel.append(o); });
    };
    opts($("targetSelect"), false);
    opts($("meSelect"), true);
    $("nameInput").value = fromShots ? "" : people[0][0];
    $("reviewBox").hidden = !fromShots;
    if (fromShots) $("shotReview").value = msgs.map((m) => `${m.sender}: ${m.text}`).join("\n");
    state.pending.fromShots = fromShots;
    $("setupForm").hidden = false;
    if (fromShots) $("nameInput").focus();
  }

  function importStatus(text) {
    const el = $("importStatus");
    el.textContent = text;
    el.hidden = !text;
  }

  async function handleFiles(fileList, addToCurrent = false) {
    const files = [...fileList];
    if (!files.length) return;
    const images = files.filter((f) => IMAGE_RE.test(f.name) || (f.type || "").startsWith("image/"));
    try {
      if (images.length) {
        const msgs = await readScreenshots(images, importStatus);
        if (!msgs.length) { alert("Couldn't find chat bubbles in those screenshots. Crop them to the conversation and try again."); return; }
        if (addToCurrent) return addMessages(msgs, `${images.length} screenshot(s)`, true);
        return offerSetup(msgs, `${images.length} screenshot(s)`, true);
      }
      const f = files[0], raw = await f.text();
      if (!addToCurrent) return handleFile(f.name, raw);
      const parsed = parseFile(f.name, raw);
      if (parsed.bundle) { alert("That's a whole profile. Import it from New contact instead."); return; }
      addMessages(parsed.messages, f.name, false);
    } catch (e) {
      importStatus("");
      alert(e.message);
    }
  }

  // Grow a browser contact with a newer export or more screenshots.
  function addMessages(msgs, source, fromShots) {
    const b = state.current && state.current.bundle;
    if (!b || !b.messages) { alert("This contact was imported without its chat, so it can't learn more here. Use the CLI's `learn` command."); return; }
    const mapped = fromShots ? msgs.map((m) => ({ ...m, sender: m.sender === "Them" ? b.meta.target : b.meta.me })) : msgs;
    if (!fromShots && !mapped.some((m) => m.sender === b.meta.target)) { alert(`No messages from "${b.meta.target}" in that file.`); return; }
    let merged;
    if (fromShots) merged = stitch(b.messages, mapped);
    else {
      const seen = new Set(b.messages.map((m) => `${m.sender}\u0000${m.text}\u0000${m.timestamp}`));
      merged = b.messages.concat(mapped.filter((m) => !seen.has(`${m.sender}\u0000${m.text}\u0000${m.timestamp}`)));
    }
    const added = merged.length - b.messages.length;
    if (!added) { importStatus("Nothing new in there."); setTimeout(() => importStatus(""), 3000); return; }
    snapshot(b, `added ${source}`, true);
    const { style, examples } = analyze(merged, b.meta.target, b.meta.me);
    Object.assign(b, { style, examples, messages: merged.slice(-5000) });
    b.meta = { ...b.meta, version: (b.meta.version || 1) + 1, updated: new Date().toISOString(), sources: [...(b.meta.sources || []), source] };
    state.local[b.slug] = b; saveLocal(state.local);
    renderContacts(); renderStyle(); renderHeader(); renderUndo();
    importStatus(`Learned ${added} new messages. ${b.meta.name} is now v${b.meta.version}.`);
    setTimeout(() => importStatus(""), 4000);
  }

  function createFromPending(e) {
    e.preventDefault();
    let { messages, source, fromShots } = state.pending || {};
    if (!messages) return;
    if (fromShots) { // use the transcript as edited by you
      messages = parseText($("shotReview").value).filter((m) => m.sender === "Them" || m.sender === "Me");
      if (!messages.some((m) => m.sender === "Them")) { alert('Keep at least one "Them:" line.'); return; }
    }
    const target = $("targetSelect").value, me = $("meSelect").value;
    if (target === me) { alert("Pick different people for 'They are' and 'You are'."); return; }
    const name = $("nameInput").value.trim() || target;
    const { style, examples } = analyze(messages, target, me);
    let slug = slugify(name), n = 2;
    while (state.local[slug]) slug = `${slugify(name)}-${n++}`;
    const now = new Date().toISOString();
    state.local[slug] = {
      format: "textback-profile/1", slug,
      meta: { name, relationship: $("relSelect").value, target, me, version: 1, created: now, updated: now, sources: [source] },
      style, persona: "", examples, corrections: [], approved: [],
      messages: messages.slice(-5000), // kept in this browser only, so the contact can keep learning
    };
    saveLocal(state.local);
    state.pending = null;
    $("setupForm").hidden = true;
    $("fileInput").value = "";
    setView("contacts");
    renderContacts(); openContact("local", slug);
  }

  function exportCurrent() {
    const { messages, snapshots, ...b } = state.current.saved || state.current.bundle; // never the raw chat or undo copies
    const blob = new Blob([JSON.stringify(b, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${b.slug}.textback.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function deleteCurrent() {
    const b = state.current.bundle;
    if (!confirm(`Remove ${b.meta.name} from this browser?`)) return;
    delete state.local[b.slug]; saveLocal(state.local);
    state.current = null; state.practice = false; renderContacts(); renderStyle(); renderHeader(); renderUndo(); clearThread(startHint());
  }

  // ----- wire up
  function bind() {
    $("fileInput").addEventListener("change", (e) => { handleFiles(e.target.files); e.target.value = ""; });
    $("addInput").addEventListener("change", (e) => { handleFiles(e.target.files, true); e.target.value = ""; });
    $("addMoreBtn").addEventListener("click", () => $("addInput").click());
    const drop = $("dropZone");
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
    drop.addEventListener("drop", async (e) => {
      e.preventDefault(); drop.classList.remove("drag");
      handleFiles(e.dataTransfer.files);
    });
    renderSamples();
    $("setupForm").addEventListener("submit", createFromPending);
    $("composer").addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $("msgInput").value.trim();
      if (!text || !state.current) return;
      $("msgInput").value = "";
      send(text);
    });
    $("nudgeBtn").addEventListener("click", nudge);
    $("fixForm").addEventListener("submit", (e) => {
      const kind = e.submitter && e.submitter.value;
      if (kind === "fix" || kind === "good") saveFeedback(kind).catch((err) => alert("Couldn't save: " + err.message));
      else fixing = null;
    });
    const showWhy = $("showWhy");
    try { showWhy.checked = localStorage.getItem("textback.showWhy") !== "0"; } catch { /* default on */ }
    const applyWhy = () => {
      $("thread").classList.toggle("hide-why", !showWhy.checked);
      try { localStorage.setItem("textback.showWhy", showWhy.checked ? "1" : "0"); } catch { /* ignore */ }
    };
    showWhy.addEventListener("change", applyWhy);
    applyWhy();
    $("exportBtn").addEventListener("click", exportCurrent);
    $("deleteBtn").addEventListener("click", deleteCurrent);
    $("contactSearch").addEventListener("input", renderContacts);
    $("featuresBtn").addEventListener("click", openFeatures);
    $("featuresClose").addEventListener("click", () => $("featuresDialog").close());
    $("featuresCsv").addEventListener("click", featuresCsv);
    $("featuresJson").addEventListener("click", () => download(`${slugify(lastFeatures.name)}-features.json`, "application/json", JSON.stringify(lastFeatures.f, null, 2)));
    $("undoBtn").addEventListener("click", () => undoLast().catch((e) => alert("Couldn't undo: " + e.message)));
    $("resetBtn").addEventListener("click", () => resetFeedback().catch((e) => alert("Couldn't reset: " + e.message)));
    $("startBtn").addEventListener("click", () => resetToStart().catch((e) => alert("Couldn't reset: " + e.message)));
    $("practiceMode").addEventListener("change", (e) => setPractice(e.target.checked));
    document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => { setView(b.dataset.view); if (b.dataset.view === "new") $("fileInput").closest(".view").scrollTop = 0; }));
    document.querySelectorAll("[data-pane-go]").forEach((b) => b.addEventListener("click", () => setPane(b.dataset.paneGo)));
    $("themeBtn").addEventListener("click", () => {
      let cur = "auto";
      try { cur = localStorage.getItem("textback.theme") || "auto"; } catch { /* default */ }
      applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("app").dataset.pane === "details") setPane("chat"); });
  }

  // ?demo opens the sample boss chat with a short conversation already played, for a quick look.
  async function runDemo() {
    const msgs = parseText(window.TEXTBACK_SAMPLE || "");
    const { style, examples } = analyze(msgs, "Dana", "Alex");
    const now = new Date().toISOString();
    state.local["dana-sample"] = {
      format: "textback-profile/1", slug: "dana-sample",
      meta: { name: "Dana", relationship: "boss", target: "Dana", me: "Alex", version: 1, created: now, updated: now, sources: ["sample_chat.txt"] },
      style, persona: "", examples, corrections: [], approved: [], messages: msgs,
    };
    await openContact("local", "dana-sample");
    state.fast = true;
    for (const t of ["when is the budget sheet due?", "can I work remotely on monday?", "sorry running late"]) await send(t);
    state.fast = false;
  }

  async function init() {
    bind();
    let theme = "auto";
    try { theme = localStorage.getItem("textback.theme") || "auto"; } catch { /* default */ }
    applyTheme(theme);
    setView("contacts");
    setPane(Object.keys(state.local).length ? "list" : "chat");
    renderContacts(); renderStyle(); renderHeader(); renderUndo();
    clearThread(startHint());
    if (await api.probe()) {
      try { state.server = await api.get("/api/profiles"); } catch { state.server = []; }
      renderContacts(); renderHeader();
    }
    if (new URLSearchParams(location.search).has("demo")) await runDemo();
  }

  // Exposed for debugging in the console: TextBack.analyze(...), TextBack.styleRules(...)
  window.TextBack = { parseText, parseCSV, rowsToMessages, computeFeatures, analyze, styleRules, offlineReply, detectIntent, extractTopic, extractTimes, explain };
  init();
})();
