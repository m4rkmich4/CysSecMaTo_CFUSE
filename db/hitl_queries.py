# Filename: db/hitl_queries.py

import logging
from typing import List, Dict, Any, Optional
from .neo4j_connector import get_driver
from neo4j.exceptions import Neo4jError, ServiceUnavailable

log = logging.getLogger(__name__)

def get_mappings_for_validation(
    source_catalog_uuid: Optional[str] = None,
    target_catalog_uuid: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    Liefert bestehende :IS_MAPPED_TO-Kanten inkl. Control-Texte.
    Optional filterbar nach Source-/Target-Katalog und Status.
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_mappings_for_validation.")
        return []

    where = []
    params: Dict[str, Any] = {"limit": limit}
    if source_catalog_uuid:
        where.append("sc.catalog_uuid = $srcCat")
        params["srcCat"] = source_catalog_uuid
    if target_catalog_uuid:
        where.append("tc.catalog_uuid = $tgtCat")
        params["tgtCat"] = target_catalog_uuid
    if status_filter:
        where.append("r.status IN $statuses")
        params["statuses"] = status_filter

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    cypher = f"""
    MATCH (sc:Control)-[r:IS_MAPPED_TO]->(tc:Control)
    {where_clause}
    WITH sc, tc, r
    MATCH (sc)-[:HAS_PART]->(sp:Part {{name:'description'}})
    MATCH (tc)-[:HAS_PART]->(tp:Part {{name:'description'}})
    RETURN
      sc.id AS source_id,
      sc.title AS source_title,
      sp.prose AS source_prose,
      tc.id AS target_id,
      tc.title AS target_title,
      tp.prose AS target_prose,
      r.type AS type,
      r.explanation AS explanation,
      r.explanation_old AS explanation_old,
      r.similarity AS similarity,
      r.method AS method,
      r.status AS status,
      r.created_timestamp AS created_timestamp,
      r.last_updated_timestamp AS last_updated_timestamp
    ORDER BY r.last_updated_timestamp DESC, r.created_timestamp DESC
    LIMIT $limit
    """
    try:
        with driver.session() as session:
            return [dict(rec) for rec in session.run(cypher, **params)]
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error get_mappings_for_validation: {e}", exc_info=True)
        return []
    except Exception as e:
        log.error(f"General error get_mappings_for_validation: {e}", exc_info=True)
        return []


def get_mapping_detail(source_id: str, target_id: str) -> Optional[Dict[str, Any]]:
    """
    Holt eine spezifische Mapping-Kante + aktuelle Properties.
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_mapping_detail.")
        return None

    cypher = """
    MATCH (sc:Control {id:$src})-[r:IS_MAPPED_TO]->(tc:Control {id:$tgt})
    RETURN
      sc.id AS source_id,
      tc.id AS target_id,
      r.type AS type,
      r.explanation AS explanation,
      r.explanation_old AS explanation_old,
      r.similarity AS similarity,
      r.method AS method,
      r.status AS status,
      r.created_timestamp AS created_timestamp,
      r.last_updated_timestamp AS last_updated_timestamp
    """
    try:
        with driver.session() as session:
            rec = session.run(cypher, src=source_id, tgt=target_id).single()
            return dict(rec) if rec else None
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error get_mapping_detail: {e}", exc_info=True)
        return None
    except Exception as e:
        log.error(f"General error get_mapping_detail: {e}", exc_info=True)
        return None


def delete_mapping_relationship(source_id: str, target_id: str) -> bool:
    """
    Löscht eine :IS_MAPPED_TO-Kante.
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for delete_mapping_relationship.")
        return False

    cypher = """
    MATCH (sc:Control {id:$src})-[r:IS_MAPPED_TO]->(tc:Control {id:$tgt})
    DELETE r
    RETURN count(*) AS deleted
    """
    try:
        with driver.session() as session:
            rec = session.run(cypher, src=source_id, tgt=target_id).single()
            return (rec and rec["deleted"] == 1)
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error delete_mapping_relationship: {e}", exc_info=True)
        return False
    except Exception as e:
        log.error(f"General error delete_mapping_relationship: {e}", exc_info=True)
        return False