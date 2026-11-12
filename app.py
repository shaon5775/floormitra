"""FloorMitra demo app (mobile-first).   Run:  streamlit run app.py

Worker: chat-style answers with a red lockout warning, numbered steps, the manual source and a big Yes / No card
before anything is written. Supervisor: KPI cards, ticket list with actions, Gemini shift report.
"""
from __future__ import annotations

import hashlib
import html
import re

import streamlit as st

from fm.agent import shift_report_prompt
from fm.config import build, gemini_key, write_text
from fm.lang import CONFIRM_ASK
from fm.plant import Plant

st.set_page_config(page_title="FloorMitra", page_icon="🛠️", layout="centered", initial_sidebar_state="collapsed")

CSS = """
<style>
#MainMenu, footer, [data-testid="stSidebarCollapsedControl"] {visibility:hidden}
.block-container {padding-top:1rem; max-width:720px}
.fm-top {background:#2c2c2a; color:#fff; border-radius:16px; padding:12px 16px; display:flex;
  justify-content:space-between; align-items:center; margin-bottom:8px}
.fm-top b {font-size:18px} .fm-chip {font-size:12px; padding:3px 10px; border-radius:8px; background:#3b6d11; color:#fff}
.fm-chip.red {background:#a32d2d}
.fm-me {margin:8px 0 8px auto; background:#c0dd97; color:#173404; border-radius:16px 16px 4px 16px;
  padding:9px 13px; max-width:82%; width:fit-content; font-size:15px}
.fm-bot {margin:8px 0; background:#fff; color:#2c2c2a; border:1px solid #e5e3dc; border-radius:16px 16px 16px 4px;
  padding:11px 13px; max-width:92%; font-size:15px}
.fm-warn {background:#fcebeb; color:#a32d2d; border-radius:10px; padding:7px 10px; font-size:14px; font-weight:600;
  margin-bottom:8px}
.fm-step {display:flex; gap:8px; align-items:flex-start; margin:6px 0; line-height:1.5}
.fm-num {width:22px; height:22px; border-radius:50%; background:#e6f1fb; color:#0c447c; font-size:12px; flex:none;
  display:flex; align-items:center; justify-content:center; margin-top:2px}
.fm-src {font-size:12px; color:#5f5e5a; margin-top:8px; border-top:1px solid #e5e3dc; padding-top:6px}
.fm-act {background:#faeeda; color:#633806; border-radius:14px; padding:10px 13px; font-size:15px; margin:6px 0 4px}
.fm-done {margin:8px 0; background:#eaf3de; color:#27500a; border:1px solid #c0dd97; border-radius:14px;
  padding:9px 13px; width:fit-content; font-size:15px}
.fm-hint {color:#5f5e5a; font-size:14px}
.fm-cards {display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:6px 0 10px}
.fm-card {background:#f1efe8; border-radius:12px; padding:10px 12px; color:#2c2c2a}
.fm-card .n {font-size:26px; font-weight:700} .fm-card .t {font-size:12px; color:#5f5e5a}
.fm-card.red {background:#fcebeb} .fm-card.red .n {color:#a32d2d}
.fm-card.amber {background:#faeeda} .fm-card.amber .n {color:#633806}
.fm-sev {font-size:12px; padding:2px 9px; border-radius:8px}
.fm-sev.high, .fm-sev.critical {background:#fcebeb; color:#a32d2d}
.fm-sev.medium {background:#faeeda; color:#633806} .fm-sev.low {background:#eaf3de; color:#27500a}
.fm-report {background:#e6f1fb; color:#0c447c; border-radius:12px; padding:10px 13px; font-size:14px}
[data-testid="stAudioInput"] {border:3px solid #ef9f27; border-radius:18px; background:#fac775; padding:4px}
[data-testid="stAudioInput"] label p {color:#412402; font-weight:700; font-size:15px}
div[role="radiogroup"] {gap:6px; flex-wrap:nowrap}
div[role="radiogroup"] label {border:1px solid #d3d1c7; border-radius:12px; padding:6px 10px; background:#fff;
  flex:1; justify-content:center; margin:0}
[data-testid="stRadioOption"] > div > div:not([data-testid]) {display:none}
div[role="radiogroup"] label p {font-size:14px; white-space:nowrap}
[data-testid="stRadioOption"][data-selected="true"], div[role="radiogroup"] label:has(input:checked)
  {background:#2c2c2a; border-color:#2c2c2a}
[data-testid="stRadioOption"][data-selected="true"] p, div[role="radiogroup"] label:has(input:checked) p {color:#fff}
.stButton button {min-height:46px; border-radius:12px; font-size:15px}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource
def shared_plant() -> Plant:
    """One plant for every browser: a ticket raised on the worker's phone appears on the supervisor's screen."""
    return Plant()


plant = shared_plant()
LANGS = {"Auto": "", "বাংলা": "bn", "हिन्दी": "hi", "English": "en", "Hinglish": "hinglish", "Banglish": "banglish"}
EXAMPLES = ["দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?", "Compressor pe A-01 alarm aa raha hai",
            "पैकिंग लाइन का कन्वेयर रोलर से बहुत आवाज़ आ रही है", "Spindle belt SB-1250 store-e koyta ache?"]
LOCKOUT = {"bn": "আগে লকআউট করুন (SOP-LOTO-01)", "hi": "पहले लॉकआउट करें (SOP-LOTO-01)",
           "en": "Lockout first (SOP-LOTO-01)"}
LOCK_WORDS = re.compile(r"LOTO|lockout|lock out|লকআউট|লক আউট|लॉकआउट|लॉक आउट", re.I)
# Live 11 Nov 2026: Bengali speech sometimes comes back in Latin letters ("banglish"), Hindi as Hinglish.
# For SPOKEN questions answer in the language itself (own script), since the answer is read aloud.
SPOKEN_ANSWER_LANG = {"banglish": "bn", "bn": "bn", "hinglish": "hi", "hi": "hi"}

ss = st.session_state
ss.setdefault("chat", [])          # [{"role": "me"|"bot"|"done", ...}]
ss.setdefault("question", "")

# ---- header + settings + navigation ------------------------------------------------------------------------
with st.expander("⚙️ Settings"):
    has_key = bool(gemini_key())
    offline = st.toggle("Offline demo (no API key)", value=not has_key,
                        help="Rule-based stand-in for Gemini, so the flow can be tried without a key.")
    worker = st.text_input("Your name", value="Ravi (Line 2)", key="worker")
    lang_label = st.selectbox("Your language", list(LANGS), key="lang")
    st.caption("Sample plant: 6 machines, 5 English manuals/SOPs, a mock maintenance system.")

down = plant.summary()["machines_down"]
chip = f'<span class="fm-chip red">{down} down</span>' if down else f'<span class="fm-chip">{html.escape(worker)} · {html.escape(lang_label)}</span>'
st.markdown(f'<div class="fm-top"><b>🛠️ FloorMitra</b>{chip}</div>', unsafe_allow_html=True)
nav = st.radio("Screen", ["🎤 Ask", "🎫 My tickets", "📊 Supervisor"], horizontal=True, key="nav",
               label_visibility="collapsed")

agent, voice = build(offline=offline, plant=plant)


def esc(t: str) -> str:
    return html.escape(t or "")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[।.!?])\s+", (text or "").strip())
    return [p for p in parts if p.strip()]


MINOR_SECTIONS = ("Spare parts", "Safety", "Daily", "Weekly")


def main_source(turn) -> dict | None:
    """The section that answers the question (not the parts list or the general safety page), else the first."""
    for s in turn.sources:
        if not any(m in s["source"] for m in MINOR_SECTIONS):
            return s
    return turn.sources[0] if turn.sources else None


def bot_html(turn, asked: bool) -> str:
    sents = sentences(turn.answer)
    # Safety first: a repair job (an action was proposed) whose manual sections require lockout gets the red bar,
    # even if the model forgot to say it (live 12 Nov: conveyor roller answer without lockout).
    manual_lock = any(LOCK_WORDS.search(s["text"]) for s in turn.sources)
    lock = bool(LOCK_WORDS.search(turn.answer)) or (asked and manual_lock)
    steps = [s for s in sents if not LOCK_WORDS.search(s)]
    if asked:                                   # the Yes/No card asks this, so drop the asking sentences
        ask_parts = {p.strip() for v in CONFIRM_ASK.values() for p in sentences(v)}
        steps = [s for s in steps if s.strip() not in ask_parts]
        if len(steps) > 1 and steps[-1].rstrip().endswith(("?", "？")):
            steps = steps[:-1]
    out = []
    if lock:
        out.append(f'<div class="fm-warn">🔒 {esc(LOCKOUT.get(turn.language, LOCKOUT["en"]))}</div>')
    if len(steps) == 1:
        out.append(f"<div>{esc(steps[0])}</div>")
    for i, s in enumerate(steps if len(steps) > 1 else [], 1):
        out.append(f'<div class="fm-step"><span class="fm-num">{i}</span><span>{esc(s)}</span></div>')
    src = main_source(turn)
    if src:
        out.append(f'<div class="fm-src">📘 {esc(src["source"])}</div>')
    return '<div class="fm-bot">' + "".join(out) + "</div>"


def ask(q: str, spoken_lang: str = "") -> None:
    q = (q or "").strip()
    if not q:
        st.warning("Say or type your question first.")
        return
    lang = LANGS[lang_label] or SPOKEN_ANSWER_LANG.get(spoken_lang, spoken_lang)
    with st.spinner("Checking the manuals..."):
        try:
            turn = agent.ask(q, lang, worker=worker)
        except Exception as e:  # noqa: BLE001
            st.error(f"Gemini did not answer ({str(e)[:140]}). Try again in a minute.")
            return
    for m in ss.chat:                             # an older unanswered Yes/No card expires
        if m["role"] == "bot":
            m["turn"].pending = None
    ss.chat += [{"role": "me", "text": q, "spoken": bool(spoken_lang)},
                {"role": "bot", "turn": turn, "asked": bool(turn.pending)}]
    ss.turn = turn
    ss.spoken, ss.spoken_for = None, None


def use_example(text: str) -> None:
    ss.question = text


def worker_screen() -> None:
    if ss.pop("clear_q", False):
        ss.question = ""
    if not ss.chat:
        st.markdown('<p class="fm-hint">Ask about any machine: an alarm code, a noise, a part. FloorMitra reads the '
                    'English manuals and answers in your language. Nothing is raised until you say yes.</p>',
                    unsafe_allow_html=True)
        cols = st.columns(2)
        for i, e in enumerate(EXAMPLES):
            cols[i % 2].button(e, key=f"ex_{i}", on_click=use_example, args=(e,), use_container_width=True)

    for i, m in enumerate(ss.chat):
        if m["role"] == "me":
            st.markdown(f'<div class="fm-me">{"🎤 " if m.get("spoken") else ""}{esc(m["text"])}</div>',
                        unsafe_allow_html=True)
        elif m["role"] == "done":
            st.markdown(f'<div class="fm-done">✔ {esc(m["text"])}</div>', unsafe_allow_html=True)
        else:
            turn = m["turn"]
            st.markdown(bot_html(turn, m.get("asked", False)), unsafe_allow_html=True)
            last = i == len(ss.chat) - 1 or (i == len(ss.chat) - 2 and ss.chat[-1]["role"] == "done")
            if last:
                if st.button("🔊 Hear the answer", key="hear"):
                    with st.spinner("Preparing the voice..."):
                        ss.spoken, ss.spoken_for = voice.speak(turn.answer), id(turn)
                if ss.get("spoken") and ss.get("spoken_for") == id(turn):
                    st.audio(ss.spoken, format="audio/wav", autoplay=True)
            if turn.pending:
                st.markdown(f'<div class="fm-act">✋ <b>Shall I do this?</b><br>{esc(turn.pending["summary"])}</div>',
                            unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button("✅ Yes, do it", key="yes", type="primary", use_container_width=True):
                    ss.chat.append({"role": "done", "text": agent.confirm(turn.pending, yes=True)})
                    turn.pending = None
                    st.rerun()
                if c2.button("❌ No", key="no", use_container_width=True):
                    ss.chat.append({"role": "done", "text": agent.confirm(turn.pending, yes=False)})
                    turn.pending = None
                    st.rerun()
            if last:
                with st.expander("🧭 What FloorMitra did"):
                    for s in turn.steps:
                        st.write(s)
                    for s in turn.sources:
                        st.caption(f"📘 {s['source']}")
                    st.caption(f"Model: {turn.model} · tokens: {turn.tokens:,} · {turn.latency_s} s")

    st.markdown("&nbsp;", unsafe_allow_html=True)
    audio = st.audio_input("🎤 Tap to speak, tap again to stop", key="mic")
    if audio is not None:
        data = audio.getvalue()
        h = hashlib.md5(data).hexdigest()
        if ss.get("heard_hash") != h:
            with st.spinner("Listening..."):
                try:
                    heard = voice.listen(data, "audio/wav", LANGS[lang_label])
                    ss.question = ss.heard_text = heard["text"]
                    ss.heard_lang = heard["language"]
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not hear that ({str(e)[:120]}). Please try again.")
            ss.heard_hash = h
    st.text_area("Your question (check the words, or type)", key="question", height=80,
                 placeholder="Lathe 2 shows E-205, what do I do?")
    if st.button("Ask FloorMitra", key="ask", type="primary", use_container_width=True):
        spoken = ss.get("heard_lang", "") if ss.question and ss.question == ss.get("heard_text") else ""
        before = len(ss.chat)
        ask(ss.question, spoken)
        if len(ss.chat) > before:
            ss.clear_q = True       # empty the box on the next run (a widget's value can't change after it is drawn)
            st.rerun()


def my_tickets_screen() -> None:
    mine = [t for t in plant.tickets() if t["reported_by"] == worker]
    st.markdown(f"**Tickets raised by {esc(worker)}**")
    if not mine:
        st.caption("None yet. Ask about a fault on the Ask screen and say yes.")
    for t in mine:
        with st.container(border=True):
            st.markdown(f'**#{t["id"]} {esc(t["machine_id"])}** &nbsp; <span class="fm-sev {t["severity"]}">'
                        f'{t["severity"]}</span> &nbsp; {t["status"]}<br>{esc(t["problem"])}', unsafe_allow_html=True)


def supervisor_screen() -> None:
    s = plant.summary()
    st.markdown(
        '<div class="fm-cards">'
        f'<div class="fm-card"><div class="n">{s["open_tickets"]}</div><div class="t">Open tickets</div></div>'
        f'<div class="fm-card red"><div class="n">{s["critical_or_high"]}</div><div class="t">High / critical</div></div>'
        f'<div class="fm-card"><div class="n">{s["open_work_orders"]}</div><div class="t">Open work orders</div></div>'
        f'<div class="fm-card amber"><div class="n">{s["spares_below_minimum"]}</div><div class="t">Spares low</div></div>'
        "</div>", unsafe_allow_html=True)

    st.markdown("**Open tickets**")
    open_t = plant.tickets(open_only=True)
    if not open_t:
        st.caption("No open tickets. They appear here when a worker says yes.")
    has_wo = {w["ticket_id"] for w in plant.work_orders()}
    for t in open_t:
        with st.container(border=True):
            st.markdown(f'**#{t["id"]} {esc(t["machine_id"])}** &nbsp; <span class="fm-sev {t["severity"]}">'
                        f'{t["severity"]}</span><br>{esc(t["problem"])}<br><span class="fm-hint">'
                        f'{esc(t["reported_by"])} · {esc(t["language"])} · “{esc(t["worker_words"][:80])}”</span>',
                        unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if t["id"] in has_wo:
                c1.caption("Work order made")
            elif c1.button("Make work order", key=f"wo_{t['id']}", use_container_width=True):
                plant.create_work_order(t["machine_id"], f"Fix: {t['problem'][:80]}", "", t["severity"],
                                        ticket_id=t["id"])
                st.rerun()
            if c2.button("Close (fixed)", key=f"close_{t['id']}", use_container_width=True):
                plant.close_ticket(t["id"])
                st.rerun()

    wos = [w for w in plant.work_orders() if w["status"] == "open"]
    with st.expander(f"🔧 Work orders ({len(wos)} open)"):
        for w in wos:
            st.markdown(f'#{w["id"]} **{esc(w["machine_id"])}** · {esc(w["task"])}'
                        + (f' · part {esc(w["part_no"])}' if w["part_no"] else "") + f' · {w["priority"]}')
        if not wos:
            st.caption("None open.")
    low = [r for r in plant.spares_all() if r["below_minimum"]]
    with st.expander(f"📦 Spares below minimum ({len(low)})"):
        for r in low:
            st.markdown(f'**{r["part_no"]}** {esc(r["name"])} · {r["qty"]} left (min {r["min_qty"]}) · {r["bin"]}')
    with st.expander("🏭 Machines"):
        for m in plant.machines():
            st.markdown(f'{"🔴" if m["status"] == "down" else "🟢"} **{m["id"]}** · {esc(m["name"])} · {m["line"]}')

    if st.button("📝 Write the shift report with Gemini", key="report", use_container_width=True):
        if offline:
            ss.shift_report = "(offline demo) " + str(plant.summary())
        else:
            with st.spinner("Gemini is writing the report..."):
                try:
                    ss.shift_report = write_text(shift_report_prompt(plant))
                except Exception as e:  # noqa: BLE001
                    ss.shift_report = f"Could not write the report: {str(e)[:160]}"
    if ss.get("shift_report"):
        st.markdown(f'<div class="fm-report">📝 <b>Shift report (Gemini)</b></div>', unsafe_allow_html=True)
        st.markdown(ss.shift_report)


if nav.startswith("🎤"):
    worker_screen()
elif nav.startswith("🎫"):
    my_tickets_screen()
else:
    supervisor_screen()
st.caption("Guidance only, from the plant's own manuals. Follow lockout (SOP-LOTO-01) and your supervisor. "
           "Sample data; fictional machines.")
