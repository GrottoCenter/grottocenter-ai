class DocumentService:
    def __init__(self):
        # Initialize any necessary resources, such as database connections
        pass

    async def get_document(self, doc_id: int):
        # Placeholder for fetching a document by its ID
        # In a real implementation, this would involve querying a database or an external service
        return {"doc_id": doc_id, "content": "This is the content of the document."}