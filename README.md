# babypips-content

Private, personal-use archive of BabyPips lessons I have access to.

## One-time setup (Windows)

1. Install Python from https://www.python.org/downloads/ (tick **"Add python.exe to PATH"** during install).
2. Open **PowerShell** in this repo folder and run:

```powershell
py -m pip install -r scraper\requirements.txt
py -m playwright install chromium
```

## Saving lessons

```powershell
py scraper\scrape.py --max-pages 3
```

A Chromium window opens. Log in, check you can see the lesson, then press **Enter** in PowerShell.
It lists the lessons it found and asks before saving. Drop `--max-pages 3` once a test run looks right.

Other examples:

```powershell
# a different starting page
py scraper\scrape.py --start https://www.babypips.com/learn/forex/kindergarten

# follow links two hops deep (e.g. from the course overview to every grade's lessons)
py scraper\scrape.py --start https://www.babypips.com/learn/forex --depth 2
```

Output:

- `content/markdown/...` – one `.md` per lesson, images in `content/markdown/images/`, plus an `_INDEX.md` per run
- `content/raw/...` – the full page HTML, so the Markdown can be regenerated later without re-downloading
- `content/manifest.json` – list of everything saved

Your login is stored in `.browser-profile/` (git-ignored, never committed).
