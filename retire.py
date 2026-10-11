"""Rule retirement: removal is a first-class change.

Harnesses only ever grow (ACE counts harmful bullets but never deletes them; AGENTS.md files add
>20% cost for no gain). Here the agent proposes deleting each rule one at a time, and the referee keeps
the deletion only if the sealed score holds. Run it after a model swap to strip stale scaffolding.
Same restricted credentials as agent.py.
"""
import time

from rich import print

from custos.db import agent_db

db = agent_db()


def wait(pid):
    while True:
        p = db.proposals.find_one({"_id": pid}, {"status": 1, "reason": 1})
        if p["status"] != "pending":
            return p
        time.sleep(2)


start = db.harness.find_one({"status": "active"})
print(f"harness v{start['version']}: {len(start['rules'])} rules")
for rule in list(start["rules"]):
    h = db.harness.find_one({"status": "active"})
    pid = db.proposals.insert_one({"parent": h["version"], "author": "retirer", "status": "pending",
                                   "rationale": f"ablate {rule['id']}: does it still earn its place?",
                                   "add_rules": [], "remove_rules": [rule["id"]]}).inserted_id
    v = wait(pid)
    tag = "[green]RETIRED[/]" if v["status"] == "accepted" else "[yellow]KEPT[/]   "
    print(f"  {tag} {rule['id']}  born_from={rule['born_from'][:3]}  \"{rule['text'][:70]}\"  ({v['reason']})")
end = db.harness.find_one({"status": "active"})
print(f"[bold]harness v{end['version']}: {len(start['rules'])} -> {len(end['rules'])} rules[/]")
