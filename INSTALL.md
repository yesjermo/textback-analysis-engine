# Installing TextBack Analysis Engine

## Requirements

- Python 3.10 or newer. The core uses only the standard library.

## 1. Get the code

```bash
git clone https://github.com/yesjermo/textback-analysis-engine.git
cd textback
```

## 2. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `TEXTBACK_HOME` | `./profiles` | where profiles are stored (`TEXTPRINT_HOME`, from the brief Textprint name, also works) |

## 3. Create your first contact

```bash
python3 main.py participants path/to/chat.txt     # see who's in the export
python3 main.py create --file path/to/chat.txt --target "Dana" --me "Alex" --relationship boss
python3 main.py chat dana
```

Leave out `--target` / `--me` to pick them from a list.

## 4. Pick a view

### Web view

```bash
python3 main.py serve            # http://127.0.0.1:8765
```

Add `?demo` to the address (http://127.0.0.1:8765/?demo) to open the sample boss chat with a short conversation already played.
The server binds to `127.0.0.1` only. Profiles from `profiles/` appear under Contacts, and
corrections you make in the browser are saved to disk.

You can also open `web/index.html` directly, or deploy `web/` to any static host (GitHub
Pages, Netlify, Vercel). In that mode chats are parsed and stored only in that browser.
Use **Export profile** / **Import** to move profiles between the CLI and a browser
(`python3 main.py export dana` writes a bundle the web view can import).

## Put the demo online (GitHub Pages)

The web view is a static page, so GitHub Pages hosts it for free. The live demo is
**https://yesjermo.github.io/textback-analysis-engine/web/?demo**, which the README's **Launch TextBack** button opens.

To publish your own copy (a fork, say):

1. Push the project to a GitHub repo.
2. In the repo, open **Settings → Pages**, set **Source** to **Deploy from a branch**, choose
   `main` and `/ (root)`, and save.
3. After a minute the demo is live at `https://<your-username>.github.io/<repo>/web/?demo`.
4. Point the README's **Launch TextBack** button at that address.

On Pages there's no Python server, so the page runs in browser-only mode: chats and screenshots
are read and stored in the visitor's own browser, and nothing is uploaded.

## 5. Analyse texting features

You can measure how two people text without chatting at all: length, bursts, reply speed, active
hours, who texts first, casing, punctuation, formality, emoji, vocabulary, slang, laughs and tone.

```bash
python3 main.py features dana                 # full report for a profile or a sample person
python3 main.py features --all-samples        # everyone side by side
python3 main.py features --file path/to/chat.txt --target "Sam" --me "Riley"   # any export
```

Add `--csv features.csv` for one row per person (about 160 columns, good for a spreadsheet or
pandas) or `--json features.json` for everything, including the hour-by-hour counts. In the web
view, open **How they text → All text features**; it has CSV and JSON buttons too.

## Screenshots (Instagram, TikTok, Snapchat, iMessage...)

Apps like Instagram and TikTok don't export DMs as text, so screenshot the conversation instead:

1. Scroll to where you want to start and take screenshots as you scroll down. Overlap between shots is fine.
2. Put them in one folder. They're read in filename order (`IMG_0012` before `IMG_0103`).
3. Preview what was read, fix any typos, then import:

```bash
python3 main.py screenshots path/to/folder --them Sam --save sam.txt
python3 main.py create --file sam.txt --target Sam --me Me --relationship talking-stage
```

Or skip the review: `python3 main.py create --screenshots path/to/folder --name Sam --relationship ex`.
Add more any time with `python3 main.py learn sam --screenshots more/`.

Text is read with the best engine available (`--ocr` picks one):

| Engine | Needs | Notes |
|---|---|---|
| `vision` | a Mac | Apple's on-device reader. Nothing to install; the first run compiles a helper (about 20 s). Doesn't read emoji. |
| `tesseract` | `brew install tesseract` or `apt install tesseract-ocr` | Works anywhere; least accurate on dark mode. |

The web view reads screenshots in the browser with Tesseract.js and shows the transcript for you to fix before
it learns. Bubbles on the **right** are treated as yours and bubbles on the **left** as theirs, which is how every
major chat app lays them out. Crop out anything that isn't the conversation if a screenshot reads badly.

## Exporting chats

| App | How |
|---|---|
| **WhatsApp** | Open the chat → ⋮ (Android) or contact name (iPhone) → **Export chat** → **Without media**. Unzip and use the `.txt`. |
| **iMessage (Mac)** | `brew install imessage-exporter`, then `imessage-exporter -f txt -o export/` (or `-f csv`). Grant Full Disk Access to your terminal first. |
| **Telegram** | Desktop app → chat → ⋮ → **Export chat history** → format **JSON**. Use `result.json`. |
| **SMS (Android)** | "SMS Backup & Restore" → export, then convert to CSV with columns `timestamp,sender,text`. |
| **Anything else** | Paste into a `.txt` with one `Name: message` per line. |

CSV and JSON columns are detected by name: `sender/from/author/name`,
`text/message/body/content`, `timestamp/date/time`.

More history gives better results. A few hundred messages from them is a good start.

## Troubleshooting

- **Screenshot bubbles end up on the wrong side**: crop the screenshot to the conversation (no keyboard or
  half-visible sidebars).

- **"No messages from 'X' found"**: run `participants` and copy the sender name exactly, including emoji.
- **Replies are canned or repetitive**: import more history, or use `/fix` a few times.
- **Dates look wrong**: dates are only used for reply delay and active hours, so a wrong date won't break anything else.
- **Port in use**: `python3 main.py serve --port 9000`.
- **Reply delay, hours and "texts first" show `-`**: the export has no timestamps (plain `Name: text`
  files and screenshots), so timing features can't be measured.
