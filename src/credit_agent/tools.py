"""Agent 도구. 모든 도구는 권한을 확인하고, 본 자료를 출처로 등록하고, 감사로그를 남긴다."""
import json
import re

from . import analysis, docs
from .connectors import dart, ecos, news
from .guardrails import AuditLog, HITLQueue, Permission, SourceRegistry, validate_citations, with_fallback


def clean_name(s):
    return re.sub(r"㈜|\(주\)|주식회사", "", s or "").strip()


class Context:
    def __init__(self, role, case, outages=(), log_path=None):
        self.case = case
        self.perm = Permission(role)
        self.audit = AuditLog(log_path)
        self.sources = SourceRegistry()
        self.hitl = HITLQueue()
        self.outages = set(outages)
        self.data = {}
        self.results = {}
        self.report = None
        self.fallbacks = []
        self.sources.register("INPUT-1", "업로드 화면 입력 기업정보", "심사 요청자 입력", "submitted")

    def note_fallback(self, what, mode):
        self.fallbacks.append({"what": what, "mode": mode})

    def missing_required(self):
        return [d for d, (_, _, req) in docs.SLOTS.items() if req and not self.case.has(d)]


# ---------------------------------------------------------------- tools
def list_documents(ctx):
    c = ctx.case
    sub = [{"id": d, "title": t, "required": req, "uploaded": c.has(d)} for d, (_, t, req) in docs.SLOTS.items()]
    internal = [{"id": k, "title": v[0], "sensitivity": v[1], "accessible": ctx.perm.allows(v[1])} for k, v in docs.INTERNAL.items()]
    for d in ctx.missing_required():
        ctx.hitl.add("{} 서류 보완".format(docs.SLOTS[d][1]), "필수 서류가 업로드되지 않았습니다", d)
    return {"case": c.info, "submitted": sub, "internal_records": internal, "regulations": list(docs.REG_FILES), "role": ctx.perm.label}


def read_document(ctx, doc_id):
    if doc_id not in docs.SLOTS:
        return {"error": "없는 문서 ID: " + doc_id}
    title = docs.SLOTS[doc_id][1]
    if not ctx.case.has(doc_id):
        ctx.audit.add("MISSING", "{} {} 미제출".format(doc_id, title))
        if docs.SLOTS[doc_id][2]:
            ctx.hitl.add("{} 서류 보완".format(title), "필수 서류가 업로드되지 않았습니다", doc_id)
        return {"doc_id": doc_id, "missing": True, "note": "미제출 서류. 내용을 추정하지 말 것"}
    content = ctx.case.read(doc_id)
    ctx.data[doc_id] = content
    ctx.sources.register(doc_id, title, "차주 제출서류 (가상)", "submitted")
    ctx.audit.add("READ", "{} {}".format(doc_id, title))
    return {"doc_id": doc_id, "content": content}


def get_internal_record(ctx, record_id):
    if record_id not in docs.INTERNAL:
        return {"error": "없는 내부자료 ID: " + record_id}
    meta, rec = docs.internal_record(record_id, ctx.case)
    if not ctx.perm.allows(meta["sensitivity"]):
        ctx.audit.add("DENY", "{} 열람 거부 (민감도 {}, 역할 {})".format(record_id, meta["sensitivity"], ctx.perm.label))
        ctx.hitl.add("{} {} 확인".format(record_id, meta["title"]), "{} 권한으로는 열람할 수 없는 자료입니다".format(ctx.perm.label), record_id)
        return {"record_id": record_id, "denied": True, "reason": "권한 없음 ({})".format(meta["sensitivity"])}
    if rec is None:
        ctx.audit.add("READ", "{} {}: 등록 정보 없음".format(record_id, meta["title"]))
        ctx.hitl.add("{} 정보 등록".format(meta["title"]), "은행 DB에 해당 회사 정보가 없습니다 (신규 거래처)", record_id)
        return {"record_id": record_id, "not_found": True}
    ctx.data[record_id] = rec
    ctx.sources.register(record_id, meta["title"], meta["system"], "internal")
    ctx.audit.add("READ", "{} {} (민감도 {})".format(record_id, meta["title"], meta["sensitivity"]))
    return {"record_id": record_id, "content": rec}


