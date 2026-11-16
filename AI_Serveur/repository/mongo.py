from functools import lru_cache

import pymongo

from config.settings import settings
from model.MongoDocument import MongoDocument


@lru_cache(maxsize=1)
def _get_database():
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is required to connect to MongoDB")
    if not settings.mongo_db_name:
        raise RuntimeError("MONGO_DB_NAME is required to select the MongoDB database")

    client = pymongo.MongoClient(settings.mongo_uri)
    return client[settings.mongo_db_name]

class MongoRepository:

    COLLECTION_NAME = "documents"

    def __init__(self, db=None):
        self.db = db if db is not None else _get_database()

    def get_collection(self, collection_name):
        return self.db[collection_name]

    def insert_one(self, document):
        collection = self.get_collection(self.COLLECTION_NAME)
        return collection.insert_one(document)

    def insert_many(self, documents):
        collection = self.get_collection(self.COLLECTION_NAME)
        return collection.insert_many(documents)

    def find_one(self, query):
        collection = self.get_collection(self.COLLECTION_NAME)
        return collection.find_one(query)

    def get_with_hash(self, file_hash: str) -> list[MongoDocument]:
        collection = self.get_collection(self.COLLECTION_NAME)
        documents = collection.find({"hash": file_hash}, {"_id": 0})
        return [MongoDocument.model_validate(document) for document in documents]
