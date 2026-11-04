# TextBack Analysis Engine

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](INSTALL.md#requirements)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](requirements.txt)
[![No API key](https://img.shields.io/badge/API%20key-not%20needed-brightgreen)](INSTALL.md)
[![Web view: no build step](https://img.shields.io/badge/web%20view-no%20build%20step-blue)](INSTALL.md#web-view)
[![Chats stay on your device](https://img.shields.io/badge/chats-stay%20on%20your%20device-blue)](docs/PRIVACY.md)
[![Imports](https://img.shields.io/badge/imports-WhatsApp%20%C2%B7%20iMessage%20%C2%B7%20Telegram%20%C2%B7%20screenshots-lightgrey)](INSTALL.md#exporting-chats)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**Learn how your boss, your friends, your talking stage or your ex text, analyse it, then text with them.**

TextBack Analysis Engine (TextBack for short) reads a chat export, measures how one person texts (length, casing, punctuation,
emoji, slang, bursts, reply speed) and turns it into a profile that replies the way they
would. Each time you say "they'd never say that, they'd say *this*", it saves the fix and
replies closer to the real person next time.

TextBack applies this idea to everyday contacts and adds:

- **A learning loop.** Corrections, approvals and notes all feed back into the profile, and corrections outrank chat history.
- **Two-sided style.** It studies how *you* text too, so it learns the dynamic between you (your boss answers your paragraphs with "ok", your best friend matches your energy).
- **Learns from screenshots too.** Drop in Instagram, TikTok, iMessage or Snapchat DM screenshots: it reads the
  bubbles, works out who sent what from which side they're on, and skips timestamps, "Seen" and the rest.
- **Any kind of relationship.** Boss, coworker, client, friend, partner, family, **talking stage** and **ex**,
  each with its own reply style ("what are we?" and "I miss you" get answers that fit the relationship).
- **Works with little history.** A built-in [reference library](reference/) of example exchanges fills gaps
  when your chat has nothing similar, and every reply tells you why it was chosen.
- **Three ways to use it.** A terminal chat, a local server and a static web view.
- **No setup to try it.** Everything runs locally with the Python standard library.

```
you > Can I push the report to Monday?
Dana: hmm
Dana: tell them we'll confirm by fri
you > /fix ya thats fine | just put it on the cal
  (correction saved; they'll text like that next time)
```

## Quick start

```bash
git clone <your-fork-url> textback-analysis-engine && cd textback-analysis-engine
python3 main.py create --file examples/sample_chat.txt --target Dana --me Alex --relationship boss
python3 main.py chat dana
```

Or pick one of [nine sample people](examples/samples/), from a boss and a client to a best friend,
a mom, a talking stage and an ex (`python3 main.py samples`, then `python3 main.py create --sample sam`).

No dependencies are needed for that. See [INSTALL.md](INSTALL.md) for the full setup.

From screenshots (newest last, folders work too):

```bash
python3 main.py screenshots ~/Desktop/sam-dms --them Sam --save sam.txt   # check what was read, fix typos
python3 main.py create --file sam.txt --target Sam --me Me --relationship talking-stage
python3 main.py learn sam --screenshots ~/Desktop/more-sam-dms             # keep adding later
```

## Ways to use it

| View | Command | Best for |
|---|---|---|
| Terminal | `python3 main.py chat dana` | fast practice, no browser |
| Web view, local | `python3 main.py serve`, then http://127.0.0.1:8765 | a phone-style UI over your saved profiles |
| Web view, static | open `web/index.html` or host `web/` anywhere | sharing the demo; everything stays in the browser |

## The learning loop

```
chat export ──► parse ──► measure style (them + you) ──► persona.md + rules + real examples
                                                                  │
         you text them ◄──── offline reply engine ◄─────────────────┘
               │                         ▲
               ▼                         │
     /fix  /good  /note  learn ──────────┘   corrections > approvals > notes > history
```

| In chat | What it does |
|---|---|
| `/fix <text>` | "They'd say this instead." Saved as a correction (use ` \| ` to split bubbles) |
| `/good` | "That's exactly them." Saved so similar moments reuse it |
| `/note <fact>` | Teaches a habit the chat doesn't show ("never texts on weekends") |
| `/nudge` | They text you first, the way they usually start a conversation |
| `/style` | Shows the rules TextBack has learned |
| `/why` | Explains how the last reply was picked |
| `python3 main.py learn <slug> --file newer.txt` | Merges a newer export, bumps the version and snapshots the old style |
| `python3 main.py learn <slug> --screenshots shots/` | Same, from screenshots; overlap with what it has is skipped |
| `/undo` or `python3 main.py undo <slug>` | Undoes the last change: a learn, correction, approval, note or reset |
| `/forget` or `python3 main.py reset <slug>` | Forgets your corrections, approvals and notes; keeps what it learned from chats |
| `python3 main.py reset <slug> --to-start` | Back to how the profile was when you created it |
| `python3 main.py chat <slug> --practice` | Practice mode: corrections shape this chat only, nothing is saved |
| `python3 main.py history <slug>` | Lists the changes that can be undone |

## Text features

TextBack can also just measure how two people text: length, bursts, reply speed, active hours,
who texts first, casing, punctuation, formality, emoji, vocabulary richness, slang, laughs, a
rough tone reading, and the kinds of texts each side sends.

```bash
python3 main.py features dana                         # full report for one person (a profile or a sample)
python3 main.py features --all-samples                # compare everyone side by side
python3 main.py features --file chat.txt --target Sam --me Riley   # any export, no profile needed
python3 main.py features --all-samples --csv features.csv          # one row per person, ~160 columns
```

In the web view: **How they text → All text features**, with CSV and JSON downloads. The web
view and the CLI compute the same numbers (`tools/features.py` and `computeFeatures` in `web/app.js`).
Timing features need timestamps, so plain "Name: text" chats and screenshots leave them out.

The web view has the same in **How they text → Undo and reset**, plus a Practice mode switch.

Every reply has a reason, for example *read your text as "when" questions about "budget sheet"; opened with their
reply when you said "When is the deadline for the Q2 report?"; used "by fri"*. In order of preference a reply
comes from: your corrections → their real reply to the same situation → their usual reaction to that kind
of text, plus a follow-up about your topic → the reference library → a template, always rewritten in their style.

## Relationships

| `--relationship` | Reply style | Notes |
|---|---|---|
| `boss`, `coworker`, `client` | work | no "relationship talk" readings; deadlines get days |
| `friend`, `best friend`, `partner`, `parent`, `sibling`, `other` | friends & family | |
| `talking-stage` (also `situationship`, `crush`) | talking stage | matches their real interest level and pace |
| `ex` | ex | keeps the distance their real texts show; never promises getting back together |

In the web view, tap any of their bubbles to correct it or mark it spot-on.

## Project layout

```
textback-analysis-engine/
├── main.py                 CLI (create, learn, screenshots, chat, correct, approve, note, reference, serve, ...)
├── tools/
│   ├── chat_parser.py      WhatsApp / plain text / CSV / JSON → messages
│   ├── screenshot_parser.py  screenshots → messages (OCR + which side each bubble is on)
│   ├── ocr_vision.swift    Apple Vision text reader used on macOS
│   ├── style_analyzer.py   measures how someone texts (and how you text, and who texts first)
│   ├── features.py         the full text-feature analysis, report and CSV rows
│   ├── intents.py          what kind of text is this? topic, times, similarity
│   ├── reply_data.json     intents, templates, relationship styles, screenshot clutter rules (shared with web)
│   ├── persona_builder.py  stats → readable rules → persona.md
│   ├── reply_engine.py     offline reply engine, with a "why" for every reply
│   ├── learner.py          create, learn, correct, approve, note
│   ├── profile_store.py    profile files on disk
│   ├── build_web.py        regenerates web/sample.js and web/reply_data.js
│   ├── make_samples.py     generates the sample people in examples/samples/
│   └── server.py           localhost web server + JSON API (stdlib only)
├── reference/              built-in example exchanges per relationship type (work, personal, ex, talking_stage)
├── web/
│   ├── index.html          the alternate view
│   ├── style.css
│   ├── app.js              parser, analyzer, offline engine and screenshot reader in JS, plus server mode
│   ├── reply_data.js       generated from tools/reply_data.json + reference/
│   └── sample.js           generated from examples/sample_chat.txt
├── tests/test_engine.py    python3 -m unittest discover tests
├── docs/
│   ├── ARCHITECTURE.md
│   └── PRIVACY.md
├── examples/               sample_chat.txt (Dana) + samples/ (eight more people, all fictional)
├── profiles/               your profiles (gitignored)
├── INSTALL.md
├── CONTRIBUTING.md
├── requirements.txt
└── LICENSE
```

## Responsible use

TextBack is for private practice: rehearsing how to ask your boss for time off, or getting
a laugh out of how your friend would answer. Please:

- Only import chats you're part of, and keep profiles on your own machine. That includes screenshots.
- For an ex or a talking stage, use it to think things through, not to decide for you or to keep tabs on someone.
- Don't send generated texts to anyone while posing as the real person.
- If someone asks you to delete their profile, delete it: `rm -rf profiles/<slug>`.

More in [docs/PRIVACY.md](docs/PRIVACY.md).

## License

MIT. See [LICENSE](LICENSE).
