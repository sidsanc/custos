# Hackathon submission

**Project:** Custos
**Tagline:** Your agent can rewrite its own harness. It can never grade its own homework.
**Repo:** https://github.com/sidsanc/custos
**Video:** `video/custos_demo.mp4` (62 s)
**Problem statement:** 1, Recursive Harnessing (with Statement 2's hard metric signals)

## Description

Self-improving agent harnesses are arriving fast, and agents already tamper with what judges them. o3 stubbed its scorer, the Darwin Gödel Machine deleted its hallucination detector's markers, and a 2026 audit found harness tampering in 63–85% of self-improvement iterations. Optimizers change harnesses, guardrail tools freeze them, observability tools watch them. Nobody governs the change itself.

Custos is a change-control plane for self-improving agents on MongoDB Atlas, where the database is the enforcement boundary, not a prompt. The agent runs as a restricted Atlas user: it can read its own failures and insert proposals (new rules, context-policy changes, rule removals), nothing else. Atlas RBAC stops it from writing its harness or reading the sealed holdout. $jsonSchema validators reject self-accepted proposals and any rule without provenance (a link to the failure it fixes). A privileged referee watches proposals through a change stream, enforces invariants (guardrails only tighten, tool grants only shrink), scores each candidate on train plus a sealed holdout, and promotes only changes that generalize, in one multi-document transaction. Metrics go to a time-series collection; every proposal and blocked tampering attempt is sent to Raindrop as a self-improvement event with a promoted/rejected signal.

Live on the hackathon Atlas sandbox (local qwen2.5-coder:7b, text-to-MongoDB scored by execution match): 7/7 documented reward-hacking attacks blocked; the agent climbed from 2/16 to 15/16 after three non-generalizing proposals were rejected, and a later proposal that regressed on unseen questions was also rejected; rule retirement confirmed the surviving rule still earns its place. Most of what a self-improving agent proposes does not generalize. Without a referee, you'd keep all of it.

Built entirely during the hackathon on 2026-10-11.

## Tech used

MongoDB Atlas (RBAC custom roles, $jsonSchema validation, change streams, multi-document transactions, time-series collections, MCP Server), Raindrop, Python, Ollama.
