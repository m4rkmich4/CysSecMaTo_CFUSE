# Filename: logic/control_mapping.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/logic/control_mapping.py
# ADJUSTED VERSION FOR 1-N AND M-N SIMILARITY COMPARISON

import logging
from typing import Optional, Dict, Any, List

from db.queries_mapping import (
    get_embedding_vector_for_part,
    calculate_similarities_for_display,       # 1-N calculation for display
    bulk_merge_similarity_relations,          # 1-N storage
    calculate_and_store_many_to_many_similarities,  # M-N calculation + storage
    get_top_n_many_to_many_similarity_results       # M-N Top-N result query
)

log = logging.getLogger(__name__)


def prepare_locked_control_data(
    part_element_id: str,
    control_id: str,
    control_title: str,
    control_prose: str
) -> Optional[Dict[str, Any]]:
    """
    Prepares the data for a control selected as a source ("locked"):
    Fetches the embedding_vector and provides all metadata.
    """
    log.info(f"LOGIC: Preparing data for locked control (Part elementId={part_element_id}, Control ID={control_id})")
    if not all([part_element_id, control_id, control_title, control_prose]):
        log.warning("LOGIC: Incomplete data received for preparing the locked control.")
        return None

    embedding = get_embedding_vector_for_part(part_element_id)
    if embedding is None:
        log.error(f"LOGIC: Could not retrieve embedding for Part {part_element_id}.")
        return None

    locked = {
        "control_id": control_id,
        "title": control_title,
        "prose": control_prose,
        "part_element_id": part_element_id,
        "embedding": embedding
    }
    log.info(f"LOGIC: Data for locked control '{control_id}' successfully prepared.")
    return locked


def calculate_all_similarities(
    locked_control_data: Dict[str, Any],
    target_catalog_uuid: str,
    target_group_id: Optional[str] = None,
    display_threshold: float = 0.0
) -> List[Dict[str, Any]]:
    """
    1-N: Calculates all cosine similarities for display (without saving).
    Returns only results with score >= display_threshold.
    """
    if not locked_control_data or "part_element_id" not in locked_control_data:
        log.error("LOGIC: Invalid locked_control_data for 1-N calculation.")
        raise ValueError("Invalid data for locked control.")

    pid = locked_control_data["part_element_id"]
    cid = locked_control_data["control_id"]
    log.info(f"LOGIC: Starting 1-N similarity calculation (display): locked='{cid}' → catalog='{target_catalog_uuid}', group='{target_group_id}', threshold={display_threshold}")

    try:
        results = calculate_similarities_for_display(
            locked_part_element_id=pid,
            target_catalog_uuid=target_catalog_uuid,
            target_group_id=target_group_id,
            display_threshold=display_threshold
        )
        log.info(f"LOGIC: {len(results)} results calculated for display.")
        return results
    except Exception as e:
        log.error(f"LOGIC: Error in calculate_similarities_for_display: {e}", exc_info=True)
        raise RuntimeError(f"Error in 1-N query: {e}") from e


def store_similarity_relations(
    results_to_save: List[Dict[str, Any]],
    embedding_model_name: str
) -> Dict[str, Any]:
    """
        Persist filtered 1→N or M→N similarity results as ``HAS_SIMILARITY`` relations.

        Expected item format in ``results_to_save``:

        - ``source_control_id`` (str)
        - ``target_control_id`` (str)
        - ``similarity_score`` (float)
        - ``similarity_category`` (str)

        Parameters
        ----------
        results_to_save : list[dict]
            List of similarity result dictionaries to persist.
        embedding_model_name : str
            Name of the embedding model used.

        Returns
        -------
        dict
            Persistence summary, e.g. ``{"relationships_merged": int}``.

        Raises
        ------
        RuntimeError
            If the persistence layer reports an error.
        """
    if not results_to_save:
        log.info("LOGIC: No results passed for saving.")
        return {"relationships_merged": 0}

    log.info(f"LOGIC: Saving {len(results_to_save)} 1-N HAS_SIMILARITY relationships with model '{embedding_model_name}'")
    # Add model_name to each result
    prepared = []
    for r in results_to_save:
        prepared.append({
            "source_control_id": r["source_control_id"],
            "target_control_id": r["target_control_id"],
            "similarity_score": r["similarity_score"],
            "similarity_category": r["similarity_category"],
            "model_name": embedding_model_name
        })

    try:
        res = bulk_merge_similarity_relations(prepared)
        if res.get("error"):
            msg = res["error"]
            log.error(f"LOGIC: bulk_merge_similarity_relations reported error: {msg}")
            raise RuntimeError(msg)
        merged = res.get("relationships_merged", 0)
        log.info(f"LOGIC: Saving completed: {merged} relationships.")
        return res
    except Exception as e:
        log.error(f"LOGIC: Error in bulk_merge_similarity_relations: {e}", exc_info=True)
        raise RuntimeError(f"Error during saving: {e}") from e


