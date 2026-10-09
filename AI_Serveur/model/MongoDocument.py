from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from AI_Serveur.model import DocumentMetadata

class MongoDocument(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True
    )

    fileName: str = Field(
        default=None,
        description="Name of the file"
    )
    hash: str = Field(
        default=None,
        description="Hash of the file"
    )

    mimeType: str = Field(
        default=None,
        description="MIME type of the file"
    )

    createAt: str = Field(
        default=None,
        description="Creation date of the file"
    )

    model: str = Field(
        default=None,
        description="Model associated with the file"
    )

    metadata: DocumentMetadata = Field(
        default=None,
        description="Metadata associated with the file"
    )