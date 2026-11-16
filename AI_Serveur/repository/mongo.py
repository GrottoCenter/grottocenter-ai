from model.MongoDocument import MongoDocument


class MongoRepository:

    COLLECTION_NAME = "documents"

    def __init__(self, db):
        # The database comes from the application's lifespan (see lifespan.py),
        # so there is one MongoDB client per process and it is closed on shutdown.
        self.db = db

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
        # In upload order: the main document first, then its articles. Documents stored
        # before `position` existed have none and keep the order they were inserted in.
        documents = collection.find({"hash": file_hash}, {"_id": 0}).sort("position", 1)
        return [MongoDocument.model_validate(document) for document in documents]
