"""The fleet decision inbox (app/inbox.py) and the app around it, on the committed quickstart data."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "quickstart" / "public"
for p in (ROOT / "src", ROOT / "app", ROOT / "baselines"):
    sys.path.insert(0, str(p))


@pytest.fixture(scope="module")
def inbox():
    from europress_data.sdk import open_dataset
    from inbox import decisions

    con = open_dataset(DATA)
    con.execute("SET TimeZone='UTC'")
    yield decisions(con, DATA, "ORG-0004").set_index("key", drop=False)
    con.close()


def test_story_compactor_wasted_trips_are_one_decision(inbox):
    from inbox import plain

    r = inbox.loc["CMP-00046|wasted"]
    assert r.title == "4 trucks came for nothing"
    assert r.stake_eur == pytest.approx(346.20, abs=0.01)
    first = plain(r.lines[0])
    assert "88 %" in first and "stuck" in first
    assert "[[" not in first


def test_combined_load_is_resplit_by_device_weight(inbox):
    r = inbox.loc["CMP-00042|resplit"]
    assert any("invoiced 2.94 t" in x and "580 kg" in x for x in r.lines)
    assert r.stake_eur == pytest.approx(606.75, abs=0.01)


def test_ranked_by_euros_with_notes_last(inbox):
    stakes = list(inbox.stake_eur)
    money = [s for s in stakes if s > 0]
    assert money == sorted(money, reverse=True)
    assert stakes[: len(money)] == money                      # every note (no €) comes after every decision with €
    assert (inbox[inbox.kind == "note"].stake_eur == 0).all()


def test_no_lift_counted_twice_between_early_and_cost(inbox):
    early = {c for items in inbox[inbox.kind == "early"]["items"] for c in items}
    cost = {c for items in inbox[inbox.kind == "cost"]["items"] for c in items}
    assert early and not early & cost


def test_app_approve_moves_euros_to_sent_and_undo_restores():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=180).run()
    assert not at.exception
    hero = lambda: next(m.value for m in at.markdown if 'class="hero"' in m.value)  # noqa: E731
    assert "40 decisions are waiting" in hero() and "€6,210" in hero()
    at.button(key="ok_0").click().run()
    assert "39 decisions are waiting" in hero() and "€607" in hero()
    assert [t.value for t in at.toast] == ["Sent to your account manager · €607"]
    at.button(key="undo_0").click().run()
    assert "40 decisions are waiting" in hero()
