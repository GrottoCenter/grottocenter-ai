from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


class DocumentMetadata(BaseModel):
    id : Optional[int] = None
    title : Optional[str] = None
    authors : List[str] | None = None
    language : Optional[str] = None
    date : Optional[datetime] = None
    summary :  Optional[str] = None
    iso3166 : Optional[List[str]] = None
    editor : Optional[str] = None
    page : Optional[str] = None
    issue : Optional[str] = None
    issn : Optional[str] = None
    isbn : Optional[str] = None
    created_at : Optional[datetime] = None