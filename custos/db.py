"""Atlas connections. Two identities: the referee (privileged) and the agent (custosAgent role)."""
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DB = "custos"


def referee_db():
    return MongoClient(os.environ["MONGODB_URI"], appname="custos-referee")[DB]


def agent_db():
    uri = os.getenv("AGENT_MONGODB_URI")
    if not uri:
        print("[warn] AGENT_MONGODB_URI not set - agent is running with referee credentials (no RBAC boundary)")
        uri = os.environ["MONGODB_URI"]
    return MongoClient(uri, appname="custos-agent")[DB]


def films(db):
    """The task data: the agent queries it read-only through the harness's tool grants."""
    return db.client["custos_data"]["films"]


# Every rule the agent adds must say which observed failure justified it.
RULE_SCHEMA = {
    "bsonType": "object",
    "required": ["id", "text", "born_from"],
    "properties": {
        "id": {"bsonType": "string"},
        "text": {"bsonType": "string", "minLength": 8},
        "born_from": {"bsonType": "array", "minItems": 1, "items": {"bsonType": "string"}},
    },
}

VALIDATORS = {
    "harness": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["version", "parent", "rules", "guardrails", "tool_grants", "context_policy", "status"],
            "properties": {
                "version": {"bsonType": "int"},
                "rules": {"bsonType": "array", "items": RULE_SCHEMA},
                "guardrails": {"bsonType": "array", "minItems": 1},
                "tool_grants": {
                    "bsonType": "object",
                    "required": ["allowed_stages"],
                    "properties": {"allowed_stages": {
                        "bsonType": "array",
                        # $out / $merge can never be granted, whatever the referee decides.
                        "items": {"enum": ["$match", "$project", "$group", "$sort", "$limit", "$unwind",
                                           "$count", "$addFields", "$set", "$skip"]},
                    }},
                },
                "status": {"enum": ["active", "retired"]},
            },
        }
    },
    "proposals": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["parent", "add_rules", "rationale", "status"],
            "properties": {
                "add_rules": {"bsonType": "array", "items": RULE_SCHEMA},
                "status": {"enum": ["pending"]},  # the agent can only ever create pending proposals
            },
        }
    },
}
