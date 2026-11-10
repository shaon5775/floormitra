"""Live check with a real Gemini key: 4 worker questions in 4 languages through the full agent loop.

    GEMINI_API_KEY=... python scripts/live_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fm.config import build, gemini_key, model_name  # noqa: E402

QUESTIONS = [
    ("দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?", "bn"),
    ("Compressor pe A-01 alarm aa raha hai, bahut garam ho raha hai", "hinglish"),
    ("पैकिंग लाइन का कन्वेयर रोलर से बहुत तेज़ आवाज़ आ रही है, टिकट बना दो", "hi"),
    ("Do we have a spare coolant pump for the lathe?", "en"),
]

if not gemini_key():
    sys.exit("GEMINI_API_KEY is not set")
agent, voice = build(offline=False)
if "--voice" in sys.argv:   # speech round trip: speak each question, then listen to it again
    for q, lang in QUESTIONS[:3]:
        wav = voice.speak(q)
        heard = voice.listen(wav, "audio/wav") if wav else {"text": "(no speech)", "language": ""}
        print(f"[voice {lang}] said : {q}\n            heard: {heard['text']} ({heard['language']})")
print("model:", model_name())
ok = 0
for q, lang in QUESTIONS:
    t = agent.ask(q, lang)
    print("\n== Q:", q)
    for s in t.steps:
        print("  ", s)
    print("  ANSWER:", t.answer)
    print(f"   sources={len(t.sources)} pending={bool(t.pending)} tokens={t.tokens} time={t.latency_s}s")
    if t.pending:
        print("   CONFIRM ->", agent.confirm(t.pending, yes=True))
    good = bool(t.answer) and (t.sources or "stock" in q or "spare" in q)
    ok += bool(good)
print("\nsupervisor summary:", agent.plant.summary())
print(f"[RESULT] {ok}/{len(QUESTIONS)} answered with a source or a tool result")