def get_financials(ctx):
    b = ctx.case.borrower
    years = ["2023", "2024", "2025"]
    fin, mode = with_fallback("dart_fin_" + b["stock_code"], lambda: dart.financials(b["stock_code"], years),
                              ctx.audit, "dart" in ctx.outages)
    submitted = ctx.case.read("SUB-05") if ctx.case.has("SUB-05") else None
    if submitted:
        ctx.sources.register("SUB-05", docs.SLOTS["SUB-05"][1], "차주 제출서류 (가상)", "submitted")
    if fin:
        ctx.sources.register("DART-FS", "{} 연결재무제표 (사업보고서)".format(b["name"]), "금융감독원 OpenDART", "real",
                             fallback=None if mode == "live" else mode)
        base = submitted["years"] if submitted else {}
        merged = {y: dict(base.get(y, {}), **fin.get(y, {})) for y in years}
        diffs = []
        if submitted:
            for y in years:
                for k in ("revenue", "operating_income", "total_liabilities", "total_equity"):
                    a, d = base.get(y, {}).get(k), fin.get(y, {}).get(k)
                    if a and d and abs(a - d) / abs(d) > 0.02:
                        diffs.append("{} {}: 제출 {:,} / DART {:,}".format(y, k, a, d))
        if diffs:
            ctx.hitl.add("제출 재무제표와 DART 공시 불일치 확인",
                         "; ".join(diffs[:4]) + (" 외 {}건".format(len(diffs) - 4) if len(diffs) > 4 else ""), "DART-FS")
        missing = [k for k in ("annual_debt_service", "depreciation") if k not in merged["2025"]]
        if missing:
            ctx.hitl.add("원리금상환액·감가상각비 확인", "DART 계정에 없어 DSCR 산출 불가: " + ", ".join(missing), "DART-FS")
        if mode != "live":
            ctx.note_fallback("재무제표", mode)
        ctx.data["financials"] = {"source": "DART-FS", "years": merged, "diffs": diffs}
        return {"source": "DART-FS", "mode": mode, "years": merged, "diffs_vs_submitted": diffs}
    if submitted:
        ctx.note_fallback("재무제표", "차주 제출본 대체")
        ctx.audit.add("FALLBACK", "DART 미연결 → 차주 제출 재무제표(SUB-05)로 대체")
        ctx.hitl.add("재무제표를 DART 공시와 대사", "DART에 연결하지 못해 차주가 제출한 수치로 분석했습니다 (여신업무규정 제12조②)", "SUB-05")
        ctx.data["financials"] = {"source": "SUB-05", "years": submitted["years"], "diffs": []}
        return {"source": "SUB-05", "mode": "fallback_submitted", "years": submitted["years"],
                "warning": "DART 미연결. 제출 자료이므로 공시 대사 전까지 확정 수치로 쓰지 말 것"}
    ctx.hitl.add("재무제표 확보", "DART 미연결이고 제출본도 없습니다", None)
    ctx.data["financials"] = {"source": None, "years": {}, "diffs": []}
    return {"source": None, "error": "재무자료 없음"}


def get_market_rates(ctx):
    out = {}
    for key in ("cd91", "base_rate", "ktb3y", "corp_loan_large"):
        v, mode = with_fallback("ecos_" + key, lambda k=key: ecos.latest(k), ctx.audit, "ecos" in ctx.outages)
        if v is None:
            ctx.hitl.add("{} 금리 확인".format(ecos.SERIES[key][3]), "ECOS 조회 실패, 캐시 없음", None)
            continue
        sid = "ECOS-" + key.upper().replace("_", "")
        ctx.sources.register(sid, "{} ({})".format(v["name"], v["time"]), "한국은행 ECOS {}".format(v["stat_code"]), "real",
                             fallback=None if mode == "live" else mode)
        if mode != "live":
            ctx.note_fallback(v["name"], mode)
        out[key] = dict(v, source=sid, mode=mode)
    ctx.data["rates"] = out
    return out


