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


def test_worker_asks_confirms_and_supervisor_sees_ticket():
    at = _app()
    at.text_area(key="typed").set_value("দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?").run()
    at.button(key="ask_typed").click().run()
    assert not at.exception
    assert any("দুই নম্বর লেদ" in i.value for i in at.info)
    assert at.session_state["turn"].pending
    at.button(key="yes").click().run()
    assert not at.exception
    assert any("টিকিট" in s.value for s in at.success)

    at.radio(key="screen").set_value("🧑‍💼 Supervisor").run()
    assert not at.exception
    assert any(m.label == "Open tickets" and int(m.value) >= 1 for m in at.metric)


def test_hear_button_makes_audio_for_current_answer():
    at = _app()
    at.text_area(key="typed").set_value("Compressor pe A-01 alarm aa raha hai").run()
    at.button(key="ask_typed").click().run()
    at.button(key="hear").click().run()
    assert not at.exception and at.session_state["spoken"]
