"""Screenshots of the SMART Weight Check app for notes/screenshots/, the deck and 2_SOFTWARE_DEMO.md.

Start the app first, then run this from the repo root:
    streamlit run app/app.py --server.headless true
    python scripts/app_screenshots.py [http://localhost:8501]

Needs Playwright with Chromium: pip install playwright && python -m playwright install chromium.
Writes notes/screenshots/*.png and copies the three deck screenshots into submission/img/.
"""
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "notes" / "screenshots"
IMG = ROOT / "submission" / "img"
URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501").rstrip("/")


def settle(page, extra: float = 2.0) -> None:
    """Wait until the inbox is drawn and Streamlit has finished running."""
    page.wait_for_selector(".hero", timeout=120_000)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120_000)
    time.sleep(extra)


def card(page, text: str):
    return page.locator("[class*='st-key-card_']", has_text=text).first


def scroll_to(page, locator, offset: int = 24) -> None:
    locator.evaluate(f"(e) => {{ e.scrollIntoView({{block: 'start'}}); const m = document.querySelector('[data-testid=\"stMain\"]'); if (m) m.scrollBy(0, -{offset}); }}")
    time.sleep(0.6)


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # the inbox as it opens (deck slide 4)
        page = browser.new_page(viewport={"width": 1440, "height": 880})
        page.goto(URL + "/")
        settle(page, 3)
        page.screenshot(path=SHOTS / "00_inbox_top.png")

        # the whole page, on a tall window (Streamlit scrolls inside its own container)
        page.set_viewport_size({"width": 1440, "height": 2100})
        time.sleep(1.5)
        page.screenshot(path=SHOTS / "01_inbox_full_page.png")
        page.set_viewport_size({"width": 1440, "height": 1300})

        # "Why?" on the story compactor: the stuck fill line, the flat weight line, the wasted trips in amber
        card(page, "trucks came for nothing").get_by_role("button", name="Why?").click()
        settle(page)
        card(page, "trucks came for nothing").screenshot(path=SHOTS / "02_why_CMP-00046_wasted_trips.png")
        card(page, "trucks came for nothing").get_by_role("button", name="Hide evidence").click()
        settle(page, 1)

        # "Why?" on the shared truck: invoiced 2.94 t for a container that held 580 kg
        card(page, "shared trucks split equally").get_by_role("button", name="Why?").click()
        settle(page)
        card(page, "shared trucks split equally").screenshot(path=SHOTS / "03_why_CMP-00042_shared_truck.png")

        # approve the biggest decision: the counter moves (fresh page so the evidence is closed)
        page = browser.new_page(viewport={"width": 1440, "height": 880})
        page.goto(URL + "/")
        settle(page, 3)
        card(page, "shared trucks split equally").get_by_role("button", name="Approve").click()
        settle(page, 1.2)
        page.screenshot(path=SHOTS / "06_after_approve_counter.png")

        # deck backup 1: CMP-00046 with one decision approved, early lifts on 4 and 11 September below it
        page = browser.new_page(viewport={"width": 1440, "height": 820})
        page.goto(URL + "/?device=CMP-00046")
        settle(page, 3)
        card(page, "trucks came for nothing").get_by_role("button", name="Approve").click()
        settle(page, 1.2)
        page.screenshot(path=SHOTS / "04_CMP-00046_one_approved.png")

        # deck backup 2: CMP-00047, lifts invoiced without a ticket, and the scale-check note
        page = browser.new_page(viewport={"width": 1440, "height": 826})
        page.goto(URL + "/?device=CMP-00047")
        settle(page, 3)
        page.get_by_text("notes without € at stake").click()
        time.sleep(1)
        page.add_style_tag(content="[data-testid='stMainBlockContainer'] { zoom: 0.8; max-width: 1720px !important; }")  # card + notes on one slide
        time.sleep(1)
        scroll_to(page, card(page, "Invoiced tonnage needs a look"), offset=12)
        page.screenshot(path=SHOTS / "05_CMP-00047_no_ticket_and_scale_check.png")
        browser.close()

    shutil.copy(SHOTS / "00_inbox_top.png", IMG / "demo_inbox.png")
    shutil.copy(SHOTS / "04_CMP-00046_one_approved.png", IMG / "backup_proposals.png")
    print("wrote", sorted(f.name for f in SHOTS.glob("*.png")))


if __name__ == "__main__":
    main()
