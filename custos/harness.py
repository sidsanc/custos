"""Run a harness version against cases. The harness is data in Atlas; this file is the interpreter."""
import json
from concurrent.futures import ThreadPoolExecutor

from custos.db import films
from custos.llm import chat, extract_json

FIELDS = "title (string), year, genres, imdb.rating, imdb.votes, runtime_s, country, director"


def build_system(h: dict, db) -> str:
    parts = ["You translate a question about a MongoDB collection `films` into an aggregation pipeline.",
             "Reply with ONLY a JSON array of pipeline stages."]
    cp = h["context_policy"]
    if cp.get("show_fields"):
        parts.append(f"Fields: {FIELDS}.")
    if cp.get("sample_docs"):
        sample = list(films(db).find({}, {"_id": 0}).limit(int(cp["sample_docs"])))
        parts.append("Sample documents:\n" + json.dumps(sample))
    parts.append("Allowed stages: " + ", ".join(h["tool_grants"]["allowed_stages"]))
    parts += [f"GUARDRAIL {g['id']}: {g['text']}" for g in h["guardrails"]]
    parts += [f"RULE {r['id']}: {r['text']}" for r in h["rules"]]
    return "\n".join(parts)


def check_pipeline(pipeline, h) -> str | None:
    """Tool-grant enforcement happens here, outside the model, every call."""
    if not isinstance(pipeline, list):
        return "pipeline is not a list"
    allowed = set(h["tool_grants"]["allowed_stages"])
    for stage in pipeline:
        if not isinstance(stage, dict) or len(stage) != 1:
            return f"malformed stage {stage!r}"
        op = next(iter(stage))
        if op in ("$out", "$merge"):
            return f"guardrail violation: {op}"
        if op not in allowed:
            return f"stage {op} not granted"
    return None


def normalise(rows):
    """Compare by values only, so `{n: 5}` and `{count: 5}` are the same answer."""
    out = []
    for d in rows:
        d = {k: v for k, v in d.items() if k != "_id"}
        out.append(tuple(sorted(json.dumps(v, sort_keys=True, default=str) for v in d.values())))
    return out


def run_case(h, case, db, model=None):
    system = build_system(h, db)
    try:
        reply = chat(system, case["question"], model=model)
        pipeline = extract_json(reply)
    except Exception as e:  # noqa: BLE001 - any model/parse failure is a failed case
        return {"case": case["_id"], "ok": False, "error": f"no pipeline: {e}", "pipeline": None}
    err = check_pipeline(pipeline, h)
    if err:
        return {"case": case["_id"], "ok": False, "error": err, "pipeline": pipeline}
    try:
        got = list(films(db).aggregate(pipeline + [{"$limit": 50}], maxTimeMS=5000))
    except Exception as e:  # noqa: BLE001
        return {"case": case["_id"], "ok": False, "error": f"execution: {e}"[:300], "pipeline": pipeline}
    ok = normalise(got) == normalise(case["expected"])
    return {"case": case["_id"], "ok": ok, "pipeline": pipeline,
            "got": [{k: v for k, v in d.items() if k != "_id"} for d in got[:5]]}


def evaluate(h, cases, db, model=None, workers=4):
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda c: run_case(h, c, db, model), cases))
    return results
