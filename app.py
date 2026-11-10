"""FloorMitra demo app.   Run:  streamlit run app.py"""
from __future__ import annotations

import hashlib

import streamlit as st

from fm.agent import shift_report_prompt
from fm.config import build, gemini_key, write_text
from fm.plant import Plant

st.set_page_config(page_title="FloorMitra", page_icon="🛠️", layout="wide")


@st.cache_resource
def shared_plant() -> Plant:
    """One plant for every browser: a ticket raised on the worker's phone appears on the supervisor's screen."""
    return Plant()


plant = shared_plant()
LANGS = {"Auto-detect": "", "বাংলা (Bengali)": "bn", "हिन्दी (Hindi)": "hi", "English": "en",
         "Hinglish": "hinglish", "Banglish": "banglish"}
EXAMPLES = ["দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?",
            "Compressor pe A-01 alarm aa raha hai, temperature high",
            "पैकिंग लाइन का कन्वेयर रोलर से बहुत आवाज़ आ रही है",
            "Spindle belt SB-1250 store-e koyta ache?"]

with st.sidebar:
    st.markdown("## 🛠️ FloorMitra")
    screen = st.radio("Screen", ["👷 Worker (voice)", "🧑‍💼 Supervisor"], key="screen")
    has_key = bool(gemini_key())
    offline = st.toggle("Offline demo (no API key)", value=not has_key,
                        help="Rule-based stand-in for Gemini, so the flow can be tried without a key.")
    worker = st.text_input("Your name", value="Ravi (Line 1)", key="worker")
    lang_label = st.selectbox("Your language", list(LANGS), key="lang")
    st.markdown("**Try saying:**\n" + "\n".join(f"- {e}" for e in EXAMPLES))
    st.caption("Sample plant: 6 machines, 5 English manuals/SOPs, a mock maintenance system. "
               "Answers come only from the manuals; tickets need your 'yes'.")

agent, voice = build(offline=offline, plant=plant)


def run_question(q: str) -> None:
    q = (q or "").strip()
    if not q:
        st.warning("Say or type a question first.")
        return
    with st.spinner("FloorMitra is checking the manuals..."):
        try:
            st.session_state.turn = agent.ask(q, LANGS[lang_label], worker=worker)
        except Exception as e:  # noqa: BLE001
            st.error(f"Gemini did not answer ({str(e)[:160]}). Please try again in a minute.")
            return
    st.session_state.spoken = None
    st.session_state.done_msg = None


def worker_screen() -> None:
    st.title("👷 FloorMitra — ask about any machine, hands-free")
    st.caption("Speak in Bengali, Hindi, Hinglish, Banglish or English. FloorMitra reads the English manuals for you, "
               "answers in your language with the source, and raises a ticket only when you say yes.")
    speak_tab, type_tab = st.tabs(["🎤 Speak", "⌨️ Type"])
    with speak_tab:
        st.markdown("1. Tap the 🎤 and speak. 2. Tap again to stop. 3. Check the words, then press **Ask FloorMitra**.")
        audio = st.audio_input("Tap to speak", key="mic")
        if audio is not None:
            data = audio.getvalue()
            h = hashlib.md5(data).hexdigest()
            if st.session_state.get("heard_hash") != h:
                with st.spinner("Listening..."):
                    try:
                        heard = voice.listen(data, "audio/wav", LANGS[lang_label])
                        st.session_state["heard"] = heard["text"]
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not hear that ({str(e)[:120]}). Please try again.")
                st.session_state.heard_hash = h
        st.text_area("What FloorMitra heard (you can correct it)", key="heard", height=80)
        if st.button("Ask FloorMitra", key="ask_voice", type="primary"):
            run_question(st.session_state.get("heard", ""))
    with type_tab:
        st.text_area("Type your question", key="typed", height=80, placeholder=EXAMPLES[0])
        if st.button("Ask FloorMitra", key="ask_typed", type="primary"):
            run_question(st.session_state.get("typed", ""))

    turn = st.session_state.get("turn")
    if not turn:
        return
    st.divider()
    st.info(f"Question: {turn.question}")
    st.markdown(f"### {turn.answer}")
    if st.button("🔊 Hear the answer", key="hear"):
        with st.spinner("Preparing the voice..."):
            st.session_state.spoken = voice.speak(turn.answer)
            st.session_state.spoken_for = turn.question
    if st.session_state.get("spoken") and st.session_state.get("spoken_for") == turn.question:
        st.audio(st.session_state.spoken, format="audio/wav", autoplay=True)

    if turn.pending:
        with st.container(border=True):
            st.markdown(f"**✋ Waiting for your yes:** {turn.pending['summary']}")
            c1, c2 = st.columns(2)
            yes = c1.button("✅ Yes, do it", key="yes", type="primary")
            no = c2.button("❌ No", key="no")
            if yes or no:
                st.session_state.done_msg = agent.confirm(turn.pending, yes=yes)
                turn.pending = None
                st.rerun()
    if st.session_state.get("done_msg"):
        st.success(st.session_state.done_msg)

    if turn.sources:
        with st.expander(f"📘 Source in the manual ({len(turn.sources)})"):
            for s in turn.sources:
                st.markdown(f"**{s['source']}**")
                st.text(s["text"][:900])
    with st.expander("🧭 What FloorMitra did (decision trace)"):
        for step in turn.steps:
            st.write(step)
        st.caption(f"Model: {turn.model} · tokens: {turn.tokens:,} · time: {turn.latency_s} s")


