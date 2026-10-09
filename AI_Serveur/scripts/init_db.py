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

        if database["database_metadata"].find_one(
            {"_id": "initialization"}
        ):
            print(f"MongoDB already initialized: {DATABASE_NAME}")
            return

        now = datetime.now(timezone.utc)

        database.create_collection(
            "documents",
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["fileName", "hash", "mimeType", "createdAt", "model", "metadata"],
                    "properties": {
                        "fileName": {"bsonType": "string"},
                        "hash": {"bsonType": "string"},
                        "mimeType": {"bsonType": "string"},
                        "createdAt": {"bsonType": "date"},
                        "model": {"bsonType": "string"},

                        "metadata": {
                            "bsonType": "object",
                            "required": ["title", "authors", "publisher", "publicationDate", "languages", "license", "identifiers", "description", "rights"],
                            "properties": {
                                "title": {"bsonType": ["string", "null"]},
                                "authors": {"bsonType": ["array", "null"], "items": {"bsonType": "string"}},
                                "publisher": {"bsonType": ["string", "null"]},
                                "publicationDate": {"bsonType": ["date", "null"]},
                                "languages": {"bsonType": ["array", "null"], "items": {"bsonType": "string"}},
                                "license": {"bsonType": ["string", "null"]},
                                "identifiers": {"bsonType": ["array", "null"], "items": {"bsonType": "string"}},
                                "description": {"bsonType": ["string", "null"]},
                                "rights": {"bsonType": ["string", "null"]},
                                "articles": {
                                    "bsonType": "array",
                                    "items": {
                                        "bsonType": "object",
                                        "required": ["title", "authors", "page_start", "page_end"],
                                        "properties": {
                                            "title": {"bsonType": ["string", "null"]},
                                            "authors": {"bsonType": ["array", "null"], "items": {"bsonType": "string"}},
                                            "page_start": {"bsonType": ["int", "null"]},
                                            "page_end": {"bsonType": ["int", "null"]},
                                        }
                                    }
                                }
                            },
                        },
                    },
                }
            },
        )

        database["documents"].create_index(
            [("created_at", ASCENDING)], name="created_at"
        )
        database["documents"].create_index(
            [("hash", ASCENDING)], name="hash"
        )

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