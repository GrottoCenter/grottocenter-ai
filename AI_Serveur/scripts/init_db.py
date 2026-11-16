import os
import time
from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("MONGO_DB_NAME")
MONGO_ADMIN_USERNAME = os.getenv("MONGO_ADMIN_USERNAME")
MONGO_ADMIN_PASSWORD = os.getenv("MONGO_ADMIN_PASSWORD")
MONGO_APP_USERNAME = os.getenv("MONGO_APP_USERNAME")
MONGO_APP_PASSWORD = os.getenv("MONGO_APP_PASSWORD")

DOCUMENTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "fileName",
            "hash",
            "mimeType",
            "createdAt",
            "model",
            "metadata",
        ],
        "properties": {
            "fileName": {"bsonType": "string"},
            "hash": {"bsonType": "string"},
            "mimeType": {"bsonType": "string"},
            "createdAt": {"bsonType": "date"},
            "model": {"bsonType": "string"},
            "metadata": {
                "bsonType": "object",
                "required": [
                    "title",
                    "authors",
                    "publisher",
                    "publication_date",
                    "identifiers",
                    "languages",
                    "descriptions",
                    "grottocenter_type",
                    "rights",
                    "formats",
                    "sources",
                    "parent",
                    "pages",
                ],
                "properties": {
                    "title": {"bsonType": ["string", "null"]},
                    "authors": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "publisher": {"bsonType": ["string", "null"]},
                    "publication_date": {"bsonType": ["string", "null"]},
                    "identifiers": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "languages": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "descriptions": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "grottocenter_type": {"bsonType": ["string", "null"]},
                    "rights": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "formats": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "sources": {
                        "bsonType": "array",
                        "items": {"bsonType": "string"},
                    },
                    "parent": {"bsonType": ["string", "null"]},
                    "pages": {"bsonType": ["string", "null"]},
                },
            },
        },
    },
}


def validate_configuration() -> None:
    required_values = {
        "MONGO_URI": MONGO_URI,
        "MONGO_DB_NAME": DATABASE_NAME,
        "MONGO_ADMIN_USERNAME": MONGO_ADMIN_USERNAME,
        "MONGO_ADMIN_PASSWORD": MONGO_ADMIN_PASSWORD,
        "MONGO_APP_USERNAME": MONGO_APP_USERNAME,
        "MONGO_APP_PASSWORD": MONGO_APP_PASSWORD,
    }
    missing_values = [
        name for name, value in required_values.items() if not value
    ]
    if missing_values:
        raise RuntimeError(
            "Missing MongoDB configuration: " + ", ".join(missing_values)
        )


def connect_to_mongodb() -> MongoClient:
    for attempt in range(30):
        try:
            client = MongoClient(
                MONGO_URI,
                username=MONGO_ADMIN_USERNAME,
                password=MONGO_ADMIN_PASSWORD,
                authSource="admin",
                serverSelectionTimeoutMS=2000,
            )
            client.admin.command("ping")
            return client
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)

    raise RuntimeError("MongoDB is not available")


def ensure_usage_indexes(database) -> None:
    """Make MongoDB delete the per-day usage counters once their day is over.

    The counters are documents of the `usage` collection (see repository/usage.py);
    `expiresAt` is set to two days after the day they count. The `_id` index already
    makes each counter unique. Safe to run any number of times.
    """
    database["usage"].create_index(
        [("expiresAt", ASCENDING)], name="expiresAt_ttl", expireAfterSeconds=0
    )


def initialize_database() -> None:
    validate_configuration()
    client = connect_to_mongodb()
    try:
        database = client[DATABASE_NAME]

        existing_users = database.command(
            "usersInfo", MONGO_APP_USERNAME
        )["users"]
        if not any(
            user["user"] == MONGO_APP_USERNAME
            for user in existing_users
        ):
            database.command(
                "createUser",
                MONGO_APP_USERNAME,
                pwd=MONGO_APP_PASSWORD,
                roles=[{"role": "readWrite", "db": DATABASE_NAME}],
            )

        now = datetime.now(timezone.utc)
        if "documents" in database.list_collection_names():
            database.command(
                "collMod",
                "documents",
                validator=DOCUMENTS_VALIDATOR,
                validationLevel="strict",
            )
        else:
            database.create_collection(
                "documents",
                validator=DOCUMENTS_VALIDATOR,
            )

        database["documents"].create_index(
            [("createdAt", ASCENDING)], name="createdAt"
        )
        database["documents"].create_index(
            [("hash", ASCENDING)], name="hash"
        )
        ensure_usage_indexes(database)

        if database["database_metadata"].find_one(
            {"_id": "initialization"}
        ):
            print(f"MongoDB already initialized: {DATABASE_NAME}")
            return

        database["database_metadata"].insert_one(
            {
                "_id": "initialization",
                "initialized_at": now,
            }
        )
        print(f"MongoDB initialized: {DATABASE_NAME}")
    finally:
        client.close()


if __name__ == "__main__":
    initialize_database()
