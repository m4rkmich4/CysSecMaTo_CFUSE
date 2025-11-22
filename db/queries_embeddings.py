# Filename: db/queries_embeddings.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/db/queries_embeddings.py
# FINAL VERSION with update_embedding_for_part AND bulk_update_embeddings_for_parts

import logging # Import logging
from typing import List, Dict, Any
from .neo4j_connector import get_driver
from neo4j.exceptions import Neo4jError, ServiceUnavailable # ServiceUnavailable added

log = logging.getLogger(__name__) # Logger for this module


# --- Retrieve catalog list ---
def get_all_catalogs() -> List[Dict[str, Any]]:
    """Returns all available catalogs with UUID and title."""
    driver = get_driver()
    if not driver: # Ensure the driver exists
        log.error("Neo4j driver not available for get_all_catalogs.")
        return []
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (c:Catalog)
                RETURN c.uuid AS uuid, c.title AS title
                ORDER BY c.title
            """)
            return [dict(record) for record in result]
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Error retrieving all catalogs: {e}", exc_info=True)
        return []


# --- Retrieve groups for a catalog ---
def get_groups_for_catalog(catalog_uuid: str) -> List[Dict[str, Any]]:
    """Returns all groups (id + title) for a catalog."""
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_groups_for_catalog.")
        return []
    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (g:Group {catalog_uuid: $uuid})
                RETURN g.id AS id, g.title AS title
                ORDER BY g.title
            """, uuid=catalog_uuid)
            return [dict(record) for record in result]
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Error retrieving groups for catalog {catalog_uuid}: {e}", exc_info=True)
        return []


# --- Controls with description parts ---
def get_controls_with_description_parts(
    catalog_uuid: str,
    group_id: str | None = None,
    show_all_controls: bool = False,
    only_without_group: bool = False,
    only_with_embedding: bool = False
) -> List[Dict[str, Any]]:
    """
    Returns all Controls with Part (name = 'description'), optionally
    filtered by group or group membership.
    (Docstring and function as last provided by you)
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_controls_with_description_parts.")
        return []

    query = ""
    params = {"cid": catalog_uuid}
    return_clause = """
        RETURN DISTINCT ctrl.id AS control_id,
               ctrl.title AS control_title,
               ctrl.`class` AS control_class,
               p.prose AS description,
               elementId(p) AS part_element_id,
               p.embedding_vector IS NOT NULL AS has_embedding,
               p.embedding_method AS embedding_method
        ORDER BY ctrl.id
    """
    try:
        with driver.session() as session:
            if show_all_controls:
                query = """
                    MATCH (ctrl:Control {catalog_uuid: $cid})
                    MATCH (ctrl)-[:HAS_PART]->(p:Part {name: 'description'})
                """ + return_clause
                # params remains {"cid": catalog_uuid}
            elif group_id:
                query = """
                    MATCH (g:Group {id: $gid, catalog_uuid: $cid})-[:HAS_CONTROL]->(topCtrl:Control)
                    MATCH (ctrl:Control)-[:IS_CHILD_OF*0..]->(topCtrl)
                    MATCH (ctrl)-[:HAS_PART]->(p:Part {name: 'description'})
                """ + return_clause
                params["gid"] = group_id
            elif only_without_group:
                 query = """
                    MATCH (cat:Catalog {uuid: $cid})-[:HAS_CONTROL]->(topCtrl:Control)
                    WHERE NOT (topCtrl)<-[:HAS_CONTROL]-(:Group {catalog_uuid: $cid})
                    MATCH (ctrl:Control)-[:IS_CHILD_OF*0..]->(topCtrl)
                    MATCH (ctrl)-[:HAS_PART]->(p:Part {name: 'description'})
                 """ + return_clause
                 # params remains {"cid": catalog_uuid}
            else: # Default case (often "<All (Default)>" in UI)
                query = """
                    MATCH (ctrl:Control {catalog_uuid: $cid})
                    MATCH (ctrl)-[:HAS_PART]->(p:Part {name: 'description'})
                """ + return_clause
                # params remains {"cid": catalog_uuid}

            result = session.run(query, **params)
            records = [dict(record) for record in result]
            if only_with_embedding:
                records = [r for r in records if r["has_embedding"]]
            return records
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Error retrieving controls for catalog {catalog_uuid}: {e}", exc_info=True)
        return []


# --- Write embedding (Single) ---cd docker
def update_embedding_for_part(part_element_id: str, embedding_vector: list[float], model_name: str) -> None:
    """
    Saves the embedding array and the model name for a single Part.
    (Function as last provided by you, with Runtime Error Propagation)
    """
    driver = get_driver()
    if not driver:
        raise ConnectionError("Neo4j driver not available for update_embedding_for_part.")
    try:
        with driver.session() as session:
            def write_tx(tx):
                tx.run("""
                    MATCH (p:Part) WHERE elementId(p) = $pid
                    SET p.embedding_vector = $vector,
                        p.embedding_method = $model
                """, pid=part_element_id, vector=embedding_vector, model=model_name)
            session.execute_write(write_tx)
            log.info(f"Embedding for Part elementId={part_element_id} saved successfully.")
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error saving embedding for Part elementId={part_element_id}: {e}", exc_info=True)
        raise RuntimeError(f"Database error saving embedding: {e}") from e
    except Exception as e:
        log.error(f"General error saving embedding for Part elementId={part_element_id}: {e}", exc_info=True)
        raise RuntimeError(f"General error saving embedding: {e}") from e


# +++ NEW FUNCTION FOR BULK EMBEDDING UPDATE +++
def bulk_update_embeddings_for_parts(embedding_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Saves a list of embedding data (vector and model name) for multiple
    Part nodes in a single transaction using UNWIND.

    :param embedding_data_list: A list of dictionaries. Each dict should contain:
                                'part_element_id': str,
                                'embedding_vector': List[float],
                                'model_name': str
    :return: A dictionary with the result, e.g., {'updated_parts_count': count}.
             Raises RuntimeError on errors.
    """
    if not embedding_data_list:
        log.info("bulk_update_embeddings_for_parts: No embedding data passed for saving.")
        return {"updated_parts_count": 0}

    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for bulk_update_embeddings_for_parts.")
        # Consistent with other error handling: raise Exception
        raise ConnectionError("Neo4j driver not available for bulk update.")

    log.info(f"Starting bulk save for {len(embedding_data_list)} embeddings...")

    cypher_query = """
    UNWIND $batch AS item
    MATCH (p:Part) WHERE elementId(p) = item.part_element_id
    SET p.embedding_vector = item.embedding_vector,
        p.embedding_method = item.model_name
    RETURN count(p) AS updated_count
    """
    params = {"batch": embedding_data_list}

    try:
        with driver.session() as session:
            log.debug(f"Executing bulk embedding update query for {len(embedding_data_list)} elements.")
            result = session.run(cypher_query, **params)
            summary = result.single()
            updated_count = summary["updated_count"] if summary and summary["updated_count"] is not None else 0

            log.info(f"Bulk embedding save completed. {updated_count} Parts updated.")
            return {"updated_parts_count": updated_count}
    except (Neo4jError, ServiceUnavailable) as e:
        msg = f"Neo4j error during bulk saving of embeddings: {e}"
        log.error(msg, exc_info=True)
        raise RuntimeError(msg) from e # Rethrow error
    except Exception as e:
        msg = f"General error during bulk saving of embeddings: {e}"
        log.error(msg, exc_info=True)
        raise RuntimeError(msg) from e # Rethrow error