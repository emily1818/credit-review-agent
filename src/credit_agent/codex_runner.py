"""Codex CLI를 Agent 두뇌로 띄운다. 도구·안전장치는 mcp_server.py가 맡는다."""
import json
import subprocess
import sys

from . import agent, config
from .docs import Case

PROMPT = """{system}

도구는 MCP 서버 `credit`의 도구만 사용하세요. 셸 명령이나 파일 직접 읽기는 쓰지 마세요.
직접 읽은 파일은 출처로 등록되지 않아 인용할 수 없고, 권한관리도 우회하게 됩니다.
submit_report가 accepted=true를 반환하면 작업을 끝내고, 권고와 핵심 근거를 3줄로 요약해 답하세요."""


def build_cmd(case_dir, role, out, log_path, last_msg, outage=""):
    server_args = ["-m", "credit_agent.mcp_server", "--case-dir", str(case_dir), "--role", role,
                   "--out", str(out), "--log", str(log_path)]
    if outage:
        server_args += ["--outage", outage]
    return ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", str(config.OUT),
            "-c", 'approval_policy="never"',
            "-c", "mcp_servers.credit.command={}".format(json.dumps(sys.executable)),
            "-c", "mcp_servers.credit.args={}".format(json.dumps(server_args)),
            "-c", "mcp_servers.credit.cwd={}".format(json.dumps(str(config.ROOT / "src"))),
            "-c", 'mcp_servers.credit.default_tools_approval_mode="approve"',  # 이 서버의 도구만 자동 승인
            "-c", "mcp_servers.credit.startup_timeout_sec=30",
            "-c", "mcp_servers.credit.tool_timeout_sec=120",
            "-c", "mcp_servers.node_repl.enabled=false",
            "-o", str(last_msg), PROMPT.format(system=agent.system_prompt(Case(case_dir)))]


def run(case_dir, role, out, log_path, last_msg, outage="", stdout=None, stderr=None):
    config.OUT.mkdir(parents=True, exist_ok=True)
    cmd = build_cmd(case_dir, role, out, log_path, last_msg, outage)
    return subprocess.call(cmd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
