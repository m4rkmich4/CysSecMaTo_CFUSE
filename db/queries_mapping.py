# File: db/queries_mapping.py
# Location: /Users/michaelmark/PycharmProjects/CySecMaTo/db/queries_mapping.py
# Combines 1-N and M-N logic in one file

import logging
from typing import Optional, List, Dict, Any
from .neo4j_connector import get_driver
from neo4j.exceptions import Neo4jError, ServiceUnavailable

log = logging.getLogger(__name__)


def get_embedding_vector_for_part(part_element_id: str) -> Optional[List[float]]:
    """
    Retrieves the stored embedding vector for a Part node using its elementId.
    """
    cypher = """
MATCH (p:Part)
WHERE elementId(p) = $pid
RETURN p.embedding_vector AS embedding
"""
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for get_embedding_vector_for_part.")
        return None
    try:
        with driver.session() as session:
            rec = session.run(cypher, pid=part_element_id).single()
            emb = rec["embedding"] if rec else None
            if isinstance(emb, list) and all(isinstance(x, (int, float)) for x in emb):
                log.info(f"Embedding (len={len(emb)}) found for Part elementId={part_element_id}.")
                return [float(x) for x in emb]
            log.warning(f"Invalid or missing embedding for Part elementId={part_element_id}.")
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error get_embedding_vector_for_part: {e}", exc_info=True)
    except Exception as e:
        log.error(f"General error get_embedding_vector_for_part: {e}", exc_info=True)
    return None


def calculate_similarities_for_display(
    locked_part_element_id: str,
    target_catalog_uuid: str,
    target_group_id: Optional[str] = None,
    display_threshold: float = 0.0
) -> List[Dict[str, Any]]:
    """
    1-N: Calculates cosine similarities between the locked Part and target Parts,
    returns only results with score >= display_threshold, but does not save anything.
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for calculate_similarities_for_display.")
        return []

    params: Dict[str, Any] = {
        "lockedPid": locked_part_element_id,
        "targetCid": target_catalog_uuid,
        "displayThreshold": display_threshold
    }
    if target_group_id:
        target_match = """
MATCH (g:Group {id:$targetGid, catalog_uuid:$targetCid})-[:HAS_CONTROL]->(top:Control)
MATCH (targetCtrl:Control)-[:IS_CHILD_OF*0..]->(top)
"""
        params["targetGid"] = target_group_id
    else:
        target_match = "MATCH (targetCtrl:Control {catalog_uuid:$targetCid})"

    cypher = f"""
// 1) Get source Part and vector
MATCH (sp:Part)
WHERE elementId(sp) = $lockedPid
WITH sp, sp.embedding_vector AS srcVec, sp.prose AS srcProse
WHERE srcVec IS NOT NULL

// 2) Target Controls (with or without group)
{target_match}

// 3) Target Parts
MATCH (targetCtrl)-[:HAS_PART]->(tp:Part {{name:'description'}})
WHERE tp.embedding_vector IS NOT NULL
AND elementId(tp) <> $lockedPid

// 4) Calculate score
WITH sp, srcVec, srcProse, targetCtrl, tp,
gds.similarity.cosine(srcVec, tp.embedding_vector) AS score
WHERE score >= $displayThreshold

// 5) Retrieve source Control
MATCH (sc:Control)-[:HAS_PART]->(sp)

// 6) Assemble result
RETURN
sc.id AS source_control_id,
srcProse AS source_control_prose,
targetCtrl.id AS target_control_id,
targetCtrl.title AS target_control_title,
tp.prose AS target_control_prose,
score AS similarity_score,
CASE
WHEN score >= 0.75 THEN 'high_similarity'
WHEN score >= 0.5 THEN 'medium_similarity'
WHEN score >= 0.3 THEN 'low_similarity'
ELSE 'very_low_similarity'
END AS similarity_category
ORDER BY similarity_score DESC
"""

    try:
        with driver.session() as session:
            records = [dict(rec) for rec in session.run(cypher, **params)]
            log.info(f"{len(records)} 1-N results calculated (>= {display_threshold}).")
            return records
    except (Neo4jError, ServiceUnavailable) as e:
        err = str(e)
        if "unknown function 'gds.similarity.cosine'" in err.lower():
            raise RuntimeError("GDS function 'gds.similarity.cosine' not found.") from e
        raise RuntimeError(f"Neo4j error 1-N: {e}") from e
    except Exception as e:
        raise RuntimeError(f"General error 1-N: {e}") from e


def bulk_merge_similarity_relations(results_to_save: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    1-N: Saves filtered similarities as HAS_SIMILARITY relationships.
    """
    if not results_to_save:
        return {"relationships_merged": 0}

    driver = get_driver()
    if not driver:
        err = "Neo4j driver not available for bulk_merge_similarity_relations."
        log.error(err)
        return {"error": err}

    cypher = """
UNWIND $results AS row
MATCH (sc:Control {id:row.source_control_id})
MATCH (tc:Control {id:row.target_control_id})
MERGE (sc)-[r:HAS_SIMILARITY]->(tc)
ON CREATE SET
r.similarity_score = row.similarity_score,
r.similarity_category = row.similarity_category,
r.model_name = row.model_name,
r.created_timestamp = timestamp(),
r.last_calculated_timestamp = timestamp()
ON MATCH SET
r.similarity_score = row.similarity_score,
r.similarity_category = row.similarity_category,
r.model_name = row.model_name,
r.last_calculated_timestamp = timestamp()
WITH count(r) AS relationships_affected
RETURN relationships_affected
"""
    try:
        with driver.session() as session:
            summary = session.run(cypher, results=results_to_save).single()
            cnt = summary["relationships_affected"] if summary else 0
            log.info(f"bulk_merge completed: {cnt} relationships.")
            return {"relationships_merged": cnt}
    except (Neo4jError, ServiceUnavailable) as e:
        raise RuntimeError(f"Neo4j error bulk_merge: {e}") from e
    except Exception as e:
        raise RuntimeError(f"General error bulk_merge: {e}") from e


