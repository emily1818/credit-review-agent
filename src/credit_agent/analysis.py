"""결정론적 계산과 규정 판정. 숫자는 LLM이 아니라 여기서만 만든다."""
from . import config

SPREAD = {"AA": 1.20, "A+": 1.40, "A": 1.55, "A-": 1.70, "BBB+": 1.95, "BBB": 2.20, "BBB-": 2.50}  # 여신업무규정 제31조②


def pct(a, b):
    return round(a / b * 100, 1) if b else None


def financial_metrics(fin):
    rows = {}
    for y, v in sorted(fin.items()):
        r = {}
        if "total_liabilities" in v and v.get("total_equity"):
            r["debt_ratio"] = pct(v["total_liabilities"], v["total_equity"])
        if "borrowings" in v and v.get("total_assets"):
            r["borrowing_dependency"] = pct(v["borrowings"], v["total_assets"])
        if "operating_income" in v and v.get("interest_expense"):
            r["interest_coverage"] = round(v["operating_income"] / v["interest_expense"], 1)
        if "operating_income" in v and v.get("revenue"):
            r["op_margin"] = pct(v["operating_income"], v["revenue"])
        if "operating_income" in v and "depreciation" in v:
            r["ebitda"] = v["operating_income"] + v["depreciation"]
        rows[y] = r
    return rows


def project_metrics(x, fin_last, rate_pct):
    """x: 서류에서 추출한 값. 없는 값은 None으로 두고 해당 지표도 None."""
    amt, total = x["loan"], sum(x["costs"].values())
    equity = total - amt
    new_ds = amt * x["amort"] / 100 + amt * rate_pct / 100
    out = {"loan": amt, "total_cost": total, "equity": equity, "equity_ratio": pct(equity, total),
           "all_in_rate": round(rate_pct, 2), "new_debt_service": round(new_ds, 1),
           "extra_cf": x["extra_cf"], "dscr": None, "dscr_ex_project": None, "post_loan_debt_ratio": None,
           "ltv_completed": None, "ltv_land": None}
    if fin_last and "annual_debt_service" in fin_last and "depreciation" in fin_last:
        ebitda = fin_last["operating_income"] + fin_last["depreciation"]
        total_ds = fin_last["annual_debt_service"] + new_ds
        out["dscr"] = round((ebitda + x["extra_cf"]) / total_ds, 2)
        out["dscr_ex_project"] = round(ebitda / total_ds, 2)
    if fin_last:
        out["post_loan_debt_ratio"] = pct(fin_last["total_liabilities"] + amt, fin_last["total_equity"])
    if x["appraisal"]:
        out["ltv_completed"] = pct(amt, x["appraisal"]["completed"])
        out["ltv_land"] = pct(amt, x["appraisal"]["land"])
    return out


