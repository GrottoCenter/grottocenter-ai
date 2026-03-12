from datetime import datetime
from pydantic import BaseModel

class DocumentMetadata(BaseModel):
    title : str | None = None
    authors : list[str] | None = None
    language : str | None = None
    date : datetime | None = None
    summary : str | None = None
    ISO_code : str | None = None
    created_at : datetime | None = None