"""실행 모드.
- offline: 정해진 순서로 도구를 호출하고 규칙 기반 템플릿으로 서술부를 쓴다. LLM 없이 재현 가능.
- claude : Claude가 도구를 골라 호출한다 (anthropic SDK). 실패하면 offline 서술로 Fallback.
- codex  : run.py / webapp.py가 Codex CLI를 띄우고 mcp_server.py가 도구를 제공한다."""
import json

from . import config, tools
from .tools import clean_name

RULES = """작업 순서
1. list_documents로 기업정보와 업로드된 서류(누락 여부)를 확인하고, 제출서류와 내부자료를 읽습니다.
2. get_financials, get_market_rates, search_news(차주와 시공사 각각)로 외부 데이터를 수집합니다.
3. run_checks로 지표·규정 판정·문서 대사·규칙상 권고를 계산합니다. 숫자는 이 결과만 쓰고 직접 계산하거나 추정하지 않습니다.
4. 필요하면 search_regulations로 조문을 더 찾습니다.
5. 확정할 수 없는 사항(원본 미확인, 권한 밖 자료, Fallback 데이터, 문서 불일치, 서류 누락)은 flag_for_review로 심사역에게 넘깁니다.
6. submit_report로 서술부를 제출합니다. 반려되면 오류를 고쳐 다시 제출합니다.

규칙
- 모든 문장은 마침표 앞에 [출처ID]를 붙입니다. 예: "부채비율은 124%이다 [SUB-05]." 도구 결과에 나온 ID만 씁니다.
- 미제출 서류나 권한이 없어 못 본 자료의 내용을 짐작해서 쓰지 않습니다.
- Fallback(캐시, 대체자료)으로 얻은 데이터는 그렇다고 밝힙니다.
- 권고는 run_checks의 suggested_recommendation보다 유리하게 낼 수 없습니다. 더 보수적인 권고는 근거와 함께 낼 수 있습니다.
- 최종 결정은 사람이 합니다. 권고와 조건까지만 씁니다."""


def system_prompt(case):
    i = case.info
    return "당신은 은행 기업여신 심사역을 보조하는 AI Agent입니다. 심사 건: ㈜{} {} 시설자금 {}억원 (시공 {}, 설계 {}).\n\n{}".format(
        clean_name(i["borrower"]["name"]), i["project"], i["loan"], i["contractor"]["name"], i["architect"]["name"], RULES)


def run(ctx, mode="offline"):
    ctx.audit.add("START", "심사 요청 {} 접수 (역할: {}, 모드: {})".format(ctx.case.id, ctx.perm.label, mode))
    if mode == "claude":
        try:
            _run_claude(ctx)
        except Exception as e:
            ctx.audit.add("FALLBACK", "LLM 실행 실패 → 규칙 기반 초안으로 대체: {}".format(str(e)[:120]))
            ctx.note_fallback("LLM 서술", "규칙 기반 템플릿")
    if ctx.report is None:
        _collect(ctx)
        _offline_narrative(ctx)
    ctx.audit.add("HITL", "심사역 확인 대기 {}건. 사람 결재 전까지 보고서는 초안 상태".format(len(ctx.hitl.items)))
    return ctx


# ------------------------------------------------------------------ offline
def _collect(ctx):
    c = lambda n, **a: tools.call(ctx, n, a)
    c("list_documents")
    for d in ("SUB-01", "SUB-02", "SUB-03", "SUB-04"):
        if d not in ctx.data:
            c("read_document", doc_id=d)
    for r in ("INT-01", "INT-02", "INT-03"):
        if r not in ctx.data:
            c("get_internal_record", record_id=r)
    if "financials" not in ctx.data:
        c("get_financials")
    if "rates" not in ctx.data:
        c("get_market_rates")
    for co in (ctx.case.borrower["name"], ctx.case.contractor["name"]):
        if clean_name(co) not in ctx.data.get("news", {}):
            c("search_news", company=co)
    if not ctx.results:
        c("run_checks")


