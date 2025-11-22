import json
import traceback
from pathlib import Path
# --- Relative imports ---
from .neo4j_importer import import_catalog, check_catalog_exists
from .models import load_catalog_from_dict, Catalog
from pydantic import ValidationError
# Type imports
from typing import Optional, Callable

"""
Manages the import of OSCAL catalogs into the Neo4j database.

This module provides functions to read OSCAL catalog files (JSON),
validate them using Pydantic, and only import when the catalog UUID
is not already present in the Neo4j database. It assumes each UUID
represents a unique, immutable catalog version. It supports sending
progress messages via a callback.
"""

# --- Import function with callback support ---
def import_if_changed(path: Path,
                      progress_callback: Optional[Callable[[str], None]] = None
                      ) -> str:
    """
    Processes a single OSCAL catalog file for import.

    Reads the specified JSON file, validates its content against the
    Pydantic model (`Catalog` from `db.models`), then checks if a catalog
    with the extracted UUID already exists in the Neo4j database. If the
    UUID is new, it triggers the import via `import_catalog`. Progress
    is reported via the optional callback.

    Catches expected errors (file not found, invalid JSON, validation
    error, database error) and returns a user-friendly status or error
    message string suitable for display in a GUI. Detailed errors are
    printed to the console within except blocks.

    :param path: Path to the OSCAL catalog file (JSON) to import.
    :type path: pathlib.Path
    :param progress_callback: Optional function to receive progress messages.
    :type progress_callback: Optional[Callable[[str], None]]
    :return: A status message indicating success, no action (already exists),
             or an error that occurred.
    :rtype: str
    """
    # --- Helper to safely call the callback ---
    def report_progress(message: str):
        # Only invoke callback if provided
        if progress_callback:
            try:
                progress_callback(message)
            except Exception as cb_err:
                # Log callback errors but do not abort import
                print(f"WARNING: Error in progress callback: {cb_err}")

    # --- Early path validity check ---
    if not path or not path.is_file():
        msg = f"ERROR: Invalid path or file not found: '{path}'"
        report_progress(msg)  # Report early errors
        return msg

    try:
        # --- Step 1: Read file and parse JSON ---
        report_progress(f"Reading file: {path.name}...")
        raw_text = path.read_text(encoding='utf-8')
        raw_data = json.loads(raw_text)
        report_progress(f"File '{path.name}' successfully read and parsed.")

        # --- Step 2: Pydantic validation ---
        report_progress(f"Starting Pydantic validation for '{path.name}'...")
        try:
            catalog_obj: Catalog = load_catalog_from_dict(raw_data)
            catalog_id = str(catalog_obj.uuid)  # Extract UUID as string
            report_progress(f"Pydantic validation succeeded (UUID: {catalog_id}).")

        except ValidationError as ve:
            # Log detailed error backend
            print(f"ERROR: Pydantic validation failed for {path.name}:\n{ve.json(indent=2)}")
            error_details = ve.json(indent=2)
            msg = f"VALIDATION ERROR in '{path.name}':\n{error_details}"
            report_progress(msg)
            return msg
        except KeyError:
            print(f"ERROR: Missing 'catalog' key in {path.name}")
            msg = f"ERROR: Missing 'catalog' key in file: {path.name}"
            report_progress(msg)
            return msg

        # --- Step 3: Check existence in Neo4j ---
        report_progress(f"Checking existence of catalog UUID {catalog_id} in Neo4j...")
        try:
            exists = check_catalog_exists(catalog_id)
            report_progress(f"Existence check result: {'Found' if exists else 'Not found'}." )
        except ConnectionError as ce:
            print(f"ERROR: Database connection error when checking UUID {catalog_id}: {ce}")
            msg = f"DATABASE ERROR checking UUID {catalog_id}: {ce}"
            report_progress(msg)
            return msg
        except Exception as db_check_err:
            print(f"ERROR checking catalog existence for UUID {catalog_id}: {db_check_err}")
            msg = f"DATABASE ERROR checking UUID {catalog_id}: {db_check_err}"
            report_progress(msg)
            return msg

        # If UUID exists -> skip import
        if exists:
            print(f"[Import Manager] Catalog with UUID '{catalog_id}' ({path.name}) already exists.")
            msg = f"Catalog with UUID '{catalog_id}' ({path.name}) already exists. No import needed."
            report_progress(msg)
            return msg

        # --- Step 4: Perform import (new UUID) ---
        report_progress(f"Starting database import for new catalog '{catalog_id}'...")
        try:
            import_catalog(raw_data, progress_callback=progress_callback)
            print(f"[Import Manager] Successfully imported: '{catalog_id}'")
            msg = f"New catalog with UUID '{catalog_id}' ({path.name}) successfully imported."
            return msg

        except ValueError as ve:  # Semantic errors from importer
            print(f"ERROR: Error during Neo4j import of {catalog_id}: {ve}")
            msg = f"ERROR during database import of '{catalog_id}' ({path.name}): {ve}"
            report_progress(msg)
            return msg
        except ConnectionError as ce:  # DB connection error during import
            print(f"ERROR: Database connection error during import of {catalog_id}: {ce}")
            msg = f"DATABASE ERROR during import of '{catalog_id}' ({path.name}): {ce}"
            report_progress(msg)
            return msg
        except Exception as import_err:  # Other DB or importer errors
            error_trace = traceback.format_exc()
            print(f"Critical ERROR during import of {catalog_id}: {import_err}\n{error_trace}")
            msg = f"Critical ERROR during database import of '{catalog_id}' ({path.name}): {import_err}"
            report_progress(msg)
            return msg

    # --- General error handling for file access/JSON ---
    except FileNotFoundError:
        msg = f"ERROR: File not found during processing: {path.name}"
        report_progress(msg)
        return msg
    except json.JSONDecodeError as json_err:
        print(f"ERROR: Invalid JSON in file: {path.name} - {json_err}")
        msg = f"ERROR: Invalid JSON in file: {path.name} (Details: {json_err})"
        report_progress(msg)
        return msg
    except IOError as io_err:  # Read error
        print(f"ERROR: Could not read file: {path.name} - {io_err}")
        msg = f"ERROR: Could not read file: {path.name} ({io_err})"
        report_progress(msg)
        return msg
    except Exception as e:
        # Catch all other unexpected errors
        error_trace = traceback.format_exc()
        print(f"Unexpected ERROR processing {path.name}: {e}\n{error_trace}")
        msg = f"Unexpected ERROR processing {path.name}: {e}"
        report_progress(msg)
        return msg
