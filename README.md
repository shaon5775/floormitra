# 🛠️ FloorMitra — a hands-free voice helper for factory workers

Built for **Build with Google Gemini** (Problem Statement 01: Voice-Powered Enterprise Knowledge & Decision Agent).

A machine operator has oily hands, a noisy floor and a manual written in English. FloorMitra lets them just
**speak** — in Bengali, Hindi, Hinglish, Banglish or English:

> "দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?" (Lathe 2 shows E-205, what do I do?)

FloorMitra (Gemini) turns that into an English search, reads the plant's own manuals and SOPs, answers **in the
worker's language with the source section**, reads it aloud, and — only after the worker says **yes** — raises a
fault ticket or creates a work order in the maintenance system. The supervisor sees everything live.

## How it works

```
Worker speaks 🎤 (bn / hi / Hinglish / Banglish / en)
   │  Gemini listens (speech → text in the worker's own script)
   ▼
FloorMitra agent = Gemini function calling (automatic calling OFF: every call passes our code)
   ├─ search_manuals(query_en)      → English manuals + SOPs (BM25 + exact alarm-code match)
   ├─ get_machine(machine_id)       → status + open tickets
   ├─ check_spare_stock(part)       → qty and store bin
   ├─ raise_fault_ticket(...)       ┐  WRITE tools are only PROPOSED.
   └─ create_work_order(...)        ┘  Nothing is written until the worker taps/says "yes".
   ▼
Answer in the worker's language + source section → Gemini speech (🔊 on request)
   ▼
Supervisor screen: open tickets, machines down, work orders, low spares, Gemini shift report
```

- **Grounded:** answers only from the plant's documents; the source section is shown; safety (lockout) first.
- **Human in control:** tickets and work orders need an explicit yes; the decision trace shows every tool call.
- **Multilingual by design:** manuals stay in English; Gemini bridges the language both ways.

## Run it

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...        # free key from https://aistudio.google.com/apikey
streamlit run app.py
python scripts/live_check.py     # 4 questions in 4 languages through the full loop
```

No key? `streamlit run app.py` starts in **offline demo** mode (a rule-based stand-in for Gemini), and
`pytest -q` runs the offline tests.

On Streamlit Community Cloud: point it at `app.py` and add `GEMINI_API_KEY` under *Secrets*.

## Project layout
```
app.py              Streamlit app: Worker (voice) and Supervisor screens
fm/agent.py         the agent: Gemini function calling, confirm-before-write rule, decision trace
fm/manuals.py       search over data/manuals (English manuals and SOPs)
fm/plant.py         mock maintenance system (SQLite): machines, spares, tickets, work orders
fm/voice.py         Gemini speech-to-text and text-to-speech
fm/lang.py          language guess + short spoken confirmations
data/manuals/       5 sample documents (fictional machines CL-200, AC-75, CV-3, IM-150 + lockout SOP)
scripts/live_check.py   live test with a real key
tests/              offline tests
```

## Notes
- All machines, manuals and stock are **fictional sample data** made for this demo.
- FloorMitra gives guidance from the plant's own documents; workers must follow lockout and their supervisor.
- A real plant would connect `fm/plant.py` to its CMMS (SAP PM, Maximo, …) and its own manuals.
