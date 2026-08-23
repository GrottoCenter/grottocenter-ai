from typing import Any, Dict


class BaseEditor:
    def _extract_values(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        print(doc is not None)  # Debugging line, can be removed later
        print(doc.get("iso3166", []) is not None)  # Debugging line, can be removed later
        print(doc.get("authorizationDocument", {}) is not None)  # Debugging line, can be removed later
        print(doc.get("editor", {}) is not None)  #
        response = {}
        response['title'] = doc.get("title", "")
        response['description'] = doc.get("description", "")
        response['identifier'] = doc.get("identifier", "")
        response['pages'] = doc.get("pages", "")
        response['creatorComment'] = doc.get("creatorComment", "")
        response['mainLanguage'] = doc.get("mainLanguage", "")
        response['license'] = doc.get("license", "")  # string
        response['identifierType'] = doc.get("identifierType", "")  # string
        response['iso3166'] = ";".join([entry.get("iso", "") for entry in doc.get("iso3166", []) if entry.get("iso")])
        if doc.get("authorizationDocument"):
            response['authorizationDocument'] = str(doc.get("authorizationDocument", {}).get("id", ""))
        else:
            response['authorizationDocument'] = ""
        if doc.get("editor"):
            response['editor'] = str(doc.get("editor", {}).get("id", ""))
        else:
            response['editor'] = ""
        return response