def supervisor_screen() -> None:
    st.title("🧑‍💼 Supervisor — live floor view")
    s = plant.summary()
    cols = st.columns(5)
    for col, (label, key) in zip(cols, [("Open tickets", "open_tickets"), ("High / critical", "critical_or_high"),
                                         ("Machines down", "machines_down"), ("Open work orders", "open_work_orders"),
                                         ("Spares below minimum", "spares_below_minimum")]):
        col.metric(label, s[key])

    st.subheader("Fault tickets")
    tickets = plant.tickets()
    if tickets:
        st.dataframe([{k: t[k] for k in ("id", "at", "machine_id", "severity", "status", "problem", "reported_by",
                                         "language", "worker_words", "source")} for t in tickets],
                     hide_index=True, use_container_width=True)
        open_ids = [t["id"] for t in tickets if t["status"] != "closed"]
        if open_ids:
            c1, c2 = st.columns([1, 3])
            tid = c1.selectbox("Ticket", open_ids, key="close_id")
            if c2.button("Mark fixed and close", key="close"):
                plant.close_ticket(int(tid))
                st.rerun()
    else:
        st.caption("No tickets yet. Ask something on the Worker screen.")

    st.subheader("Work orders")
    wos = plant.work_orders()
    if wos:
        st.dataframe(wos, hide_index=True, use_container_width=True)
    else:
        st.caption("No work orders yet.")

    left, right = st.columns(2)
    with left:
        st.subheader("Machines")
        st.dataframe(plant.machines(), hide_index=True, use_container_width=True)
    with right:
        st.subheader("Spare stock")
        st.dataframe([{**r, "below_minimum": "⚠️" if r["below_minimum"] else ""} for r in plant.spares_all()],
                     hide_index=True, use_container_width=True)

    st.subheader("Shift handover report")
    if st.button("📝 Write the shift report with Gemini", key="report"):
        if offline:
            st.session_state.report = "(offline demo) " + str(plant.summary())
        else:
            with st.spinner("Gemini is writing the report..."):
                try:
                    st.session_state.report = write_text(shift_report_prompt(plant))
                except Exception as e:  # noqa: BLE001
                    st.session_state.report = f"Could not write the report: {str(e)[:160]}"
    if st.session_state.get("report"):
        st.markdown(st.session_state.report)


if screen.startswith("👷"):
    worker_screen()
else:
    supervisor_screen()
st.caption("Guidance only, from the plant's own manuals. Follow lockout (SOP-LOTO-01) and your supervisor's "
           "instructions. Sample data; fictional machines.")
