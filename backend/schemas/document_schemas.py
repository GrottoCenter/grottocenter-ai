from typing import Optional, List
from pydantic import BaseModel

class IdentifierTypeRef(BaseModel):
    id: str

class LicenseRef(BaseModel):
    id: int

class AuthorizationDocRef(BaseModel):
    id: int

class EditorRef(BaseModel):
    id: int

class Iso3166Item(BaseModel):
    iso: str

class DocumentUpdateRequest(BaseModel):
    identifier: Optional[str] = None
    identifierType: Optional[IdentifierTypeRef] = None
    pages: Optional[str] = None
    license: Optional[LicenseRef] = None
    creatorComment: Optional[str] = None
    description: Optional[str] = None
    title: Optional[str] = None
    mainLanguage: Optional[str] = None
    iso3166: Optional[List[Iso3166Item]] = None
    authorizationDocument: Optional[AuthorizationDocRef] = None
    editor: Optional[EditorRef] = None