# Filename: logic/hitl_processes.py

import logging
from typing import Optional
from db.queries_rag import add_mapping_relationship
from db.hitl_queries import get_mapping_detail

log = logging.getLogger(__name__)

VALID_TYPES = ["EQUAL", "SUBSET", "SUPERSET", "RELATED", "UNRELATED", "ERROR"]

def human_validate_without_changes(source_id: str, target_id: str) -> bool:
    """
    Human klickt 'Bestätigen' ohne Änderungen:
    method bleibt 'LLM', status -> 'human_validated'.
    """
    props = {
        "status": "human_validated"
    }
    return add_mapping_relationship(source_id, target_id, props)

def human_edit_and_confirm(
    source_id: str,
    target_id: str,
    new_type: Optional[str],
    new_explanation: str
) -> bool:
    """
    Human ändert type/explanation:
    - explanation_old sichern
    - explanation überschreiben
    - optional type setzen (validiert)
    - method='Human', status='confirmed'
    """
    current = get_mapping_detail(source_id, target_id)
    if current is None:
        raise RuntimeError("Mapping not found for edit.")

    props = {
        "method": "Human",
        "status": "confirmed",
    }

    # Explanation-Versionierung
    old_expl = current.get("explanation")
    if old_expl is not None and old_expl != new_explanation:
        props["explanation_old"] = old_expl
    props["explanation"] = new_explanation

    # Type validieren/setzen
    if new_type:
        nt = new_type.upper()
        if nt not in VALID_TYPES:
            raise ValueError(f"Invalid mapping type: {new_type}")
        props["type"] = nt

    return add_mapping_relationship(source_id, target_id, props)