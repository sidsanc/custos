# Demo script

## Setup (before recording)
Use two terminals in `D:\Projects\custos`. Atlas Data Explorer should be open on db `custos`.

```bash
python seed.py          # reset: harness v0, fresh collections
```

## 1-minute video (submission)

| Time | Screen | Say |
|---|---|---|
| 0:00 | README headline | "Self-improving harnesses are here, and agents already edit their own graders: o3, the Darwin Gödel Machine, 63–85% tampering per iteration. Custos lets an agent rewrite its own harness, but never grade its own homework." |
| 0:10 | T1: `python referee.py` | "The referee is privileged and out-of-band. It watches proposals through an Atlas change stream and scores every change on a sealed holdout the agent cannot read." |
| 0:18 | T2: `python redteam.py` | "Same credentials as the agent. It tries to rewrite its harness: Atlas RBAC blocks it. It tries to read the answer key: blocked. It tries to accept its own proposal or add a rule with no provenance: the schema validator blocks it. Deleting a guardrail or granting itself `$out`: the referee rejects it. Hard-coding answers: rejected, it didn't generalize." |
| 0:35 | T2: `python agent.py 5` | "Now honest self-improvement. It reads its failures and proposes rules that cite the failures they came from. 2/16 to 14/16, promoted in a transaction. Two proposals that regressed on the sealed holdout were rejected. Then 16/16." |
| 0:50 | T2: `python retire.py` | "Harnesses only ever grow. Custos ablates every rule and retires dead weight: 5 rules to 3, no loss." |
| 0:57 | Atlas: `harness` versions + `audit` | "Every version, verdict and reason lives in MongoDB." |

## 3-minute live pitch (judging)
1. **Problem (30s):** self-improving agents can reach their own constraints. Cite the incident and paper table in the README.
2. **Red team live (45s):** the RBAC "not authorized" errors are the wow moment.
3. **Agent loop live (60s):** the score climbs, and the holdout rejections are visible.
4. **Retirement plus Atlas tour (30s):** harness lineage, the `audit` collection, the `metrics` time-series.
5. **Business (15s):** a change-control plane for self-modifying agents. It fills the gap in Atlas Agent Engine (no versioning, evals or outcome learning). Buyer: AI platform teams.

**Expected Q&A:**
- *Couldn't the referee be gamed?* It runs under a different Atlas identity. The agent can't write its code, data or verdicts, and it only receives a sign-only verdict, so the holdout can't leak through feedback (arXiv 2607.25152).
- *Why MongoDB?* RBAC is the boundary. Validators make provenance and status unforgeable. Change streams drive the loop. Transactions make promotion atomic. Time-series holds the metric.