def search_news(ctx, company, limit=6):
    company = clean_name(company)  # 법인 표기가 붙으면 검색이 안 됨
    items, mode = with_fallback("news_" + company, lambda: news.search(company, limit), ctx.audit, "news" in ctx.outages)
    if items is None:
        ctx.hitl.add("{} 최근 뉴스 직접 확인".format(company), "뉴스 조회 실패, 캐시 없음", None)
        return {"company": company, "items": [], "mode": None}
    if mode != "live":
        ctx.note_fallback("{} 뉴스".format(company), mode)
        ctx.hitl.add("{} 당일 뉴스 추가 확인".format(company), "뉴스를 캐시본({})으로 분석했습니다".format(mode[6:]), None)
    prefix = "NEWS-" + ("B" if company == clean_name(ctx.case.borrower["name"]) else "C")
    for i, it in enumerate(items, 1):
        it["source"] = "{}{}".format(prefix, i)
        ctx.sources.register(it["source"], "{} ({}, {})".format(it["title"], it["publisher"], it["date"]),
                             "Google News RSS", "real", fallback=None if mode == "live" else mode, url=it["url"])
    ctx.data.setdefault("news", {})[company] = items
    return {"company": company, "mode": mode,
            "items": [{k: it[k] for k in ("source", "date", "title", "publisher", "tone", "keywords")} for it in items]}


def search_regulations(ctx, query):
    hits = docs.search_regulations(query)
    for h in hits:
        ctx.sources.register(h["id"], "{} {}".format(h["doc"], h["article"]), "사내 규정 DB (가상)", "regulation")
    ctx.audit.add("RAG", "'{}' → {}".format(query, ", ".join("{}({})".format(h["id"], h["score"]) for h in hits) or "결과 없음"))
    if not hits:
        return {"query": query, "hits": [], "note": "관련 조항을 찾지 못함. 규정을 추정해서 인용하지 말 것"}
    return {"query": query, "hits": hits}


def _extract(ctx):
    """업로드 서류에서 심사에 필요한 값을 뽑는다."""
    app = docs.fields(ctx.data["SUB-01"])
    plan_md = ctx.data.get("SUB-02", "")
    contract_md = ctx.data.get("SUB-03", "")
    ap = docs.fields(ctx.data["SUB-04"]) if "SUB-04" in ctx.data else None
    cf = docs.fields(contract_md) if contract_md else {}
    extra = docs.fields(docs.section(plan_md, "4.")) if plan_md else {}
    funding = docs.table(docs.section(plan_md, "3.")) if plan_md else {}
    info, b_name, c_name = ctx.case.info, clean_name(app.get("차주")), clean_name(app.get("시공사"))
    spread_m = re.search(r"\+\s*([\d.]+)%p", app.get("신청금리", ""))
    return {
        "loan": docs.num(app.get("신청금액(억원)")), "tenor": docs.num(app.get("대출기간(년)")),
        "grace": docs.num(app.get("거치기간(년)")), "amort": docs.num(app.get("연간분할상환비율(%)")) or 0,
        "spread": float(spread_m.group(1)) if spread_m else 0.0,
        "rate_request": app.get("신청금리"), "purpose": app.get("자금용도"), "collateral": app.get("담보"),
        "industry": app.get("업종"), "application_no": app.get("신청번호"),
        "costs": docs.table(docs.section(plan_md, "2.")) if plan_md else {},
        "plan_loan": next((v for k, v in funding.items() if "대출" in k), None),
        "extra_cf": sum(docs.num(v) or 0 for v in extra.values()), "extra_items": extra,
        "project": docs.fields(plan_md).get("사업명", info.get("project")), "plan": docs.fields(plan_md),
        "contract_amount": docs.num(cf.get("계약금액(억원)")) if cf else None,
        "adj_clause": "계약금액을 조정할 수 있다" in contract_md,
        "guarantee": cf.get("확약서 제출", "미제출"), "liability": cf.get("배상한도", "-"),
        "appraisal": {"land": docs.num(ap.get("토지가치(억원)")), "completed": docs.num(ap.get("준공후가치(억원)"))} if ap else None,
        "identity_checks": [
            ("차주명", "{} [INPUT-1]".format(clean_name(info["borrower"]["name"])), "{} [SUB-01]".format(b_name)),
            ("차주 종목코드", "{} [INPUT-1]".format(info["borrower"].get("stock_code", "")), "{} [SUB-01]".format(app.get("종목코드", ""))),
            ("시공사", "{} [INPUT-1]".format(clean_name(info["contractor"]["name"])), "{} [SUB-01]".format(c_name)),
        ],
    }


