"""Agent 도구를 MCP(stdio) 서버로 노출한다. Codex 같은 외부 Agent가 이 도구만으로 심사를 진행한다.

권한·출처 검증·Fallback·HITL은 모두 이 서버 안에서 강제되므로, 어떤 LLM이 두뇌가 되든 같은 안전장치가 적용된다.
Codex가 보고서를 제출하지 못하고 끝나면(연결이 닫히면) 규칙 기반 초안으로 Fallback한 뒤 보고서를 쓴다.

  python3 -m credit_agent.mcp_server --role reviewer --out out/report_codex.html
"""
import argparse
import json
import signal
import sys
from pathlib import Path

from . import agent, report, tools
from .docs import Case
from .tools import Context

PROTO_OUT = sys.stdout
sys.stdout = sys.stderr  # 감사로그 print가 프로토콜 채널(stdout)을 오염시키지 않도록


def send(msg):
    PROTO_OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
    PROTO_OUT.flush()


def write_outputs(ctx, out, mode):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.render(ctx, mode), encoding="utf-8")
    out.with_suffix(".audit.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in ctx.audit.entries), encoding="utf-8")
    ctx.audit.add("OUTPUT", "보고서 저장: {}".format(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="reviewer")
    ap.add_argument("--outage", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--log", default=None)
    a = ap.parse_args()
    out = Path(a.out)

    case = Case(Path(a.case_dir))
    ctx = Context(a.role, case, outages=[x for x in a.outage.split(",") if x], log_path=a.log)
    ctx.audit.add("START", "심사 요청 {} 접수 (역할: {}, 모드: Codex via MCP)".format(case.id, ctx.perm.label))
    defs = {d["name"]: d for d in tools.claude_tool_defs()}
    # 종료 신호를 받아도 아래 마무리(Fallback·저장)가 돌도록 stdin 루프만 끊는다
    signal.signal(signal.SIGTERM, lambda *_: sys.stdin.close())

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:  # notification
            continue
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "credit-agent", "version": "0.1.0"},
                "instructions": agent.system_prompt(case)}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": d["name"], "description": d["description"], "inputSchema": d["input_schema"]} for d in defs.values()]}})
        elif method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if name not in defs:
                send({"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [{"type": "text", "text": "unknown tool " + str(name)}]}})
                continue
            try:
                had_report = ctx.report is not None
                res = tools.call(ctx, name, args)
                if ctx.report is not None and not had_report:
                    write_outputs(ctx, out, "codex")
                    res = dict(res, report_path=str(out), note="보고서 저장 완료. 작업을 마치고 요약만 답하세요.")
                send({"jsonrpc": "2.0", "id": mid, "result": {"isError": False, "content": [
                    {"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)[:60000]}]}})
            except Exception as e:
                ctx.audit.add("ERROR", "{}: {}".format(name, str(e)[:120]))
                send({"jsonrpc": "2.0", "id": mid, "result": {"isError": True, "content": [{"type": "text", "text": str(e)}]}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: " + str(method)}})

    # 연결 종료. Codex가 보고서를 못 냈으면 규칙 기반 초안으로 대체한다.
    if ctx.report is None:
        ctx.audit.add("FALLBACK", "Codex가 보고서를 제출하지 않고 종료 → 규칙 기반 초안으로 대체")
        ctx.note_fallback("LLM 서술(Codex)", "규칙 기반 템플릿")
        agent._collect(ctx)
        agent._offline_narrative(ctx)
        ctx.audit.add("HITL", "심사역 확인 대기 {}건".format(len(ctx.hitl.items)))
        write_outputs(ctx, out, "codex")
    else:
        ctx.audit.add("HITL", "심사역 확인 대기 {}건. 사람 결재 전까지 보고서는 초안 상태".format(len(ctx.hitl.items)))
        write_outputs(ctx, out, "codex")


if __name__ == "__main__":
    main()
