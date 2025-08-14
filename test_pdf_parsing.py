#!/usr/bin/env python3
"""
Script de test pour vérifier les améliorations du parsing PDF.
"""

import sys
sys.path.append('backend')

from services.pdf_service import PDFService, _format_issue_title

def test_parsing():
    """Test les nouvelles fonctionnalités de parsing."""
    
    service = PDFService()
    
    # Test de fusion des composants
    print("=== Test de la fusion des composants ===\n")
    
    fusion_tests = [
        {
            "name": "Métadonnées avec nom, couverture avec numéro/date",
            "metadata_components": ("L'Écho des Rhinos", None, None, None),
            "cover_components": (None, "123", "Décembre", "2024"),
            "expected": ("L'Écho des Rhinos", "123", "Décembre", "2024")
        },
        {
            "name": "Nom complet dans métadonnées",
            "metadata_components": ("Regards", "94", "Janvier", "2024"),
            "cover_components": (None, None, None, None),
            "expected": ("Regards", "94", "Janvier", "2024")
        },
        {
            "name": "Informations réparties",
            "metadata_components": ("Science et Vie", None, None, "2024"),
            "cover_components": ("Magazine", "123", "Mars", None),
            "expected": ("Science et Vie", "123", "Mars", "2024")
        }
    ]
    
    for i, test in enumerate(fusion_tests, 1):
        print(f"Test fusion {i}: {test['name']}")
        print(f"  Métadonnées: {test['metadata_components']}")
        print(f"  Couverture: {test['cover_components']}")
        
        result = service._merge_components(test['metadata_components'], test['cover_components'])
        
        print(f"  Result: {result}")
        print(f"  Expected: {test['expected']}")
        
        if result == test['expected']:
            print("  ✅ PASS")
        else:
            print("  ❌ FAIL")
        print()
    
    # Test cases basés sur l'exemple fourni
    test_cases = [
        {
            "name": "Metadata title avec suffixe technique",
            "metadata": {"title": "Regards-94-Janvier2024.indd Janvier"},
            "filename": "e2765b4e7bbd454db68880702960fd04_Regards-94.pdf",
            "expected": "Regards N°94 Janvier 2024"
        },
        {
            "name": "Filename seul",
            "metadata": {},
            "filename": "e2765b4e7bbd454db68880702960fd04_Regards-94-Janvier2024.pdf",
            "expected": "Regards N°94 Janvier 2024"
        },
        {
            "name": "Collection avec tirets",
            "metadata": {"title": "Science-et-Vie-123-Mars2023"},
            "filename": "uuid_original.pdf",
            "expected": "Science et Vie N°123 Mars 2023"
        },
        {
            "name": "Éléments manquants - juste collection et numéro",
            "metadata": {"title": "Regards-94"},
            "filename": "uuid_original.pdf",
            "expected": "Regards N°94"
        },
        {
            "name": "Juste année et collection",
            "metadata": {"title": "Regards-2024"},
            "filename": "uuid_original.pdf",
            "expected": "Regards 2024"
        }
    ]
    
    print("=== Test extraction depuis métadonnées/nom de fichier ===\n")
    
    for i, case in enumerate(test_cases, 1):
        print(f"Test {i}: {case['name']}")
        print(f"  Input metadata: {case['metadata']}")
        print(f"  Input filename: {case['filename']}")
        
        # Test la nouvelle méthode d'extraction de composants
        result_components = service._extract_components_from_metadata_or_filename(
            case['metadata'], 
            case['filename']
        )
        
        formatted_result = _format_issue_title(*result_components) if any(result_components) else None
        
        print(f"  Components: {result_components}")
        print(f"  Result: {formatted_result}")
        print(f"  Expected: {case['expected']}")
        
        if formatted_result == case['expected']:
            print("  ✅ PASS")
        else:
            print("  ❌ FAIL")
        print()
    
    # Test du parsing de composants
    print("=== Test du parsing de composants ===\n")
    
    component_tests = [
        "Regards-94-Janvier2024",
        "Science et Vie N°123 Mars 2023", 
        "Cahiers-Spéléologiques-45-Septembre2022",
        "Simple Magazine 2024",
        "L'Écho des Rhinos"
    ]
    
    for text in component_tests:
        print(f"Text: '{text}'")
        components = service._parse_issue_components_from_text(text)
        collection, number, month, year = components
        print(f"  Collection: {collection}")
        print(f"  Number: {number}")
        print(f"  Month: {month}")
        print(f"  Year: {year}")
        
        formatted = _format_issue_title(collection, number, month, year) if any(components) else None
        print(f"  Formatted: {formatted}")
        print()

if __name__ == "__main__":
    test_parsing()