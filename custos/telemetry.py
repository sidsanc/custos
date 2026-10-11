"""Raindrop telemetry for the self-improvement loop. A no-op unless RAINDROP_WRITE_KEY is set.

Every proposal becomes a Raindrop AI event (input = what the agent wanted to change, output = the
referee's verdict), with a POSITIVE signal on promotion and a NEGATIVE signal naming the reason on
rejection. Blocked tampering attempts are tracked as their own events. The result in Raindrop: the
harness's recursive self-improvement history, with every caught cheat as a flagged failure.
"""
import json
import os
import uuid

from dotenv import load_dotenv

load_dotenv()

_rd = None
if os.getenv("RAINDROP_WRITE_KEY"):
    try:
        import raindrop.analytics as _rd

        _rd.init(os.environ["RAINDROP_WRITE_KEY"])
    except Exception as e:  # noqa: BLE001 - telemetry must never break the referee
        print(f"[raindrop] disabled: {e}")
        _rd = None

USER = "custos-harness"


def proposal(p: dict, verdict: str, reason: str, parent: int, version: int, scores, parent_scores, model: str):
    if not _rd:
        return
    try:
        eid = str(uuid.uuid4())
        change = {k: p.get(k) for k in ("rationale", "add_rules", "remove_rules", "remove_guardrails",
                                        "tool_grants", "context_policy") if p.get(k)}
        _rd.track_ai(
            user_id=USER, event="harness_proposal", event_id=eid, model=model,
            convo_id=f"lineage-from-v{parent}",
            input=json.dumps(change, default=str)[:4000],
            output=f"{verdict.upper()}: {reason}",
            properties={"author": p.get("author"), "parent_version": parent, "new_version": version,
                        "verdict": verdict, "reason": reason,
                        "train": (scores or {}).get("train"), "holdout": (scores or {}).get("holdout"),
                        "parent_train": parent_scores.get("train"), "parent_holdout": parent_scores.get("holdout")},
        )
        _rd.track_signal(event_id=eid, name="promoted" if verdict == "accepted" else reason.split(":")[0],
                         sentiment="POSITIVE" if verdict == "accepted" else "NEGATIVE")
        _rd.flush()
    except Exception as e:  # noqa: BLE001
        print(f"[raindrop] send failed: {e}")


def blocked(attack: str, error: str):
    if not _rd:
        return
    try:
        eid = str(uuid.uuid4())
        _rd.track_ai(user_id=USER, event="tamper_attempt_blocked", event_id=eid, convo_id="redteam",
                     input=attack, output=f"BLOCKED BY ATLAS: {error}", properties={"layer": "database"})
        _rd.track_signal(event_id=eid, name="tamper_blocked", sentiment="NEGATIVE")
        _rd.flush()
    except Exception as e:  # noqa: BLE001
        print(f"[raindrop] send failed: {e}")
