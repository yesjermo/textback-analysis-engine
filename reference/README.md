# Reference library

Hand-written example exchanges for each kind of relationship. TextBack uses them **only as a
fallback** when your own chat history has nothing similar. They're down-weighted, always
rewritten in the person's own style, and every reply that uses one says so in its "why" line.

| File | Used for relationships |
|---|---|
| `work.jsonl` | boss, coworker, client |
| `personal.jsonl` | friend, best friend, partner, parent, sibling, other |
| `ex.jsonl` | ex |
| `talking_stage.jsonl` | talking stage, situationship, crush |

Each line is `{"context": "<what you texted>", "reply": ["<bubble>", "<bubble>"]}`.

Add your own lines to grow the library (keep them generic: no real names or private details),
then run `python3 tools/build_web.py` so the web view gets them too. Turn the library off for
one person with `python3 main.py reference <slug> off`.
