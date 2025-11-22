# db/neo4j_importer.py
"""
This module contains functions for importing OSCAL catalog data
from a Python dictionary into a Neo4j database.
(Rest of the docstring unchanged)
"""

# --- Relative Imports and Type Imports ---
from .neo4j_connector import get_driver
from neo4j.exceptions import ServiceUnavailable, ResultError
from neo4j import Transaction # Needed for type hints
from typing import Dict, Any, Optional, Callable

# --- Existence Check Function ---
def check_catalog_exists(catalog_uuid: str) -> bool:
    """Checks if a catalog with the given UUID already exists in Neo4j."""
    # (Code unchanged)
    driver = get_driver()
    if not driver:
         raise ConnectionError("Neo4j driver is not available.")
    try:
        with driver.session() as session:
            result = session.run("MATCH (c:Catalog {uuid: $uuid}) RETURN count(c) > 0 AS exists", uuid=catalog_uuid)
            record = result.single()
            return record["exists"] if record else False
    except ServiceUnavailable as e:
        raise ConnectionError(f"Neo4j service not available: {e}") from e
    except ResultError:
         raise
    except Exception:
        raise

# --- Custom Import Functions with Callback ---

def import_catalog(catalog_dict: Dict[str, Any],
                   progress_callback: Optional[Callable[[str], None]] = None):
    """
    Imports a complete OSCAL catalog from a dictionary into Neo4j.
    (Docstring unchanged)
    """
    catalog_data = catalog_dict.get("catalog")
    if not catalog_data:
        raise ValueError("No valid 'catalog' block found in the dictionary.")

    def report_progress(message: str):
        if progress_callback:
            try: progress_callback(message)
            except Exception as cb_err: print(f"WARNING: Error in progress callback: {cb_err}")

    driver = get_driver()
    catalog_uuid = "unknown" # Default for error reporting if UUID is not found early
    try:
        with driver.session() as session:
            # Use explicit transaction for all operations of this catalog
            with session.begin_transaction() as tx:
                catalog_uuid = catalog_data.get("uuid")
                if not catalog_uuid: raise ValueError("Catalog must have a 'uuid'.")
                catalog_title = catalog_data.get("metadata", {}).get("title", "N/A")
                report_progress(f"Starting import for catalog: '{catalog_title}' (UUID: {catalog_uuid})")

                # 1. Catalog Node
                report_progress(f"  Processing catalog node...")
                tx.run("""MERGE (c:Catalog {uuid: $uuid}) ON CREATE SET c.title = $title, 
                                 c.import_timestamp = timestamp() ON MATCH SET c.title = $title, c.update_timestamp = timestamp()""",

                       uuid=catalog_uuid, title=catalog_title)

                # --- Metadata ---
                metadata = catalog_data.get("metadata", {})
                metadata_id = f"{catalog_uuid}-metadata"
                report_progress(f"  Processing metadata...")

                # 2. Metadata Node (unchanged)
                tx.run("""MERGE (m:Metadata {id: $id}) SET m.title = $title, m.published = $published, m.last_modified = $last_modified, m.version = $version, m.oscal_version = $oscal_version""",
                     id=metadata_id, title=metadata.get("title", "N/A"), published=metadata.get("published"), last_modified=metadata.get("last-modified"), version=metadata.get("version"), oscal_version=metadata.get("oscal-version"))
                tx.run("MATCH (c:Catalog {uuid: $catalog_uuid}), (m:Metadata {id: $metadata_id}) MERGE (c)-[:HAS_METADATA]->(m)",
                       catalog_uuid=catalog_uuid, metadata_id=metadata_id)

                # 3. Meta Links (unchanged)
                report_progress(f"    Processing Metadata Links...")
                for i, link in enumerate(metadata.get("links", [])):
                    link_id = f"{metadata_id}-link-{i}"
                    tx.run("MERGE (l:Link {id: $id}) SET l.href = $href, l.rel = $rel",
                           id=link_id, href=link.get("href"), rel=link.get("rel"))
                    tx.run("MATCH (m:Metadata {id: $mid}), (l:Link {id: $lid}) MERGE (m)-[:HAS_LINK]->(l)",
                           mid=metadata_id, lid=link_id)

                # 4. Parties (unchanged)
                report_progress(f"    Processing Parties...")
                for party in metadata.get("parties", []):
                    party_uuid = party.get("uuid")
                    if not party_uuid:
                        report_progress(f"    WARNING: Party without UUID skipped.")
                        continue
                    tx.run("MERGE (p:Party {uuid: $uuid}) SET p.name = $name, p.type = $type",
                           uuid=str(party_uuid), name=party.get("name"), type=party.get("type"))

                # 5. Roles <<< CHANGE HERE >>>
                report_progress(f"    Processing Role Definitions...")
                for role in metadata.get("roles", []):
                    role_id = role.get("id")
                    if not role_id:
                        report_progress(f"    WARNING: Role without ID skipped.")
                        continue
                    # <<< CHANGED: MERGE with id AND catalog_uuid >>>
                    tx.run("""
                        MERGE (r:Role {id: $id, catalog_uuid: $catalog_uuid})
                        ON CREATE SET
                            r.title = $title,
                            r.description = $description
                        ON MATCH SET  // Optional: Update if necessary
                            r.title = $title,
                            r.description = $description
                    """,
                         id=role_id,
                         catalog_uuid=catalog_uuid, # Important: Pass Catalog UUID
                         title=role.get("title"),
                         description=role.get("description"))
                    # <<< END CHANGE >>>

                # 6. Responsible Parties <<< CHANGE HERE >>>
                report_progress(f"    Processing Responsible Parties...")
                for i, rp in enumerate(metadata.get("responsible-parties", [])):
                    role_id = rp.get("role-id")
                    party_uuids_raw = rp.get("party-uuids", [])
                    if not role_id:
                        report_progress(f"    WARNING: RP without role-id skipped.")
                        continue
                    party_uuid_strings = [str(p_uuid) for p_uuid in party_uuids_raw if p_uuid]
                    if not party_uuid_strings:
                        report_progress(f"    WARNING: RP for role '{role_id}' without party-uuids skipped.")
                        continue
                    # Create ResponsibleParty Node (unchanged)
                    rp_node_id = f"{metadata_id}-resp-{role_id}-{i}"
                    tx.run("""MERGE (rp_node:ResponsibleParty {id: $id}) SET rp_node.role_id = $rid, rp_node.party_uuids = $pids""",
                           id=rp_node_id, rid=role_id, pids=party_uuid_strings)
                    # Link Metadata -> ResponsibleParty (unchanged)
                    tx.run("MATCH (m:Metadata {id: $mid}), (rp_node:ResponsibleParty {id: $rpid}) MERGE (m)-[:HAS_RESPONSIBLE_PARTY]->(rp_node)",
                           mid=metadata_id, rpid=rp_node_id)

                    # <<< CHANGED: Find the correct role with catalog_uuid when linking >>>
                    tx.run("""
                        MATCH (role:Role {id: $rid, catalog_uuid: $catalog_uuid})
                        MATCH (rp_node:ResponsibleParty {id: $rpid})
                        MERGE (role)-[:ASSIGNED_TO]->(rp_node)
                    """,
                           rid=role_id,
                           catalog_uuid=catalog_uuid, # Important: Pass Catalog UUID
                           rpid=rp_node_id)
                    # <<< END CHANGE >>>

                    # Link Party -> ResponsibleParty (unchanged)
                    for party_uuid_str in party_uuid_strings:
                         tx.run("MATCH (p:Party {uuid: $pid}), (rp_node:ResponsibleParty {id: $rpid}) MERGE (p)-[:ASSIGNED_TO]->(rp_node)",
                                pid=party_uuid_str, rpid=rp_node_id)

                # 7. Properties (Metadata) (unchanged)
                report_progress(f"    Processing Metadata Properties...")
                for i, prop in enumerate(metadata.get("props", [])):
                    label = prop.get("name")
                    value = prop.get("value")
                    if not label or value is None:
                        report_progress(f"    WARNING: Metadata Property without name/value skipped.")
                        continue
                    tx.run("""MATCH (m:Metadata {id: $mid}) CREATE (p:Property {label: $label, value: $value, namespace: $ns, `class`: $prop_class}) MERGE (m)-[:HAS_PROPERTY]->(p)""",
                           mid=metadata_id, label=label, value=value, ns=prop.get("ns"), prop_class=prop.get("class"))

                # --- Main Content ---
                # 8. Import Groups Recursively (unchanged)
                report_progress(f"  Processing Groups...")
                for group in catalog_data.get("groups", []):
                    import_group(tx, group, catalog_uuid, progress_callback)

                # 9. Import Top-Level Controls (unchanged)
                report_progress(f"  Processing Top-Level Controls...")
                for control in catalog_data.get("controls", []):
                    import_control(tx, control, catalog_uuid, progress_callback=progress_callback)

                # 10. Backmatter (unchanged)
                backmatter = catalog_data.get("back-matter")
                if backmatter:
                    report_progress(f"  Processing Backmatter...")
                    back_id = f"{catalog_uuid}-backmatter"
                    tx.run("MERGE (b:Backmatter {id: $id})", id=back_id)
                    tx.run("MATCH (c:Catalog {uuid: $cid}), (b:Backmatter {id: $bid}) MERGE (c)-[:HAS_BACKMATTER]->(b)",
                           cid=catalog_uuid, bid=back_id)

                # Commit at the end of the transaction for this catalog
                tx.commit()
                report_progress(f"Import for catalog '{catalog_title}' completed.")

    except (ServiceUnavailable, ResultError, ConnectionError) as db_err:
         report_progress(f"❌ Database error during import of catalog {catalog_uuid}: {db_err}")
         # Rethrow error so the calling code notices it
         raise
    except ValueError as val_err: # Catches ValueErrors from the code
        report_progress(f"❌ Invalid data during import of catalog {catalog_uuid}: {val_err}")
        raise
    except Exception as e:
        report_progress(f"❌ Unexpected error during import of catalog {catalog_uuid}: {e}")
        # Throw broader error or more specific one, if desired
        raise ValueError(f"Import failed: {e}") from e


