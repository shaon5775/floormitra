"""Offline UI check of app.py with Streamlit's AppTest."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    if not at.toggle[0].value:
        at.toggle[0].set_value(True).run()   # offline demo
    return at


def _html(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_worker_asks_sees_card_confirms_and_supervisor_sees_ticket():
    at = _app()
    at.text_area(key="question").set_value("দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?").run()
    at.button(key="ask").click().run()
    assert not at.exception
    page = _html(at)
    assert "fm-me" in page and "দুই নম্বর লেদ" in page          # question bubble
    assert "fm-bot" in page and "📘" in page                     # answer card with manual source
    assert "Shall I do this?" in page                            # Yes/No card
    assert at.session_state["question"] == ""                    # box emptied after asking
    at.button(key="yes").click().run()
    assert not at.exception
    assert "fm-done" in _html(at) and "টিকিট" in _html(at)

    at.radio(key="nav").set_value("🎫 My tickets").run()
    assert not at.exception and "L2-LATHE" not in _html(at) and "L1-LATHE-02" in _html(at)

    at.radio(key="nav").set_value("📊 Supervisor").run()
    assert not at.exception and "Open tickets" in _html(at)
    ticket = [t for t in at.session_state["chat"] if t["role"] == "done"]
    assert ticket
    at.button(key="report").click().run()          # live bug 11 Nov: button key clashed with the state key
    assert not at.exception and at.session_state["shift_report"]


def test_supervisor_makes_work_order_and_closes_ticket():
    at = _app()
    at.text_area(key="question").set_value("Compressor pe A-01 alarm aa raha hai").run()
    at.button(key="ask").click().run()
    at.button(key="yes").click().run()
    at.radio(key="nav").set_value("📊 Supervisor").run()
    wo = [b for b in at.button if b.key and b.key.startswith("wo_")]
    assert wo
    wo[0].click().run()
    assert not at.exception and "Work order made" in " ".join(c.value for c in at.caption)
    close = [b for b in at.button if b.key and b.key.startswith("close_")]
    close[0].click().run()
    assert not at.exception


def test_example_button_and_hear():
    at = _app()
    at.button(key="ex_1").click().run()
    assert at.session_state["question"].startswith("Compressor")
    at.button(key="ask").click().run()
    at.button(key="hear").click().run()
    assert not at.exception and at.session_state["spoken"]


def test_no_creates_nothing():
    at = _app()
    before = len(at.session_state["chat"])
    at.text_area(key="question").set_value("Compressor pe A-01 alarm aa raha hai").run()
    at.button(key="ask").click().run()
    at.button(key="no").click().run()
    assert not at.exception
    assert len(at.session_state["chat"]) == before + 3 and "fm-done" in _html(at)
