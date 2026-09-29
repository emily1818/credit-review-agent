"""여신심사 AI Agent 데모 웹앱 (표준 라이브러리만 사용).

  python3 webapp.py            → http://localhost:8780

1) 사례 선택 → 2) 기업정보 확인·서류 업로드 → 3) Agent(Codex 또는 규칙 기반) 분석 진행 → 4) 심사보고서
"""
import html
import json
import re
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent / "src"))
from credit_agent import agent, codex_runner, config, report  # noqa: E402
from credit_agent.docs import SLOTS, Case  # noqa: E402
from credit_agent.tools import Context  # noqa: E402

PORT = 8780
RID_RE = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9a-f]{6}$")
CASE_RE = re.compile(r"^C[0-9]+$")


def cases():
    return json.loads((config.CASES / "index.json").read_text(encoding="utf-8"))


def run_dir(rid):
    return config.RUNS / rid


def write_status(rid, **kw):
    p = run_dir(rid) / "status.json"
    st = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    st.update(kw)
    p.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def execute(rid, mode, role):
    d = run_dir(rid)
    case_dir, out, log = d / "case", d / "report.html", d / "audit.jsonl"
    try:
        if mode == "codex":
            with open(d / "codex.log", "w", encoding="utf-8") as f:
                rc = codex_runner.run(case_dir, role, out, log, d / "codex_answer.txt", stdout=f, stderr=f)
            if not out.exists():
                ctx = Context(role, Case(case_dir), log_path=str(log))
                ctx.audit.add("FALLBACK", "Codex가 보고서를 남기지 못함(종료코드 {}) → 규칙 기반 초안으로 대체".format(rc))
                ctx.note_fallback("LLM 서술(Codex)", "규칙 기반 템플릿")
                agent.run(ctx, "offline")
                out.write_text(report.render(ctx, "offline"), encoding="utf-8")
        else:
            ctx = Context(role, Case(case_dir), log_path=str(log))
            agent.run(ctx, "offline")
            out.write_text(report.render(ctx, "offline"), encoding="utf-8")
        write_status(rid, state="done", finished=datetime.now().strftime("%H:%M:%S"))
    except Exception as e:
        write_status(rid, state="error", error=str(e)[:300])


