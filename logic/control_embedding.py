# Filename: logic/control_embedding.py
# CORRECTED VERSION (Linter errors fixed)

"""
Embedding control parts for Neo4j catalogs.

This module provides a small embedding subsystem that

* lazily initializes a SentenceTransformer model and its tokenizer,
* exposes the currently active model configuration,
* retrieves the embedding status for control description parts from Neo4j, and
* calculates and stores embeddings for those parts in bulk.

The functions are designed to be used from a GUI or CLI environment that
passes an optional progress callback for user feedback. All heavy work is
centralized here so that the rest of the application can remain thin.
"""
import os
import logging
import numpy as np
import requests  # For exception types
import torch
from typing import Optional, Callable, Any, List, Dict

from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
from huggingface_hub.utils import HfHubHTTPError

from db.queries_embeddings import (
    get_controls_with_description_parts,
    bulk_update_embeddings_for_parts,
)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global variables for caching ---
# These globals hold the currently active embedding model configuration.
_model: Optional[SentenceTransformer] = None
_tokenizer: Optional[Any] = None
_current_model_name: Optional[str] = None
_current_token_limit: Optional[int] = None


# --- Core functions ---

def initialize_embedding_system(
    model_name: str = "sentence-transformers/all-mpnet-base-v2",
    progress_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """Initialize or (re-)initialize the global embedding system."""

    global _model, _tokenizer, _current_model_name, _current_token_limit

    # ------------------------------------------------------------
    # NEW: Local dynamic model override
    # If the caller passes the default HuggingFace name,
    # automatically replace it with the local mpnet path.
    # ------------------------------------------------------------
    if model_name == "sentence-transformers/all-mpnet-base-v2":
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_name = os.path.join(BASE_DIR, "models", "all-mpnet-base-v2")
    # ------------------------------------------------------------

    if progress_callback:
        progress_callback(f"Initializing embedding system for model: '{model_name}'...")

    # Fast path: model already loaded  
    if _current_model_name == model_name and _model is not None and _tokenizer is not None:
        if progress_callback:
            progress_callback(
                f"✅ Model '{model_name}' is already initialized (Token Limit: {_current_token_limit})."
            )
        return True

    logging.info(
        f"Model change or first-time initialization requested for '{model_name}'. Resetting internal cache."
    )
    _model = None
    _tokenizer = None
    _current_model_name = None
    _current_token_limit = None
    model_loaded = False
    tokenizer_loaded = False

    try:
        if progress_callback:
            progress_callback(f"Loading model '{model_name}'...")
        temp_model = SentenceTransformer(model_name)
        _model = temp_model
        model_loaded = True
        if progress_callback:
            progress_callback("✅ Model successfully loaded.")

        # Token limit detection
        try:
            if (
                hasattr(_model, 'max_seq_length') and
                isinstance(_model.max_seq_length, int) and
                _model.max_seq_length > 0
            ):
                _current_token_limit = _model.max_seq_length
                if progress_callback:
                    progress_callback(f"ℹ️ Token limit of the model detected: {_current_token_limit}")
            else:
                if (
                    _tokenizer and
                    hasattr(_tokenizer, 'model_max_length') and
                    isinstance(_tokenizer.model_max_length, int) and
                    _tokenizer.model_max_length > 0
                ):
                    _current_token_limit = _tokenizer.model_max_length
                    if progress_callback:
                        progress_callback(f"ℹ️ Token limit from tokenizer detected: {_current_token_limit}")
                else:
                    _current_token_limit = 512
                    if progress_callback:
                        progress_callback(
                            f"⚠️ Could not determine token limit dynamically, using default: {_current_token_limit}"
                        )
                    logging.warning(
                        f"Could not determine 'max_seq_length' for model '{model_name}' or tokenizer. "
                        f"Falling back to {_current_token_limit}."
                    )

        except Exception as e_limit:
            _current_token_limit = 512
            if progress_callback:
                progress_callback(
                    f"⚠️ Error determining token limit ({e_limit}), using default: {_current_token_limit}"
                )
            logging.error(
                f"Error determining token limit for '{model_name}': {e_limit}. "
                f"Fallback: {_current_token_limit}."
            )

    except (requests.exceptions.ConnectionError, HfHubHTTPError) as e_net:
        error_msg = (
            f"❌ Network error downloading model '{model_name}': {type(e_net).__name__}"
        )
        if progress_callback:
            progress_callback(error_msg)
        logging.error(f"{error_msg} - {e_net}")

    except Exception as e_gen:
        error_msg = (
            f"❌ General error loading model '{model_name}': {type(e_gen).__name__}"
        )
        if progress_callback:
            progress_callback(error_msg)
        logging.error(f"{error_msg} - {e_gen}", exc_info=True)

    # --- TOKENIZER LOADING ---
    if model_loaded:
        try:
            if progress_callback:
                progress_callback(f"Loading tokenizer for '{model_name}'...")
            temp_tokenizer = AutoTokenizer.from_pretrained(model_name)
            _tokenizer = temp_tokenizer
            tokenizer_loaded = True
            if progress_callback:
                progress_callback("✅ Tokenizer successfully loaded.")

            # Update token limit if needed
            if (
                (_current_token_limit == 512 or _current_token_limit is None) and
                hasattr(_tokenizer, 'model_max_length') and
                isinstance(_tokenizer.model_max_length, int) and
                _tokenizer.model_max_length > 0
            ):
                _current_token_limit = _tokenizer.model_max_length
                if progress_callback:
                    progress_callback(
                        f"ℹ️ Token limit updated from tokenizer: {_current_token_limit}"
                    )
                logging.info(
                    f"Token limit for '{model_name}' updated from tokenizer to {_current_token_limit}."
                )

        except (requests.exceptions.ConnectionError, HfHubHTTPError) as e_net:
            error_msg = (
                f"❌ Network error downloading tokenizer '{model_name}': {type(e_net).__name__}"
            )
            if progress_callback:
                progress_callback(error_msg)
            logging.error(f"{error_msg} - {e_net}")
            model_loaded = False

        except Exception as e_gen:
            error_msg = (
                f"❌ General error loading tokenizer '{model_name}': {type(e_gen).__name__}"
            )
            if progress_callback:
                progress_callback(error_msg)
            logging.error(f"{error_msg} - {e_gen}", exc_info=True)
            model_loaded = False

    # Safety check  
    if model_loaded and tokenizer_loaded and (_current_token_limit is None or _current_token_limit <= 0):
        _current_token_limit = 512
        logging.warning(
            f"Token limit for '{model_name}' was invalid, setting final fallback to {_current_token_limit}."
        )
        if progress_callback:
            progress_callback(
                f"⚠️ Token limit was invalid, final fallback: {_current_token_limit}"
            )

    # Finalize  
    if model_loaded and tokenizer_loaded:
        _current_model_name = model_name
        if progress_callback:
            progress_callback(
                f"✅ System ready with model '{_current_model_name}' (Limit: {_current_token_limit})."
            )
        logging.info(
            f"Embedding system init: '{_current_model_name}' (Limit: {_current_token_limit})"
        )
        return True

    _model = None
    _tokenizer = None
    _current_model_name = None
    _current_token_limit = None
    if progress_callback:
        progress_callback("❌ Initialization failed.")
    logging.error(f"Initialization for '{model_name}' failed.")
    return False



def get_active_model_components() -> tuple[Optional[SentenceTransformer], Optional[Any], Optional[int], Optional[str]]:
    """Return the currently active embedding components.

    This function acts as a safe accessor for the global embedding state.
    It verifies that

    * a model is loaded,
    * a tokenizer is available,
    * a positive token limit is configured, and
    * a model name is known.

    If any of these conditions is not met, a ``RuntimeError`` is raised to
    force the caller to run :func:`initialize_embedding_system` first.

    Returns:
        tuple: A 4-tuple ``(model, tokenizer, token_limit, model_name)`` where:

        * ``model`` is the active :class:`SentenceTransformer` instance,
        * ``tokenizer`` is the corresponding tokenizer,
        * ``token_limit`` is the maximum number of tokens per sequence, and
        * ``model_name`` is the identifier of the currently active model.

    Raises:
        RuntimeError: If the embedding system has not been initialized or
        the token limit is invalid (``None`` or ``<= 0``).
    """
    if _model is None or _tokenizer is None or _current_token_limit is None or _current_model_name is None or _current_token_limit <= 0:
        logging.error("ERROR: Embedding system not correctly initialized (components or token limit missing/invalid).")
        raise RuntimeError("Embedding system not initialized or token limit invalid. Please call initialize_embedding_system() first.")
    return _model, _tokenizer, _current_token_limit, _current_model_name


def get_current_active_model_name() -> Optional[str]:
    """Get the name of the currently active embedding model.

    This is a convenience helper for UI components that only need to
    display the model name without accessing the full embedding state.

    Returns:
        str | None: The configured model name, or ``None`` if no model
        has been successfully initialized yet.
    """
    return _current_model_name


def get_control_embedding_status(
    catalog_uuid: str,
    group_id: Optional[str] = None,
    only_without_group: bool = False,
    only_with_embedding: bool = False,
    show_all_controls: bool = False
) -> list[dict]:
    """Retrieve embedding status for description parts of controls.

    This function delegates to :func:`get_controls_with_description_parts`
    in ``db.queries_embeddings`` and adds logging plus a safe fallback
    (empty list) in case of errors. It is typically used to populate a
    table in the GUI that shows which parts already have embeddings and
    which are still missing.

    Args:
        catalog_uuid: UUID of the catalog whose controls should be
            inspected.
        group_id: Optional group identifier to restrict the selection
            to controls within a specific group.
        only_without_group: If ``True``, limit results to controls that
            are not associated with any group.
        only_with_embedding: If ``True``, return only parts that already
            have an embedding stored in the database.
        show_all_controls: If ``True``, ignore group-related filters and
            return all eligible controls for the given catalog.

    Returns:
        list[dict]: A list of dictionaries describing each part, as
        returned by the database query. On errors, an empty list is
        returned and an error is logged.
    """
    logging.info(f"Retrieving embedding status for catalog {catalog_uuid} (Filter: ...)")
    try:
        status_list = get_controls_with_description_parts(
            catalog_uuid=catalog_uuid,
            group_id=group_id,
            only_without_group=only_without_group,
            only_with_embedding=only_with_embedding,
            show_all_controls=show_all_controls,
        )
        logging.info(f"Embedding status for {len(status_list)} parts received from DB.")
        return status_list
    except Exception as e:
        logging.error(f"Error retrieving embedding status: {e}", exc_info=True)
        return []


def create_embeddings_for_parts(
        parts: list[dict],
        progress_callback: Optional[Callable[[str], None]] = None
) -> int:
    """Create and persist embeddings for a list of description parts.

    Each item in ``parts`` is expected to describe a single ``Part`` node
    in Neo4j (usually with ``name = "description"``) and must at least
    provide

    * the element id of the part node (``part_element_id``),
    * the parent control id (``control_id``), and
    * the text to embed (``description``).

    Parts that already have an embedding (``has_embedding`` is truthy)
    are skipped. For remaining parts, a sentence-transformer embedding
    is computed. If the input text exceeds the configured token limit,
    the function performs chunking and mean pooling across multiple
    encoded segments to stay within model constraints.

    All calculated embeddings are collected and then stored in bulk using
    :func:`bulk_update_embeddings_for_parts`.

    Args:
        parts: List of dictionaries describing the parts that should be
            embedded. The concrete schema is defined by the database
            query in ``db.queries_embeddings``.
        progress_callback: Optional callable used to report progress and
            status messages (e.g. to a GUI text area).

    Returns:
        int: Number of embeddings that were successfully calculated
        (i.e. embeddings that were added to the bulk payload). This is
        independent of the exact number of rows actually updated in the
        database, which is reported via logging and progress messages.

    Raises:
        RuntimeError: Propagated from :func:`get_active_model_components`
        if the embedding system has not been initialized. In this case
        the function catches the error, logs it, reports it via the
        progress callback and returns ``0``.
        Exception: Any exceptions during encoding or database operations
        are caught internally, logged and reported via the progress
        callback. The function continues processing remaining parts
        where possible.
    """
    try:
        model, tokenizer, token_limit, model_name = get_active_model_components()
        # CORRECTION for linter type warning:
        # get_active_model_components throws a RuntimeError if token_limit is None or <= 0.
        # Therefore, after a successful call, we can assume that token_limit is an int > 0.
        # An assert can help the linter, or one can rely on the runtime check.
        assert token_limit is not None and token_limit > 0, "Token limit was not initialized correctly"

    except RuntimeError as e:
        if progress_callback:
            progress_callback(f"❌ ERROR: Embedding system not ready - {e}")
        logging.error(f"Error retrieving active model components: {e}", exc_info=True)
        return 0

    if progress_callback:
        progress_callback(f"Starting embedding creation with model '{model_name}' (Limit: {token_limit})...")

    embeddings_to_save: List[Dict[str, Any]] = []
    created_count = 0
    processed_count = 0
    # CORRECTION: Variable name lowercased
    batch_size_for_model_encode = 32

    for i, part in enumerate(parts):
        processed_count += 1
        # Periodically update progress to avoid flooding the UI.
        if progress_callback and processed_count % 10 == 0:
            progress_callback(f"Processing part {processed_count}/{len(parts)} for embedding creation...")

        if part.get("has_embedding"):
            continue
        part_id = part.get("part_element_id")
        control_id = part.get("control_id", "Unknown")  # Translated "Unbekannt"
        description = part.get("description")

        if not part_id or not description:
            warn_msg = f"⚠️ No text or part_element_id for Control {control_id} (Part ID: {part_id}), skipped."
            if progress_callback:
                progress_callback(warn_msg)
            logging.warning(warn_msg)
            continue

        try:
            if progress_callback:
                progress_callback(f"Calculating embedding for Control {control_id}...")
            tokens = tokenizer.encode(description, add_special_tokens=True, truncation=False)

            # Handle texts that exceed the configured token limit by chunking
            # and mean-pooling their embeddings.
            if len(tokens) > token_limit:
                if progress_callback:
                    progress_callback(f"🔄 Text for {control_id} too long ({len(tokens)} > {token_limit} Tokens). Using Mean-Pooling...")
                logging.info(f"Text for Control {control_id} (Part ID: {part_id}) > Limit ({len(tokens)} > {token_limit}). Chunking.")
                inner_tokens = tokens[1:-1]
                chunk_size = token_limit - 2 if token_limit > 2 else token_limit
                if chunk_size <= 0:
                    chunk_size = 1
                token_chunks = [inner_tokens[j: j + chunk_size] for j in range(0, len(inner_tokens), chunk_size)]
                text_chunks = [tokenizer.decode(chunk, skip_special_tokens=True) for chunk in token_chunks if chunk]
                if not text_chunks:
                    warn_msg = f"⚠️ Could not create text chunks for {control_id}, skipped."
                    if progress_callback:
                        progress_callback(warn_msg)
                    logging.warning(warn_msg)
                    continue
                chunk_embeddings = model.encode(
                    text_chunks,
                    convert_to_tensor=False,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    batch_size=batch_size_for_model_encode,
                )
                final_embedding_np = np.mean(chunk_embeddings, axis=0)
                final_embedding = final_embedding_np.tolist()
                if progress_callback:
                    progress_callback(f"📊 Mean-Pooling for {control_id} ({len(text_chunks)} chunks) completed.")
            else:
                if progress_callback:
                    progress_callback(f"Generating standard embedding for {control_id}...")
                embedding_np = model.encode(
                    description,
                    convert_to_tensor=False,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
                final_embedding = embedding_np.tolist()
            embeddings_to_save.append(
                {"part_element_id": part_id, "embedding_vector": final_embedding, "model_name": model_name}
            )
            created_count += 1
            if progress_callback:
                progress_callback(f"✔️ Embedding for {control_id} calculated (not yet saved).")
        except Exception as e:
            error_msg = f"❌ ERROR during embedding calculation for {control_id} (Part ID: {part_id}): {type(e).__name__} - {str(e)}"
            if progress_callback:
                progress_callback(error_msg)
            logging.error(error_msg, exc_info=True)
        finally:
            # For Apple Silicon / MPS backends, try to free GPU memory after each
            # iteration to keep long-running jobs stable.
            if _current_model_name and hasattr(torch, 'backends') and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                try:
                    torch.mps.empty_cache()
                except Exception as e_mps:
                    logging.warning(f"Could not empty MPS cache: {e_mps}")

    # Persist all collected embeddings in a single bulk operation.
    if embeddings_to_save:
        if progress_callback:
            progress_callback(f"💾 Saving {len(embeddings_to_save)} new embeddings to DB (Bulk)...")
        try:
            save_result = bulk_update_embeddings_for_parts(embeddings_to_save)
            if save_result.get("error"):
                error_msg = f"❌ Error during bulk saving of embeddings: {save_result['error']}"
                if progress_callback:
                    progress_callback(error_msg)
                logging.error(error_msg)
                # CORRECTION: Explicit return not necessary here, created_count is returned at the end
            else:
                updated_db_count = save_result.get('updated_parts_count', 0)
                if progress_callback:
                    progress_callback(f"✅ {updated_db_count} embeddings successfully saved/updated in DB.")
                logging.info(f"Bulk embedding saving: {updated_db_count} Parts updated.")
        except Exception as e_bulk_save:
            error_msg = f"❌ Critical error calling bulk_update_embeddings_for_parts: {e_bulk_save}"
            if progress_callback:
                progress_callback(error_msg)
            logging.error(error_msg, exc_info=True)
            # CORRECTION: Explicit return not necessary here
    elif created_count > 0:
        warn_msg = f"⚠️ {created_count} embeddings were calculated, but nothing prepared for saving."
        if progress_callback:
            progress_callback(warn_msg)
        logging.warning(warn_msg)
        # CORRECTION: Explicit return not necessary here

    final_msg = f"🏁 Embedding creation completed. {created_count} embeddings were calculated (and attempted to be saved)."
    if progress_callback:
        progress_callback(final_msg)
    logging.info(f"Embedding creation for {len(parts)} parts completed. {created_count} calculated.")
    return created_count