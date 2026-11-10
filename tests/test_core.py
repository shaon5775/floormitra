"""Offline tests: manuals search, maintenance DB, the confirm rule, and the agent loop with the rule-based brain."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fm.agent import FloorMitra, MockBrain  # noqa: E402
from fm.lang import guess_language  # noqa: E402
from fm.manuals import Manuals  # noqa: E402
from fm.plant import Plant  # noqa: E402
from fm.voice import parse_heard  # noqa: E402


def test_manual_search_finds_alarm_code_section():
    hits = Manuals().search("E-205 coolant level low", "cnc_lathe")
    assert hits and "Alarm codes" in hits[0]["source"] and "E-205" in hits[0]["text"]


def test_manual_search_filters_by_machine_type_but_keeps_sops():
    hits = Manuals().search("lockout steps padlock", "conveyor", k=5)
    assert any("SOP-LOTO-01" in h["source"] for h in hits)
    assert not any("Lathe" in h["source"] for h in hits)


def test_plant_stock_and_ticket_and_work_order():
    p = Plant()
    belt = p.spare("SB-1250")[0]
    assert belt["qty"] == 2 and belt["in_stock"]
    assert p.spare("coolant pump")[0]["in_stock"] is False
    t = p.raise_ticket("l1-lathe-02", "Spindle belt whining", "high")
    assert t["machine_id"] == "L1-LATHE-02" and p.machine("L1-LATHE-02")["status"] == "down"
    w = p.create_work_order("L1-LATHE-02", "Replace spindle belt", "SB-1250", "high")
    assert w["ticket_id"] == t["ticket_id"] and w["part_reserved"] is True
    assert p.spare("SB-1250")[0]["qty"] == 1
    p.close_ticket(t["ticket_id"])
    assert p.machine("L1-LATHE-02")["status"] == "running" and p.summary()["open_tickets"] == 0


def test_agent_never_writes_without_yes():
    p = Plant()
    agent = FloorMitra(MockBrain(p), p, Manuals())
    turn = agent.ask("দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?")
    assert turn.language == "bn"
    assert turn.sources and "E-205" in turn.sources[0]["text"]
    assert turn.pending and turn.pending["tool"] == "raise_fault_ticket"
    assert turn.pending["args"]["machine_id"] == "L1-LATHE-02"
    assert p.tickets() == []                                    # nothing written yet
    msg = agent.confirm(turn.pending, yes=True)
    assert "টিকিট" in msg and len(p.tickets()) == 1
    assert p.tickets()[0]["worker_words"].startswith("দুই নম্বর")
    assert any("PROPOSED" in s for s in turn.steps)


def test_agent_no_means_nothing_created():
    p = Plant()
    agent = FloorMitra(MockBrain(p), p, Manuals())
    turn = agent.ask("Compressor pe A-01 alarm aa raha hai")
    assert turn.pending
    agent.confirm(turn.pending, yes=False)
    assert p.tickets() == []


def test_stock_question_is_read_only():
    p = Plant()
    turn = FloorMitra(MockBrain(p), p, Manuals()).ask("Spindle belt SB-1250 store-e koyta ache? stock")
    assert turn.pending is None and any("check_spare_stock" in s for s in turn.steps)


def test_language_guess_and_lenient_listen_parse():
    assert guess_language("पैकिंग लाइन का कन्वेयर") == "hi"
    assert guess_language("Compressor pe alarm") == "en"
    assert parse_heard('{"text": "লেদ E-205", "language": "bn"}') == {"text": "লেদ E-205", "language": "bn"}
    assert parse_heard('{"text": "\\u09b2\\u09c7\\u09a6 \\u09", "language": "bn"}')["language"] == "bn"