# ------------------------------------------------------------------ pages
STYLE = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#f3f4f2;--paper:#fff;--ink:#15212b;--muted:#5d6a73;--line:#d9dedd;--accent:#1f5f6b;--accent-soft:#e2eeef;
--ok:#2d7a4b;--ok-soft:#e3f1e8;--warn:#a86a10;--warn-soft:#faf0dc;--bad:#b0392f;--bad-soft:#f8e4e1;
--f-display:"Noto Serif KR","Apple SD Gothic Neo",serif;--f-body:"IBM Plex Sans KR","Apple SD Gothic Neo",sans-serif;--f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0f1519;--paper:#161e23;--ink:#e3e8ea;--muted:#95a3ab;--line:#2a353c;--accent:#6fb3bf;--accent-soft:#1c3237;
--ok:#6cc08c;--ok-soft:#1a2f23;--warn:#e0a54a;--warn-soft:#33281a;--bad:#e57c72;--bad-soft:#3a201e;color-scheme:dark}}
[hidden]{display:none!important}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:14px;line-height:1.6}
a{color:var(--accent)}.wrap{max-width:1080px;margin:0 auto;padding-inline:16px;padding-block:28px 60px}
header{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:24px}
header b{font-family:var(--f-display);font-size:22px}header small{font-family:var(--f-mono);font-size:11px;color:var(--muted);letter-spacing:.06em}
.steps{display:flex;gap:6px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.steps span{padding:2px 10px;border-radius:999px;background:var(--paper);border:1px solid var(--line)}
.steps span.on{background:var(--accent);color:var(--paper);border-color:var(--accent)}
h1{font-family:var(--f-display);font-size:24px;margin:0 0 6px}p.lead{color:var(--muted);margin:0 0 22px;max-width:70ch}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:18px;text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:6px}
.card:hover{border-color:var(--accent)}.card .id{font-family:var(--f-mono);font-size:11px;color:var(--accent)}
.card h3{margin:0;font-size:16px}.card .row{font-size:12.5px;color:var(--muted)}.card .amt{font-family:var(--f-mono);font-size:18px}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:20px;margin-bottom:16px}
.panel h2{font-size:15px;margin:0 0 12px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
fieldset{border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:0;min-width:0}legend{font-size:12px;color:var(--muted);padding:0 4px}
label.f{display:block;font-size:12px;color:var(--muted);margin-top:8px}
input[type=text],select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink);font:inherit;font-size:13px}
.slots{display:grid;gap:10px}
.slot{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;border:1.5px dashed var(--line);border-radius:8px;padding:12px 14px;transition:border-color .2s,background .2s}
.slot.drag{border-color:var(--accent);background:var(--accent-soft)}.slot.filled{border-style:solid;border-color:var(--ok);background:var(--ok-soft)}
.slot b{font-size:13.5px}.slot .req{font-size:11px;color:var(--bad);margin-left:6px}.slot .opt{font-size:11px;color:var(--muted);margin-left:6px}
.slot .fn{font-family:var(--f-mono);font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.slot .acts{display:flex;gap:6px}
.btn{border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:6px;padding:7px 14px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none;display:inline-block}
.btn:hover{border-color:var(--accent)}.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--paper)}.btn.sm{padding:3px 10px;font-size:12px}
.btn:disabled{opacity:.45;cursor:not-allowed}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.hint{font-size:12px;color:var(--muted)}
.log{font-family:var(--f-mono);font-size:12px;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:12px 14px;max-height:520px;overflow:auto}
.log div{padding:2px 0;border-bottom:1px dashed var(--line);display:grid;grid-template-columns:70px 84px minmax(0,1fr);gap:8px}
.k-TOOL{color:var(--accent)}.k-FALLBACK,.k-MISSING{color:var(--warn)}.k-DENY,.k-REJECT{color:var(--bad)}.k-DRAFT,.k-LIVE{color:var(--ok)}.k-HITL{color:var(--bad)}
.state{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.state.running{background:var(--warn-soft);color:var(--warn)}.state.done{background:var(--ok-soft);color:var(--ok)}.state.error{background:var(--bad-soft);color:var(--bad)}
.note{font-size:12px;color:var(--warn);background:var(--warn-soft);border-radius:6px;padding:8px 12px;margin-bottom:18px}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style>"""


def page(title, step, body):
    steps = "".join('<span class="{}">{}</span>'.format("on" if i == step else "", s)
                    for i, s in enumerate(["1 사례 선택", "2 서류 업로드", "3 Agent 분석", "4 심사보고서"], 1))
    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>{}</title>{}</head><body><div class='wrap'><header><div><small>CORPORATE CREDIT REVIEW AGENT · POC</small><br>"
            "<a href='/' style='text-decoration:none;color:inherit'><b>여신심사 AI Agent</b></a></div><div class='steps'>{}</div></header>{}</div></body></html>"
            ).format(html.escape(title), STYLE, steps, body)


def home():
    cards = ""
    for c in cases():
        cards += """<a class="card" href="/new?case={id}"><span class="id">{id}</span><h3>㈜{b}</h3>
<div class="row">{p}</div><div class="amt">{loan:,}억원</div><div class="row">시공 {c} · 설계 {a}</div></a>""".format(
            id=c["case_id"], b=html.escape(c["borrower"]["name"]), p=html.escape(c["project"]), loan=c["loan"],
            c=html.escape(c["contractor"]["name"]), a=html.escape(c["architect"]["name"]))
    body = """<h1>심사할 사례를 고르세요</h1>
<p class="lead">사례마다 차주가 제출하는 서류 5종이 <code>data/cases/사례ID/</code> 폴더에 준비되어 있습니다. 다음 화면에서 파일을 직접 끌어다 넣거나, 일부를 빼고 넣어 결과가 어떻게 달라지는지 볼 수 있습니다.</p>
<div class="note">모든 서류와 은행 내부자료는 시연용 가상 데이터입니다. 금리(한국은행 ECOS)와 뉴스(Google News)는 실행 시점의 실제 데이터이고, DART 키가 있으면 재무제표도 실제 공시로 대체됩니다.</div>
<div class="cards">{}</div>""".format(cards)
    return page("여신심사 AI Agent", 1, body)


def new_form(case_id):
    info = json.loads((config.CASES / case_id / "case.json").read_text(encoding="utf-8"))
    slots = ""
    for sid, (fn, title, req) in SLOTS.items():
        exists = (config.CASES / case_id / fn).exists()
        slots += """<div class="slot" data-slot="{sid}" data-sample="{sample}">
  <div><b>{title}</b><span class="{rc}">{rt}</span><div class="fn" id="fn-{sid}">파일을 끌어다 놓거나 선택하세요 · 샘플: {fn}{nos}</div></div>
  <div class="acts"><label class="btn sm">파일 선택<input type="file" id="file-{sid}" accept=".md,.txt,.json" hidden></label>
  <button type="button" class="btn sm" data-clear="{sid}">비우기</button></div></div>""".format(
            sid=sid, title=html.escape(title), fn=html.escape(fn), rc="req" if req else "opt",
            rt="필수" if req else "선택 · DART 연결 시 불필요", sample="/sample/{}/{}".format(case_id, fn) if exists else "",
            nos="" if exists else " (이 사례는 샘플 없음)")
    b, c, a = info["borrower"], info["contractor"], info["architect"]
    body = """<h1>{cid} · ㈜{bn}</h1><p class="lead">{proj} · 신청 {loan:,}억원</p>
<form id="f" class="panel"><h2>기업정보</h2><div class="grid3">
<fieldset><legend>차주 · 발주자</legend><label class="f" for="b_name">회사명</label><input type="text" id="b_name" value="{bn}">
<label class="f" for="b_code">종목코드 (DART·뉴스 조회)</label><input type="text" id="b_code" value="{bc}">
<label class="f" for="b_ind">업종</label><input type="text" id="b_ind" value="{bi}"></fieldset>
<fieldset><legend>시공사</legend><label class="f" for="c_name">회사명</label><input type="text" id="c_name" value="{cn}">
<label class="f" for="c_code">종목코드</label><input type="text" id="c_code" value="{cc}"></fieldset>
<fieldset><legend>설계</legend><label class="f" for="a_name">건축사사무소</label><input type="text" id="a_name" value="{an}">
<label class="f" for="proj">사업명</label><input type="text" id="proj" value="{proj}"></fieldset>
</div></form>
<div class="panel"><div class="bar" style="margin-bottom:12px"><h2 style="margin:0">제출 서류</h2>
<span><button type="button" class="btn sm" id="fill">샘플 서류 모두 채우기</button> <span class="hint">샘플 위치: data/cases/{cid}/</span></span></div>
<div class="slots">{slots}</div></div>
<div class="panel bar"><div style="display:flex;gap:14px;flex-wrap:wrap">
<label class="hint" for="mode">Agent 두뇌 <select id="mode" style="width:auto"><option value="codex">Codex (MCP 도구 호출)</option><option value="offline">규칙 기반 (빠름, LLM 없음)</option></select></label>
<label class="hint" for="role">요청자 권한 <select id="role" style="width:auto"><option value="reviewer">심사역</option><option value="rm">영업점 RM</option><option value="compliance">준법감시</option></select></label></div>
<div><span class="hint" id="cnt"></span> <button class="btn primary" id="go" disabled>분석 시작</button></div></div>
<script>
var CASE="{cid}",files={{}},req={req};
function upd(){{var n=0,m=0;req.forEach(function(s){{if(files[s])n++;}});Object.keys(files).forEach(function(){{m++;}});
document.getElementById('cnt').textContent='필수 '+n+'/'+req.length+' · 전체 '+m+'/5';document.getElementById('go').disabled=m===0;}}
function setFile(sid,name,text){{files[sid]={{name:name,text:text}};var el=document.querySelector('[data-slot="'+sid+'"]');el.classList.add('filled');
document.getElementById('fn-'+sid).textContent=name+' · '+text.length.toLocaleString()+'자';upd();}}
function clear(sid){{delete files[sid];var el=document.querySelector('[data-slot="'+sid+'"]');el.classList.remove('filled');
document.getElementById('fn-'+sid).textContent='비어 있음 (제출하지 않음)';upd();}}
function readInto(sid,f){{var r=new FileReader();r.onload=function(){{setFile(sid,f.name,r.result);}};r.readAsText(f,'utf-8');}}
document.querySelectorAll('.slot').forEach(function(el){{var sid=el.dataset.slot;
 el.addEventListener('dragover',function(e){{e.preventDefault();el.classList.add('drag');}});
 el.addEventListener('dragleave',function(){{el.classList.remove('drag');}});
 el.addEventListener('drop',function(e){{e.preventDefault();el.classList.remove('drag');if(e.dataTransfer.files[0])readInto(sid,e.dataTransfer.files[0]);}});
 document.getElementById('file-'+sid).addEventListener('change',function(e){{if(e.target.files[0])readInto(sid,e.target.files[0]);}});}});
document.querySelectorAll('[data-clear]').forEach(function(b){{b.onclick=function(){{clear(b.dataset.clear);}};}});
document.getElementById('fill').onclick=function(){{document.querySelectorAll('.slot').forEach(function(el){{if(!el.dataset.sample)return;
 fetch(el.dataset.sample).then(function(r){{return r.text();}}).then(function(t){{setFile(el.dataset.slot,el.dataset.sample.split('/').pop(),t);}});}});}};
document.getElementById('go').onclick=function(){{var b=this;b.disabled=true;b.textContent='요청 중…';
 var v=function(id){{return document.getElementById(id).value.trim();}};
 var body={{case_id:CASE,mode:v('mode'),role:v('role'),files:files,info:{{case_id:CASE,project:v('proj'),
  borrower:{{name:v('b_name'),stock_code:v('b_code'),industry:v('b_ind')}},contractor:{{name:v('c_name'),stock_code:v('c_code')}},architect:{{name:v('a_name')}}}}}};
 fetch('/api/run',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}}).then(function(r){{return r.json();}})
 .then(function(j){{if(j.run_id)location.href='/run/'+j.run_id;else{{b.textContent='오류: '+(j.error||'');b.disabled=false;}}}});}};