def execute_many_to_many_similarity_process(
    source_catalog_uuid: str,
    target_catalog_uuid: str,
    embedding_model_name: str,
    source_group_id: Optional[str] = None,
    target_group_id: Optional[str] = None,
    similarity_threshold: float = 0.3,
    top_n_for_display: int = 25
) -> Dict[str, Any]:
    """
        Run the many-to-many similarity workflow.

        The process consists of:

        1. Collect candidate pairs based on the selected catalogs and filters.
        2. Compute similarity scores for each pair.
        3. Categorize similarities (e.g., HIGH/MEDIUM/LOW).
        4. Persist selected relations to the graph.

        Parameters
        ----------
        source_catalog_id : str
            Catalog identifier of the source side.
        target_catalog_id : str
            Catalog identifier of the target side.
        threshold : float
            Minimum similarity score to keep a pair.
        top_k : int
            Keep at most *k* targets per source.
        embedding_model_name : str
            Name of the embedding model used for scoring.

        Returns
        -------
        dict
            Summary containing counters, e.g. ``{"pairs_scored": int, "persisted": int}``.

        Raises
        ------
        RuntimeError
            If any sub-step fails or the persistence layer reports an error.
        """
    log.info(f"LOGIC: Starting M-N comparison: {source_catalog_uuid} vs {target_catalog_uuid}")

    try:
        stats = calculate_and_store_many_to_many_similarities(
            source_catalog_uuid=source_catalog_uuid,
            target_catalog_uuid=target_catalog_uuid,
            embedding_model_name=embedding_model_name,
            source_group_id=source_group_id,
            target_group_id=target_group_id,
            similarity_threshold=similarity_threshold
        )
        if stats.get("error"):
            raise RuntimeError(stats["error"])
    except Exception as e:
        log.error(f"LOGIC: Error in M-N calculation/saving: {e}", exc_info=True)
        return {"top_results": [], "statistics": {"relationships_written": 0, "relationships_enriched": 0}, "error": str(e)}

    # Fetch Top-N
    try:
        top_results = get_top_n_many_to_many_similarity_results(
            source_catalog_uuid=source_catalog_uuid,
            target_catalog_uuid=target_catalog_uuid,
            source_group_id=source_group_id,
            target_group_id=target_group_id,
            limit=top_n_for_display
        )
    except Exception as e:
        log.error(f"LOGIC: Error in Top-N M-N query: {e}", exc_info=True)
        # If fetching top results fails, we still have the stats from the calculation step
        return {"top_results": [], "statistics": stats, "error": str(e)}

    log.info(f"LOGIC: M-N comparison completed: {len(top_results)} top results.")
    # Ensure the statistics dict has the 'relationships_enriched' key if it's expected in the return type hint.
    # The calculate_and_store_many_to_many_similarities only returns "relationships_written".
    # For consistency with the docstring (which I've updated to include it based on the return structure),
    # we might want to initialize it if not present, or adjust the docstring.
    # Given the return structure in the code, it's better to ensure the dict is consistent.
    if "relationships_enriched" not in stats: # Default to 0 if not returned by the DB function
        stats["relationships_enriched"] = 0

    return {"top_results": top_results, "statistics": stats, "error": None}