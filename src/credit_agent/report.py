"""심사보고서 HTML 렌더링. 서술부(ctx.report)와 계산부(ctx.results)를 합쳐 한 장의 보고서로 만든다."""
import html
import json
import re
from datetime import datetime

from .docs import num as docs_num
from .guardrails import CITE_RE

KIND = {"real": ("실제", "k-real"), "submitted": ("제출·가상", "k-syn"), "internal": ("내부·가상", "k-syn"),
        "regulation": ("규정·가상", "k-reg")}
LEVEL = {"높음": "h", "중간": "m", "낮음": "l"}
VERDICT = {"적합": "l", "부적합": "h", "조건부가": "m", "확인필요": "h", "위원회": "q"}
TONE = {"부정": "h", "중립": "q", "긍정": "l"}


def esc(s):
    return html.escape(str(s))


def cite(text):
    return CITE_RE.sub(lambda m: '<button class="cite" data-src="{0}">{0}</button>'.format(m.group(1)), esc(text))


def pill(text, cls):
    return '<span class="pill {}">{}</span>'.format(cls, esc(text))


def num(v, suffix=""):
    if v is None:
        return "–"
    return ("{:,}".format(v) if isinstance(v, int) else "{}".format(v)) + suffix


def render(ctx, mode):
    R, D, rep = ctx.results, ctx.data, ctx.report
    x, pm, fm = R["x"], R["project"], R["fin_metrics"]
    case = ctx.case
    fin = D["financials"]["years"]
    fs = D["financials"]["source"]
    rates = D.get("rates", {})
    grade = D.get("INT-02")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    masked = '<span class="masked">권한 없음</span>'
    na = '<span class="masked">미제출</span>'

    kinds = {}
    for s in ctx.sources.sources.values():
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    tool_calls = sum(1 for e in ctx.audit.entries if e["kind"] == "TOOL")

    # 1. 개요
    cd = rates.get("cd91")
    rate_txt = "CD {}% ({}) + {:.2f}%p = <b>{:.2f}%</b> {}".format(
        cd["value"], cd["time"], R["spread_used"], pm["all_in_rate"], cite("[{}]".format(cd["source"]))) if cd else "CD 조회 실패"
    b_name = case.borrower["name"]
    overview = [
        ("차주", "㈜{} ({}) {}".format(esc(b_name.replace("㈜", "")), esc(x["industry"] or case.borrower.get("industry", "")), cite("[SUB-01]"))),
        ("사업명", esc(x["project"])), ("여신과목", "시설자금대출 (신규)"),
        ("신청금액", "{:,.0f}억원".format(x["loan"])),
        ("기간", "{:.0f}년 (거치 {:.0f}년, 연 {:.0f}% 분할상환)".format(x["tenor"] or 0, x["grace"] or 0, x["amort"])),
        ("자금용도", esc(x["purpose"] or "")), ("담보", esc(x["collateral"] or "")),
        ("시공사", esc(case.contractor["name"])), ("설계", esc(case.info["architect"]["name"])),
        ("총사업비", "{:,}억원 (자기자금 {:,.0f}억)".format(pm["total_cost"], pm["equity"])),
        ("내부등급", "{} (CSS {}점, PD {}%) {}".format(grade["grade"], grade["css_score"], grade["pd_1y_pct"], cite("[INT-02]")) if grade else masked),
        ("신청금리", esc(x["rate_request"] or "")),
        ("적용금리(안)", rate_txt if grade else masked + " (등급별 가산금리 필요)"),
    ]
    ov_html = "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(k, v) for k, v in overview)

    # 3. 시장금리
    rate_rows = "".join(
        "<tr><td>{}</td><td class='num'>{}%</td><td class='num'>{}</td><td>{}</td><td>{}</td></tr>".format(
            esc(v["name"]), v["value"], esc(v["time"]), "실시간" if v["mode"] == "live" else pill("캐시 " + v["mode"][6:16], "m"),
            cite("[{}]".format(v["source"]))) for v in rates.values())

    # 4. 재무
    years = sorted(fin) if fin else []
    def frow(label, get, fmt=lambda x: num(x)):
        return "<tr><td>{}</td>{}</tr>".format(label, "".join("<td class='num'>{}</td>".format(fmt(get(y))) for y in years))
    fin_rows = "".join([
        frow("매출액", lambda y: fin[y].get("revenue")), frow("영업이익", lambda y: fin[y].get("operating_income")),
        frow("영업이익률", lambda y: fm[y].get("op_margin"), lambda x: num(x, "%")),
        frow("EBITDA", lambda y: fm[y].get("ebitda")), frow("부채총계", lambda y: fin[y].get("total_liabilities")),
        frow("자본총계", lambda y: fin[y].get("total_equity")),
        frow("부채비율", lambda y: fm[y].get("debt_ratio"), lambda x: num(x, "%")),
        frow("차입금의존도", lambda y: fm[y].get("borrowing_dependency"), lambda x: num(x, "%")),
        frow("이자보상배율", lambda y: fm[y].get("interest_coverage"), lambda x: num(x, "배")),
        frow("영업활동현금흐름", lambda y: fin[y].get("operating_cf")),
    ])
    fin_src = ("OpenDART 공시 " + cite("[DART-FS]")) if fs == "DART-FS" else (
        (pill("Fallback", "m") + " DART 미연결로 차주 제출본 사용 " + cite("[SUB-05]") + ". 공시 대사 전까지 잠정 수치입니다.") if fs else pill("재무자료 없음", "h"))

    # 5. 사업성
    fsid = "[{}]".format(fs) if fs else ""
    show = lambda v, u: "–" if v is None else "{}{}".format(v, u)
    proj = [("총사업비", "{:,}억".format(pm["total_cost"]), "[SUB-02]"), ("자기자금비율", "{}%".format(pm["equity_ratio"]), "[SUB-02]"),
            ("신규 연 원리금(거치 후)", "{}억".format(pm["new_debt_service"]), "[SUB-01]"),
            ("DSCR", show(pm["dscr"], "배"), fsid), ("DSCR (사업 현금흐름 제외)", show(pm["dscr_ex_project"], "배"), fsid),
            ("준공 후 LTV", show(pm["ltv_completed"], "%"), "[SUB-04]" if pm["ltv_completed"] else ""),
            ("토지가치 대비 대출", show(pm["ltv_land"], "%"), "[SUB-04]" if pm["ltv_land"] else ""),
            ("대출 후 부채비율", show(pm["post_loan_debt_ratio"], "%"), fsid)]
    proj_html = "".join("<div class='metric'><small>{}</small><b>{}</b>{}</div>".format(esc(a), esc(b), cite(c)) for a, b, c in proj)

    # 6. 참여자
    parties = "".join("<article><div class='role'>{}</div><h4>{}</h4><ul>{}</ul></article>".format(
        esc(p["role"]), esc(p["name"]), "".join("<li>{}</li>".format(cite(n)) for n in p["notes"])) for p in rep["participants"])

    # 7. 대사
    xc = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td class='num'>{}</td><td>{}</td></tr>".format(
        esc(x["item"]), cite(x["a"]), cite(x["b"]), x["diff"], pill(x["status"], "l" if x["status"] == "일치" else "h")) for x in R["cross"])

    # 8. 위험
    risks = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
        esc(r["factor"]), pill(r["level"], LEVEL.get(r["level"], "q")), cite(r["basis"]), esc(r["mitigation"])) for r in rep["risks"])

    # 9. 규정
    reg_title = lambda rid: ctx.sources.sources.get(rid, {}).get("title", rid)
    rules = "".join("<tr><td>{}<br>{}</td><td>{}</td><td class='num'>{}</td><td>{}</td><td>{}</td></tr>".format(
        esc(reg_title(r["rule"])), cite("[{}]".format(r["rule"])), esc(r["criterion"]), esc(r["value"]),
        pill(r["verdict"], VERDICT.get(r["verdict"], "q")), esc(r["note"])) for r in R["rules"])

    # 10. 뉴스
    news_html = ""
    for co, items in D.get("news", {}).items():
        news_html += "<h4 class='sub'>{}</h4><div class='tbl-wrap'><table><tbody>".format(esc(co))
        for n in items:
            news_html += "<tr><td class='num'>{}</td><td><a href='{}' target='_blank' rel='noopener'>{}</a> <span class='muted'>{}</span></td><td>{}</td><td>{}</td></tr>".format(
                esc(n["date"]), esc(n["url"]), esc(n["title"]), esc(n["publisher"]),
                pill(n["tone"], TONE[n["tone"]]) + (" <span class='muted'>" + esc(", ".join(n["keywords"])) + "</span>" if n["keywords"] else ""),
                cite("[{}]".format(n["source"])))
        news_html += "</tbody></table></div>"
    if not news_html:
        news_html = "<p>뉴스를 가져오지 못했습니다. 심사역 확인 항목에 추가했습니다.</p>"

    # 11. HITL
    hitl = "".join('<label><input type="checkbox" class="hc" id="h{}"> <span><b>{}</b><br><span class="muted">{}</span></span></label>'.format(
        i, esc(h["item"]), cite(h["reason"])) for i, h in enumerate(ctx.hitl.items))

    # 12. 출처
    srcs = "".join("<li id='s-{0}'><code>{0}</code><span>{1} {2}<br><span class='muted'>{3} · {4}{5}</span></span></li>".format(
        esc(s["id"]), pill(KIND[s["kind"]][0], KIND[s["kind"]][1]),
        ("<a href='{}' target='_blank' rel='noopener'>{}</a>".format(esc(s["url"]), esc(s["title"])) if s.get("url") else esc(s["title"])),
        esc(s["origin"]), esc(s["fetched_at"]), (" · " + pill("Fallback: " + s["fallback"][:22], "m")) if s.get("fallback") else ""
    ) for s in sorted(ctx.sources.sources.values(), key=lambda s: ("real", "submitted", "internal", "regulation").index(s["kind"])))

    audit = "\n".join("[{}] {:<9} {}".format(e["ts"], e["kind"], e["msg"]) for e in ctx.audit.entries)
    conds = "".join("<li>{}</li>".format(esc(c)) for c in rep["conditions"])
    fb_html = "".join("<li>{} → {}</li>".format(esc(x["what"]), esc(x["mode"])) for x in ctx.fallbacks) or "<li>없음</li>"

    body = TEMPLATE
    for k, v in {
        "BORROWER": esc(case.borrower["name"]), "PROJECT": esc(x["project"]), "APPNO": esc(x["application_no"] or case.id),
        "EXTRA": esc(", ".join("{} {}억".format(k.split("(")[0], v) for k, v in x["extra_items"].items() if (docs_num(v) or 0) > 0) or "없음"),
        "ROLE": esc(ctx.perm.label), "MODE": {"claude": "Claude Agent", "codex": "Codex Agent (MCP)"}.get(mode, "규칙 기반(offline)"), "NOW": now,
        "CAN_APPROVE": json.dumps(ctx.perm.can_approve), "OVERVIEW": ov_html, "REC": esc(rep["recommendation"]),
        "OPINION": cite(rep["opinion"]), "CONDS": conds, "RATES": rate_rows or "<tr><td colspan=5>조회 실패</td></tr>",
        "YEARS": "".join("<th class='num'>{}</th>".format(y) for y in years), "FINROWS": fin_rows, "FINSRC": fin_src,
        "PROJ": proj_html, "PARTIES": parties, "XC": xc, "RISKS": risks, "RULES": rules, "NEWS": news_html,
        "HITL": hitl, "HITLN": str(len(ctx.hitl.items)), "SRCS": srcs, "AUDIT": esc(audit),
        "N_TOOLS": str(tool_calls), "N_SRC": str(len(ctx.sources.sources)), "N_REAL": str(kinds.get("real", 0)),
        "N_SYN": str(kinds.get("submitted", 0) + kinds.get("internal", 0)), "N_REG": str(kinds.get("regulation", 0)),
        "N_FB": str(len(ctx.fallbacks)), "FB": fb_html,
        "N_DENY": str(sum(1 for e in ctx.audit.entries if e["kind"] == "DENY")),
    }.items():
        body = body.replace("{{" + k + "}}", v)
    return body


