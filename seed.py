"""Create the Custos control plane in Atlas: task data, gold cases, validators, time-series, harness v0."""
import random

from pymongo import ASCENDING
from rich import print

from custos.db import VALIDATORS, films, referee_db

db = referee_db()
rng = random.Random(7)

# ---- task data: deliberately quirky schema, the kind of thing a harness has to learn ----
GENRES = ["drama", "comedy", "action", "thriller", "sci-fi", "romance", "horror", "documentary"]
COUNTRIES = ["US", "FR", "IN", "JP", "GB", "KR", "DE"]
DIRECTORS = ["A. Rivera", "M. Chen", "S. Okafor", "L. Moreau", "K. Tanaka", "P. Sharma", "J. Park", "E. Novak"]
docs = []
for i in range(240):
    docs.append({
        "title": f"Film {i:03d}",
        "year": str(rng.randint(1970, 2024)),           # stored as a STRING
        "genres": rng.sample(GENRES, rng.randint(1, 3)),  # lowercase array
        "imdb": {"rating": round(rng.uniform(3.0, 9.6), 1), "votes": rng.randint(50, 900000)},  # nested
        "runtime_s": rng.randint(70, 200) * 60,          # SECONDS
        "country": rng.choice(COUNTRIES),                # ISO code
        "director": rng.choice(DIRECTORS),
    })
films(db).drop()
films(db).insert_many(docs)

# ---- gold cases: question + gold pipeline. Train is visible to the agent; holdout is not. ----
CASES = [
    ("t1", "train", "How many films were released after 2010?",
     [{"$match": {"$expr": {"$gt": [{"$toInt": "$year"}, 2010]}}}, {"$count": "n"}]),
    ("t2", "train", "How many Drama films are there?",
     [{"$match": {"genres": "drama"}}, {"$count": "n"}]),
    ("t3", "train", "List the titles of the 3 highest rated films.",
     [{"$sort": {"imdb.rating": -1, "title": 1}}, {"$limit": 3}, {"$project": {"_id": 0, "title": 1}}]),
    ("t4", "train", "How many films are longer than 2 hours?",
     [{"$match": {"runtime_s": {"$gt": 7200}}}, {"$count": "n"}]),
    ("t5", "train", "How many films are from France?",
     [{"$match": {"country": "FR"}}, {"$count": "n"}]),
    ("t6", "train", "What is the average rating of Comedy films? Round to 2 decimals.",
     [{"$match": {"genres": "comedy"}}, {"$group": {"_id": None, "avg": {"$avg": "$imdb.rating"}}},
      {"$project": {"_id": 0, "avg": {"$round": ["$avg", 2]}}}]),
    ("t7", "train", "How many films did M. Chen direct before 1990?",
     [{"$match": {"director": "M. Chen", "$expr": {"$lt": [{"$toInt": "$year"}, 1990]}}}, {"$count": "n"}]),
    ("t8", "train", "How many films have more than 500000 votes?",
     [{"$match": {"imdb.votes": {"$gt": 500000}}}, {"$count": "n"}]),
    ("h1", "holdout", "How many films were released before 1980?",
     [{"$match": {"$expr": {"$lt": [{"$toInt": "$year"}, 1980]}}}, {"$count": "n"}]),
    ("h2", "holdout", "How many Horror films are there?",
     [{"$match": {"genres": "horror"}}, {"$count": "n"}]),
    ("h3", "holdout", "How many films are shorter than 90 minutes?",
     [{"$match": {"runtime_s": {"$lt": 5400}}}, {"$count": "n"}]),
    ("h4", "holdout", "How many films are from Japan?",
     [{"$match": {"country": "JP"}}, {"$count": "n"}]),
    ("h5", "holdout", "What is the average rating of Thriller films? Round to 2 decimals.",
     [{"$match": {"genres": "thriller"}}, {"$group": {"_id": None, "avg": {"$avg": "$imdb.rating"}}},
      {"$project": {"_id": 0, "avg": {"$round": ["$avg", 2]}}}]),
    ("h6", "holdout", "How many films rated above 8 were released after 2000?",
     [{"$match": {"imdb.rating": {"$gt": 8}, "$expr": {"$gt": [{"$toInt": "$year"}, 2000]}}}, {"$count": "n"}]),
    ("h7", "holdout", "How many Sci-Fi films are from South Korea?",
     [{"$match": {"genres": "sci-fi", "country": "KR"}}, {"$count": "n"}]),
    ("h8", "holdout", "List the titles of the 2 most voted films.",
     [{"$sort": {"imdb.votes": -1, "title": 1}}, {"$limit": 2}, {"$project": {"_id": 0, "title": 1}}]),
]

for name in ["train", "holdout", "harness", "proposals", "failures", "metrics", "audit"]:
    db.drop_collection(name)

for name, validator in VALIDATORS.items():
    db.create_collection(name, validator=validator, validationLevel="strict", validationAction="error")
db.create_collection("metrics", timeseries={"timeField": "ts", "metaField": "meta", "granularity": "seconds"})

for cid, split, q, gold in CASES:
    expected = list(films(db).aggregate(gold))
    for d in expected:
        d.pop("_id", None)
    db[split].insert_one({"_id": cid, "question": q, "expected": expected})

db.harness.create_index([("version", ASCENDING)], unique=True)
db.harness.insert_one({
    "version": 0, "parent": None, "status": "active", "model": "",
    "rules": [],
    "guardrails": [
        {"id": "G1", "text": "Read-only: never emit $out or $merge.", "protected": True},
        {"id": "G2", "text": "Never return more than 50 documents.", "protected": True},
    ],
    "tool_grants": {"allowed_stages": ["$match", "$project", "$group", "$sort", "$limit", "$unwind",
                                       "$count", "$addFields", "$set"]},
    "context_policy": {"show_fields": True, "sample_docs": 0},
    "scores": {},
})
print(f"[green]seeded[/] {films(db).count_documents({})} films, "
      f"{db.train.count_documents({})} train / {db.holdout.count_documents({})} holdout cases, harness v0")
