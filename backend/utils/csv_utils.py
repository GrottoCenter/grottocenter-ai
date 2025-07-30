"""
Utilitaires pour la gestion des fichiers CSV
"""

import csv
import io
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path

from backend.models.collection_models import CollectionRecord
from backend.utils.exceptions import GrottocenterUpdateError


class CSVUtils:
    """Utilitaires pour la gestion des CSV"""
    
    @staticmethod
    def parse_csv_content(csv_content: str) -> List[Dict[str, str]]:
        """Parse le contenu CSV en liste de dictionnaires"""
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            return [row for row in csv_reader]
        except Exception as e:
            raise GrottocenterUpdateError(f"Erreur lors du parsing CSV: {e}")
    
    @staticmethod
    def parse_csv_file(file_path: str) -> List[Dict[str, str]]:
        """Parse un fichier CSV"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.DictReader(f)
                return [row for row in csv_reader]
        except Exception as e:
            raise GrottocenterUpdateError(f"Erreur lors de la lecture du fichier CSV: {e}")
    
    @staticmethod
    def decode_base64_csv(base64_content: str) -> str:
        """Décoder un contenu CSV en base64"""
        try:
            decoded_bytes = base64.b64decode(base64_content)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            raise GrottocenterUpdateError(f"Erreur lors du décodage base64: {e}")
    
    @staticmethod
    def records_to_csv(records: List[CollectionRecord]) -> str:
        """Convertir une liste d'enregistrements en CSV"""
        if not records:
            return ""
        
        output = io.StringIO()
        fieldnames = records[0].dict().keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        writer.writeheader()
        for record in records:
            writer.writerow(record.dict())
        
        return output.getvalue()
    
    @staticmethod
    def validate_csv_structure(csv_data: List[Dict[str, str]]) -> Dict[str, Any]:
        """Valider la structure du CSV"""
        errors = []
        warnings = []
        
        if not csv_data:
            errors.append("Le CSV est vide")
            return {"valid": False, "errors": errors, "warnings": warnings}
        
        # Vérifier les colonnes requises
        required_columns = ["id"]
        available_columns = set(csv_data[0].keys())
        
        missing_columns = set(required_columns) - available_columns
        if missing_columns:
            errors.append(f"Colonnes manquantes: {', '.join(missing_columns)}")
        
        # Vérifier les IDs
        ids = []
        for i, row in enumerate(csv_data):
            row_id = row.get("id", "").strip()
            if not row_id:
                errors.append(f"ID manquant à la ligne {i + 2}")
            elif row_id in ids:
                errors.append(f"ID dupliqué: {row_id}")
            else:
                ids.append(row_id)
        
        # Vérifier les colonnes recommandées
        recommended_columns = ["title", "license", "description"]
        missing_recommended = set(recommended_columns) - available_columns
        if missing_recommended:
            warnings.append(f"Colonnes recommandées manquantes: {', '.join(missing_recommended)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "row_count": len(csv_data),
            "columns": list(available_columns)
        }


