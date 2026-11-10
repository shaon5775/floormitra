"""FloorMitra agent: Gemini function calling over the plant's manuals and maintenance system.

Read-only tools run at once (search manuals, machine status, spare stock). Write tools (raise a fault ticket,
create a work order) are NEVER run by the model: they become a pending action that the worker must confirm with
a spoken or tapped "yes". Every step is kept as a trace so a supervisor can see why the agent did what it did.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .lang import CONFIRM_ASK, DONE, NAMES, guess_language, phrase
from .manuals import CODE, Manuals
from .plant import Plant

WRITE_TOOLS = {"raise_fault_ticket", "create_work_order"}

TOOLS = [
    {"name": "search_manuals",
     "description": "Search the plant's English machine manuals and safety SOPs. ALWAYS call this before giving "
                    "any how-to, alarm, safety or repair answer. Write the query in English.",
     "parameters": {"type": "OBJECT", "properties": {
         "query_en": {"type": "STRING", "description": "Short English search query, include alarm codes like E-205"},
         "machine_type": {"type": "STRING", "description": "Optional: cnc_lathe, air_compressor, conveyor, "
                                                           "injection_moulding"}},
         "required": ["query_en"]}},
    {"name": "get_machine",
     "description": "Status of one machine and its open fault tickets.",
     "parameters": {"type": "OBJECT", "properties": {
         "machine_id": {"type": "STRING", "description": "Machine id, e.g. L1-LATHE-02"}}, "required": ["machine_id"]}},
    {"name": "check_spare_stock",
     "description": "How many of a spare part are in the store, and where. Part number (e.g. SB-1250) or name.",
     "parameters": {"type": "OBJECT", "properties": {
         "part": {"type": "STRING", "description": "Part number or part name in English"}}, "required": ["part"]}},
    {"name": "raise_fault_ticket",
     "description": "Raise a fault ticket for maintenance. Use when the worker reports a fault the manual says "
                    "needs maintenance, or asks for a ticket. The worker will be asked to confirm first.",
     "parameters": {"type": "OBJECT", "properties": {
         "machine_id": {"type": "STRING"},
         "problem_en": {"type": "STRING", "description": "One English sentence for the maintenance team"},
         "severity": {"type": "STRING", "description": "low, medium, high (machine must stop) or critical (safety)"}},
         "required": ["machine_id", "problem_en", "severity"]}},
    {"name": "create_work_order",
     "description": "Create a maintenance work order (a planned repair job), optionally reserving a spare part. "
                    "The worker or supervisor will be asked to confirm first.",
     "parameters": {"type": "OBJECT", "properties": {
         "machine_id": {"type": "STRING"},
         "task_en": {"type": "STRING", "description": "The job in English, e.g. Replace spindle belt"},
         "part_no": {"type": "STRING", "description": "Spare part number to reserve, or empty"},
         "priority": {"type": "STRING", "description": "low, medium, high or critical"}},
         "required": ["machine_id", "task_en", "priority"]}},
]

SYSTEM = """You are FloorMitra, a hands-free voice helper for factory-floor workers in an Indian plant.
Workers talk to you while working, often in Bengali, Hindi, Hinglish or Banglish. The manuals are in English.

Rules:
1. For any how-to, alarm code, noise, leak, quality or safety question, FIRST call search_manuals with an English
   query. Answer ONLY from what the manuals say. If the manuals do not cover it, say so and suggest a ticket.
2. Safety first: if the job needs hands inside a machine, say lockout (SOP-LOTO-01) in the first sentence.
3. If the worker reports a fault that the manual says needs maintenance (or it repeats, or the worker asks), call
   raise_fault_ticket. If a spare part is needed, call check_spare_stock, and if the worker or supervisor asks for
   a repair job, call create_work_order. These write tools only PROPOSE the action; the worker confirms on screen.
   NEVER say a ticket or work order "is raised/created/done": say you have prepared it and ask "Shall I raise it?".
4. Reply in {language}. {script_rule} Short and spoken-style: at most 4 short sentences, numbers as digits, no
   markdown, no tables, no URLs. Alarm codes and part numbers stay as they are (E-205, SB-1250).

