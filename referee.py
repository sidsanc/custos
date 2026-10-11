"""The referee. Privileged, out-of-band, the only writer of `harness`.

Watches `proposals` via a change stream, checks invariants, scores the candidate on train AND the
sealed holdout, and promotes or rejects in one multi-document transaction. The agent only ever
learns accepted/rejected plus a reason category - never holdout questions, answers, or scores.
"""
import copy
import datetime as dt
import sys

from rich import print
from rich.panel import Panel

from custos.db import films, referee_db
from custos.harness import evaluate

db = referee_db()
client = db.client


def now():
    return dt.datetime.now(dt.timezone.utc)


def active():
    return db.harness.find_one({"status": "active"})


def score(h):
    train = list(db.train.find())
    hold = list(db.holdout.find())
    rt, rh = evaluate(h, train, db), evaluate(h, hold, db)
    return rt, rh


def record_failures(version, results):
    db.failures.delete_many({"version": version})
    train = {c["_id"]: c for c in db.train.find()}
    sample = films(db).find_one({}, {"_id": 0})  # the trace shows what the data actually looks like
    docs = [{"_id": f"v{version}-{r['case']}", "version": version, "case": r["case"],
             "question": train[r["case"]]["question"], "expected": train[r["case"]]["expected"],
             "pipeline": r.get("pipeline"), "got": r.get("got"), "error": r.get("error"), "data_sample": sample}
            for r in results if not r["ok"]]
    if docs:
        db.failures.insert_many(docs)


def baseline():
    h = active()
    if h.get("scores"):
        return h
    print(f"[cyan]referee[/] scoring baseline v{h['version']} ...")
    rt, rh = score(h)
    s = {"train": sum(r["ok"] for r in rt), "holdout": sum(r["ok"] for r in rh),
         "pass": [r["case"] for r in rt + rh if r["ok"]]}
    db.harness.update_one({"_id": h["_id"]}, {"$set": {"scores": s}})
    record_failures(h["version"], rt)
    db.metrics.insert_one({"ts": now(), "meta": {"version": h["version"], "event": "baseline"},
                           "train": s["train"], "holdout": s["holdout"], "rules": len(h["rules"])})
    print(f"[cyan]referee[/] v{h['version']}  train {s['train']}/8  holdout {s['holdout']}/8")
    return active()


def invariants(p, parent):
    if p["parent"] != parent["version"]:
        return "stale: proposal is not against the active harness"
    if p.get("remove_guardrails"):
        return "guardrail monotonicity: guardrails can be added, never removed"
    if "tool_grants" in p:
        extra = set(p["tool_grants"].get("allowed_stages", [])) - set(parent["tool_grants"]["allowed_stages"])
        if extra:
            return f"tool grants can only shrink; tried to add {sorted(extra)}"
    known = {f["_id"] for f in db.failures.find({"version": parent["version"]}, {"_id": 1})}
    for r in p["add_rules"]:
        missing = [b for b in r["born_from"] if b not in known]
        if missing:
            return f"provenance: rule cites failures that were never observed {missing}"
    return None


def candidate_from(p, parent):
    c = copy.deepcopy(parent)
    c.pop("_id")
    c.update(version=parent["version"] + 1, parent=parent["version"], status="active", scores={},
             proposal=p["_id"], created=now())
    drop = set(p.get("remove_rules", []))
    c["rules"] = [r for r in c["rules"] if r["id"] not in drop]
    for i, r in enumerate(p["add_rules"]):
        c["rules"].append({"id": f"R{c['version']}.{i + 1}", "text": r["text"], "born_from": r["born_from"],
                           "added_in": c["version"]})
    c["guardrails"] = parent["guardrails"] + p.get("add_guardrails", [])
    if "tool_grants" in p:
        c["tool_grants"] = p["tool_grants"]
    if "context_policy" in p:
        c["context_policy"] = {**parent["context_policy"], **p["context_policy"]}
    return c


def judge(p):
    parent = active()
    reason = invariants(p, parent)
    verdict, cand, s, rt = "rejected", None, None, []
    if reason is None:
        cand = candidate_from(p, parent)
        rt, rh = score(cand)
        s = {"train": sum(r["ok"] for r in rt), "holdout": sum(r["ok"] for r in rh),
             "pass": [r["case"] for r in rt + rh if r["ok"]]}
        ps = parent["scores"]
        regressed = sorted(set(ps["pass"]) - set(s["pass"]))
        total_c, total_p = s["train"] + s["holdout"], ps["train"] + ps["holdout"]
        removal_only = not p["add_rules"] and p.get("remove_rules")
        print(f"   train {ps['train']}->{s['train']}   holdout(sealed) {ps['holdout']}->{s['holdout']}"
              f"   regressions {regressed or '-'}")
        # Promotion rule: a change must GENERALISE (sealed holdout goes up, train does not drop),
        # or make the harness smaller at no loss. Train-only gains are memorisation, not learning.
        if s["holdout"] < ps["holdout"]:
            reason = "regressed on the sealed holdout"
        elif s["holdout"] > ps["holdout"] and s["train"] >= ps["train"]:
            verdict, reason = "accepted", "generalised: sealed holdout improved"
        elif removal_only and total_c >= total_p:
            verdict, reason = "accepted", "simpler harness, no loss"
        elif s["train"] > ps["train"]:
            reason = "did not generalise: train-only gain (memorisation)"
        else:
            reason = "no measurable improvement"

    def txn(session):
        if verdict == "accepted":
            cand["scores"] = s
            db.harness.update_one({"_id": parent["_id"]}, {"$set": {"status": "retired"}}, session=session)
            db.harness.insert_one(cand, session=session)
        db.proposals.update_one({"_id": p["_id"]},
                                {"$set": {"status": verdict, "reason": reason, "judged": now()}},
                                session=session, bypass_document_validation=True)
        db.audit.insert_one({"ts": now(), "proposal": p["_id"], "author": p.get("author"), "verdict": verdict,
                             "reason": reason, "parent": parent["version"],
                             "scores": s, "parent_scores": parent["scores"]}, session=session)

    with client.start_session() as session:
        session.with_transaction(txn)
    if verdict == "accepted":
        record_failures(cand["version"], rt)
    v = cand["version"] if verdict == "accepted" else parent["version"]
    db.metrics.insert_one({"ts": now(), "meta": {"version": v, "event": verdict},
                           "train": (s or parent["scores"])["train"], "holdout": (s or parent["scores"])["holdout"],
                           "rules": len((cand or parent)["rules"])})
    color = "green" if verdict == "accepted" else "red"
    print(Panel(f"[bold {color}]{verdict.upper()}[/]  {reason}" +
                (f"\npromoted to v{cand['version']} in a transaction" if verdict == "accepted" else ""),
                title=f"proposal by {p.get('author', '?')}: {p['rationale'][:70]}"))


def main():
    baseline()
    print("[cyan]referee[/] watching custos.proposals (change stream) ...")
    for p in db.proposals.find({"status": "pending"}):
        judge(p)
    with db.proposals.watch([{"$match": {"operationType": "insert"}}]) as stream:
        for change in stream:
            judge(change["fullDocument"])


if __name__ == "__main__":
    sys.exit(main())
