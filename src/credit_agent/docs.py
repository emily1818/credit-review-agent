"""사례(업로드 서류 묶음) 로딩, 은행 내부 DB, 사내 규정 검색(RAG)."""
import json
import math
import re
from collections import Counter

from . import config

# 업로드 슬롯: 문서ID → (파일명, 제목, 필수 여부)
SLOTS = {
    "SUB-01": ("01_여신거래신청서.md", "여신거래신청서", True),
    "SUB-02": ("02_사업계획서.md", "사업계획서", True),
    "SUB-03": ("03_공사도급계약서.md", "공사도급계약서(책임준공 포함)", True),
    "SUB-04": ("04_감정평가서.md", "감정평가서", True),
    "SUB-05": ("05_재무제표.json", "재무제표 (차주 제출)", False),
}
INTERNAL = {  # 내부자료ID → (제목, 민감도, 시스템)
    "INT-01": ("차주 거래현황", "internal", "여신원장 (가상)"),
    "INT-02": ("내부신용등급(CSS)", "restricted", "기업신용평가시스템 (가상)"),
    "INT-03": ("시공사 책임준공 약정 관리현황", "internal", "리스크관리 DB (가상)"),
}
REG_FILES = {"REG-01": "여신업무규정.md", "REG-02": "시설자금_취급세칙.md", "REG-03": "건설여신_심사가이드.md"}


class Case:
    def __init__(self, path):
        self.dir = path
        self.info = json.loads((path / "case.json").read_text(encoding="utf-8"))
        self.id = self.info.get("case_id", path.name)

    @property
    def borrower(self):
        return self.info["borrower"]

    @property
    def contractor(self):
        return self.info["contractor"]

    def has(self, doc_id):
        return (self.dir / SLOTS[doc_id][0]).exists()

    def read(self, doc_id):
        p = self.dir / SLOTS[doc_id][0]
        text = p.read_text(encoding="utf-8")
        return json.loads(text) if p.suffix == ".json" else text


def fields(md):
    """'- 항목: 값' 형식의 행을 dict로."""
    return {k.strip(): v.strip() for k, v in re.findall(r"^- ([^:\n]+):\s*(.+)$", md, re.M)}


def section(md, heading_prefix):
    m = re.search(r"^## " + re.escape(heading_prefix) + r".*?$(.*?)(?=^## |\Z)", md, re.M | re.S)
    return m.group(1) if m else ""


def table(md_section):
    rows = {}
    for name, val in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([-\d,]+)\s*\|", md_section, re.M):
        name = name.replace("*", "").strip()
        if name not in ("항목", "합계"):
            rows[name] = int(val.replace(",", ""))
    return rows


def num(s):
    m = re.search(r"-?[\d,]+(?:\.\d+)?", s or "")
    return float(m.group(0).replace(",", "")) if m else None


# ---- 은행 내부 DB ----
def _bank(name):
    return json.loads((config.BANK / name).read_text(encoding="utf-8"))


def internal_record(rec_id, case):
    title, sens, system = INTERNAL[rec_id]
    b = case.borrower["name"]
    if rec_id == "INT-01":
        r = _bank("borrowers.json")["borrowers"].get(b, {}).get("relationship")
    elif rec_id == "INT-02":
        r = _bank("borrowers.json")["borrowers"].get(b, {}).get("grade")
    else:
        r = _bank("contractors.json")["contractors"].get(case.contractor["name"])
    meta = {"title": title, "sensitivity": sens, "system": system}
    return meta, r


# ---- 규정 RAG: 조문 단위, 문자 bigram BM25 ----
def _articles():
    out = []
    for rid, fn in REG_FILES.items():
        text = (config.BANK / "regulations" / fn).read_text(encoding="utf-8")
        doc_title = re.search(r"^# (.+)$", text, re.M).group(1)
        for m in re.finditer(r"^## (제(\d+)조 \(([^)]+)\))\n(.*?)(?=^## |\Z)", text, re.M | re.S):
            out.append({"id": "{}-{}".format(rid, m.group(2)), "doc": doc_title, "article": m.group(1),
                        "text": m.group(4).strip()})
    return out


def _bigrams(s):
    s = re.sub(r"\s+", "", s)
    return [s[i:i + 2] for i in range(len(s) - 1)]


ARTICLES = _articles()
_DF = Counter(b for a in ARTICLES for b in set(_bigrams(a["article"] + a["text"])))


def search_regulations(query, top_k=3, min_score=0.25):
    q = set(_bigrams(query))
    n = len(ARTICLES)
    scored = []
    for a in ARTICLES:
        tf = Counter(_bigrams(a["article"] * 2 + a["text"]))
        dl = sum(tf.values())
        s = 0.0
        for b in q:
            if b in tf:
                idf = math.log(1 + (n - _DF[b] + 0.5) / (_DF[b] + 0.5))
                s += idf * tf[b] * 2.2 / (tf[b] + 1.2 * (0.25 + 0.75 * dl / 150))
        scored.append((s, a))
    scored.sort(key=lambda x: -x[0])
    top = scored[0][0] or 1
    return [dict(a, score=round(s / top, 2)) for s, a in scored[:top_k] if s / top >= min_score and s > 0]