def calculate_and_store_many_to_many_similarities(
    source_catalog_uuid: str,
    target_catalog_uuid: str,
    embedding_model_name: str,
    source_group_id: Optional[str] = None,
    target_group_id: Optional[str] = None,
    similarity_threshold: float = 0.3
) -> Dict[str, Any]:
    """
    M-N without GDS projection: Directly compares all description Parts and
    saves HAS_SIMILARITY relationships above the threshold.
    """
    driver = get_driver()
    if not driver:
        err = "Neo4j driver not available for M-N."
        log.error(err)
        return {"error": err, "relationships_written": 0}

    cypher = """
MATCH 
  (sc:Control {catalog_uuid:$srcCat})-[:HAS_PART]->(sp:Part {name:$partName}),
  (tc:Control {catalog_uuid:$tgtCat})-[:HAS_PART]->(tp:Part {name:$partName})
WHERE 
  sp.embedding_vector IS NOT NULL
  AND tp.embedding_vector IS NOT NULL
  AND elementId(tp) <> elementId(sp)
WITH 
  sc, 
  tc, 
  gds.similarity.cosine(sp.embedding_vector, tp.embedding_vector) AS score,
  timestamp() AS now
WHERE 
  score >= $threshold
MERGE (sc)-[r:HAS_SIMILARITY]->(tc)
ON CREATE SET 
  r.created_timestamp = now
SET 
  r.similarity_score            = score,
  r.similarity_category         = CASE 
                                     WHEN score >= 0.75 THEN 'high_similarity'  
                                     WHEN score >= 0.5  THEN 'medium_similarity' 
                                     WHEN score >= 0.3  THEN 'low_similarity'   
                                     ELSE 'low_similarity'    
                                  END,
  r.model_name                  = $model,
  r.last_calculated_timestamp   = now
RETURN 
  count(r) AS relationships_written;
"""
    params = {
        "srcCat": source_catalog_uuid,
        "tgtCat": target_catalog_uuid,
        "threshold": similarity_threshold,
        "model": embedding_model_name,
        "partName": "description"
    }

    try:
        with driver.session() as session:
            summary = session.run(cypher, **params).single()
            w = summary["relationships_written"] if summary else 0
            log.info(f"M-N saved: {w} relationships.")
            return {"error": None, "relationships_written": w}
    except (Neo4jError, ServiceUnavailable) as e:
        msg = f"Neo4j error M-N: {e}"
        log.error(msg, exc_info=True)
        return {"error": msg, "relationships_written": 0}
    except Exception as e:
        msg = f"General error M-N: {e}"
        log.error(msg, exc_info=True)
        return {"error": msg, "relationships_written": 0}


def get_top_n_many_to_many_similarity_results(
    source_catalog_uuid: str,
    target_catalog_uuid: str,
    source_group_id: Optional[str] = None,
    target_group_id: Optional[str] = None,
    limit: int = 10000
) -> List[Dict[str, Any]]:
    """
    Retrieves Top-N M-N results from HAS_SIMILARITY relationships.
    """
    driver = get_driver()
    if not driver:
        log.error("Neo4j driver not available for Top-N M-N.")
        return []

    cypher = """
MATCH (sc:Control {catalog_uuid:$srcCat})-[r:HAS_SIMILARITY]->(tc:Control {catalog_uuid:$tgtCat})
RETURN
sc.id AS source_control_id,
sc.title AS source_control_title,
tc.id AS target_control_id,
tc.title AS target_control_title,
r.similarity_score AS similarity_score,
r.similarity_category AS similarity_category,
r.model_name AS model_name
ORDER BY similarity_score DESC
LIMIT $limit
"""
    params = {"srcCat": source_catalog_uuid, "tgtCat": target_catalog_uuid, "limit": limit}

    try:
        with driver.session() as session:
            return [dict(rec) for rec in session.run(cypher, **params)]
    except (Neo4jError, ServiceUnavailable) as e:
        log.error(f"Neo4j error Top-N M-N: {e}", exc_info=True)
    except Exception as e:
        log.error(f"General error Top-N M-N: {e}", exc_info=True)
    return []