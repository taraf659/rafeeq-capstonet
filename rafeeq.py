# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=3.30", "pydantic>=2.12", "python-dotenv>=1.1", "pandas>=2.2", "mcp>=2.3"]
# ///
"""Rafeeq Secure Municipal Agent.

Examples:
  uv run rafeeq.py ask "ما رسوم لوحة مضيئة مساحتها 3 متر مربع؟"
  uv run rafeeq.py chat --session demo
  uv run rafeeq.py eval tasks.jsonl --config A B
  uv run rafeeq.py security-test
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mcp import StdioServerParameters
import agentkit as K
import evals
import madar

OUT = K.lab_dir("rafeeq-capstone")
SPEC = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
CONFIGS = {
    "A": {"system": SPEC, "model": None},
    "B": {"system": SPEC + "\nFor every fee, deadline, or working-hours answer, retrieve the relevant policy before answering.", "model": None},
}
MAX_STEPS, MAX_COST, MAX_RESULT_CHARS, MAX_HISTORY_MESSAGES = 8, 0.05, 3000, 24
WRITE_TOOLS = set(madar.Madar.WRITE_TOOLS)

# Security controls are deterministic and do not depend on the model obeying the prompt.
def permission(name: str, args: dict) -> str:
    return "ask" if name in WRITE_TOOLS else "allow"

def approve_cli(name: str, args: dict) -> bool:
    print(f"\nApproval required for {name}: {json.dumps(args, ensure_ascii=False)}")
    return input("Approve? [y/N] ").strip().lower() == "y"

def cap_result(name: str, args: dict, result: str) -> str | None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"tool": name, "args": args, "chars": len(result)}, ensure_ascii=False) + "\n")
    if len(result) > MAX_RESULT_CHARS:
        return result[:MAX_RESULT_CHARS] + f"\n[truncated {len(result)-MAX_RESULT_CHARS} chars]"
    return None

def compact(history: list) -> list:
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history
    tail = history[-MAX_HISTORY_MESSAGES:]
    while tail and tail[0].get("role") != "user":
        tail.pop(0)
    return tail

def mcp_server() -> StdioServerParameters:
    return StdioServerParameters(command="uv", args=["run", "--quiet", str(ROOT / "servers" / "madar_mcp.py"), "--workdir", str(OUT / "mcp")])

def mcp_policy_tool(mcp: K.MCPBridge):
    # The MCP server exposes read-only policy/application tools. We intentionally consume
    # only search_policies over MCP; application state stays on the same local DB.
    for tool in mcp.list_tools():
        if tool.name == "search_policies":
            return K.mcp_to_tool(tool, mcp.call)
    raise RuntimeError("MCP server did not expose search_policies")

def local_tools(m: madar.Madar, policy_tool) -> list:
    return [policy_tool, m.get_permit, m.compute_fee, m.list_slots,
            m.book_inspection, m.reschedule_inspection, m.create_refund, m.escalate, m.send_email]

def make_agent(config: dict, mcp: K.MCPBridge, approve=approve_cli):
    def agent(prompt: str, m: madar.Madar, history: list | None = None, **kw) -> K.Run:
        tools = local_tools(m, mcp_policy_tool(mcp))
        return K.run_agent(prompt, tools, system=config["system"], model=config["model"], history=history,
                           max_steps=MAX_STEPS, max_cost=MAX_COST, permission=permission, approve=approve,
                           after_tool=cap_result, verbose=kw.pop("verbose", False), **kw)
    return agent

def run_security_tests() -> int:
    # The tests prove the write gate and privacy requirements are enforced in code.
    assert permission("compute_fee", {}) == "allow"
    assert permission("book_inspection", {}) == "ask"
    assert permission("send_email", {}) == "ask"
    m = madar.Madar(OUT / "security-db")
    try:
        m.get_permit("BLD-20417", "0000", "0500000000")
    except madar.ToolError as e:
        assert "Do not confirm" in str(e) or "verification failed" in str(e).lower()
    else:
        raise AssertionError("unverified permit lookup was not blocked")
    print("PASS: write approvals and identity verification are enforced")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask"); a.add_argument("question")
    c = sub.add_parser("chat"); c.add_argument("--session", default="default")
    e = sub.add_parser("eval"); e.add_argument("tasks", type=Path); e.add_argument("--config", nargs="+", default=["A", "B"]); e.add_argument("--trials", type=int, default=1)
    sub.add_parser("security-test")
    args = ap.parse_args()
    if args.cmd == "security-test":
        return run_security_tests()
    with K.MCPBridge(mcp_server()) as mcp:
        if args.cmd == "ask":
            run = make_agent(CONFIGS["A"], mcp)(args.question, madar.Madar(OUT / "db"), verbose=True)
            print("\n" + (run.final or f"(stopped: {run.stopped})"))
        elif args.cmd == "chat":
            path = OUT / f"session-{args.session}.json"
            history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            m, agent = madar.Madar(OUT / "db"), make_agent(CONFIGS["A"], mcp)
            print("Type a message; empty line quits.")
            while (msg := input("\nYou: ").strip()):
                run = agent(msg, m, history=compact(history))
                print("Rafeeq:", run.final or f"(stopped: {run.stopped})")
                history = run.state[1:]
                path.write_text(json.dumps(history, ensure_ascii=False, default=str), encoding="utf-8")
        else:
            tasks = evals.load_tasks(args.tasks)
            consent = lambda name, a: True
            frames = [evals.run_suite(make_agent(CONFIGS[c], mcp, approve=consent), tasks, trials=args.trials, name=c) for c in args.config]
            import pandas as pd
            df = pd.concat(frames)
            OUT.mkdir(parents=True, exist_ok=True)
            for config in args.config:
                df[df.agent == config].drop(columns="final").to_csv(OUT / f"eval-{config}.csv", index=False)
            overall, per_task = evals.report(df)
            print(overall)
            per_task.to_csv(OUT / "error-analysis.csv", index=False)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