# *******************************************************************
# *** import_group Function (unchanged) ***
# *******************************************************************
def import_group(tx: Transaction, group: Dict[str, Any], catalog_uuid: str,
                 progress_callback: Optional[Callable[[str], None]] = None):
    """
    Imports an OSCAL group specifically for its catalog into Neo4j.
    (Code unchanged)
    """
    group_id = group.get("id")
    if not group_id:
        if progress_callback: progress_callback(f"    WARNING: Group without ID skipped.")
        return
    def report_progress(message: str):
        if progress_callback:
             try: progress_callback(message)
             except Exception as cb_err: print(f"WARNING: Callback error: {cb_err}")
    group_title_for_log = group.get('title', '')
    report_progress(f"    Processing group: {group_id} ('{group_title_for_log}' for catalog {catalog_uuid[:8]}...).")
    tx.run("""
        MERGE (g:Group {id: $id, catalog_uuid: $catalog_uuid})
        ON CREATE SET g.title = $title, g.`class` = $group_class, g.import_timestamp = timestamp()
        ON MATCH SET g.title = $title, g.`class` = $group_class, g.update_timestamp = timestamp()
    """, id=group_id, catalog_uuid=catalog_uuid, title=group.get("title"), group_class=group.get("class"))
    tx.run("""
        MATCH (c:Catalog {uuid: $catalog_uuid}), (g:Group {id: $group_id, catalog_uuid: $catalog_uuid})
        MERGE (c)-[:HAS_GROUP]->(g)
    """, catalog_uuid=catalog_uuid, group_id=group_id)
    for i, prop in enumerate(group.get("props", [])):
        label = prop.get("name"); value = prop.get("value")
        if not label or value is None:
             report_progress(f"      WARNING: Property without name/value in group {group_id} skipped.")
             continue
        tx.run("""
             MATCH (g:Group {id: $gid, catalog_uuid: $catalog_uuid})
             CREATE (p:Property {label: $label, value: $value, namespace: $ns, `class`: $prop_class})
             MERGE (g)-[:HAS_PROPERTY]->(p)
         """, gid=group_id, catalog_uuid=catalog_uuid, label=label, value=value, ns=prop.get("ns"), prop_class=prop.get("class"))
    for control in group.get("controls", []):
        import_control(tx, control, catalog_uuid, group_id=group_id, progress_callback=progress_callback)


