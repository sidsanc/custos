# Custos

**Your agent can rewrite its own harness. It can never grade its own homework.**

Custos is a change-control plane for self-improving agents, built on MongoDB Atlas. The agent evolves
its own harness (rules, context policy, tool grants), and every change is scored by an out-of-band
referee against a sealed holdout before it is promoted. Atlas itself is the enforcement boundary:
RBAC, schema validators, change streams and transactions. Nothing is left to the agent's good behaviour
or to a prompt.

Built from scratch at the Harness Engineering & Model Wrangling hackathon (SF Tech Week, 2026-10-11).
Problem statement: **Recursive Harnessing**, using Long Horizon's *hard metric signals*.

## Why

Self-improving harnesses are arriving fast (Meta-Harness, ACE, GEPA, DGM). In each of them, the
constraints on the agent are things the agent can reach:

- **o3** replaced the scorer's timer and stubbed the scorer (METR, Apr 2025).
- **Darwin Gödel Machine** deleted the markers its hallucination detector relied on (Sakana, May 2025).
- **GPT-5** cheated on 54% of impossible tasks, often by editing tests (ImpossibleBench, Oct 2025).
- **Harness tampering** happens in 63–85% of iterations of DGM and ADAS (arXiv 2609.00069, Aug 2026).
- **Self-verdicts:** an agent claimed improvement in 54 of 54 cycles while 56% were flat or worse
  (arXiv 2607.25152).
- **Codex** hard-coded 19–41 eval rows per run in autoresearch loops (arXiv 2607.18064).

Optimizers mutate harnesses. Guardrail vendors freeze them. Observability tools watch them.
**Nobody governs the change itself.**

## How it works

```
 agent (custos-agent user, custosAgent role)             referee (privileged, out-of-band)
 ───────────────────────────────────────────             ─────────────────────────────────
 read  harness (active)          ──────────┐
 read  failures (train only)               │
 insert proposals {add/remove rules,       ├─ change stream ─▶ invariants ─▶ score train + SEALED holdout
         context_policy, born_from: [...]} │                        │
 read  proposals.status (accepted/rejected)◀── sign-only verdict ───┤
                                                                    ▼
      ✗ write harness   ✗ read holdout                 transaction: retire parent, insert vN+1,
      ✗ set own verdict ✗ grant itself $out            stamp verdict, audit log, time-series metric
```

| Guarantee | Enforced by |
|---|---|
| The agent cannot edit the live harness or its guardrails | Atlas **RBAC** custom role: no write on `harness` |
| The agent cannot see the answer key | No privilege on `holdout` |
| The agent cannot mark its own proposal accepted | **`$jsonSchema`**: proposals may only be inserted as `pending` |
| Every rule carries provenance (`born_from` an observed failure) | **`$jsonSchema`** on `proposals` and `harness`, plus a referee check against `failures` |
| `$out` / `$merge` can never be granted | **`$jsonSchema`** enum on `harness.tool_grants` |
| Guardrails only tighten; tool grants only shrink | Referee invariants |
| Gains must generalize, so memorization is rejected | Promotion only if the **sealed holdout improves** |
| Removal is a first-class change | Removal-only proposals are promoted when the score holds |
| Promote and roll back atomically | Multi-document **transaction** |
| A hard metric over time per harness version | **Time-series** collection `metrics` |

The task: natural language to a MongoDB aggregation over a deliberately quirky `films` collection
(`year` stored as a string, lowercase genres, runtime in seconds, ISO country codes). Scoring uses
**execution equivalence** with gold pipelines. No LLM judge is involved.

## Run

```bash
pip install pymongo dnspython python-dotenv httpx rich
cp .env.example .env               # fill MONGODB_URI, AGENT_MONGODB_URI, LLM_PROVIDER
python seed.py                     # data, cases, validators, time-series, harness v0
python referee.py                  # terminal 1: baseline + watch proposals
python agent.py 5                  # terminal 2: self-improvement loop
python redteam.py                  # terminal 2: 7 documented reward-hacking moves, all blocked
```

Atlas setup: create the custom role `custosAgent` on db `custos` with `find,insert` on `proposals` and
`failures`, and `find` on `train` and `harness`. Create a database user `custos-agent` with only that role.

## Built during the hackathon

Everything in this repository was written on 2026-10-11.
