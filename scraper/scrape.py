"""
Personal-use BabyPips lesson saver.

Opens a visible Chromium window, lets you log in yourself, then visits the
lesson pages linked from a starting page and saves each one as Markdown
(plus the raw HTML, so the conversion can be improved later without
re-downloading anything).

Usage (from the repo folder):
    py scraper\\scrape.py
    py scraper\\scrape.py --start https://www.babypips.com/learn/forex/preschool --depth 1
    py scraper\\scrape.py --max-pages 3          # quick test run

Your login is kept in .browser-profile\\ (git-ignored), so you only log in once.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from markdownify import markdownify as html_to_md
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / ".browser-profile"
OUT_DIR = ROOT / "content"

# Where the lesson text most likely lives, tried in order. The first match
# with a reasonable amount of text wins; otherwise the whole <body> is used.
CONTENT_SELECTORS = [
    "article",
    "main article",
    "[class*='lesson-content']",
    "[class*='LessonContent']",
    "[class*='lesson']",
    "main",
    "[role='main']",
]

# Removed from the saved content before converting to Markdown.
STRIP_SELECTORS = [
    "script", "style", "noscript", "iframe", "nav", "header", "footer",
    "aside", "form", "#comments", ".comments", "[class*='advert']",
]

# Links matching these are never followed.
SKIP_PATTERNS = [
    r"/quiz", r"/comments", r"/login", r"/logout", r"/sign", r"/register",
    r"/account", r"\.(pdf|zip|png|jpe?g|gif|svg|webp)$",
]


def clean_url(url: str) -> str:
    """Drop query string and #fragment, and any trailing slash."""
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def slug_for(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return re.sub(r"[^A-Za-z0-9._/-]", "-", path) or "index"


def in_scope(url: str, scope: str) -> bool:
    p = urlparse(url)
    if p.netloc not in ("www.babypips.com", "babypips.com"):
        return False
    if not p.path.startswith(scope):
        return False
    return not any(re.search(pat, p.path, re.I) for pat in SKIP_PATTERNS)


def extract_content_html(page) -> str:
    """Return the HTML of the main lesson area, with clutter removed."""
    return page.evaluate(
        """([candidates, strip]) => {
            let el = null;
            for (const sel of candidates) {
                const found = document.querySelector(sel);
                if (found && found.innerText.trim().length > 300) { el = found; break; }
            }
            el = (el || document.body).cloneNode(true);
            for (const sel of strip) el.querySelectorAll(sel).forEach(n => n.remove());
            return el.innerHTML;
        }""",
        [CONTENT_SELECTORS, STRIP_SELECTORS],
    )


def save_images(context, html: str, page_url: str, img_dir: Path, rel_prefix: str) -> str:
    """Download images referenced in html and point the tags at local copies."""
    img_dir.mkdir(parents=True, exist_ok=True)

    def replace(match):
        src = match.group(2)
        if src.startswith("data:"):
            return match.group(0)
        full = urljoin(page_url, src)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(urlparse(full).path).name) or "image"
        target = img_dir / name
        if not target.exists():
            try:
                resp = context.request.get(full, timeout=30000)
                if resp.ok:
                    target.write_bytes(resp.body())
                else:
                    return match.group(0)
            except Exception:
                return match.group(0)
        return f'{match.group(1)}{rel_prefix}{name}{match.group(3)}'

    return re.sub(r'(<img[^>]*?\ssrc=["\'])([^"\']+)(["\'])', replace, html)


