# Filename: db/queries_rag.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/db/queries_rag.py
# FINAL VERSION for RAG DB functions

import logging
from typing import Optional, List, Dict, Any
# Relative imports for the DB layer
from .neo4j_connector import get_driver
from neo4j.exceptions import Neo4jError, ServiceUnavailable

log = logging.getLogger(__name__)

# By default, we fetch medium and high similarities for the context
DEFAULT_RAG_CATEGORIES = ["high_similarity", "medium_similarity"]
DEFAULT_RAG_LIMIT = 5  # Fetch Top 5 hits by default


def get_similar_control_context(
    source_control_id: str,
    allowed_categories: Optional[List[str]] = None,
    limit: Optional[int] = DEFAULT_RAG_LIMIT
) -> List[Dict[str, Any]]:
    """
        Retrieve context documents for the most similar controls.

        Args:
            source_control_id (str): Control ID used as the source for similarity.
            allowed_categories (list[str] | None): Similarity categories to include
                (e.g., ``["high_similarity", "medium_similarity"]``). If ``None``,
                a sensible default is used.
            limit (int | None): Maximum number of similar controls to return.
                If ``None`` or ``<= 0``, no explicit LIMIT is applied.

        Returns:
            list[dict]: Each item contains fields such as:
                - ``target_id`` (str)
                - ``target_title`` (str | None)
                - ``target_prose`` (str | None)
                - ``score`` (float)
                - ``category`` (str)
                - ``has_confirmed_mapping`` (bool)

        Notes:
            The query filters by similarity category, prefers higher scores first,
            retrieves the description (``Part{name: "description"}``), and also checks
            whether an explicit mapping (``IS_MAPPED_TO``) exists between the
            source control and the candidate.

        Example (Cypher):

        .. code-block:: text

           MATCH (source:Control {id: $sourceId})-[r:HAS_SIMILARITY]->(target:Control)
           WHERE r.similarity_category IN $allowedCategories
           WITH source, target, r
           ORDER BY r.similarity_score DESC
           LIMIT $limit
           MATCH (target)-[:HAS_PART]->(p:Part {name: 'description'})
           WHERE p.prose IS NOT NULL
           OPTIONAL MATCH (source)-[m:IS_MAPPED_TO]->(target)
           RETURN target.id AS target_id,
                  target.title AS target_title,
                  p.prose AS target_prose,
                  r.similarity_score AS score,
                  r.similarity_category AS category,
                  m IS NOT NULL AS has_confirmed_mapping
        """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_similar_control_context.")
        return []

    categories_to_use = allowed_categories if allowed_categories is not None else DEFAULT_RAG_CATEGORIES
    limit_clause = f"LIMIT {int(limit)}" if limit is not None and limit > 0 else ""

    log.info(
        f"Fetching RAG context for source_control='{source_control_id}'. "
        f"Categories={categories_to_use}, Limit={limit or 'None'}"
    )

    # Adjusted Cypher Query with OPTIONAL MATCH
    cypher_query = f"""
    MATCH (source:Control {{id: $sourceId}})
          -[r:HAS_SIMILARITY]->
          (target:Control)
    WHERE r.similarity_category IN $allowedCategories // Filter by similarity category
    WITH source, target, r // Include source for OPTIONAL MATCH
    ORDER BY r.similarity_score DESC // Sort by highest score first
    {limit_clause} // Apply optional limit

    // Get the description of the target
    MATCH (target)-[:HAS_PART]->(p:Part {{name: 'description'}})
    WHERE p.prose IS NOT NULL // Ensure text is present

    // Check for existing mapping (IS_MAPPED_TO)
    OPTIONAL MATCH (source)-[m:IS_MAPPED_TO]->(target) // Search for the mapping edge

    // Return all data, including info on whether 'm' was found
    RETURN
        target.id AS target_id,
        target.title AS target_title,
        p.prose AS target_prose,
        r.similarity_score AS score, // Score of the similarity
        r.similarity_category AS category, // Category of the similarity
        m IS NOT NULL AS has_confirmed_mapping // true, if IS_MAPPED_TO exists
    // ORDER BY score DESC // Sorting already done before the limit
    """
    params = {"sourceId": source_control_id, "allowedCategories": categories_to_use}

    try:
        with driver.session() as session:
            log.debug(f"Executing query to retrieve RAG context (with mapping check): {params}")
            result = session.run(cypher_query, **params)
            records = [dict(record) for record in result]
            log.info(f"{len(records)} context Controls found for RAG (including mapping status).")
            return records
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error retrieving RAG context for '{source_control_id}': {e}", exc_info=True)
        # In case of error, return an empty list so UI is not blocked
        return []
    except Exception as e:
        log.error(f"General error retrieving RAG context for '{source_control_id}': {e}", exc_info=True)
        return []


def add_mapping_relationship(
    source_control_id: str,
    target_control_id: str,
    properties: Dict[str, Any]
) -> bool:
    """
       Create or update an ``IS_MAPPED_TO`` relationship between two controls.

       Args:
           source_control_id (str): ID of the source control node (``Control{id}``).
           target_control_id (str): ID of the target control node (``Control{id}``).
           properties (dict[str, Any]): Properties to set/merge into the relationship.
               On create, they are assigned wholesale; on match, they are merged
               (``+=``) so only provided keys are updated/added.

       Returns:
           bool: ``True`` if the MERGE executed successfully (created or matched),
           otherwise ``False``.

       Example (Cypher):

       .. code-block:: text

          MATCH (source:Control {id: $sourceId})
          MATCH (target:Control {id: $targetId})
          MERGE (source)-[r:IS_MAPPED_TO]->(target)
          ON CREATE SET
              r = $props,
              r.created_timestamp = timestamp(),
              r.last_updated_timestamp = timestamp()
          ON MATCH SET
              r += $props,
              r.last_updated_timestamp = timestamp()
          RETURN count(r) AS affected_count
       """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for add_mapping_relationship.")
        return False

    log.info(
        f"Saving/Updating mapping: {source_control_id} -[:IS_MAPPED_TO]-> "
        f"{target_control_id} with Properties: {properties}"
    )

    cypher_query = """
    MATCH (source:Control {id: $sourceId})
    MATCH (target:Control {id: $targetId})
    MERGE (source)-[r:IS_MAPPED_TO]->(target)
    ON CREATE SET
        r = $props,
        r.created_timestamp = timestamp(),
        r.last_updated_timestamp = timestamp()
    ON MATCH SET
        r += $props, // += only updates provided keys or adds new ones
        r.last_updated_timestamp = timestamp()
    RETURN count(r) AS affected_count
    """
    params = {
        "sourceId": source_control_id,
        "targetId": target_control_id,
        "props": properties
    }

    try:
        with driver.session() as session:
            log.debug(f"Executing query to save mapping relationship: {params}")
            result = session.run(cypher_query, **params)
            summary = result.single()
            affected_count = summary["affected_count"] if summary else 0
            if affected_count == 1:
                log.info("Mapping relationship successfully created/updated.")
                return True
            else:
                log.warning(
                    f"MERGE for mapping relationship ({source_control_id}->{target_control_id}) "
                    f"returned count {affected_count}."
                )
                # Merge war erfolgreich, auch wenn ON MATCH nichts geändert hat.
                return True
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error saving mapping relationship: {e}", exc_info=True)
        return False
    except Exception as e:
        log.error(f"General error saving mapping relationship: {e}", exc_info=True)
        return False