Machines on the floor (id - name - type - place):
{machines}
"""


SCRIPT_RULE = {   # live 11 Nov 2026: without this, Bengali and Hindi answers came back in Latin letters
    "bn": "Write in Bengali letters (বাংলা লিপি), e.g. 'কুল্যান্ট লেভেল কম।' - NOT in English/Latin letters.",
    "hi": "Write in Devanagari letters (देवनागरी), e.g. 'कूलेंट लेवल कम है।' - NOT in English/Latin letters.",
    "hinglish": "Write Hindi in Latin letters (Hinglish), e.g. 'Coolant level kam hai.'",
    "banglish": "Write Bengali in Latin letters (Banglish), e.g. 'Coolant level kom ache.'",
    "en": "Write in simple English.",
}
NATIVE = {"bn", "hi", "ta", "te", "gu", "kn", "ml", "or", "pa"}


@dataclass
class Turn:
    question: str
    language: str
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    pending: dict | None = None          # {"tool": ..., "args": {...}, "summary": "..."} waiting for "yes"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    model: str = ""

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _retry(call, tries: int = 5):
    for attempt in range(tries):
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            if attempt == tries - 1 or not any(c in str(e) for c in ("429", "RESOURCE_EXHAUSTED", "503", "504",
                                                                     "UNAVAILABLE", "DEADLINE")):
                raise
            print(f"  (Gemini busy or rate-limited, retrying in {10 * (attempt + 1)}s)")
            time.sleep(10 * (attempt + 1))


class GeminiBrain:
    """One conversation with Gemini using native function calling (automatic calling switched off, so every
    tool call passes through our own code and the confirmation rule)."""

    def __init__(self, api_key: str, model: str):
        from google import genai
        from google.genai import types

        self.t = types
        self.model = model
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1)))

    def start(self, system: str, question: str) -> None:
        t = self.t
        self.cfg = t.GenerateContentConfig(
            system_instruction=system, temperature=0.2,
            tools=[t.Tool(function_declarations=[t.FunctionDeclaration(**d) for d in TOOLS])],
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True))
        self.contents = [t.Content(role="user", parts=[t.Part(text=question)])]

    def step(self, results: list[tuple[str, dict]] | None = None) -> tuple[list[tuple[str, dict]], str, int, int]:
        t = self.t
        if results:
            self.contents.append(t.Content(role="user", parts=[
                t.Part.from_function_response(name=n, response={"result": r}) for n, r in results]))
        resp = _retry(lambda: self.client.models.generate_content(model=self.model, contents=self.contents,
                                                                  config=self.cfg))
        u = getattr(resp, "usage_metadata", None)
        tin, tout = getattr(u, "prompt_token_count", 0) or 0, getattr(u, "candidates_token_count", 0) or 0
        calls = [(c.name, dict(c.args or {})) for c in (resp.function_calls or [])]
        if calls:
            self.contents.append(resp.candidates[0].content)   # keeps Gemini's thought signatures
            return calls, "", tin, tout
        self.contents.append(resp.candidates[0].content)
        return [], (resp.text or "").strip(), tin, tout

    def rewrite(self, instruction: str) -> tuple[str, int, int]:
        """Follow-up in the same conversation, no tools (used to fix the script of an answer)."""
        t = self.t
        self.contents.append(t.Content(role="user", parts=[t.Part(text=instruction)]))
        cfg = t.GenerateContentConfig(system_instruction=self.cfg.system_instruction, temperature=0.2)
        resp = _retry(lambda: self.client.models.generate_content(model=self.model, contents=self.contents,
                                                                  config=cfg))
        u = getattr(resp, "usage_metadata", None)
        return ((resp.text or "").strip(), getattr(u, "prompt_token_count", 0) or 0,
                getattr(u, "candidates_token_count", 0) or 0)


# --- offline brain: fixed rules so the app and tests run without a key ------------------------------------------
TYPE_WORDS = [
    ("cnc_lathe", r"lathe|লেদ|লেথ|लेथ|cnc|spindle|chuck|coolant|কুল্যান্ট|कूलेंट"),
    ("air_compressor", r"compressor|কম্প্রেসার|कंप्रेसर|air pressure|হাওয়ার চাপ|हवा का दबाव"),
    ("conveyor", r"conveyor|কনভেয়ার|कन्वेयर|roller|রোলার|रोलर|belt.*(line|packing)"),
    ("injection_moulding", r"mould|mold|মোল্ড|मोल्ड|heater|হিটার|हीटर|imm"),
]
STOCK = r"stock|spare|স্টক|স্পেয়ার|स्टॉक|स्पेयर|kitne|কটা|কতগুলো"
FAULT = r"noise|sound|আওয়াজ|शोर|आवाज|leak|লিক|लीक|alarm|error|not working|বন্ধ|बंद|stop|ticket|টিকিট|टिकट|squeal|[A-Z]-\d"
SECOND = r"\b2\b|two|দুই|দু নম্বর|दो|second|০২|02"


class MockBrain:
    model = "mock"

    def __init__(self, plant: Plant):
        self.plant = plant

    def start(self, system: str, question: str) -> None:
        self.q, self.stage, self.found = question, 0, []

    def rewrite(self, instruction: str) -> tuple[str, int, int]:
        return "", 0, 0   # offline demo keeps the English text

    def _machine(self) -> tuple[str, str]:
        q = self.q.lower()
        mtype = next((m for m, pat in TYPE_WORDS if re.search(pat, q)), "cnc_lathe")
        ids = [m["id"] for m in self.plant.machines() if m["type"] == mtype]
        return (ids[1] if len(ids) > 1 and re.search(SECOND, q) else ids[0]), mtype

    def step(self, results=None):
        self.stage += 1
        mid, mtype = self._machine()
        codes = CODE.findall(self.q.upper())
        cost = (len(self.q) + 400) // 4
        if self.stage == 1:
            if re.search(STOCK, self.q, re.I):
                part = codes[0] if codes else {"cnc_lathe": "SB-1250", "air_compressor": "AIF-75",
                                               "conveyor": "RL-50", "injection_moulding": "HB-150"}[mtype]
                return [("check_spare_stock", {"part": part})], "", cost, 20
            return [("search_manuals", {"query_en": " ".join(codes) + " noise alarm problem", "machine_type": mtype})], "", cost, 20
        if self.stage == 2:
            name, res = results[0]
            if name == "search_manuals":
                self.found = res
                if re.search(FAULT, self.q, re.I):
                    return [("raise_fault_ticket", {"machine_id": mid, "problem_en": f"Worker reports: {self.q[:120]}",
                                                    "severity": "medium"})], "", cost, 30
            else:
                rows = res if isinstance(res, list) else []
                return [], "(offline demo) " + ("; ".join(f"{r['part_no']} {r['name']}: {r['qty']} in {r['bin']}"
                                                          for r in rows) or "Part not found."), cost, 40
        first = self.found[0] if isinstance(self.found, list) and self.found else {}
        lines = [ln for ln in first.get("text", "").splitlines() if ln.strip() and not ln.startswith("|---")]
        hit = [ln for ln in lines if any(c in ln for c in codes)]
        text = (hit or lines or ["Nothing found in the manuals."])[0].replace("|", " ").strip()
        return [], f"(offline demo) From the manual: {text[:220]}", cost, 60


class FloorMitra:
    def __init__(self, brain, plant: Plant, manuals: Manuals):
        self.brain, self.plant, self.manuals = brain, plant, manuals

    def _system(self, language: str) -> str:
        machines = "\n".join(f"- {m['id']} - {m['name']} - {m['type']} - {m['line']}" for m in self.plant.machines())
        return SYSTEM.format(language=NAMES.get(language, language), script_rule=SCRIPT_RULE.get(
            language, "Use that language's own script."), machines=machines)

    def _run_tool(self, name: str, args: dict, turn: Turn) -> dict | list:
        if name == "search_manuals":
            hits = self.manuals.search(args.get("query_en", ""), args.get("machine_type", ""))
            for h in hits:
                if h["source"] not in [s["source"] for s in turn.sources]:
                    turn.sources.append(h)
            turn.steps.append(f"🔎 search_manuals(\"{args.get('query_en', '')}\") → "
                              + (", ".join(h["source"] for h in hits) or "nothing found"))
            return [{"source": h["source"], "text": h["text"]} for h in hits] or {"found": False}
        if name == "get_machine":
            m = self.plant.machine(args.get("machine_id", ""))
            turn.steps.append(f"🏭 get_machine({args.get('machine_id')}) → {m['status'] if m else 'unknown id'}")
            return m or {"error": "unknown machine id"}
        if name == "check_spare_stock":
            rows = self.plant.spare(args.get("part", ""))
            turn.steps.append(f"📦 check_spare_stock({args.get('part')}) → "
                              + (", ".join(f"{r['part_no']}: {r['qty']} in {r['bin']}" for r in rows) or "not found"))
            return rows or {"found": False}
        if name in WRITE_TOOLS:
            if turn.pending:   # one action at a time
                return {"status": "another action is already waiting for confirmation"}
            turn.pending = {"tool": name, "args": args, "summary": self.describe(name, args)}
            turn.steps.append(f"✋ {name} PROPOSED (waiting for the worker's yes): {turn.pending['summary']}")
            return {"status": "proposed; the worker must confirm on screen before it is created"}
        return {"error": f"unknown tool {name}"}

    @staticmethod
    def describe(name: str, a: dict) -> str:
        if name == "raise_fault_ticket":
            return f"Fault ticket for {a.get('machine_id')} ({a.get('severity', 'medium')}): {a.get('problem_en', '')}"
        part = f", reserve part {a['part_no']}" if a.get("part_no") else ""
        return f"Work order for {a.get('machine_id')} ({a.get('priority', 'medium')}): {a.get('task_en', '')}{part}"

    def ask(self, question: str, language: str = "", worker: str = "worker") -> Turn:
        t0 = time.time()
        language = language or guess_language(question)
        turn = Turn(question=question, language=language, model=self.brain.model)
        self.brain.start(self._system(language), question)
        results = None
        for _ in range(6):
            calls, text, tin, tout = self.brain.step(results)
            turn.input_tokens += tin
            turn.output_tokens += tout
            if not calls:
                turn.answer = text
                break
            results = [(n, self._run_tool(n, a, turn)) for n, a in calls]
        else:
            turn.answer = "Sorry, I could not finish. Please ask your supervisor."
        if language in NATIVE and turn.answer and guess_language(turn.answer) != language:
            # wrong letters (e.g. Bengali written in Latin): ask once to rewrite, keeping the content
            text, tin, tout = self.brain.rewrite(f"Rewrite your last answer in {NAMES.get(language, language)} "
                                                 f"using its own script. {SCRIPT_RULE.get(language, '')} "
                                                 "Same content, same length. Only the answer.")
            turn.input_tokens += tin
            turn.output_tokens += tout
            if text:
                turn.answer = text
                turn.steps.append(f"🔤 rewrote the answer in {NAMES.get(language, language)} script")
        if turn.pending and not re.search(r"\?|？|।|confirm|হ্যাঁ|हाँ", turn.answer[-80:]):
            turn.answer = f"{turn.answer} {phrase(CONFIRM_ASK, language)}".strip()
        if turn.pending:
            turn.pending.update(worker=worker, question=question, language=language,
                                source=turn.sources[0]["source"] if turn.sources else "")
        turn.latency_s = round(time.time() - t0, 2)
        return turn

    def confirm(self, pending: dict, yes: bool) -> str:
        lang = pending.get("language", "en")
        if not yes:
            return phrase(DONE["cancel"], lang)
        a = pending["args"]
        if pending["tool"] == "raise_fault_ticket":
            r = self.plant.raise_ticket(a["machine_id"], a.get("problem_en", ""), a.get("severity", "medium"),
                                        reported_by=pending.get("worker", "worker"), language=lang,
                                        worker_words=pending.get("question", ""), source=pending.get("source", ""))
            return phrase(DONE["ticket"], lang, id=r["ticket_id"], machine=r["machine_id"])
        r = self.plant.create_work_order(a["machine_id"], a.get("task_en", ""), a.get("part_no", "") or "",
                                         a.get("priority", "medium"))
        return phrase(DONE["work_order"], lang, id=r["work_order_id"], machine=r["machine_id"])


def shift_report_prompt(plant: Plant) -> str:
    return ("Write a short English shift handover note for the maintenance supervisor (max 8 bullet points): "
            "what is down, open tickets by severity, work orders, spare parts below minimum and what to order. "
            "Data:\n" + json.dumps({"summary": plant.summary(), "open_tickets": plant.tickets(open_only=True),
                                     "work_orders": plant.work_orders(),
                                     "low_stock": [s for s in plant.spares_all() if s["below_minimum"]]},
                                    default=str)[:12000])
