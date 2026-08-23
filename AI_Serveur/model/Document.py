from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentMetadata(BaseModel):
    """
    Métadonnées descriptives d'un document Grottocenter.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    title: Optional[str] = Field(
        default=None,
        description="Titre principal du document.",
    )

    authors: List[str] = Field(
        default_factory=list,
        description="Auteurs ou créateurs du document.",
    )

    contributor: Optional[str] = Field(
        default=None,
        description="Contributeur du document.",
    )

    publisher: Optional[str] = Field(
        default=None,
        description="Éditeur ou organisme de publication.",
    )

    publication_date: Optional[date] = Field(
        default=None,
        description="Date de publication.",
    )

    languages: List[str] = Field(
        default_factory=list,
        description="Langues ISO 639-3, par exemple fra ou eng.",
    )

    descriptions: List[str] = Field(
        default_factory=list,
        description="Descriptions ou résumés du document.",
    )

    subjects: List[DocumentSubject] = Field(
        default_factory=list,
        description="Sujets issus de la taxonomie t_subject.",
    )

    coverages: List[str] = Field(
        default_factory=list,
        description="Pays, régions, massifs ou zones géographiques.",
    )

    formats: List[str] = Field(
        default_factory=list,
        description="Formats ou types MIME des fichiers associés.",
    )

    identifiers: List[str] = Field(
        default_factory=list,
        description="DOI, ISBN, ISSN, URL ou autres identifiants.",
    )

    relations: List[str] = Field(
        default_factory=list,
        description="Ressources ou documents liés.",
    )

    sources: List[str] = Field(
        default_factory=list,
        description="Sources bibliographiques.",
    )

    rights: List[LicenseName] = Field(
        default_factory=list,
        description="Licences et droits d'utilisation.",
    )

    grottocenter_type: Optional[GrottocenterType] = Field(
        default=None,
        description="Type de document Grottocenter.",
    )

    dcmi_type: Optional[DCMIType] = Field(
        default=None,
        description="Type Dublin Core Metadata Initiative.",
    )

    pages: Optional[str] = Field(
        default=None,
        description="Pagination ou nombre de pages.",
    )