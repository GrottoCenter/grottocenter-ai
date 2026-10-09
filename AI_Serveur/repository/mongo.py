import pymongo
from config.settings import settings
from model.MongoDocument import MongoDocument

client = pymongo.MongoClient(
    f"mongodb://{settings.mongo_username}:{settings.mongo_password}@mongodb:27017/{settings.mongo_db_name}?authSource={settings.mongo_db_name}"
)
db = client[settings.mongo_db_name]

class MongoRepository:

    COLLECTION_NAME = "documents"

    def __init__(self, db):
        client = pymongo.MongoClient(
            f"mongodb://{settings.mongo_username}:{settings.mongo_password}@mongodb:27017/{settings.mongo_db_name}?authSource={settings.mongo_db_name}"
        )
        self.db = client[settings.mongo_db_name]

    def get_collection(self, collection_name):
        return self.db[collection_name]

    def insert_one(self, document):
        collection = self.get_collection(self.COLLECTION_NAME)
        return collection.insert_one(document)

    def find_one(self, query):
        collection = self.get_collection(self.COLLECTION_NAME)
        return collection.find_one(query)

    def get_with_hash(self, file_hash: str) -> MongoDocument | None:
        collection = self.get_collection(self.COLLECTION_NAME)
        document = collection.find_one({"hash": file_hash}, {"_id": 0})
        if document is None:
            return None
        return MongoDocument.model_validate(document)