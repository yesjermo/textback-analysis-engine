# Architecture

## Data flow

1. **Parse** (`tools/chat_parser.py`). Any export becomes `Message(sender, text, timestamp)`.
   The text parser samples the first 200 lines to choose a format (WhatsApp bracket, WhatsApp
   dash, or `Name: text`), joins multi-line messages, and drops system lines like "<Media omitted>".
2. **Measure** (`tools/style_analyzer.py`). Consecutive messages from one sender form a *turn*.
   For each side it computes length, casing, ending punctuation, emoji, laugh style, slang and
   phrases. For them it also records texts per turn, reply delay, active hours, turn openers,
   real `(context → reply)` pairs, and *starters* (turns after more than 3 hours of silence).
3. **Describe** (`tools/persona_builder.py`). `style_rules()` turns the numbers into plain-English
   rules. `build_persona()` writes `persona.md` from a template.
4. **Reply** (`tools/reply_engine.py`). `tools/intents.py` first reads what kind of text yours is
   (a "when" question, an apology, "omw", a laugh...; the patterns are in `reply_data.json`), its
   topic and any time in it. Stored contexts are ranked by TF-IDF wording similarity plus whether
   they were the same kind of text, weighted by source (correction 1.6, approved 1.25, history 1.0,
   reference 0.75). A near-identical situation reuses their real reply; otherwise the reply is
   composed from how they usually react to that kind of text and a follow-up about your topic,
   then the reference library, then a template. `stylize()` applies their casing, punctuation,
   shorthand, laugh and emoji habits, and every reply carries a `why`.
5. **Learn** (`tools/learner.py`). Corrections, approvals and notes are appended to the profile.
   `learn` merges a new export and rebuilds everything. Before every change, the profile's files
   are copied to `snapshots/NNNN/` so `undo` and `reset --to-start` can put them back.

## Screenshots

`tools/screenshot_parser.py` reads each screenshot's text lines with their positions (Apple Vision via
`tools/ocr_vision.swift`, or Tesseract). It drops the top and bottom of the screen (header, typing bar) and lines
matching the clutter rules in `reply_data.json` → `screenshot.junk`. It then joins stacked, left-aligned lines
into bubbles and assigns each bubble to the column it lines up with: the left column is them, the right is you,
and centred lines are skipped. `stitch()` joins screenshots and skips bubbles repeated from the previous one,
tolerating small OCR differences ("7?" vs "77?"). The browser version (`web/app.js`) does the same with
Tesseract.js. It runs two passes, one on the image and one on a mask where bright text becomes dark, and keeps
the more confident reading.

## Relationships and the reference library

`reply_data.json` → `families` maps relationships to a reply style (work, personal, ex, talking_stage). Each style
has its own templates and default times, and some kinds of text (relationship
talks, "miss you", flirting) are only recognized outside work. `reference/<family>.jsonl` holds generic example
exchanges. The offline engine uses one only when the person's own history has nothing similar, weights it at
0.75, and always rewrites it in their style. Turn it off per profile with `main.py reference <slug> off`.

## Text features

`tools/features.py` measures both sides of a chat for the `features` command, the
`GET /api/features/<slug>` endpoint and the web view's **All text features** panel.
`compute_features(messages, target, me, relationship)` returns a `shared` block (date span,
active days, conversations, who texts first, reply delays) and a `them` and a `you` block (length
and its histogram, bursts, hours and weekdays, casing, endings, formality, emoji, vocabulary,
MATTR, slang, laughs, tone, kinds of text). `flat_row()` turns that into one CSV row.

How a few of them are defined:

- **Turns and conversations** use the same rules as the analyzer: consecutive texts from one sender
  are a turn, and a gap of more than 3 hours starts a new conversation. Reply delays are measured
  only inside a conversation.
- **Formality** (0-100) is the mean of five parts: capitalised starts, texts with ending
  punctuation, texts that aren't all lowercase, little slang, and longer words.
- **Richness** is MATTR, the moving-average type-token ratio over a 50-word window, so a long chat
  doesn't look less varied just for being long.
- **Tone** is the share of texts containing a word from the `sentiment` lists in `reply_data.json`.
  It's a rough reading, not a sentiment model.
- **Characters** are counted as Unicode code points, so an emoji counts once, and the date span
  is in calendar days.
- Timing features need timestamps: plain `Name: text` chats and screenshots leave them out.

`computeFeatures()` in `web/app.js` computes the same keys in the browser, so browser contacts get
the same report. On the nine samples the two agree on every value; keep it that way when you
change either.

## Profile on disk

See the docstring in `tools/profile_store.py`. The "bundle" (everything except the raw messages)
is the exchange format between the CLI, the server and the web view (`format: textback-profile/1`).

## Web view

`web/app.js` ports the parser, analyzer, rules and offline engine to JavaScript so the page works
with no backend. On load it calls `GET /api/status`. If the page is served by `main.py serve`, it
lists disk profiles and sends replies and feedback through the API. Browser-only profiles live in
`localStorage` under `textback.profiles.v1` (moved back automatically from `textprint.profiles.v1`), with their chat kept so they can learn more, be undone
and have their text features measured. The sample people are bundled into `web/sample.js` by
`tools/build_web.py`.

## Extending

- **New export format**: add a parser in `chat_parser.py` and a branch in `parse_file`, then
  mirror it in `parseFile` in `app.js`.
- **New style signal**: add it to `text_stats` / `analyze`, phrase it in `style_rules`, and
  mirror both in `app.js`.
- **New text feature**: add it to `side_features` or `compute_features` in `features.py`, the same
  key in `computeFeatures` in `app.js`, a row in `format_report` and in the web view's feature table,
  and a check in `tests/test_engine.py`. Compare the two engines on the samples before committing.
