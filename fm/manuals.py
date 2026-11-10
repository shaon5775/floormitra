"""Search the plant's English manuals and SOPs.

Manuals are split into sections ("## ..." headings). Search is a small BM25 over English words, with a strong
boost for exact alarm codes (E-205, A-01, H-11) and part numbers. The worker may speak Bengali or Hindi: the agent
(Gemini) turns the question into an English search query first, so the manuals can stay in English.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

MANUAL_DIR = Path(__file__).resolve().parent.parent / "data" / "manuals"
STOP = set("a an the is are was be to of in on at for and or not no it this that with by as do does my our your "
           "what why how when which from if then there their can will should i we you he she they me".split())
CODE = re.compile(r"\b[A-Z]{1,3}-\d{1,4}\b")


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower()) if w not in STOP and len(w) > 1]


@dataclass
class Section:
    manual: str        # file stem, e.g. "CL-200_cnc_lathe"
    title: str         # manual title line
    heading: str       # section heading
    text: str
    machine_type: str

    @property
    def source(self) -> str:
        return f"{self.title.split(' — ')[0]} › {self.heading}"


class Manuals:
    def __init__(self, folder: Path = MANUAL_DIR):
        self.sections: list[Section] = []
        for path in sorted(folder.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            title = raw.splitlines()[0].lstrip("# ").strip()
            mtype = re.search(r"Machine type:\s*(\w+)", raw)
            mtype = mtype.group(1) if mtype else "all"
            for part in re.split(r"\n(?=## )", raw)[1:]:
                head, _, body = part.partition("\n")
                self.sections.append(Section(path.stem, title, head.lstrip("# ").strip(), body.strip(), mtype))
        self._index()

    def _index(self) -> None:
        self.docs = [words(f"{s.title} {s.heading} {s.text}") for s in self.sections]
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df: dict[str, int] = {}
        for d in self.docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def search(self, query: str, machine_type: str = "", k: int = 3) -> list[dict]:
        q = words(query)
        codes = {c.lower() for c in CODE.findall(query.upper())}
        scored = []
        for s, d in zip(self.sections, self.docs):
            if machine_type and s.machine_type not in (machine_type, "all"):
                continue
            tf = {}
            for w in d:
                tf[w] = tf.get(w, 0) + 1
            score = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    score += self.idf.get(w, 0) * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(d) / self.avg))
            score += 6.0 * sum(1 for c in codes if c in d)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [{"source": s.source, "manual": s.manual, "text": s.text[:1800], "score": round(sc, 2)}
                for sc, s in scored[:k]]