# --- Function import_control (unchanged) ---
def import_control(tx: Transaction, control: Dict[str, Any], catalog_uuid: str,
                   group_id: Optional[str] = None, parent_control_id: Optional[str] = None,
                   progress_callback: Optional[Callable[[str], None]] = None):
    """
    Imports an OSCAL control and its content into Neo4j.
    (Code unchanged)
    """
    control_id = control.get("id")
    if not control_id:
        if progress_callback: progress_callback(f"      WARNING: Control without ID skipped.")
        return
    def report_progress(message: str):
        if progress_callback:
             try: progress_callback(message)
             except Exception as cb_err: print(f"WARNING: Callback error: {cb_err}")
    parent_ref = group_id or parent_control_id or "Catalog" # Translated "Katalog"
    indent = "      " if group_id or parent_control_id else "  "
    report_progress(f"{indent}Processing Control: {control_id} ('{control.get('title', '')}' under {parent_ref})...")
    tx.run("""
        MERGE (c:Control {id: $id})
        SET c.title = $title, c.`class` = $control_class, c.catalog_uuid = $catalog_uuid
    """, id=control_id, title=control.get("title"), control_class=control.get("class"), catalog_uuid=catalog_uuid)
    if group_id:
        tx.run("MATCH (g:Group {id: $gid, catalog_uuid: $catalog_uuid}), (c:Control {id: $cid}) MERGE (g)-[:HAS_CONTROL]->(c)",
               gid=group_id, catalog_uuid=catalog_uuid, cid=control_id)
    elif parent_control_id:
        tx.run("MATCH (p:Control {id: $pid}), (c:Control {id: $cid}) MERGE (c)-[:IS_CHILD_OF]->(p)",
               pid=parent_control_id, cid=control_id)
    else:
        tx.run("MATCH (cat:Catalog {uuid: $catid}), (c:Control {id: $cid}) MERGE (cat)-[:HAS_CONTROL]->(c)",
               catid=catalog_uuid, cid=control_id)
    for i, prop in enumerate(control.get("props", [])):
        label = prop.get("name"); value = prop.get("value")
        if not label or value is None: report_progress(f"{indent}  WARNING: Property without name/value in Control {control_id} skipped."); continue
        tx.run("""
             MATCH (c:Control {id: $cid})
             CREATE (p:Property {label: $label, value: $value, namespace: $ns, `class`: $prop_class})
             MERGE (c)-[:HAS_PROPERTY]->(p)
         """, cid=control_id, label=label, value=value, ns=prop.get("ns"), prop_class=prop.get("class"))
    for i, part in enumerate(control.get("parts", [])):
        part_name = part.get("name"); report_progress(f"{indent}  Processing Part: {part_name}...")
        part_params = {"name": part_name, "namespace": part.get("ns"), "title": part.get("title"), "prose": part.get("prose"), "control_id": control_id}
        part_params = {k: v for k, v in part_params.items() if v is not None}; set_clauses = [f"p.{key} = ${key}" for key in part_params.keys()]
        if not set_clauses: cypher_part_create = "MATCH (c:Control {id: $cid}) CREATE (p:Part) MERGE (c)-[:HAS_PART]->(p) RETURN elementId(p) AS part_element_id"
        else: cypher_part_create = f"MATCH (c:Control {{id: $cid}}) CREATE (p:Part) SET {', '.join(set_clauses)} MERGE (c)-[:HAS_PART]->(p) RETURN elementId(p) AS part_element_id"
        final_params = part_params.copy(); final_params["cid"] = control_id
        result = tx.run(cypher_part_create, parameters=final_params) # type: ignore
        record = result.single()
        if record:
            part_element_id = record["part_element_id"]
            for j, prop in enumerate(part.get("props", [])):
                label = prop.get("name"); value = prop.get("value")
                if not label or value is None: report_progress(f"{indent}    WARNING: Property without name/value in Part {part_name} skipped."); continue
                tx.run("""
                     MATCH (part_node) WHERE elementId(part_node) = $part_element_id
                     CREATE (p_prop:Property {label: $label, value: $value, namespace: $ns, `class`: $prop_class})
                     MERGE (part_node)-[:HAS_PROPERTY]->(p_prop)
                 """, part_element_id=part_element_id, label=label, value=value, ns=prop.get("ns"), prop_class=prop.get("class"))
        else: report_progress(f"{indent}    ERROR: Could not retrieve elementId for newly created Part '{part_name}'.")
    for sub_control in control.get("controls", []):
        import_control(tx, sub_control, catalog_uuid, parent_control_id=control_id, progress_callback=progress_callback)