TEMPLATE = r"""<title>{{BORROWER}} 여신심사 보고서</title>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: 좌측 Agent 실행 요약(sticky) + 우측 심사보고서 본문 */
:root{--bg:#f3f4f2;--paper:#fff;--ink:#15212b;--muted:#5d6a73;--line:#d9dedd;--accent:#1f5f6b;--accent-soft:#e2eeef;
--ok:#2d7a4b;--ok-soft:#e3f1e8;--warn:#a86a10;--warn-soft:#faf0dc;--bad:#b0392f;--bad-soft:#f8e4e1;--mask:#e8ebea;--real:#2b5aa8;--real-soft:#e3ebf8;
--f-display:"Noto Serif KR","Apple SD Gothic Neo",serif;--f-body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;--f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1519;--paper:#161e23;--ink:#e3e8ea;--muted:#95a3ab;--line:#2a353c;--accent:#6fb3bf;--accent-soft:#1c3237;--ok:#6cc08c;--ok-soft:#1a2f23;--warn:#e0a54a;--warn-soft:#33281a;--bad:#e57c72;--bad-soft:#3a201e;--mask:#232d33;--real:#86a9e8;--real-soft:#1d2940;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1519;--paper:#161e23;--ink:#e3e8ea;--muted:#95a3ab;--line:#2a353c;--accent:#6fb3bf;--accent-soft:#1c3237;--ok:#6cc08c;--ok-soft:#1a2f23;--warn:#e0a54a;--warn-soft:#33281a;--bad:#e57c72;--bad-soft:#3a201e;--mask:#232d33;--real:#86a9e8;--real-soft:#1d2940;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:14px;line-height:1.65}
a{color:var(--accent)}
.wrap{max-width:1240px;margin:0 auto;padding-inline:16px;padding-block:20px 60px}
.note{font-size:12px;color:var(--warn);background:var(--warn-soft);border-radius:6px;padding:8px 12px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:280px minmax(0,1fr);gap:20px;align-items:start}
@media (max-width:900px){.grid{grid-template-columns:1fr}}
aside{position:sticky;top:calc(env(safe-area-inset-top,0px) + 12px);background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:16px;font-size:12.5px}
@media (max-width:900px){aside{position:static}}
aside h2{font-size:12px;letter-spacing:.06em;margin:0 0 10px;color:var(--muted)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.stats div{background:var(--bg);border-radius:6px;padding:8px}.stats small{display:block;font-size:10.5px;color:var(--muted)}
.stats b{font-family:var(--f-mono);font-size:16px;font-weight:500}
aside ul{margin:4px 0 12px;padding-left:16px}
.legend{display:flex;flex-wrap:wrap;gap:6px}
main{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:clamp(18px,4vw,44px);min-width:0}
.head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;border-bottom:2px solid var(--ink);padding-bottom:14px;margin-bottom:22px}
.head h1{font-family:var(--f-display);font-size:clamp(22px,3vw,28px);margin:0;line-height:1.3;text-wrap:balance}
.head .meta{font-family:var(--f-mono);font-size:11.5px;color:var(--muted);text-align:right}
@media (max-width:600px){.head .meta{text-align:left}}
.stamp{display:inline-block;border:1.5px solid var(--bad);color:var(--bad);font-size:11px;font-weight:600;padding:1px 8px;border-radius:3px;letter-spacing:.06em;margin-bottom:6px}
.stamp.done{border-color:var(--ok);color:var(--ok)}
h3{font-family:var(--f-display);font-size:17px;margin:36px 0 10px;display:flex;gap:10px;align-items:baseline}
h3 .n{font-family:var(--f-mono);font-size:12px;color:var(--accent);font-weight:500}
h4.sub{font-size:13px;margin:14px 0 4px}
p{margin:0 0 10px;max-width:74ch}.muted{color:var(--muted);font-size:12px}
.tbl-wrap{overflow-x:auto;margin:6px 0 8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12px;background:var(--bg);white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--f-mono);white-space:nowrap}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));column-gap:24px;border-top:1px solid var(--line);margin:0}
.kv div{display:grid;grid-template-columns:92px minmax(0,1fr);gap:8px;padding:7px 0;border-bottom:1px solid var(--line);font-size:13px}
.kv dt{color:var(--muted);font-size:12px}.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}
.verdict{display:grid;grid-template-columns:auto minmax(0,1fr);gap:20px;background:var(--accent-soft);border-radius:8px;padding:18px}
@media (max-width:600px){.verdict{grid-template-columns:1fr}}
.grade{min-width:120px}.grade small{display:block;font-size:11px;color:var(--muted)}
.grade b{font-family:var(--f-display);font-size:22px;color:var(--accent);display:block;line-height:1.3}
.verdict ol{margin:8px 0 0;padding-left:20px;font-size:13px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.metric{border:1px solid var(--line);border-radius:6px;padding:10px 12px}
.metric small{display:block;font-size:11.5px;color:var(--muted)}.metric b{font-family:var(--f-mono);font-size:18px;font-weight:500;margin-right:4px}
.pill{display:inline-block;font-size:11.5px;font-weight:600;padding:1px 8px;border-radius:999px;white-space:nowrap}
.pill.h{background:var(--bad-soft);color:var(--bad)}.pill.m{background:var(--warn-soft);color:var(--warn)}
.pill.l{background:var(--ok-soft);color:var(--ok)}.pill.q{background:var(--mask);color:var(--muted)}
.pill.k-real{background:var(--real-soft);color:var(--real)}.pill.k-syn{background:var(--mask);color:var(--muted)}.pill.k-reg{background:var(--accent-soft);color:var(--accent)}
.cite{font-family:var(--f-mono);font-size:10.5px;color:var(--accent);background:var(--accent-soft);border:0;border-radius:3px;padding:0 4px;margin-left:2px;cursor:pointer;vertical-align:1px}
.cite:hover{text-decoration:underline}
.masked{background:var(--mask);color:var(--muted);border-radius:3px;padding:0 6px;font-size:12px;white-space:nowrap}
.party{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.party article{border:1px solid var(--line);border-radius:8px;padding:14px;min-width:0}
.party h4{margin:0;font-size:14px}.party .role{font-size:11px;color:var(--muted);letter-spacing:.04em}
.party ul{margin:8px 0 0;padding-left:18px;font-size:12.5px}
.hitl{border:1.5px solid var(--bad);border-radius:8px;padding:18px;background:var(--bad-soft)}
.hitl label{display:flex;gap:10px;align-items:flex-start;padding:7px 0;font-size:13px;cursor:pointer;border-bottom:1px dashed var(--line)}
.hitl input{margin-top:4px;accent-color:var(--accent)}
.hitl textarea{width:100%;min-height:64px;margin-top:10px;border:1px solid var(--line);border-radius:6px;padding:8px;font:inherit;font-size:13px;background:var(--paper);color:var(--ink)}
.decide{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
.btn{border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:6px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--paper)}.btn:disabled{opacity:.45;cursor:not-allowed}
button:focus-visible,input:focus-visible,textarea:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.src{list-style:none;padding:0;margin:0;font-size:12.5px}
.src li{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;padding:6px 8px;border-bottom:1px solid var(--line);border-radius:4px;transition:background .3s}
.src li.flash{background:var(--accent-soft)}.src code{font-family:var(--f-mono);color:var(--accent);font-size:11.5px}
.audit{font-family:var(--f-mono);font-size:11.5px;background:var(--bg);border-radius:6px;padding:10px 12px;max-height:300px;overflow:auto;white-space:pre-wrap;word-break:break-all;margin:0}
.foot{font-size:11.5px;color:var(--muted);margin-top:28px;border-top:1px solid var(--line);padding-top:12px}
</style>
<div class="wrap">
<div class="note">PoC 결과물입니다. <b>실제</b> 표시 출처(한국은행 ECOS 금리, Google 뉴스, OpenDART)는 실행 시점에 조회한 실데이터이고, <b>가상</b> 표시 출처(차주 제출서류, 은행 내부자료, 사내 규정)는 시연용으로 만든 자료입니다. 가상 재무수치는 실제 공시와 다릅니다.</div>
<div class="grid">
<aside aria-label="Agent 실행 요약">
  <h2>AGENT 실행 요약</h2>
  <div class="stats">
    <div><small>도구 호출</small><b>{{N_TOOLS}}</b></div><div><small>등록 출처</small><b>{{N_SRC}}</b></div>
    <div><small>실데이터</small><b>{{N_REAL}}</b></div><div><small>가상자료</small><b>{{N_SYN}}</b></div>
    <div><small>규정 조문</small><b>{{N_REG}}</b></div><div><small>권한 거부</small><b>{{N_DENY}}</b></div>
    <div><small>Fallback</small><b>{{N_FB}}</b></div><div><small>사람 확인</small><b>{{HITLN}}</b></div>
  </div>
  <h2>FALLBACK 내역</h2><ul>{{FB}}</ul>
  <h2>출처 구분</h2>
  <div class="legend"><span class="pill k-real">실제</span><span class="pill k-syn">제출·가상</span><span class="pill k-syn">내부·가상</span><span class="pill k-reg">규정·가상</span></div>
</aside>
<main id="report">
  <div class="head">
    <div><span class="stamp" id="stamp">AI 초안 · 심사역 검토 전</span>
      <h1>기업여신 심사보고서<br>{{PROJECT}}</h1></div>
    <div class="meta">문서번호 {{APPNO}}<br>작성 {{MODE}}<br>생성 {{NOW}}<br>열람 권한 {{ROLE}}<br>결재 <span id="reviewer">대기</span></div>
  </div>

  <h3><span class="n">1</span>신청 개요</h3>
  <dl class="kv">{{OVERVIEW}}</dl>

  <h3><span class="n">2</span>종합의견</h3>
  <div class="verdict">
    <div class="grade"><small>AI 권고</small><b>{{REC}}</b><small>최종 결정은 여신위원회</small></div>
    <div><p>{{OPINION}}</p><b style="font-size:13px">승인 조건</b><ol>{{CONDS}}</ol></div>
  </div>

  <h3><span class="n">3</span>시장금리 <span class="pill k-real">실제</span></h3>
  <div class="tbl-wrap"><table><thead><tr><th>지표</th><th class="num">값</th><th class="num">기준일</th><th>조회</th><th>출처</th></tr></thead><tbody>{{RATES}}</tbody></table></div>

  <h3><span class="n">4</span>차주 재무분석 <span class="muted">(억원)</span></h3>
  <p class="muted">{{FINSRC}}</p>
  <div class="tbl-wrap"><table><thead><tr><th>항목</th>{{YEARS}}</tr></thead><tbody>{{FINROWS}}</tbody></table></div>

  <h3><span class="n">5</span>사업성 지표</h3>
  <div class="metrics">{{PROJ}}</div>
  <p class="muted" style="margin-top:8px">DSCR = (EBITDA + 사업 추가 현금흐름 {{EXTRA}}) ÷ (기존 원리금 + 신규 원리금). 사업 현금흐름 제외값은 EBITDA만 사용.</p>

  <h3><span class="n">6</span>사업 참여자 검증</h3>
  <div class="party">{{PARTIES}}</div>

  <h3><span class="n">7</span>문서 간 대사</h3>
  <div class="tbl-wrap"><table><thead><tr><th>항목</th><th>자료 A</th><th>자료 B</th><th class="num">차이(억)</th><th>결과</th></tr></thead><tbody>{{XC}}</tbody></table></div>

  <h3><span class="n">8</span>위험요인과 완화방안</h3>
  <div class="tbl-wrap"><table><thead><tr><th>위험요인</th><th>수준</th><th>근거</th><th>완화방안</th></tr></thead><tbody>{{RISKS}}</tbody></table></div>

  <h3><span class="n">9</span>내부규정 적합성</h3>
  <div class="tbl-wrap"><table><thead><tr><th>규정</th><th>기준</th><th class="num">결과</th><th>판정</th><th>비고</th></tr></thead><tbody>{{RULES}}</tbody></table></div>

  <h3><span class="n">10</span>외부뉴스 <span class="pill k-real">실제</span></h3>
  <p class="muted">부정·긍정 분류는 키워드 규칙이며, 기사 내용 판단은 심사역이 합니다.</p>
  {{NEWS}}

  <h3><span class="n">11</span>심사역 확인 (Human-in-the-loop)</h3>
  <div class="hitl">
    <p><b>Agent가 확정하지 않고 사람에게 넘긴 {{HITLN}}개 항목입니다.</b> 모두 확인해야 상신할 수 있습니다.</p>
    {{HITL}}
    <textarea id="opinion" placeholder="심사역 의견 (AI 초안 수정 사항, 추가 조건 등)"></textarea>
    <div class="decide">
      <button class="btn primary" id="d-ok" disabled>조건부 승인으로 상신</button>
      <button class="btn" id="d-mod">재작성 요청</button>
      <button class="btn" id="d-no">반려</button>
      <span class="muted" id="d-hint"></span>
    </div>
  </div>

  <h3><span class="n">12</span>출처</h3>
  <ul class="src">{{SRCS}}</ul>

  <h3><span class="n">13</span>감사로그</h3>
  <pre class="audit" id="audit">{{AUDIT}}</pre>

  <p class="foot">모든 판단 문장에는 출처가 연결되어 있고, 출처 없는 문장이 있으면 보고서 제출 단계에서 반려됩니다. 숫자는 코드가 계산하고 AI는 서술만 작성합니다. 최종 여신 결정은 심사역과 여신위원회가 합니다.</p>
</main></div></div>
<script>
(function(){
  var canApprove={{CAN_APPROVE}},decided=false;
  var checks=[].slice.call(document.querySelectorAll('.hc')),ok=document.getElementById('d-ok'),
      mod=document.getElementById('d-mod'),no=document.getElementById('d-no'),hint=document.getElementById('d-hint'),audit=document.getElementById('audit');
  function t(){return new Date().toTimeString().slice(0,8);}
  function log(m){audit.textContent+='\n['+t()+'] REVIEW    '+m;audit.scrollTop=audit.scrollHeight;}
  function upd(){
    var n=checks.filter(function(c){return c.checked;}).length;
    checks.forEach(function(c){c.disabled=!canApprove||decided;});
    ok.disabled=!(canApprove&&!decided&&n===checks.length);mod.disabled=no.disabled=!canApprove||decided;
    hint.textContent=decided?'결재 완료':(!canApprove?'이 역할은 열람만 가능합니다':'확인 '+n+' / '+checks.length);
  }
  checks.forEach(function(c){c.addEventListener('change',function(){log((c.checked?'확인 ':'해제 ')+c.nextElementSibling.querySelector('b').textContent);upd();});});
  function decide(label){
    decided=true;var s=document.getElementById('stamp');s.textContent='심사역 결재 · '+label;s.classList.add('done');
    document.getElementById('reviewer').textContent=label;var op=document.getElementById('opinion').value.trim();
    log('결정: '+label+(op?' / 의견: '+op:''));upd();
  }
  ok.onclick=function(){decide('조건부 승인 상신');};mod.onclick=function(){decide('재작성 요청');};no.onclick=function(){decide('반려');};
  document.getElementById('report').addEventListener('click',function(e){
    var b=e.target.closest('.cite');if(!b)return;var li=document.getElementById('s-'+b.dataset.src);if(!li)return;
    li.scrollIntoView({behavior:'smooth',block:'center'});li.classList.add('flash');setTimeout(function(){li.classList.remove('flash');},1400);
  });
  upd();
})();
</script>
"""