def run_checks(ctx):
    """재무·사업성 지표, 규정 판정, 문서 간 대사를 코드로 계산한다. 필요한 자료가 없으면 먼저 가져온다."""
    for d in ("SUB-01", "SUB-02", "SUB-03", "SUB-04"):
        if d not in ctx.data:
            read_document(ctx, d)
    if "SUB-01" not in ctx.data or "SUB-02" not in ctx.data:
        return {"error": "여신거래신청서와 사업계획서가 있어야 분석할 수 있습니다", "hitl": ctx.hitl.items}
    if "financials" not in ctx.data:
        get_financials(ctx)
    if "rates" not in ctx.data:
        get_market_rates(ctx)
    for r in ("INT-01", "INT-02", "INT-03"):
        if r not in ctx.data and ctx.perm.allows(docs.INTERNAL[r][1]):
            get_internal_record(ctx, r)
    for q in ("부채비율 재무기준", "DSCR 상환능력", "자기자금 비율", "LTV 담보", "시공사 행정처분", "설계변경 공사비 조정",
              "전결권 여신위원회", "가산금리", "책임준공확약서 원본 인감증명서", "분할인출 공정률"):
        search_regulations(ctx, q)

    x = _extract(ctx)
    fin = ctx.data["financials"]["years"]
    fm = analysis.financial_metrics(fin) if fin else {}
    cd = ctx.data["rates"].get("cd91", {}).get("value")
    grade = ctx.data.get("INT-02")
    std = analysis.SPREAD.get(grade["grade"]) if grade else None
    spread = std if std is not None else x["spread"]
    if cd is None:
        ctx.hitl.add("적용금리 산정 확인", "CD 금리를 조회하지 못해 3.50% 가정", None)
    pm = analysis.project_metrics(x, fin.get("2025") if fin else None, (cd or 3.5) + spread)
    rules = analysis.rule_checks(pm, fm, grade, x, ctx.data.get("INT-03"))
    xc = analysis.cross_checks(x)
    missing = ctx.missing_required()

    for r in rules:
        if r["verdict"] in ("확인필요", "부적합"):
            ctx.hitl.add("{} {}: {}".format(r["rule"], r["verdict"], r["criterion"]), r["note"] or r["value"], r["rule"])
    for c in xc:
        if c["status"] == "불일치":
            ctx.hitl.add("{} 불일치 확인".format(c["item"]), "{} vs {}".format(c["a"], c["b"]), None)
    if "스캔" in x["guarantee"]:
        ctx.hitl.add("책임준공확약서 원본·인감증명서 징구", "스캔본만 제출됨 [REG-03-9]", "REG-03-9")
    if pm["loan"] > 300:
        ctx.hitl.add("여신위원회 부의 안건 등록", "신청 {}억, 전결 한도 300억 초과 [REG-01-40]".format(int(pm["loan"])), "REG-01-40")

    rec = analysis.recommend(rules, missing)
    ctx.results = {"x": x, "fin_metrics": fm, "project": pm, "rules": rules, "cross": xc, "spread_used": spread,
                   "missing": missing, "suggested_recommendation": rec}
    ctx.audit.add("CHECK", "규정 {}건 판정, 대사 {}건, 사람 확인 {}건, 규칙상 권고 {}".format(len(rules), len(xc), len(ctx.hitl.items), rec))
    return {"extracted": {k: v for k, v in x.items() if k != "identity_checks"}, "financial_metrics": fm, "project_metrics": pm,
            "rule_checks": rules, "cross_checks": xc, "missing_required_docs": missing,
            "suggested_recommendation": rec, "hitl_so_far": ctx.hitl.items}


def flag_for_review(ctx, item, reason, source=None):
    ctx.hitl.add(item, reason, source)
    ctx.audit.add("HITL", "{} ({})".format(item, reason))
    return {"queued": True, "count": len(ctx.hitl.items)}


def submit_report(ctx, recommendation, opinion, conditions, risks, participants):
    if not ctx.results:
        return {"accepted": False, "errors": ["run_checks를 먼저 실행해야 합니다"]}
    errors = validate_citations(opinion, ctx.sources)
    for r in risks:
        if not re.search(r"\[[A-Z]+-", r.get("basis", "")):
            errors.append("근거 출처 없는 위험요인: " + r.get("factor", "?"))
        errors += validate_citations(r.get("basis", ""), ctx.sources)
    for p in participants:
        for n in p.get("notes", []):
            errors += [e for e in validate_citations(n, ctx.sources) if "등록되지 않은" in e]
    order = ["승인", "조건부 승인", "보류", "거절"]
    if recommendation not in order:
        errors.append("recommendation은 승인/조건부 승인/보류/거절 중 하나")
    else:
        rule_rec = ctx.results["suggested_recommendation"]
        if order.index(recommendation) < order.index(rule_rec):
            errors.append("규정 판정상 권고는 '{}' 이상이어야 합니다 (부적합 또는 필수서류 누락). 더 유리한 권고는 낼 수 없음".format(rule_rec))
    if errors:
        ctx.audit.add("REJECT", "보고서 초안 반려: {}건 (출처·규정 검증)".format(len(errors)))
        return {"accepted": False, "errors": errors[:10]}
    ctx.report = {"recommendation": recommendation, "opinion": opinion, "conditions": conditions,
                  "risks": risks, "participants": participants}
    ctx.audit.add("DRAFT", "보고서 초안 제출 (권고: {})".format(recommendation))
    return {"accepted": True, "hitl_items": len(ctx.hitl.items)}