def _offline_narrative(ctx):
    R, D, case = ctx.results, ctx.data, ctx.case
    if not R:
        raise RuntimeError("run_checks 결과 없음 (신청서·사업계획서 누락)")
    x, pm, fm = R["x"], R["project"], R["fin_metrics"]
    fin, fs = D["financials"]["years"], D["financials"]["source"]
    b, cname = clean_name(case.borrower["name"]), clean_name(case.contractor["name"])
    contractor = D.get("INT-03")
    news_c = D.get("news", {}).get(cname, [])
    neg_c = [n for n in news_c if n["tone"] == "부정"]
    bad = {r["rule"] + r["criterion"]: r for r in R["rules"] if r["verdict"] in ("부적합", "확인필요", "조건부가")}
    rec = R["suggested_recommendation"]
    from . import docs as _docs

    s = []
    if fin and fs:
        s.append("차주의 매출은 2023년 {:,}억원에서 2025년 {:,}억원으로 {}했고 부채비율은 {}%이다 [{}].".format(
            fin["2023"]["revenue"], fin["2025"]["revenue"], "증가" if fin["2025"]["revenue"] >= fin["2023"]["revenue"] else "감소",
            fm["2025"].get("debt_ratio"), fs))
    if pm["dscr"] is not None:
        s.append("준공 후 DSCR은 {}배, 신규 사업 현금흐름을 빼면 {}배로 기준 1.20배{} [REG-02-8].".format(
            pm["dscr"], pm["dscr_ex_project"], "를 넘는다" if pm["dscr_ex_project"] >= 1.2 else ("는 사업 현금흐름을 더해야 넘는다" if pm["dscr"] >= 1.2 else "에 못 미친다")))
    s.append("자기자금 비율은 {}%로 기준 30%{} [REG-02-10].".format(pm["equity_ratio"], " 이상이다" if pm["equity_ratio"] >= 30 else "에 미달한다"))
    if pm["ltv_completed"] is not None:
        s.append("준공 후 LTV는 {}%로 기준 70%{} [SUB-04].".format(pm["ltv_completed"], " 이내이다" if pm["ltv_completed"] <= 70 else "를 넘는다"))
    for d in R["missing"]:
        s.append("필수 서류인 {}가 제출되지 않아 관련 항목을 판단할 수 없다 [INPUT-1].".format(_docs.SLOTS[d][1]))
    if "미제출" in x["guarantee"]:
        s.append("책임준공확약서가 제출되지 않아 준공 전 채권보전 수단이 없다 [SUB-03].")
    elif "스캔" in x["guarantee"]:
        s.append("책임준공확약서는 스캔본만 제출되어 원본 확인이 필요하다 [SUB-03].")
    if "전액" not in x["liability"] and "미제출" not in x["guarantee"]:
        s.append("책임준공 배상한도가 {}로 대출원금 전액을 보전하지 못한다 [SUB-03].".format(x["liability"]))
    recent = [h for h in (contractor or {}).get("sanction_history", []) if config.CURRENT_YEAR - h["year"] <= 3]
    if recent:
        s.append("시공사 {}는 {}년 {} 이력이 있어 추가 조건이 필요하다 [INT-03].".format(cname, recent[0]["year"], recent[0]["event"]))
    if contractor:
        use = round((contractor["commitment_used_krw_100m"] + pm["loan"]) / contractor["commitment_limit_krw_100m"] * 100, 1)
        if use > 90:
            s.append("취급 후 시공사 책임준공 약정 한도 사용률이 {}%로 90%를 넘는다 [INT-03].".format(use))
    for c in R["cross"]:
        if c["status"] == "불일치" and c["item"] == "공사비":
            s.append("사업계획서와 도급계약서의 공사비가 {}억원 차이 난다 [SUB-02].".format(abs(c["diff"])))
    if neg_c:
        s.append("시공사 관련 최근 기사 {}건 중 부정 키워드 기사가 {}건 있다 [{}].".format(len(news_c), len(neg_c), neg_c[0]["source"]))
    tail = {"승인": "규정상 결격 사항이 없어 승인을 권고한다 [REG-02-8].",
            "조건부 승인": "아래 조건을 붙인 조건부 승인을 권고한다 [REG-03-5].",
            "보류": "기준 미달 또는 필수 서류 누락이 있어 보완 전까지 보류를 권고한다 [REG-01-12]."}
    s.append(tail[rec])

    conditions = []
    if rec != "승인":
        conditions.append("감리자 확인 공정률에 연동한 분할인출 (시설자금 취급세칙 제14조)")
    if recent:
        conditions += ["월간 감리보고서 제출 (건설여신 심사가이드 제5조)", "책임준공 미이행 시 시공사의 손해배상 또는 채무인수 약정"]
    if x["adj_clause"]:
        conditions.append("도급계약 조정 조항에 따른 공사비 증액분 차주 자기부담 확약 (가이드 제7조)")
    if "스캔" in x["guarantee"]:
        conditions.append("책임준공확약서 원본과 인감증명서 징구 (가이드 제9조)")
    if "전액" not in x["liability"] and "미제출" not in x["guarantee"]:
        conditions.append("책임준공 배상한도를 대출원금 전액으로 상향하거나 추가 신용보강")
    for d in R["missing"]:
        conditions.append("{} 제출".format(_docs.SLOTS[d][1]))
    if "미제출" in x["guarantee"]:
        conditions.append("시공사 책임준공확약서 제출")
    if pm["equity_ratio"] < 30:
        conditions.append("자기자금 비율 30% 이상으로 증액 (부족분 약 {:.0f}억원)".format(pm["total_cost"] * 0.3 - pm["equity"]))
    if pm["ltv_completed"] and pm["ltv_completed"] > 70:
        conditions.append("대출금 감액 또는 추가 담보로 LTV 70% 이하 조정")
    conditions += ["재무약정: 부채비율 200% 이하 유지, 연 1회 점검", "준공 후 재감정 및 건물 근저당 추가 설정"]

    risks = []
    if recent:
        risks.append({"factor": "시공 품질·공정 지연", "level": "높음", "basis": "시공사의 {}년 중대사고 관련 행정처분 이력이 있다 [INT-03].".format(recent[0]["year"]),
                      "mitigation": "분할인출, 월간 감리보고서"})
    if "미제출" in x["guarantee"] or "스캔" in x["guarantee"] or "전액" not in x["liability"]:
        risks.append({"factor": "준공 전 채권보전", "level": "높음" if "미제출" in x["guarantee"] else "중간",
                      "basis": ("책임준공확약서가 제출되지 않았다 [SUB-03]." if "미제출" in x["guarantee"] else
                                "책임준공 확약이 {}, 배상한도 {}이다 [SUB-03].".format(x["guarantee"], x["liability"])),
                      "mitigation": "확약서 원본·배상한도 보강"})
    if contractor and (contractor["commitment_used_krw_100m"] + pm["loan"]) / contractor["commitment_limit_krw_100m"] > 0.9:
        risks.append({"factor": "시공사 약정 집중", "level": "중간", "basis": "취급 후 책임준공 약정 한도 사용률이 90%를 넘는다 [INT-03].",
                      "mitigation": "리스크관리부 협의"})
    if x["adj_clause"] or any(c["status"] == "불일치" and c["item"] == "공사비" for c in R["cross"]):
        risks.append({"factor": "공사비 증액", "level": "중간", "basis": "도급계약 조정 조항 또는 문서 간 공사비 차이가 있다 [SUB-03].",
                      "mitigation": "초과분 차주 자기부담 확약"})
    if pm["equity_ratio"] < 30:
        risks.append({"factor": "자기자금 부족", "level": "높음", "basis": "자기자금 비율이 {}%로 기준 30%에 미달한다 [SUB-02].".format(pm["equity_ratio"]),
                      "mitigation": "자기자금 증액"})
    if pm["dscr"] is not None:
        lvl = "낮음" if pm["dscr_ex_project"] >= 1.3 else ("중간" if pm["dscr"] >= 1.2 else "높음")
        risks.append({"factor": "차주 상환능력", "level": lvl, "basis": "DSCR {}배 (사업 현금흐름 제외 {}배) [{}].".format(pm["dscr"], pm["dscr_ex_project"], fs),
                      "mitigation": "재무약정 점검"})
    if pm["ltv_completed"] is not None:
        risks.append({"factor": "담보가치", "level": "낮음" if pm["ltv_completed"] <= 60 else ("중간" if pm["ltv_completed"] <= 70 else "높음"),
                      "basis": "준공 후 LTV {}% [SUB-04].".format(pm["ltv_completed"]), "mitigation": "준공 후 재감정"})
    else:
        risks.append({"factor": "담보가치", "level": "높음", "basis": "감정평가서가 제출되지 않아 담보가치를 확인할 수 없다 [INPUT-1].",
                      "mitigation": "감정평가서 징구"})

    bn = []
    if "INT-01" in D:
        i1 = D["INT-01"]
        bn.append("{}년부터 거래, 최근 12개월 연체 {}건 [INT-01]".format(i1["relationship_since"], i1["delinquency_12m"]))
        bn.append("기존 여신 {:,}억원, 예금 {:,}억원 [INT-01]".format(i1["existing_loans_krw_100m"], i1["deposits_krw_100m"]))
    if fs:
        bn.append("재무자료: {} [{}]".format("OpenDART 공시" if fs == "DART-FS" else "차주 제출본 (DART 대사 필요)", fs))
    cn = []
    if x["contract_amount"]:
        cn.append("도급액 {:,.0f}억원, {} [SUB-03]".format(x["contract_amount"], "계약금액 조정 조항 있음" if x["adj_clause"] else "총액확정(조정 없음)"))
    cn.append("책임준공 확약: 미제출 [SUB-03]" if "미제출" in x["guarantee"] else "책임준공 확약: {}, 배상한도 {} [SUB-03]".format(x["guarantee"], x["liability"]))
    for h in (contractor or {}).get("sanction_history", []):
        cn.append("{}년 {} [INT-03]".format(h["year"], h["event"]))
    if news_c:
        cn.append("최근 기사 {}건 중 부정 {}건 [{}]".format(len(news_c), len(neg_c), (neg_c or news_c)[0]["source"]))
    an = ["{} [SUB-02]".format(x["plan"].get("규모", "")), "용도: {} [SUB-02]".format(x["plan"].get("용도", ""))]
    participants = [{"role": "차주·발주자", "name": "㈜" + b, "notes": bn},
                    {"role": "시공사", "name": case.contractor["name"], "notes": cn},
                    {"role": "설계", "name": case.info["architect"]["name"], "notes": an}]
    res = tools.call(ctx, "submit_report", {"recommendation": rec, "opinion": " ".join(s), "conditions": conditions,
                                            "risks": risks, "participants": participants})
    if not res["accepted"]:
        raise RuntimeError("offline 초안 출처 검증 실패: {}".format(res["errors"]))


# ------------------------------------------------------------------ claude
def _run_claude(ctx, max_turns=30):
    import anthropic  # pip install anthropic

    client = anthropic.Anthropic()
    tool_defs = tools.claude_tool_defs()
    messages = [{"role": "user", "content": "심사 건 {}의 심사보고서 초안을 작성하세요. 요청자 역할: {}".format(ctx.case.id, ctx.perm.label)}]
    for _ in range(max_turns):
        resp = client.beta.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=16000, system=system_prompt(ctx.case), tools=tool_defs, messages=messages,
            thinking={"type": "adaptive"},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"output_config": {"effort": "high"}, "fallbacks": "default"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("모델이 요청을 거절함: {}".format(getattr(resp, "stop_details", None)))
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("응답이 max_tokens에서 잘림")
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                ctx.audit.add("LLM", b.text.strip()[:100])
        if not uses:
            break
        results = []
        for u in uses:
            try:
                out = tools.call(ctx, u.name, dict(u.input))
                results.append({"type": "tool_result", "tool_use_id": u.id,
                                "content": json.dumps(out, ensure_ascii=False, default=str)[:60000]})
            except Exception as e:
                results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True, "content": str(e)})
        messages.append({"role": "user", "content": results})
        if ctx.report is not None:
            break
