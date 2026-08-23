from enum import Enum

class DCMIType(str, Enum):
    """
    Valeurs produites par la vue v_bibliographic_metadata.dc_type_dcmi.
    """

    COLLECTION = "collection"
    DATASET = "dataset"
    IMAGE = "image"
    MOVING_IMAGE = "moving image"
    SOUND = "sound"
    INTERACTIVE_RESOURCE = "interactive resource"
    PHYSICAL_OBJECT = "physical object"
    TEXT = "text"