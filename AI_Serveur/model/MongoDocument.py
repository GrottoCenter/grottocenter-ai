from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .DocumentMetadata import DocumentMetadata


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

    createdAt: datetime = Field(
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

    position: int | None = Field(
        default=None,
        description=(
            "Place of this document in the upload: 0 for the file itself (or the issue), "
            "1 to n for the articles found in it. Documents stored before this field "
            "existed have none."
        ),
    )
