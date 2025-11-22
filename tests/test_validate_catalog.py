import json
from pathlib import Path
from pydantic import ValidationError
from db.models import load_catalog_from_dict

def test_catalog_validation():
    """
    Testet die Validierung einer OSCAL-kompatiblen Katalogdatei im JSON-Format.

    - Lädt die JSON-Datei von einem definierten Pfad
    - Wandelt die Daten mit Pydantic in das definierte Catalog-Modell um
    - Gibt validierte Daten als JSON (mit Aliases & ohne leere Felder) auf der Konsole aus
    - Meldet Validierungsfehler oder unerwartete Probleme
    """

    # Pfad zur zu validierenden OSCAL-Katalogdatei
    json_path = Path("../files/catalog_enterprise_uuid_fixed.json")

    try:
        # Schritt 1: JSON-Datei einlesen
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        print("📦 Rohdaten geladen:", raw_data.keys())

        # Schritt 2: Pydantic-Validierung und Umwandlung in das Catalog-Objekt
        catalog = load_catalog_from_dict(raw_data)
        print("✅ Validation successful!")

        # Schritt 3: Validiertes Modell als JSON mit Aliases & ohne None-Werte ausgeben
        validated_json = catalog.model_dump(by_alias=True, exclude_none=True)

        # JSON ausgeben (inkl. UUIDs und Datetime-Werten als Strings)
        #print(json.dumps(validated_json, indent=2, default=str))

    except ValidationError as ve:
        # Fehler bei der Validierung → detailliert anzeigen
        print("❌ Validation failed:")
        print(ve.json(indent=2))

    except Exception as e:
        # Alle anderen (z. B. Datei nicht gefunden, JSON kaputt)
        print(f"❌ Unexpected error: {e}")

test_catalog_validation()