# ---------------------------------------------------------------- schema
S = lambda props, req=(): {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}
STR = {"type": "string"}

TOOLS = [
    ("list_documents", list_documents, "이번 심사 건의 기업정보, 업로드된 서류(누락 여부 포함), 내부자료, 규정 목록을 반환한다.", S({})),
    ("read_document", read_document,
     "업로드된 차주 제출서류(SUB-01 신청서, SUB-02 사업계획서, SUB-03 도급계약서, SUB-04 감정평가서, SUB-05 재무제표)를 읽는다.",
     S({"doc_id": STR}, ["doc_id"])),
    ("get_internal_record", get_internal_record,
     "은행 내부자료(INT-01 거래현황, INT-02 내부등급, INT-03 시공사 관리현황)를 권한 범위 안에서 읽는다.", S({"record_id": STR}, ["record_id"])),
    ("get_financials", get_financials, "차주의 3개년 재무제표. OpenDART를 먼저 조회하고 실패하면 차주 제출본으로 대체한다.", S({})),
    ("get_market_rates", get_market_rates, "한국은행 ECOS에서 CD91일, 기준금리, 국고채3년, 대기업대출 평균금리 최신값을 조회한다.", S({})),
    ("search_news", search_news, "기업명으로 최근 뉴스를 검색하고 부정/중립/긍정 키워드 분류를 붙인다.",
     S({"company": STR, "limit": {"type": "integer"}}, ["company"])),
    ("search_regulations", search_regulations, "사내 여신 규정을 조문 단위로 검색한다. 결과의 id(예: REG-02-8)를 인용에 쓴다.",
     S({"query": STR}, ["query"])),
    ("run_checks", run_checks,
     "서류에서 값을 추출해 재무지표, DSCR·LTV, 규정 적합성, 문서 간 대사, 규칙상 권고를 계산한다. 숫자는 반드시 이 결과를 쓴다.", S({})),
    ("flag_for_review", flag_for_review, "Agent가 확정할 수 없는 사항을 심사역 확인 목록에 올린다.",
     S({"item": STR, "reason": STR, "source": STR}, ["item", "reason"])),
    ("submit_report", submit_report,
     "최종 심사보고서 서술부를 제출한다. 모든 문장에 [출처ID]를 붙여야 하고, 규칙상 권고보다 유리한 권고는 반려된다.",
     S({"recommendation": {"type": "string", "enum": ["승인", "조건부 승인", "보류", "거절"]},
        "opinion": {"type": "string", "description": "종합의견 3~6문장. 문장마다 마침표 앞에 [출처ID]"},
        "conditions": {"type": "array", "items": STR},
        "risks": {"type": "array", "items": S({"factor": STR, "level": {"type": "string", "enum": ["높음", "중간", "낮음"]},
                                               "basis": STR, "mitigation": STR}, ["factor", "level", "basis", "mitigation"])},
        "participants": {"type": "array", "items": S({"role": STR, "name": STR, "notes": {"type": "array", "items": STR}},
                                                     ["role", "name", "notes"])}},
       ["recommendation", "opinion", "conditions", "risks", "participants"])),
]
HANDLERS = {name: fn for name, fn, _, _ in TOOLS}


def claude_tool_defs():
    defs = []
    for n, _, d, s in TOOLS:
        t = {"name": n, "description": d, "input_schema": s}
        if set(s["required"]) == set(s["properties"]):  # strict는 모든 필드가 필수일 때만
            t["strict"] = True
        defs.append(t)
    return defs


def call(ctx, name, args):
    ctx.audit.add("TOOL", "{}({})".format(name, json.dumps(args, ensure_ascii=False)[:80]))
    return HANDLERS[name](ctx, **args)
