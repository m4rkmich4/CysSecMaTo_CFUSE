# Filename: logic/rag_processor.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/logic/rag_processor.py
# CORRECTED VERSION - Uses call_local_llm from llm_interface

import logging
import re
from typing import Optional, Dict, Any, List, Tuple

# Import the required database functions
from db.queries_rag import get_similar_control_context, add_mapping_relationship

# --- CHANGED LLM IMPORT ---
# Import the actual LLM function
try:
    # Try to import the correct function
    from .llm_interface import call_local_llm
    LLM_AVAILABLE = True
    log = logging.getLogger(__name__) # Get logger if import succeeds
    log.info("LLM interface 'call_local_llm' imported successfully.")
except ImportError:
    log = logging.getLogger(__name__)
    log.warning("llm_interface or the function 'call_local_llm' not found. LLM functionality is disabled.")
    LLM_AVAILABLE = False
    # Define a dummy function that throws an error if called
    def call_local_llm(prompt: str, model: str = "default") -> str: # Adapt signature to original?
        log.error("Call to dummy call_local_llm because import failed.")
        raise RuntimeError("LLM interface (call_local_llm) is not available.")
# --- END LLM IMPORT ---

# Import prompt template from the configuration file
try:
    from config.prompts_rag import RAG_MAPPING_PROMPT_TEMPLATE
    if not isinstance(RAG_MAPPING_PROMPT_TEMPLATE, str) or '{source_prose}' not in RAG_MAPPING_PROMPT_TEMPLATE or '{target_prose}' not in RAG_MAPPING_PROMPT_TEMPLATE:
         if not log: log = logging.getLogger(__name__) # Get logger if not yet initialized
         log.error("RAG_MAPPING_PROMPT_TEMPLATE from config.prompts_rag seems invalid or incomplete.")
         raise ValueError("Imported RAG_MAPPING_PROMPT_TEMPLATE is invalid.")
except ImportError:
    if not log: log = logging.getLogger(__name__) # Get logger if not yet initialized
    log.critical("FATAL: Could not import RAG_MAPPING_PROMPT_TEMPLATE from config.prompts_rag!")
    raise ImportError("RAG_MAPPING_PROMPT_TEMPLATE could not be loaded from config.prompts_rag.")

# Initialize logger here as a safety measure, in case errors occurred during imports above
if 'log' not in globals():
   log = logging.getLogger(__name__)


def fetch_similar_controls_for_rag(
    source_control_id: str,
    allowed_categories: Optional[List[str]] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Calls the database function to fetch a list of similar Controls.
    (Function unchanged)
    """
    log.info(f"Fetching similar Controls for RAG from Control '{source_control_id}'...")
    try:
        similar_controls = get_similar_control_context(
            source_control_id=source_control_id,
            allowed_categories=allowed_categories,
            limit=limit
        )
        log.info(f"{len(similar_controls)} similar Controls found.")
        return similar_controls
    except Exception as e:
        log.error(f"Error fetching similar Controls for '{source_control_id}': {e}", exc_info=True)
        raise RuntimeError(f"Database error fetching similar Controls: {e}") from e


def _parse_llm_mapping_response(response_text: str) -> Tuple[Optional[str], str]:
    """
    Tries to extract the classification and explanation from the LLM response.
    (Function unchanged)
    """
    classification = None
    explanation = response_text
    try:
        match_class = re.search(r"Classification:\s*([A-Z_]+)", response_text, re.IGNORECASE) # Translated "Klassifikation"
        if match_class:
            classification = match_class.group(1).upper()
            explanation_match = re.search(r"Explanation:\s*(.*)", response_text, re.IGNORECASE | re.DOTALL) # Translated "Erklärung"
            if explanation_match: explanation = explanation_match.group(1).strip()
            else: explanation = response_text[match_class.end():].strip()
        else: log.warning("Could not find 'Classification:' in LLM response.") # Translated "Klassifikation"
    except Exception as e:
        log.error(f"Error parsing LLM response: {e}", exc_info=True)
    valid_classes = ["EQUAL", "SUBSET", "SUPERSET", "RELATED", "UNRELATED", "ERROR"]
    if classification not in valid_classes:
         log.warning(f"Invalid classification '{classification}' received from LLM. Will be treated as None.")
         classification = None
    return classification, explanation


def generate_llm_comparison(
    source_control_prose: str,
    target_control_prose: str
) -> Tuple[Optional[str], str]:
    """
    Generates a prompt, calls the LLM via call_local_llm, and returns
    the parsed response.
    """
    if not LLM_AVAILABLE: raise RuntimeError("LLM interface is not available.")
    if not source_control_prose or not target_control_prose: raise ValueError("Source and target prose must not be empty.")
    log.info("Generating LLM comparison...")
    try:
        if RAG_MAPPING_PROMPT_TEMPLATE is None or not isinstance(RAG_MAPPING_PROMPT_TEMPLATE, str):
             raise ValueError("RAG_MAPPING_PROMPT_TEMPLATE is not loaded correctly.")
        prompt = RAG_MAPPING_PROMPT_TEMPLATE.format(
            source_prose=source_control_prose,
            target_prose=target_control_prose
        )
    except KeyError as e:
        log.error(f"Error formatting prompt template: Missing key {e}")
        raise ValueError(f"Prompt template is faulty: Key {e} missing.")
    except Exception as e:
        log.error(f"Unknown error formatting prompt: {e}", exc_info=True)
        raise ValueError(f"Error creating prompt: {e}")

    try:
        # --- CHANGED FUNCTION CALL ---
        raw_response = call_local_llm(prompt) # Use the imported function
        # --- END CHANGE ---
        if not raw_response: raise ValueError("LLM returned an empty response.")
        log.info("LLM response received, parsing result...")
        classification, explanation = _parse_llm_mapping_response(raw_response)
        return classification, explanation
    except Exception as e:
        log.error(f"Error during LLM request or parsing: {e}", exc_info=True)
        # Rethrow the original exception if it comes from call_local_llm
        if isinstance(e, RuntimeError) and "LLM interface" in str(e): # Translated "LLM-Schnittstelle"
             raise e # Rethrow the error from the dummy or interface directly
        raise RuntimeError(f"LLM comparison failed: {e}") from e


def save_confirmed_mapping(
    source_control_id: str,
    target_control_id: str,
    mapping_properties: Dict[str, Any]
) -> bool:
    """
    Calls the database function to save a confirmed :IS_MAPPED_TO relationship.
    (Function unchanged)
    """
    if not source_control_id or not target_control_id or not mapping_properties:
        raise ValueError("Invalid inputs for saving the mapping.")
    log.info(f"Saving confirmed mapping to DB: {source_control_id} -> {target_control_id}")
    try:
        success = add_mapping_relationship(
            source_control_id=source_control_id,
            target_control_id=target_control_id,
            properties=mapping_properties
        )
        if not success: raise RuntimeError("DB function reported error during saving without exception.")
        log.info("Mapping successfully saved to DB.")
        return True
    except Exception as e:
        log.error(f"Error saving mapping for {source_control_id} -> {target_control_id}: {e}", exc_info=True)
        raise RuntimeError(f"Database error saving mapping: {e}") from e