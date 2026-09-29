"""GitHub Pages용 정적 데모를 docs/에 만든다.

  python3 scripts/build_pages.py

- docs/reports/C1~C6.html : 빌드 시점의 실데이터(ECOS·뉴스)로 미리 생성한 심사보고서
- docs/bundle.json        : Agent 엔진(파이썬 소스)·은행 DB·샘플 서류·API 캐시 스냅샷
- docs/index.html         : 사례 선택 → 서류 업로드 → 브라우저(Pyodide)에서 Agent 실행 → 보고서

브라우저에서는 외부 API를 직접 호출할 수 없으므로 엔진이 캐시로 Fallback하고, 보고서에 그 사실이 표시된다.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from credit_agent import agent, config, report  # noqa: E402
from credit_agent.docs import SLOTS, Case  # noqa: E402
from credit_agent.tools import Context  # noqa: E402
from webapp import STYLE  # noqa: E402

DOCS = ROOT / "docs"
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/"


def build_reports():
    (DOCS / "reports").mkdir(parents=True, exist_ok=True)
    summary = []
    for d in sorted(p for p in config.CASES.iterdir() if (p / "case.json").exists()):
        ctx = Context("reviewer", Case(d))
        agent.run(ctx, "offline")
        (DOCS / "reports" / (d.name + ".html")).write_text(report.render(ctx, "offline"), encoding="utf-8")
        summary.append({"case_id": d.name, "recommendation": ctx.report["recommendation"], "hitl": len(ctx.hitl.items)})
    return summary


def build_bundle():
    files = {}
    for p in (ROOT / "src" / "credit_agent").rglob("*.py"):
        if p.name not in ("mcp_server.py", "codex_runner.py"):
            files[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8")
    for base in ("data/bank", "data/cases", "data/cache"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and p.suffix in (".md", ".json"):
                files[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8")
    (DOCS / "bundle.json").write_text(json.dumps({"files": files}, ensure_ascii=False), encoding="utf-8")
    return len(files)


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>여신심사 AI Agent 데모</title>__STYLE__
<style>
.tabs{display:flex;gap:8px;margin:0 0 16px}.view[hidden]{display:none}
.card .rec{font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px;align-self:flex-start}
.rec.승인{background:var(--ok-soft);color:var(--ok)}.rec.조건부{background:var(--warn-soft);color:var(--warn)}.rec.보류{background:var(--bad-soft);color:var(--bad)}
.card .links{display:flex;gap:8px;margin-top:6px}
iframe{width:100%;height:80vh;border:1px solid var(--line);border-radius:10px;background:var(--paper)}
</style></head><body><div class="wrap">
<header><div><small>CORPORATE CREDIT REVIEW AGENT · POC</small><br><a href="#" id="home" style="text-decoration:none;color:inherit"><b>여신심사 AI Agent</b></a></div>
<div class="steps" id="steps"><span class="on">1 사례 선택</span><span>2 서류 업로드</span><span>3 Agent 분석</span><span>4 심사보고서</span></div></header>

<section class="view" id="v1">
<h1>심사할 사례를 고르세요</h1>
<p class="lead">차주가 서류를 제출하면 AI Agent가 재무·기업정보·내부규정·외부뉴스를 모아 심사보고서 초안을 쓰고, 확정할 수 없는 항목은 심사역에게 넘깁니다. 사례를 골라 미리 생성된 보고서를 보거나, 서류를 직접 올려 브라우저에서 Agent를 돌려보세요.</p>
<div class="note">모든 서류와 은행 내부자료는 시연용 가상 데이터이며 실제 기업의 재무·신용상태와 무관합니다. 금리(한국은행 ECOS)와 뉴스(Google News)는 __BUILT__ 기준 실데이터입니다. 이 페이지는 브라우저 안에서 규칙 기반 Agent를 실행하고, 로컬 버전에서는 Codex가 MCP 도구를 호출해 분석합니다.</div>
<div class="cards" id="cards"></div>
</section>

<section class="view" id="v2" hidden>
<h1 id="t2"></h1><p class="lead" id="s2"></p>
<div class="panel"><div class="bar" style="margin-bottom:12px"><h2 style="margin:0">제출 서류</h2>
<span><button type="button" class="btn sm" id="fill">샘플 서류 모두 채우기</button> <span class="hint">파일을 끌어다 놓거나 선택하세요. 일부를 비워두면 결과가 달라집니다.</span></span></div>
<div class="slots" id="slots"></div></div>
<div class="panel bar"><label class="hint" for="role">요청자 권한 <select id="role" style="width:auto"><option value="reviewer">심사역</option><option value="rm">영업점 RM</option><option value="compliance">준법감시</option></select></label>
<div><span class="hint" id="cnt"></span> <button class="btn primary" id="go" disabled>분석 시작</button></div></div>
</section>

<section class="view" id="v3" hidden>
<h1 id="t3">Agent 분석 중 <span class="state running" id="st">준비 중</span></h1>
<p class="lead" id="s3">처음 실행하면 브라우저용 Python(Pyodide)을 내려받느라 10~20초 걸립니다.</p>
<div class="panel bar"><span class="hint" id="meta"></span><span><button class="btn" id="back">다른 사례</button> <button class="btn primary" id="open" hidden>심사보고서 보기</button></span></div>
<div class="log" id="log"></div>
</section>

<section class="view" id="v4" hidden>
<div class="bar" style="margin-bottom:12px"><h1 style="margin:0" id="t4">심사보고서</h1><span><button class="btn" id="back2">다른 사례</button></span></div>
<iframe id="rep" title="심사보고서"></iframe>
</section>
</div>
<script src="__PYODIDE__pyodide.js"></script>
<script>
var CASES=__CASES__, SLOTS=__SLOTS__, SUMMARY=__SUMMARY__, bundle=null, py=null, cur=null, files={};
function show(n){for(var i=1;i<=4;i++){document.getElementById('v'+i).hidden=i!==n;document.getElementById('steps').children[i-1].className=i===n?'on':'';}window.scrollTo(0,0);}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function getBundle(){return bundle?Promise.resolve(bundle):fetch('bundle.json').then(function(r){return r.json();}).then(function(b){bundle=b;return b;});}
function recClass(r){return r==='승인'?'승인':(r==='보류'?'보류':'조건부');}
CASES.forEach(function(c){var s=SUMMARY[c.case_id]||{};var a=document.createElement('div');a.className='card';
 a.innerHTML='<span class="id">'+c.case_id+'</span><h3>㈜'+esc(c.borrower.name)+'</h3><div class="row">'+esc(c.project)+'</div><div class="amt">'+c.loan.toLocaleString()+'억원</div><div class="row">시공 '+esc(c.contractor.name)+' · 설계 '+esc(c.architect.name)+'</div>'+
 (s.recommendation?'<span class="rec '+recClass(s.recommendation)+'">샘플 결과: '+s.recommendation+'</span>':'')+
 '<div class="links"><a class="btn sm" href="reports/'+c.case_id+'.html" target="_blank" rel="noopener">보고서 보기</a><button class="btn sm primary" data-case="'+c.case_id+'">서류 올려 분석</button></div>';
 document.getElementById('cards').appendChild(a);});
document.getElementById('cards').addEventListener('click',function(e){var b=e.target.closest('[data-case]');if(b)openCase(b.dataset.case);});
function openCase(id){cur=CASES.filter(function(c){return c.case_id===id;})[0];files={};
 document.getElementById('t2').textContent=cur.case_id+' · ㈜'+cur.borrower.name;document.getElementById('s2').textContent=cur.project+' · 신청 '+cur.loan.toLocaleString()+'억원 · 시공 '+cur.contractor.name;
 var box=document.getElementById('slots');box.innerHTML='';
 Object.keys(SLOTS).forEach(function(sid){var s=SLOTS[sid];var el=document.createElement('div');el.className='slot';el.dataset.slot=sid;
  el.innerHTML='<div><b>'+esc(s[1])+'</b><span class="'+(s[2]?'req':'opt')+'">'+(s[2]?'필수':'선택')+'</span><div class="fn" id="fn-'+sid+'">비어 있음 · 샘플: '+esc(s[0])+'</div></div><div class="acts"><label class="btn sm">파일 선택<input type="file" accept=".md,.txt,.json" hidden></label><button type="button" class="btn sm">비우기</button></div>';
  el.addEventListener('dragover',function(e){e.preventDefault();el.classList.add('drag');});el.addEventListener('dragleave',function(){el.classList.remove('drag');});
  el.addEventListener('drop',function(e){e.preventDefault();el.classList.remove('drag');if(e.dataTransfer.files[0])readInto(sid,e.dataTransfer.files[0]);});
  el.querySelector('input').addEventListener('change',function(e){if(e.target.files[0])readInto(sid,e.target.files[0]);});
  el.querySelectorAll('button')[0].onclick=function(){delete files[sid];el.classList.remove('filled');document.getElementById('fn-'+sid).textContent='비어 있음 (제출하지 않음)';upd();};
  box.appendChild(el);});
 upd();show(2);}
function setFile(sid,name,text){files[sid]={name:name,text:text};document.querySelector('[data-slot="'+sid+'"]').classList.add('filled');document.getElementById('fn-'+sid).textContent=name+' · '+text.length.toLocaleString()+'자';upd();}
function readInto(sid,f){var r=new FileReader();r.onload=function(){setFile(sid,f.name,r.result);};r.readAsText(f,'utf-8');}
function upd(){var req=Object.keys(SLOTS).filter(function(s){return SLOTS[s][2];});var n=req.filter(function(s){return files[s];}).length;var m=Object.keys(files).length;
 document.getElementById('cnt').textContent='필수 '+n+'/'+req.length+' · 전체 '+m+'/'+Object.keys(SLOTS).length;document.getElementById('go').disabled=m===0;}
document.getElementById('fill').onclick=function(){getBundle().then(function(b){Object.keys(SLOTS).forEach(function(sid){var p='data/cases/'+cur.case_id+'/'+SLOTS[sid][0];if(b.files[p])setFile(sid,SLOTS[sid][0],b.files[p]);});});};
function log(e){var d=document.createElement('div');d.innerHTML='<span>'+e.ts+'</span><span class="k-'+e.kind+'">'+e.kind+'</span><span></span>';d.lastChild.textContent=e.msg;var box=document.getElementById('log');box.appendChild(d);box.scrollTop=box.scrollHeight;}
function status(t,cls){var s=document.getElementById('st');s.textContent=t;s.className='state '+cls;}
function boot(){if(py)return Promise.resolve(py);status('Python 불러오는 중','running');
 return Promise.all([loadPyodide(),getBundle()]).then(function(r){py=r[0];var b=r[1];
  Object.keys(b.files).forEach(function(p){var parts=('/app/'+p).split('/');for(var i=2;i<parts.length;i++){var d=parts.slice(0,i).join('/');try{py.FS.mkdir(d);}catch(e){}}py.FS.writeFile('/app/'+p,b.files[p]);});
  py.runPython("import sys; sys.path.insert(0, '/app/src')");return py;});}
var RUNNER="import json, shutil\nfrom pathlib import Path\nfrom credit_agent import agent, report\nfrom credit_agent.docs import Case, SLOTS\nfrom credit_agent.tools import Context\n"+
"def run_case(info_json, files_json, role):\n    info, files = json.loads(info_json), json.loads(files_json)\n    d = Path('/work/case')\n    shutil.rmtree(d, ignore_errors=True)\n    d.mkdir(parents=True)\n"+
"    (d / 'case.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')\n    for sid, f in files.items():\n        (d / SLOTS[sid][0]).write_text(f['text'], encoding='utf-8')\n"+
"    ctx = Context(role, Case(d))\n    agent.run(ctx, 'offline')\n    return json.dumps({'html': report.render(ctx, 'offline'), 'log': ctx.audit.entries, 'rec': ctx.report['recommendation'], 'hitl': len(ctx.hitl.items)}, ensure_ascii=False)\n";
var lastHtml='';
document.getElementById('go').onclick=function(){document.getElementById('log').innerHTML='';document.getElementById('open').hidden=true;show(3);
 document.getElementById('t3').firstChild.textContent='Agent 분석 중 ';document.getElementById('meta').textContent='규칙 기반 Agent (브라우저) · '+document.getElementById('role').selectedOptions[0].text;
 boot().then(function(py){status('분석 중','running');return new Promise(function(res){setTimeout(function(){
   py.runPython(RUNNER);var out=py.globals.get('run_case')(JSON.stringify(cur),JSON.stringify(files),document.getElementById('role').value);res(JSON.parse(out));},30);});})
 .then(function(r){var i=0;(function next(){if(i<r.log.length){log(r.log[i++]);setTimeout(next,25);return;}
   status('완료','done');document.getElementById('t3').firstChild.textContent='분석 완료 · 권고 '+r.rec+' ';
   var n=function(k){return r.log.filter(function(e){return e.kind===k;}).length;};
   document.getElementById('meta').textContent+=' · 도구 호출 '+n('TOOL')+' · Fallback '+n('FALLBACK')+' · 권한 거부 '+n('DENY')+' · 사람 확인 '+r.hitl;
   lastHtml=r.html;document.getElementById('open').hidden=false;})();})
 .catch(function(e){status('오류','error');document.getElementById('s3').textContent=String(e).slice(0,400);});};
document.getElementById('open').onclick=function(){document.getElementById('rep').srcdoc=lastHtml;document.getElementById('t4').textContent='심사보고서 · ㈜'+cur.borrower.name;show(4);};
['home','back','back2'].forEach(function(id){document.getElementById(id).onclick=function(e){e.preventDefault();show(1);};});
</script></body></html>"""


def main():
    if DOCS.exists():
        shutil.rmtree(DOCS)
    DOCS.mkdir()
    summary = build_reports()
    n = build_bundle()
    cases = json.loads((config.CASES / "index.json").read_text(encoding="utf-8"))
    from datetime import date
    page = (PAGE.replace("__STYLE__", STYLE).replace("__PYODIDE__", PYODIDE)
            .replace("__BUILT__", date.today().isoformat())
            .replace("__CASES__", json.dumps(cases, ensure_ascii=False))
            .replace("__SLOTS__", json.dumps(SLOTS, ensure_ascii=False))
            .replace("__SUMMARY__", json.dumps({s["case_id"]: s for s in summary}, ensure_ascii=False)))
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print("docs/ 생성: 보고서 {}건, 번들 파일 {}개".format(len(summary), n))
    for s in summary:
        print("  {case_id}: {recommendation} (사람 확인 {hitl}건)".format(**s))


if __name__ == "__main__":
    main()