def rule_checks(pm, fm, grade, x, contractor):
    """판정 ∈ 적합/부적합/조건부가/확인필요/위원회"""
    C = []

    def add(rule, crit, val, verdict, note=""):
        C.append({"rule": rule, "criterion": crit, "value": val, "verdict": verdict, "note": note})

    years = sorted(fm)
    if pm["post_loan_debt_ratio"] is None:
        add("REG-01-24", "신규 여신 반영 후 부채비율 200% 이하", "재무자료 없음", "확인필요")
    else:
        add("REG-01-24", "신규 여신 반영 후 부채비율 200% 이하", "{}%".format(pm["post_loan_debt_ratio"]),
            "적합" if pm["post_loan_debt_ratio"] <= 200 else "부적합")
    ics = [fm[y].get("interest_coverage") for y in years[-2:]]
    if all(i is not None for i in ics) and ics:
        both_low = all(i < 1.5 for i in ics)
        add("REG-01-24", "이자보상배율 2년 연속 1.5배 미만이면 위원회 승인", " / ".join("{}배".format(i) for i in ics),
            "위원회" if both_low else "적합", "2년 연속 1.5배 미만" if both_low else "")
    if pm["dscr"] is None:
        add("REG-02-8", "DSCR 1.20배 이상", "재무자료 없음", "확인필요")
    else:
        v = "적합" if pm["dscr_ex_project"] >= 1.2 else ("조건부가" if pm["dscr"] >= 1.2 else "부적합")
        add("REG-02-8", "DSCR 1.20배 이상", "{}배 (사업현금흐름 제외 {}배)".format(pm["dscr"], pm["dscr_ex_project"]), v,
            "신규 사업 현금흐름에 의존" if v == "조건부가" else ("기준에 근접" if pm["dscr_ex_project"] < 1.3 and v == "적합" else ""))
    add("REG-02-10", "자기자금 30% 이상", "{}%".format(pm["equity_ratio"]), "적합" if pm["equity_ratio"] >= 30 else "부적합")
    if pm["ltv_completed"] is None:
        add("REG-02-11", "준공 후 LTV 70% 이하", "감정평가서 미제출", "확인필요", "감정평가서 징구 필요")
    else:
        add("REG-02-11", "준공 후 LTV 70% 이하", "{}%".format(pm["ltv_completed"]), "적합" if pm["ltv_completed"] <= 70 else "부적합")
    g = x["guarantee"]
    need_credit = pm["ltv_land"] is None or pm["ltv_land"] > 100
    if need_credit:
        label = "토지 대비 {}%".format(pm["ltv_land"]) if pm["ltv_land"] else "토지가치 미확인"
        if "미제출" in g:
            add("REG-02-11", "준공 전 토지가치 미달 시 책임준공 등 신용보강", label, "부적합", "책임준공확약서 미제출")
        elif "스캔" in g:
            add("REG-02-11", "준공 전 토지가치 미달 시 책임준공 등 신용보강", label, "확인필요", "확약서가 스캔본만 제출됨")
        else:
            add("REG-02-11", "준공 전 토지가치 미달 시 책임준공 등 신용보강", label, "적합", "확약서 원본 제출")
    if "미제출" not in g and "전액" not in x["liability"]:
        add("REG-02-11", "책임준공 배상한도가 대출원금을 보전", x["liability"], "확인필요", "배상한도 부족분 보강 필요")
    recent = [s for s in (contractor or {}).get("sanction_history", []) if config.CURRENT_YEAR - s["year"] <= 3]
    older = [s for s in (contractor or {}).get("sanction_history", []) if config.CURRENT_YEAR - s["year"] > 3]
    if recent:
        add("REG-03-5", "시공사 최근 3년 행정처분 이력 시 추가조건", "{}년 이력 있음".format(recent[0]["year"]), "조건부가",
            "감리보고서·분할인출·손해배상 약정")
    elif older:
        add("REG-03-5", "시공사 최근 3년 행정처분 이력 시 추가조건", "{}년 이력(3년 경과)".format(older[0]["year"]), "적합", "참고 사항")
    if contractor:
        use_pct = pct(contractor["commitment_used_krw_100m"] + pm["loan"], contractor["commitment_limit_krw_100m"])
        add("REG-03-5", "시공사 책임준공 약정 한도 90% 이하", "취급 후 {}%".format(use_pct),
            "적합" if use_pct <= 90 else "확인필요", "리스크관리부 협의 필요" if use_pct > 90 else "")
    else:
        add("REG-03-5", "시공사 책임준공 약정 한도 90% 이하", "관리현황 없음", "확인필요", "신규 시공사 등록 필요")
    if x["adj_clause"]:
        add("REG-03-7", "계약금액 조정 조항 시 차주 자기부담 확약", "도급계약 조정 조항 있음", "조건부가", "공사비 초과분 자기부담 확약")
    if grade is None:
        add("REG-01-31", "내부등급별 가산금리", "등급 열람 권한 없음", "확인필요", "심사역 확인")
    else:
        std = SPREAD.get(grade["grade"])
        ok = std is not None and std - 0.2 <= x["spread"] <= std + 0.2
        note = ""
        if ok and x["spread"] < std:
            note = "표준보다 {:.2f}%p 낮음".format(std - x["spread"])
        add("REG-01-31", "{} 표준 가산금리 {:.2f}%p ±0.20".format(grade["grade"], std or 0), "신청 {:.2f}%p".format(x["spread"]),
            "적합" if ok else "확인필요", note if ok else "조정 범위 밖")
    add("REG-01-40", "300억 초과 시 여신위원회 부의", "{}억".format(int(pm["loan"])), "위원회" if pm["loan"] > 300 else "적합")
    return C


def cross_checks(x):
    out = []
    plan_c, contract = x["costs"].get("공사비"), x["contract_amount"]
    if plan_c is not None and contract is not None:
        out.append({"item": "공사비", "a": "사업계획서 {}억 [SUB-02]".format(plan_c), "b": "도급계약서 {}억 [SUB-03]".format(int(contract)),
                    "diff": int(plan_c - contract), "status": "일치" if plan_c == contract else "불일치"})
    if x["plan_loan"] is not None:
        out.append({"item": "대출금액", "a": "신청서 {}억 [SUB-01]".format(int(x["loan"])), "b": "사업계획서 조달 {}억 [SUB-02]".format(x["plan_loan"]),
                    "diff": int(x["plan_loan"] - x["loan"]), "status": "일치" if x["plan_loan"] == x["loan"] else "불일치"})
    for label, a, b in x["identity_checks"]:
        out.append({"item": label, "a": a, "b": b, "diff": "–", "status": "일치" if a.split(" [")[0] == b.split(" [")[0] else "불일치"})
    return out


def recommend(rules, missing_required):
    v = [r["verdict"] for r in rules]
    if "부적합" in v or missing_required:
        return "보류"
    if "조건부가" in v or "확인필요" in v:
        return "조건부 승인"
    return "승인"