def scroll_to_bottom(page):
    """Scroll slowly so lazy-loaded images and text appear."""
    page.evaluate(
        """async () => {
            for (let y = 0; y < document.body.scrollHeight; y += 800) {
                window.scrollTo(0, y);
                await new Promise(r => setTimeout(r, 150));
            }
            window.scrollTo(0, 0);
        }"""
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="https://www.babypips.com/learn/forex/preschool",
                    help="Page to start from (default: Preschool)")
    ap.add_argument("--scope", default="/learn/forex/",
                    help="Only follow links whose path starts with this (default: /learn/forex/)")
    ap.add_argument("--depth", type=int, default=1,
                    help="How many link-hops from the start page to follow (default: 1 = the start page and the lessons it links to)")
    ap.add_argument("--max-pages", type=int, default=0, help="Stop after this many pages (0 = no limit)")
    ap.add_argument("--delay", type=float, default=3.0, help="Seconds to wait between pages (default: 3)")
    ap.add_argument("--no-images", action="store_true", help="Don't download images")
    ap.add_argument("--yes", action="store_true", help="Don't ask for confirmation before crawling")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    manifest_path = OUT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, viewport={"width": 1280, "height": 900}
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.start, wait_until="domcontentloaded")

        print("\n" + "=" * 70)
        print("A Chromium window has opened.")
        print("1. Log in to BabyPips in that window (if you aren't already).")
        print("2. Make sure you can see the lesson content.")
        print("3. Come back here and press Enter to start saving.")
        print("=" * 70)
        input("Press Enter when ready... ")

        start = clean_url(args.start)
        queue = [(start, 0)]
        seen = {start}
        order = []
        saved = 0

        while queue:
            url, depth = queue.pop(0)
            if args.max_pages and saved >= args.max_pages:
                break

            print(f"[{saved + 1}] {url}")
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                print(f"    ! load problem ({e.__class__.__name__}), continuing with what loaded")
                resp = None
            if resp is not None and resp.status >= 400:
                print(f"    ! HTTP {resp.status}, skipping")
                continue

            scroll_to_bottom(page)
            title = page.title()

            # Collect links (in page order) for the next level.
            if depth < args.depth:
                hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                new = []
                for h in hrefs:
                    c = clean_url(h)
                    if c not in seen and in_scope(c, args.scope):
                        seen.add(c)
                        new.append(c)
                queue.extend((c, depth + 1) for c in new)
                if url == start:
                    print(f"    found {len(new)} lesson links on the start page")
                    if not args.yes:
                        for c in new[:15]:
                            print("      ", c)
                        if len(new) > 15:
                            print(f"       ... and {len(new) - 15} more")
                        if input("    Save these pages? [Y/n] ").strip().lower() == "n":
                            break

            slug = slug_for(url)
            md_path = OUT_DIR / "markdown" / f"{slug}.md"
            raw_path = OUT_DIR / "raw" / f"{slug}.html"
            md_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.parent.mkdir(parents=True, exist_ok=True)

            raw_path.write_text(page.content(), encoding="utf-8")
            body_html = extract_content_html(page)
            if not args.no_images:
                img_dir = OUT_DIR / "markdown" / "images"
                rel = "../" * slug.count("/") + "images/"
                body_html = save_images(context, body_html, url, img_dir, rel)

            md = html_to_md(body_html, heading_style="ATX", strip=["span"])
            md = re.sub(r"\n{3,}", "\n\n", md).strip()
            md_path.write_text(f"# {title}\n\nSource: {url}\n\n{md}\n", encoding="utf-8")

            order.append(url)
            manifest[url] = {"title": title, "markdown": str(md_path.relative_to(ROOT)).replace("\\", "/"),
                             "raw": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                             "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            saved += 1
            print(f"    saved {md_path.relative_to(ROOT)} ({len(md):,} chars)")

            if queue:
                time.sleep(args.delay)

        # A simple table of contents for this run, in the order visited.
        toc = OUT_DIR / "markdown" / f"{slug_for(start).replace('/', '_')}_INDEX.md"
        toc.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Index: {start}\n"]
        for u in order:
            entry = manifest[u]
            link = Path(entry["markdown"]).relative_to("content/markdown").as_posix()
            lines.append(f"- [{entry['title']}]({link})")
        toc.write_text("\n".join(lines) + "\n", encoding="utf-8")

        print(f"\nDone. Saved {saved} page(s) into {OUT_DIR}.")
        context.close()


if __name__ == "__main__":
    sys.exit(main())
