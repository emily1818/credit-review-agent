"""안전장치: 출처 등록, 권한관리, Fallback, 사람 검토 요청, 감사로그."""
import json
import re
import time
from datetime import datetime

from . import config


class AuditLog:
    def __init__(self, sink=None):
        self.entries = []
        self.sink = sink  # 진행 화면이 읽을 jsonl 파일

    def add(self, kind, msg, **extra):
        e = {"ts": datetime.now().strftime("%H:%M:%S"), "kind": kind, "msg": msg}
        e.update(extra)
        self.entries.append(e)
        print("  [{}] {:<9} {}".format(e["ts"], kind, msg))
        if self.sink:
            with open(self.sink, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        return e


class SourceRegistry:
    """Agent가 본 모든 자료에 ID를 붙인다. 보고서 문장은 등록된 ID만 인용할 수 있다."""

    def __init__(self):
        self.sources = {}

    def register(self, sid, title, origin, kind, fallback=None, url=None):
        self.sources[sid] = {"id": sid, "title": title, "origin": origin, "kind": kind,
                             "fallback": fallback, "url": url,
                             "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        return sid

    def has(self, sid):
        return sid in self.sources


CITE_RE = re.compile(r"\[([A-Z]+-[0-9A-Za-z-]+)\]")


def validate_citations(text, registry):
    """문장마다 출처가 있는지, 인용한 출처가 실제로 등록돼 있는지 검사한다."""
    problems = []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?!\[)", text) if len(s.strip()) > 8]
    for s in sentences:
        ids = CITE_RE.findall(s)
        if not ids:
            problems.append("출처 없는 문장: " + s[:50])
        for i in ids:
            if not registry.has(i):
                problems.append("등록되지 않은 출처 인용: [{}]".format(i))
    return problems


class Permission:
    def __init__(self, role):
        pol = json.loads((config.BANK / "권한정책.json").read_text(encoding="utf-8"))
        if role not in pol["roles"]:
            raise ValueError("unknown role: " + role)
        self.role = role
        self.label = pol["roles"][role]["label"]
        self.allowed = set(pol["roles"][role]["sensitivity"])
        self.can_approve = pol["roles"][role]["can_approve"]

    def allows(self, sensitivity):
        return sensitivity in self.allowed


class HITLQueue:
    def __init__(self):
        self.items = []

    def add(self, item, reason, source=None):
        if any(i["item"] == item for i in self.items):
            return
        self.items.append({"item": item, "reason": reason, "source": source})


def cache_path(key):
    return config.CACHE / (re.sub(r"[^0-9A-Za-z가-힣_-]", "_", key) + ".json")


def with_fallback(key, live_fn, audit, simulate_outage=False):
    """1) 실시간 호출 → 2) 로컬 캐시 → 3) None (호출한 쪽에서 대체자료 또는 사람 검토로 넘김).
    반환: (data, mode) mode ∈ {'live','cache',None}"""
    p = cache_path(key)
    try:
        if simulate_outage:
            raise TimeoutError("simulated outage")
        t0 = time.time()
        data = live_fn()
        config.CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"saved_at": datetime.now().isoformat(timespec="seconds"), "data": data},
                                ensure_ascii=False, indent=1), encoding="utf-8")
        audit.add("LIVE", "{} 조회 성공 ({:.1f}s)".format(key, time.time() - t0))
        return data, "live"
    except Exception as e:  # 네트워크, 인증, 파싱 오류 모두 Fallback 대상
        audit.add("FALLBACK", "{} 실시간 조회 실패: {}".format(key, str(e)[:80]))
        if p.exists():
            cached = json.loads(p.read_text(encoding="utf-8"))
            audit.add("FALLBACK", "{} 캐시 사용 (저장시각 {})".format(key, cached["saved_at"]))
            return cached["data"], "cache:" + cached["saved_at"]
        return None, None