upd();
</script>""".format(cid=case_id, bn=html.escape(b["name"]), bc=html.escape(b["stock_code"]), bi=html.escape(b.get("industry", "")),
                    cn=html.escape(c["name"]), cc=html.escape(c.get("stock_code", "")), an=html.escape(a["name"]),
                    proj=html.escape(info["project"]), loan=info["loan"], slots=slots,
                    req=json.dumps([s for s, v in SLOTS.items() if v[2]]))
    return page("{} 서류 업로드".format(case_id), 2, body)


def run_page(rid):
    body = """<h1 id="t">Agent 분석 중 <span class="state running" id="st">진행 중</span></h1>
<p class="lead" id="sub">도구 호출과 안전장치 동작이 아래에 실시간으로 쌓입니다.</p>
<div class="panel bar"><span class="hint" id="meta"></span><span><a class="btn" href="/">다른 사례</a> <a class="btn primary" id="rep" href="/report/{rid}" hidden>심사보고서 열기</a></span></div>
<div class="panel" id="ans" hidden><h2>Agent 최종 답변</h2><div id="anst" style="white-space:pre-wrap"></div></div>
<div class="log" id="log"></div>
<script>
var seen=0;function tick(){{fetch('/api/run/{rid}').then(function(r){{return r.json();}}).then(function(j){{
 var box=document.getElementById('log');j.log.slice(seen).forEach(function(e){{var d=document.createElement('div');
  d.innerHTML='<span>'+e.ts+'</span><span class="k-'+e.kind+'">'+e.kind+'</span><span></span>';d.lastChild.textContent=e.msg;box.appendChild(d);}});
 if(j.log.length>seen){{seen=j.log.length;box.scrollTop=box.scrollHeight;}}
 var n=function(k){{return j.log.filter(function(e){{return e.kind===k;}}).length;}};
 document.getElementById('meta').textContent=j.mode_label+' · '+j.role+' · 도구 호출 '+n('TOOL')+' · Fallback '+n('FALLBACK')+' · 권한 거부 '+n('DENY')+' · 반려 '+n('REJECT');
 var st=document.getElementById('st');
 if(j.state==='done'){{st.className='state done';st.textContent='완료';document.getElementById('t').firstChild.textContent='분석 완료 ';
  document.getElementById('rep').hidden=false;if(j.answer){{document.getElementById('ans').hidden=false;document.getElementById('anst').textContent=j.answer;}}return;}}
 if(j.state==='error'){{st.className='state error';st.textContent='오류';document.getElementById('sub').textContent=j.error;return;}}
 setTimeout(tick,1000);}}).catch(function(){{setTimeout(tick,2000);}});}}
