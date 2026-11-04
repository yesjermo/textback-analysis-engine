# Contributing

Thanks for helping. A few things to keep in mind:

- **Never commit real chats.** Test with `examples/sample_chat.txt` or synthetic data.
- **Keep the core dependency-free.** The core uses only the Python standard library.
- **Keep Python and JS in sync.** The parser, `style_rules` and the offline engine exist in both
  `tools/` and `web/app.js`. Run the tests:

```bash
python3 -m unittest discover tests
```

`tools/reply_data.json` (intents, templates, screenshot rules), `reference/*.jsonl`,
`examples/sample_chat.txt` and `examples/samples/` are shared with the web view. If you change a
sample person in `tools/make_samples.py`, run it first; the tests check the files match the script. After editing either, rebuild the generated web files:

```bash
python3 tools/build_web.py
```
