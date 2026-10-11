"""The self-improving agent. Runs as the restricted `custos-agent` Atlas user.

It may READ its active harness and its own train failures, and INSERT proposals. That is all.
It cannot write the harness, read the holdout, or touch the referee - Atlas RBAC, not a prompt,
enforces that.
"""
import json
import sys
import time

from rich import print

from custos.db import agent_db
from custos.llm import chat, extract_json

db = agent_db()

SYSTEM = """You improve the harness of a text-to-MongoDB-aggregation agent.
You see the current harness and the training cases it failed (question, the pipeline it produced,
what it got, what was expected). Output field names do NOT matter, only values. Diagnose by comparing the question with the data_sample:
check field TYPES (e.g. numbers stored as strings), value CASING, UNITS (seconds vs minutes), CODES
(e.g. ISO country codes) and NESTED paths. Propose ONE small change that fixes the ROOT CAUSE of the failures
in general, not the specific answers. Rules must describe the data or the method, never literal answers.
Reply with ONLY a JSON object:
{"rationale": "...",
 "add_rules": [{"text": "general rule", "born_from": ["<failure _id>", ...]}],
 "remove_rules": ["<rule id>", ...],
 "context_policy": {"sample_docs": <0-3>}}   # optional
Every added rule must cite the failure _ids it was born from."""


def wait_verdict(pid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = db.proposals.find_one({"_id": pid}, {"status": 1, "reason": 1})
        if p["status"] != "pending":
            return p
        time.sleep(2)
    return {"status": "timeout", "reason": ""}


def step(gen):
    h = db.harness.find_one({"status": "active"})
    fails = list(db.failures.find({"version": h["version"]}))
    print(f"\n[bold]gen {gen}[/]  harness v{h['version']}  rules={len(h['rules'])}  "
          f"failing train cases={len(fails)}")
    if not fails:
        print("[green]no visible failures left[/]")
        return False
    view = {k: h[k] for k in ("version", "rules", "guardrails", "tool_grants", "context_policy")}
    failures = [{k: f.get(k) for k in ("_id", "question", "pipeline", "got", "expected", "error", "data_sample")} for f in fails]
    reply = chat(SYSTEM, json.dumps({"harness": view, "failures": failures}, default=str), temperature=0.3)
    try:
        prop = extract_json(reply)
    except ValueError:
        print("[yellow]proposer produced no JSON; skipping[/]")
        return True
    doc = {"parent": h["version"], "author": "agent", "status": "pending",
           "rationale": str(prop.get("rationale", ""))[:500],
           "add_rules": [{"id": "new", "text": str(r.get("text", "")), "born_from": list(r.get("born_from", []))}
                         for r in prop.get("add_rules", []) if isinstance(r, dict)],
           "remove_rules": list(prop.get("remove_rules", []))}
    if isinstance(prop.get("context_policy"), dict):
        doc["context_policy"] = {"sample_docs": int(prop["context_policy"].get("sample_docs", 0))}
    for r in doc["add_rules"]:
        print(f"  proposes rule: [italic]{r['text']}[/]  <- {r['born_from']}")
    if "context_policy" in doc:
        print(f"  proposes context policy: {doc['context_policy']}")
    try:
        pid = db.proposals.insert_one(doc).inserted_id
    except Exception as e:  # noqa: BLE001 - schema validator rejection is a verdict too
        print(f"  [red]Atlas rejected the proposal at write time:[/] {str(e)[:160]}")
        return True
    v = wait_verdict(pid)
    print(f"  verdict: [{'green' if v['status'] == 'accepted' else 'red'}]{v['status']}[/] ({v['reason']})")
    return True


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    for g in range(1, n + 1):
        if not step(g):
            break
