from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from model.GrottocenterType import GrottocenterType
from model.LicenseName import LicenseName
from model.TopLevelSubjectCode import TopLevelSubjectCode


class ArticleMetadata(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: Optional[str] = Field(
        default=None,
        description="Title of the article.",
    )

    authors: List[str] = Field(
        default_factory=list,
        description="Authors or creators of the article.",
    )

    grottocenter_type: Literal["article"] = Field(
        default="article",
        description="Grottocenter type of the nested document.",
    )

    publication_date: Optional[date] = Field(
        default=None,
        description="Publication date of the article.",
    )

    page_start: Optional[int] = Field(
        default=None,
        description="First page of the article.",
    )

    page_end: Optional[int] = Field(
        default=None,
        description="Last page of the article.",
    )


class DocumentAnalyseMetadata(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: Optional[str] = Field(
        default=None,
        description="Main title of the document.",
    )

    authors: List[str] = Field(
        default_factory=list,
        description="Authors or creators of the document.",
    )

    publisher: Optional[str] = Field(
        default=None,
        description="Publisher or publishing organization.",
    )

    publication_date: Optional[date] = Field(
        default=None,
        description="Publication date.",
    )
    
    identifiers: List[str] = Field(
        default_factory=list,
        description="DOI, ISBN, ISSN, URL, or other identifiers.",
    )

    languages: List[str] = Field(
        default_factory=list,
        description="ISO 639-3 languages, for example fra or eng.",
    )

    descriptions: List[str] = Field(
        default_factory=list,
        description="Descriptions or summaries of the document.",
    )
    
    grottocenter_type: Optional[GrottocenterType] = Field(
        default=None,
        description="Grottocenter document type.",
    )
    
    rights: List[LicenseName] = Field(
        default_factory=list,
        description="Licenses and usage rights.",
    )

    articles: Optional[List[ArticleMetadata]] = Field(
        default=None,
        description="Articles contained in the document when it is an issue.",
    )

    @field_validator(
        "authors",
        "identifiers",
        "languages",
        "descriptions",
        "rights",
        mode="before",
    )
    @classmethod
    def convert_null_lists_to_empty_lists(cls, value):
        return [] if value is None else value

class DocumentMetadata(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: Optional[str] = Field(
        default=None,
        description="Main title of the document.",
    )

    authors: List[str] = Field(
        default_factory=list,
        description="Authors or creators of the document.",
    )

    publisher: Optional[str] = Field(
        default=None,
        description="Publisher or publishing organization.",
    )

    publication_date: Optional[date] = Field(
        default=None,
        description="Publication date.",
    )
    
    identifiers: List[str] = Field(
        default_factory=list,
        description="DOI, ISBN, ISSN, URL, or other identifiers.",
    )

    languages: List[str] = Field(
        default_factory=list,
        description="ISO 639-3 languages, for example fra or eng.",
    )

    descriptions: List[str] = Field(
        default_factory=list,
        description="Descriptions or summaries of the document.",
    )
    
    grottocenter_type: Optional[GrottocenterType] = Field(
        default=None,
        description="Grottocenter document type.",
    )
    
    rights: List[LicenseName] = Field(
        default_factory=list,
        description="Licenses and usage rights.",
    )
    
    formats: List[str] = Field(
        default_factory=list,
        description="Formats or MIME types of associated files.",
    )

    sources: List[str] = Field(
        default_factory=list,
        description="Bibliographic sources.",
    )

    parent: Optional[str] = Field(
        default=None,
        description="Parent document identifier if this document is part of a larger work.",
    )

    pages: Optional[str] = Field(
        default=None,
        description="Pagination or page count.",
    )