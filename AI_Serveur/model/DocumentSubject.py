from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentSubject(BaseModel):
    """
    Sujet issu du référentiel t_subject.

    Exemples de codes :
    - 1
    - 1.1
    - 1.1.0.1
    - 8.3.4
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    code: str = Field(
        min_length=1,
        description="Code hiérarchique du sujet Grottocenter.",
    )

    label: str = Field(
        min_length=1,
        description="Libellé du sujet.",
    )

    parent_code: Optional[str] = Field(
        default=None,
        description="Code du sujet parent.",
    )

    dewey_code: Optional[str] = Field(
        default=None,
        description="Cote Dewey associée au sujet.",
    )

    dewey_topic: Optional[str] = Field(
        default=None,
        description="Thème Dewey associé au sujet.",
    )

    url: Optional[str] = Field(
        default=None,
        description="URL de référence du sujet.",
    )