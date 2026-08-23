from enum import Enum

class TopLevelSubjectCode(str, Enum):
    """
    Grandes catégories de t_subject.

    Les sous-sujets utilisent des codes comme 1.1, 1.1.0.1 ou 8.3.4.
    """

    KARSTOLOGY_AND_GEOSPELEOLOGY = "1"
    REGIONAL_SPELEOLOGY_AND_KARSTOLOGY = "2"
    BIOSPELEOLOGY = "3"
    ANTHROPOSPELEOLOGY_AND_PALAEONTHOSPELEOLOGY = "4"
    SPELEOLOGICAL_AND_KARSTOLOGICAL_ACTIVITIES = "5"
    SPELEOLOGY_AND_APPLIED_KARST_SCIENCE = "6"
    TECHNICAL_SPELEOLOGY = "7"
    DOCUMENTATION_OF_KARST_AND_CAVES = "8"
    OTHER_TOPICS = "9"