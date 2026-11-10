"""A small mock maintenance system (CMMS) in SQLite: machines, spare stock, fault tickets, work orders.

A real plant would connect FloorMitra to SAP PM, Maximo or similar; the agent only talks to these functions,
so swapping the backend does not change the agent.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

MACHINES = [
    ("L1-LATHE-01", "CNC Lathe CL-200 #1", "cnc_lathe", "Line 1", "running"),
    ("L1-LATHE-02", "CNC Lathe CL-200 #2", "cnc_lathe", "Line 1", "running"),
    ("UT-COMP-01", "Screw Air Compressor AC-75", "air_compressor", "Utility room", "running"),
    ("L2-CONV-01", "Belt Conveyor CV-3 (packing)", "conveyor", "Line 2", "running"),
    ("L2-CONV-02", "Belt Conveyor CV-3 (dispatch)", "conveyor", "Line 2", "running"),
    ("L3-IMM-01", "Injection Moulding IM-150", "injection_moulding", "Line 3", "running"),
]
SPARES = [  # part_no, name, machine_type, qty, min_qty, bin
    ("SB-1250", "Spindle drive belt", "cnc_lathe", 2, 2, "Store A-3"),
    ("CP-60", "Coolant pump 60 W", "cnc_lathe", 0, 1, "Store A-4"),
    ("AF-200", "Drive cabinet air filter", "cnc_lathe", 6, 2, "Store A-1"),
    ("CI-12", "Carbide insert (box of 10)", "cnc_lathe", 14, 5, "Tool crib"),
    ("AIF-75", "Compressor intake air filter", "air_compressor", 1, 2, "Store B-2"),
    ("OF-75", "Compressor oil filter", "air_compressor", 3, 1, "Store B-2"),
    ("SE-75", "Oil separator element", "air_compressor", 1, 1, "Store B-3"),
    ("OIL-46", "Compressor oil ISO VG 46, 20 L", "air_compressor", 2, 1, "Oil room"),
    ("RL-50", "Conveyor carrying roller 50 mm", "conveyor", 8, 4, "Store C-1"),
    ("BL-CV3", "Conveyor belt, 10 m", "conveyor", 1, 1, "Store C-5"),
    ("GM-1", "Gear motor 1.1 kW", "conveyor", 0, 1, "Store C-6"),
    ("HB-150", "Barrel heater band 1.5 kW", "injection_moulding", 2, 2, "Store D-2"),
    ("GS-01", "Safety gate switch", "injection_moulding", 1, 1, "Store D-4"),
    ("TC-K", "Thermocouple type K", "injection_moulding", 5, 2, "Store D-4"),
]
SEVERITIES = ("low", "medium", "high", "critical")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class Plant:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._setup()

    def _setup(self) -> None:
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS machines (id TEXT PRIMARY KEY, name TEXT, type TEXT, line TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS spares (part_no TEXT PRIMARY KEY, name TEXT, machine_type TEXT, qty INTEGER,
                min_qty INTEGER, bin TEXT);
            CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, machine_id TEXT,
                problem TEXT, severity TEXT, status TEXT, reported_by TEXT, language TEXT, worker_words TEXT,
                source TEXT);
            CREATE TABLE IF NOT EXISTS work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, ticket_id INTEGER,
                machine_id TEXT, task TEXT, part_no TEXT, priority TEXT, status TEXT, assigned_to TEXT);
            """)
            if not self.db.execute("SELECT COUNT(*) FROM machines").fetchone()[0]:
                self.db.executemany("INSERT INTO machines VALUES (?,?,?,?,?)", MACHINES)
                self.db.executemany("INSERT INTO spares VALUES (?,?,?,?,?,?)", SPARES)
            self.db.commit()

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # ---- read-only tools -------------------------------------------------------------------------------------
    def machines(self) -> list[dict]:
        return self._rows("SELECT * FROM machines ORDER BY id")

    def machine(self, machine_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM machines WHERE id = ? COLLATE NOCASE", (machine_id.strip(),))
        if not rows:
            return None
        m = rows[0]
        m["open_tickets"] = self._rows("SELECT id, problem, severity, status FROM tickets WHERE machine_id = ? "
                                       "AND status != 'closed' ORDER BY id DESC", (m["id"],))
        return m

    def spare(self, part: str) -> list[dict]:
        """Find spares by part number or by words in the name."""
        p = part.strip()
        rows = self._rows("SELECT * FROM spares WHERE part_no = ? COLLATE NOCASE", (p,))
        if not rows:
            words = [w for w in p.lower().split() if len(w) > 2] or [p.lower()]
            rows = [r for r in self._rows("SELECT * FROM spares")
                    if all(w in (r["name"] + " " + r["part_no"]).lower() for w in words)]
        for r in rows:
            r["in_stock"] = r["qty"] > 0
            r["below_minimum"] = r["qty"] < r["min_qty"]
        return rows

    # ---- write tools (only after the worker confirms) ----------------------------------------------------------
    def raise_ticket(self, machine_id: str, problem: str, severity: str = "medium", reported_by: str = "worker",
                     language: str = "", worker_words: str = "", source: str = "") -> dict:
        m = self.machine(machine_id)
        if not m:
            raise ValueError(f"Unknown machine {machine_id}")
        severity = severity if severity in SEVERITIES else "medium"
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO tickets (at, machine_id, problem, severity, status, reported_by, language, worker_words,"
                " source) VALUES (?,?,?,?,?,?,?,?,?)",
                (_now(), m["id"], problem, severity, "open", reported_by, language, worker_words, source))
            if severity in ("high", "critical"):
                self.db.execute("UPDATE machines SET status = 'down' WHERE id = ?", (m["id"],))
            self.db.commit()
        return {"ticket_id": cur.lastrowid, "machine_id": m["id"], "severity": severity, "status": "open"}

    def create_work_order(self, machine_id: str, task: str, part_no: str = "", priority: str = "medium",
                          ticket_id: int | None = None, assigned_to: str = "maintenance") -> dict:
        m = self.machine(machine_id)
        if not m:
            raise ValueError(f"Unknown machine {machine_id}")
        if ticket_id is None and m["open_tickets"]:
            ticket_id = m["open_tickets"][0]["id"]
        priority = priority if priority in SEVERITIES else "medium"
        reserved = None
        with self.lock:
            if part_no:
                row = self.db.execute("SELECT qty FROM spares WHERE part_no = ? COLLATE NOCASE", (part_no,)).fetchone()
                if row and row[0] > 0:   # reserve one from stock for this job
                    self.db.execute("UPDATE spares SET qty = qty - 1 WHERE part_no = ? COLLATE NOCASE", (part_no,))
                    reserved = True
                elif row:
                    reserved = False
            cur = self.db.execute(
                "INSERT INTO work_orders (at, ticket_id, machine_id, task, part_no, priority, status, assigned_to)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (_now(), ticket_id, m["id"], task, part_no.upper(), priority, "open", assigned_to))
            self.db.commit()
        return {"work_order_id": cur.lastrowid, "machine_id": m["id"], "ticket_id": ticket_id,
                "part_no": part_no.upper(), "part_reserved": reserved, "status": "open"}

    # ---- supervisor -----------------------------------------------------------------------------------------
    def tickets(self, open_only: bool = False) -> list[dict]:
        where = "WHERE status != 'closed'" if open_only else ""
        return self._rows(f"SELECT * FROM tickets {where} ORDER BY id DESC")

    def work_orders(self) -> list[dict]:
        return self._rows("SELECT * FROM work_orders ORDER BY id DESC")

    def spares_all(self) -> list[dict]:
        return self._rows("SELECT *, qty < min_qty AS below_minimum FROM spares ORDER BY machine_type, part_no")

    def close_ticket(self, ticket_id: int) -> None:
        with self.lock:
            row = self.db.execute("SELECT machine_id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            self.db.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
            self.db.execute("UPDATE work_orders SET status = 'done' WHERE ticket_id = ?", (ticket_id,))
            if row:
                still = self.db.execute("SELECT COUNT(*) FROM tickets WHERE machine_id = ? AND status != 'closed' "
                                        "AND severity IN ('high','critical')", (row[0],)).fetchone()[0]
                if not still:
                    self.db.execute("UPDATE machines SET status = 'running' WHERE id = ?", (row[0],))
            self.db.commit()

    def summary(self) -> dict:
        t = self.tickets(open_only=True)
        return {
            "open_tickets": len(t),
            "critical_or_high": sum(1 for x in t if x["severity"] in ("high", "critical")),
            "machines_down": sum(1 for m in self.machines() if m["status"] == "down"),
            "open_work_orders": sum(1 for w in self.work_orders() if w["status"] == "open"),
            "spares_below_minimum": sum(1 for s in self.spares_all() if s["below_minimum"]),
        }
