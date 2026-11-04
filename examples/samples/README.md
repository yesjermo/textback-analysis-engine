# Sample people

Nine fictional people to try TextBack with, each texting a different (also fictional) person.
They cover every relationship type and every export format the parser reads.

| id | Them | Relationship | You | Messages | Format | How they text |
|---|---|---|---|---|---|---|
| `dana` | Dana | boss | Alex | 106 | WhatsApp (iPhone) | Short, lowercase, bursts of two texts, a 👍 or 🙌 now and then. |
| `marcus` | Marcus | coworker | Nina | 182 | WhatsApp (Android) | Dry humour, full punctuation, one text at a time. |
| `priya` | Priya | client | Alex | 208 | iMessage CSV | Formal, full sentences, always punctuated. |
| `jordan` | Jordan | best friend | Kai | 375 | WhatsApp (iPhone) | All lowercase, bursts of texts, lots of 😭 and 💀. |
| `mom` | Mom | parent | Emily | 190 | iMessage CSV | Capitalised sentences, ellipses, 😊 and ❤️, checks in a lot. |
| `sam` | Sam | talking stage | Riley | 184 | WhatsApp (iPhone) | Interested but unhurried; slow replies, asks questions back. |
| `taylor` | Taylor | ex | Jamie | 238 | plain "Name: text" | Guarded and brief, ends texts with a period, no emoji. |
| `mateo` | Mateo | sibling | Sofia | 217 | Telegram JSON | Teasing, lowercase, laughs with "jaja", asks for favours. |
| `keisha` | Keisha | friend | Dee | 235 | WhatsApp (Android) | Long voice-to-text messages, warm, punctuated, a 😂 here and there. |

Try one:

```bash
python3 main.py samples              # the list above
python3 main.py create --sample sam  # learn Sam, the talking stage
python3 main.py chat sam
```

In the web view: **New contact → Or try a sample person**.

## How they're made

Dana's chat (`examples/sample_chat.txt`) is written by hand. The other eight come from
`tools/make_samples.py`: each person has hand-written lines in their own voice, grouped into small
scenes (you ask, they answer, maybe one more back and forth). The script plays those scenes over a
few months, with that person's reply delays, active hours and habit of texting first, then writes
each chat in a different export format. It's seeded, so the files only change when the script does.

To change a person or add one, edit `PEOPLE` in `tools/make_samples.py`, then:

```bash
python3 tools/make_samples.py   # rewrites this folder and samples.json
python3 tools/build_web.py      # bundles them into the web view
```

Everyone here is made up. Any resemblance to real people is a coincidence.