tick();
</script>""".format(rid=rid)
    return page("Agent 분석", 3, body)


# ------------------------------------------------------------------ server
class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        if not parts:
            return self._send(200, home())
        if parts[0] == "new":
            cid = parse_qs(u.query).get("case", ["C1"])[0]
            if not CASE_RE.match(cid) or not (config.CASES / cid / "case.json").exists():
                return self._send(404, "없는 사례")
            return self._send(200, new_form(cid))
        if parts[0] == "sample" and len(parts) == 3 and CASE_RE.match(parts[1]):
            from urllib.parse import unquote
            fn = unquote(parts[2])
            if fn not in [v[0] for v in SLOTS.values()]:
                return self._send(404, "없음")
            p = config.CASES / parts[1] / fn
            return self._send(200, p.read_bytes(), "text/plain; charset=utf-8") if p.exists() else self._send(404, "없음")
        if len(parts) == 2 and RID_RE.match(parts[1]):
            rid, d = parts[1], run_dir(parts[1])
            if not d.exists():
                return self._send(404, "없는 실행")
            if parts[0] == "run":
                return self._send(200, run_page(rid))
            if parts[0] == "report":
                p = d / "report.html"
                return self._send(200, p.read_bytes()) if p.exists() else self._send(404, "보고서가 아직 없습니다")
        if len(parts) == 3 and parts[:2] == ["api", "run"] and RID_RE.match(parts[2]):
            d = run_dir(parts[2])
            st = json.loads((d / "status.json").read_text(encoding="utf-8"))
            log = []
            if (d / "audit.jsonl").exists():
                for line in (d / "audit.jsonl").read_text(encoding="utf-8").splitlines():
                    try:
                        log.append(json.loads(line))
                    except ValueError:
                        pass
            ans = (d / "codex_answer.txt").read_text(encoding="utf-8").strip() if (d / "codex_answer.txt").exists() else ""
            return self._json(dict(st, log=log, answer=ans))
        self._send(404, "Not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/run":
            return self._send(404, "Not found")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        except ValueError:
            return self._json({"error": "잘못된 요청"}, 400)
        cid, mode, role = body.get("case_id", ""), body.get("mode"), body.get("role")
        if not CASE_RE.match(cid) or mode not in ("codex", "offline") or role not in ("reviewer", "rm", "compliance"):
            return self._json({"error": "잘못된 파라미터"}, 400)
        rid = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        case_dir = run_dir(rid) / "case"
        case_dir.mkdir(parents=True)
        info = body.get("info") or {}
        info["case_id"] = cid
        info["loan"] = next((c["loan"] for c in cases() if c["case_id"] == cid), 0)
        (case_dir / "case.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        for sid, f in (body.get("files") or {}).items():
            if sid in SLOTS and isinstance(f, dict) and isinstance(f.get("text"), str) and len(f["text"]) < 2_000_000:
                (case_dir / SLOTS[sid][0]).write_text(f["text"], encoding="utf-8")
        write_status(rid, state="running", mode=mode, role={"reviewer": "심사역", "rm": "영업점 RM", "compliance": "준법감시"}[role],
                     mode_label="Codex Agent (MCP)" if mode == "codex" else "규칙 기반", started=datetime.now().strftime("%H:%M:%S"),
                     uploaded=sorted(k for k in (body.get("files") or {}) if k in SLOTS))
        threading.Thread(target=execute, args=(rid, mode, role), daemon=True).start()
        self._json({"run_id": rid})


def main():
    config.RUNS.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("여신심사 AI Agent 데모: http://localhost:{}".format(PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