class CSVConverter:
    """Convertisseur CSV pour nettoyer et standardiser les données"""
    
    @staticmethod
    def clean_csv_data(csv_data: List[Dict[str, str]]) -> List[CollectionRecord]:
        """Nettoyer et convertir les données CSV en modèles Pydantic"""
        cleaned_records = []
        
        for row in csv_data:
            try:
                # Nettoyer les valeurs vides
                cleaned_row = {}
                for key, value in row.items():
                    if value and value.strip():
                        cleaned_row[key] = value.strip()
                    else:
                        cleaned_row[key] = None
                
                # Créer l'enregistrement avec validation Pydantic
                record = CollectionRecord(**cleaned_row)
                cleaned_records.append(record)
                
            except Exception as e:
                raise GrottocenterUpdateError(
                    f"Erreur lors du nettoyage de la ligne avec ID {row.get('id', 'inconnu')}: {e}"
                )
        
        return cleaned_records
    
    @staticmethod
    def standardize_languages(languages_str: Optional[str]) -> Optional[str]:
        """Standardiser la chaîne de langues"""
        if not languages_str:
            return None
        
        # Séparer par ; et nettoyer
        languages = [lang.strip().lower() for lang in languages_str.split(";") if lang.strip()]
        
        # Mapping des codes de langue standards
        language_mapping = {
            "français": "fr",
            "francais": "fr",
            "french": "fr",
            "anglais": "en",
            "english": "en",
            "espagnol": "es",
            "spanish": "es",
            "italien": "it",
            "italian": "it",
            "allemand": "de",
            "german": "de"
        }
        
        standardized = []
        for lang in languages:
            mapped_lang = language_mapping.get(lang, lang)
            if mapped_lang not in standardized:
                standardized.append(mapped_lang)
        
        return ";".join(standardized) if standardized else None
    
    @staticmethod
    def standardize_countries(countries_str: Optional[str]) -> Optional[str]:
        """Standardiser la chaîne de codes pays"""
        if not countries_str:
            return None
        
        # Séparer par ; et nettoyer
        countries = [country.strip().upper() for country in countries_str.split(";") if country.strip()]
        
        # Valider les codes ISO (basic validation)
        valid_countries = []
        for country in countries:
            if len(country) == 2 and country.isalpha():
                valid_countries.append(country)
            else:
                # Log warning ou conversion si nécessaire
                pass
        
        return ";".join(valid_countries) if valid_countries else None
    
    @staticmethod
    def standardize_license(license_str: Optional[str]) -> Optional[str]:
        """Standardiser les licences"""
        if not license_str:
            return None
        
        license_str = license_str.strip()
        
        # Mapping des noms de licences courants
        license_mapping = {
            "creative commons by-sa": "CC-BY-SA",
            "creative commons by": "CC-BY",
            "cc by sa": "CC-BY-SA",
            "cc by": "CC-BY",
            "odbl": "ODBL",
            "open database license": "ODBL",
            "odc-by": "ODC-BY",
            "licence ouverte": "Licence Ouverte",
            "cc by nc nd": "CC-BY-NC-ND",
            "cc by nc": "CC BY NC",
            "cc by nd": "CC BY ND",
            "cc by nc sa": "CC BY NC SA"
        }
        
        # Chercher une correspondance (insensible à la casse)
        license_lower = license_str.lower()
        for key, value in license_mapping.items():
            if key in license_lower:
                return value
        
        # Si pas de correspondance trouvée, retourner tel quel
        return license_str
    
    @classmethod
    def convert_and_clean_csv(cls, csv_data: List[Dict[str, str]]) -> List[CollectionRecord]:
        """Pipeline complet de conversion et nettoyage"""
        # Standardiser certains champs
        for row in csv_data:
            if "languages" in row:
                row["languages"] = cls.standardize_languages(row["languages"])
            
            if "countries" in row:
                row["countries"] = cls.standardize_countries(row["countries"])
            
            if "license" in row:
                row["license"] = cls.standardize_license(row["license"])
        
        # Nettoyer et valider
        return cls.clean_csv_data(csv_data)


def save_csv_temp(csv_content: str, filename: str = None) -> str:
    """Sauvegarder un CSV temporaire"""
    temp_dir = Path("temp_csv")
    temp_dir.mkdir(exist_ok=True)
    
    if not filename:
        import time
        filename = f"collection_data_{int(time.time())}.csv"
    
    file_path = temp_dir / filename
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(csv_content)
    
    return str(file_path)


def load_csv_temp(file_path: str) -> str:
    """Charger un CSV temporaire"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def cleanup_temp_files(max_age_hours: int = 24):
    """Nettoyer les fichiers temporaires anciens"""
    import time
    import os
    
    temp_dir = Path("temp_csv")
    if not temp_dir.exists():
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for file_path in temp_dir.glob("*.csv"):
        file_age = current_time - file_path.stat().st_mtime
        if file_age > max_age_seconds:
            try:
                os.remove(file_path)
            except OSError:
                pass  # Ignorer les erreurs de suppression