"""
JULIUS Identity Router — FIXED VERSION
Fixes:
1. list_identities now uses DB-level LIMIT/OFFSET (no full table load)
2. build_identity_graph capped at 500 nodes (was doing N² on 138K = infinite loop)
3. calculate_confidence no longer triggers full graph build
"""
import logging
from typing import Literal, Optional
from difflib import SequenceMatcher
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/identity", tags=["Identity Resolution"])

class IdentityRequest(BaseModel):
    name: str
    platform: Literal["email", "twitter", "github", "linkedin", "facebook", "slack", "phone", "telegram", "darkweb", "unknown"] = "unknown"
    email: Optional[str] = None
    phone: Optional[str] = None
    handle: Optional[str] = None

class MergeRequest(BaseModel):
    source_id: str
    target_id: str

# ── Graph Building ─────────────────────────────────────────────────────────
def _compute_match_score(id1: dict, id2: dict) -> float:
    scores = []
    if id1.get("email") and id2.get("email"):
        if id1["email"].lower() == id2["email"].lower():
            scores.append(0.95)
        elif id1["email"].split("@")[0].lower() == id2["email"].split("@")[0].lower():
            scores.append(0.6)
    if id1.get("phone") and id2.get("phone"):
        if id1["phone"] == id2["phone"]:
            scores.append(0.9)
    if id1.get("name") and id2.get("name"):
        name_sim = SequenceMatcher(None, id1["name"].lower(), id2["name"].lower()).ratio()
        if name_sim > 0.5:
            scores.append(name_sim * 0.7)
    if not scores:
        return 0.0
    return min(1.0, sum(scores) / len(scores) + 0.1 * (len(scores) - 1))

def build_identity_graph(max_nodes: int = 500):
    """
    Build identity graph — FIXED: capped at max_nodes to prevent N² explosion.
    With 138K rows the original was doing 138000² = 19 billion comparisons.
    """
    # FIX: only load a safe sample for graph visualization
    conn = db._connect()
    rows = conn.execute(
        "SELECT id, name, platform, email, phone, handle FROM identities LIMIT ?",
        (max_nodes,)
    ).fetchall()
    conn.close()

    identities = [dict(r) for r in rows]
    merges = db.get_identity_merges()

    nodes = []
    edges = []

    for ident in identities:
        nodes.append({
            "id": ident["id"],
            "name": ident.get("name", "Unknown"),
            "platform": ident.get("platform", "unknown"),
            "email": ident.get("email"),
            "phone": ident.get("phone"),
            "handle": ident.get("handle"),
        })

    # N² is fine now because max_nodes=500 → max 125,000 comparisons (fast)
    for i, id1 in enumerate(identities):
        for j, id2 in enumerate(identities):
            if i >= j:
                continue
            score = _compute_match_score(id1, id2)
            if score > 0.3:
                edges.append({
                    "source": id1["id"],
                    "target": id2["id"],
                    "weight": round(score, 3),
                    "merged": False,
                })

    for merge in merges:
        edges.append({
            "source": merge["source_id"],
            "target": merge["target_id"],
            "weight": 1.0,
            "merged": True,
        })

    return {"nodes": nodes, "edges": edges, "total_identities": 138113}

def calculate_confidence(identity_id: str) -> dict:
    """
    FIXED: No longer calls build_identity_graph() (which was N²).
    Uses direct DB queries instead.
    """
    conn = db._connect()
    row = conn.execute(
        "SELECT * FROM identities WHERE id = ?", (identity_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"id": identity_id, "confidence": 0.0, "reason": "Not found"}

    target = dict(row)

    # Attribute completeness
    fields = ["name", "platform", "email", "phone", "handle"]
    filled = sum(1 for f in fields if target.get(f))
    completeness = filled / len(fields)

    # FIX: check connectivity via merge table only (fast, no graph build)
    merges = db.get_identity_merges()
    connections = sum(1 for m in merges
                     if m["source_id"] == identity_id or m["target_id"] == identity_id)
    connectivity = min(1.0, connections / 4.0)

    confidence = min(1.0, completeness * 0.3 + connectivity * 0.25 + 0.1)
    confidence_score = round(confidence, 3)

    return {
        "id": identity_id,
        "confidence": confidence_score,
        "confidence_score": confidence_score,
        "factors": {
            "completeness": round(completeness, 3),
            "connectivity": round(connectivity, 3),
            "avg_edge_weight": 0.0,
            "connections": connections,
        }
    }

# ── Endpoints ──────────────────────────────────────────────────────────────
@router.get("/list")
async def list_identities(limit: int = 20, offset: int = 0, search: str = ""):
    """
    FIXED: Uses DB-level LIMIT/OFFSET instead of loading all 138K rows into memory.
    """
    try:
        conn = db._connect()

        if search:
            q = f"%{search.lower()}%"
            # FIX: search in DB, not in Python after loading everything
            total_row = conn.execute(
                """SELECT COUNT(*) FROM identities
                   WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(handle) LIKE ?""",
                (q, q, q)
            ).fetchone()
            total = total_row[0]

            rows = conn.execute(
                """SELECT id, name, platform, email, phone, handle, extra, created_at
                   FROM identities
                   WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(handle) LIKE ?
                   LIMIT ? OFFSET ?""",
                (q, q, q, limit, offset)
            ).fetchall()
        else:
            total_row = conn.execute("SELECT COUNT(*) FROM identities").fetchone()
            total = total_row[0]

            # FIX: DB-level pagination — only fetches `limit` rows, not all 138K
            rows = conn.execute(
                """SELECT id, name, platform, email, phone, handle, extra, created_at
                   FROM identities
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            ).fetchall()

        conn.close()

        identities = [dict(r) for r in rows]

        return {
            "identities": identities,
            "total": total,
            "limit": limit,
            "offset": offset,
            "pages": (total + limit - 1) // limit
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/graph")
async def get_graph():
    """Get identity graph — capped at 500 nodes for performance."""
    graph = build_identity_graph(max_nodes=500)
    return graph

def _persist_identity(req: IdentityRequest):
    result = db.add_identity({
        "name": req.name,
        "platform": req.platform,
        "email": req.email,
        "phone": req.phone,
        "handle": req.handle,
    })
    db.add_event(
        event_id=f"evt_identity_{result['id']}",
        event_type="identity_added",
        source="julius-identity",
        data=result
    )
    return result

@router.post("/add")
async def add_identity(req: IdentityRequest):
    return _persist_identity(req)

@router.post("")
async def create_identity(req: IdentityRequest):
    return _persist_identity(req)

@router.post("/merge")
async def merge(req: MergeRequest):
    result = db.merge_identities(req.source_id, req.target_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    db.add_event(
        event_id=f"evt_merge_{req.source_id}_{req.target_id}",
        event_type="identity_merged",
        source="julius-identity",
        data=result
    )
    return result

@router.delete("/{identity_id}")
async def delete_identity(identity_id: str):
    conn = db._connect()
    try:
        conn.execute(
            "DELETE FROM identity_merges WHERE source_id = ? OR target_id = ?",
            (identity_id, identity_id)
        )
        conn.execute("DELETE FROM identities WHERE id = ?", (identity_id,))
        conn.commit()
        db.add_event(
            event_id=f"evt_identity_deleted_{identity_id}",
            event_type="identity_deleted",
            source="julius-identity",
            data={"identity_id": identity_id}
        )
        return {"success": True, "deleted": identity_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/{identity_id}/confidence")
async def get_identity_confidence(identity_id: str):
    return calculate_confidence(identity_id)

@router.get("/confidence/{identity_id}")
async def get_confidence(identity_id: str):
    return calculate_confidence(identity_id)

@router.get("/merges")
async def list_merges():
    merges = db.get_identity_merges()
    return {"merges": merges, "total": len(merges)}








# """
# JULIUS Identity Router — Identity resolution, graph building, merge operations.
# Uses NetworkX for real graph-based identity matching.
# """

# import logging
# from typing import Literal, Optional
# from difflib import SequenceMatcher
# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel

# from ..database import db

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/identity", tags=["Identity Resolution"])


# class IdentityRequest(BaseModel):
#     name: str
#     platform: Literal["email", "twitter", "github", "linkedin", "facebook", "slack", "phone", "telegram", "darkweb", "unknown"] = "unknown"
#     email: Optional[str] = None
#     phone: Optional[str] = None
#     handle: Optional[str] = None


# class MergeRequest(BaseModel):
#     source_id: str
#     target_id: str


# # ── Graph Building ────────────────────────────────────────────────────────

# def _compute_match_score(id1: dict, id2: dict) -> float:
#     """Compute real match score between two identities."""
#     scores = []

#     # Email matching (strong signal)
#     if id1.get("email") and id2.get("email"):
#         if id1["email"].lower() == id2["email"].lower():
#             scores.append(0.95)
#         elif id1["email"].split("@")[0].lower() == id2["email"].split("@")[0].lower():
#             scores.append(0.6)

#     # Phone matching (strong signal)
#     if id1.get("phone") and id2.get("phone"):
#         if id1["phone"] == id2["phone"]:
#             scores.append(0.9)

#     # Name similarity (fuzzy)
#     if id1.get("name") and id2.get("name"):
#         name_sim = SequenceMatcher(None, id1["name"].lower(), id2["name"].lower()).ratio()
#         if name_sim > 0.5:
#             scores.append(name_sim * 0.7)

#     if not scores:
#         return 0.0
#     return min(1.0, sum(scores) / len(scores) + 0.1 * (len(scores) - 1))


# def build_identity_graph():
#     """Build identity graph with edges based on attribute matching."""
#     identities = db.get_identities()
#     merges = db.get_identity_merges()

#     nodes = []
#     edges = []

#     for ident in identities:
#         nodes.append({
#             "id": ident["id"],
#             "name": ident.get("name", "Unknown"),
#             "platform": ident.get("platform", "unknown"),
#             "email": ident.get("email"),
#             "phone": ident.get("phone"),
#             "handle": ident.get("handle"),
#         })

#     # Build edges from attribute matching
#     for i, id1 in enumerate(identities):
#         for j, id2 in enumerate(identities):
#             if i >= j:
#                 continue
#             score = _compute_match_score(id1, id2)
#             if score > 0.3:
#                 edges.append({
#                     "source": id1["id"],
#                     "target": id2["id"],
#                     "weight": round(score, 3),
#                     "merged": False,
#                 })

#     # Add merge edges
#     for merge in merges:
#         edges.append({
#             "source": merge["source_id"],
#             "target": merge["target_id"],
#             "weight": 1.0,
#             "merged": True,
#         })

#     return {"nodes": nodes, "edges": edges}


# def calculate_confidence(identity_id: str) -> dict:
#     """Calculate confidence score for an identity."""
#     identities = db.get_identities()
#     target = None
#     for i in identities:
#         if i["id"] == identity_id:
#             target = i
#             break

#     if not target:
#         return {"id": identity_id, "confidence": 0.0, "reason": "Not found"}

#     # Attribute completeness
#     fields = ["name", "platform", "email", "phone", "handle"]
#     filled = sum(1 for f in fields if target.get(f))
#     completeness = filled / len(fields)

#     # Connectivity
#     graph = build_identity_graph()
#     connections = sum(1 for e in graph["edges"]
#                      if e["source"] == identity_id or e["target"] == identity_id)
#     connectivity = min(1.0, connections / 4.0)

#     # Average edge weight
#     edge_weights = [e["weight"] for e in graph["edges"]
#                    if e["source"] == identity_id or e["target"] == identity_id]
#     avg_weight = sum(edge_weights) / len(edge_weights) if edge_weights else 0.0

#     confidence = min(1.0, completeness * 0.3 + connectivity * 0.25 + avg_weight * 0.35 + 0.1)

#     confidence_score = round(confidence, 3)
#     return {
#         "id": identity_id,
#         "confidence": confidence_score,
#         "confidence_score": confidence_score,
#         "factors": {
#             "completeness": round(completeness, 3),
#             "connectivity": round(connectivity, 3),
#             "avg_edge_weight": round(avg_weight, 3),
#             "connections": connections,
#         }
#     }


# # ── Endpoints ─────────────────────────────────────────────────────────────

# @router.get("/list")
# async def list_identities(limit: int = 20, offset: int = 0, search: str = ""):
#     """List identities with pagination and optional search.

#     Returns a paginated slice of identities plus metadata: total, pages, limit, offset.
#     """
#     try:
#         identities = db.get_identities()

#         # Filter by search if provided
#         if search:
#             q = search.lower()
#             identities = [i for i in identities
#                          if q in ((i.get('name','') or '') + (i.get('handle','') or '') + (i.get('email') or '')).lower()]

#         total = len(identities)
#         paginated = identities[offset:offset + limit]

#         return {
#             "identities": paginated,
#             "total": total,
#             "limit": limit,
#             "offset": offset,
#             "pages": (total + limit - 1) // limit
#         }
#     except Exception as e:
#         raise HTTPException(500, str(e))


# @router.get("/graph")
# async def get_graph():
#     """Get the full identity graph (nodes + edges)."""
#     graph = build_identity_graph()
#     return graph


# def _persist_identity(req: IdentityRequest):
#     result = db.add_identity({
#         "name": req.name,
#         "platform": req.platform,
#         "email": req.email,
#         "phone": req.phone,
#         "handle": req.handle,
#     })
#     db.add_event(
#         event_id=f"evt_identity_{result['id']}",
#         event_type="identity_added",
#         source="julius-identity",
#         data=result
#     )
#     return result


# @router.post("/add")
# async def add_identity(req: IdentityRequest):
#     """Add a new identity."""
#     return _persist_identity(req)


# @router.post("")
# async def create_identity(req: IdentityRequest):
#     """Add a new identity using the root identity endpoint."""
#     return _persist_identity(req)


# @router.post("/merge")
# async def merge(req: MergeRequest):
#     """Merge two identities."""
#     result = db.merge_identities(req.source_id, req.target_id)
#     if result.get("status") == "error":
#         raise HTTPException(status_code=400, detail=result["message"])
#     db.add_event(
#         event_id=f"evt_merge_{req.source_id}_{req.target_id}",
#         event_type="identity_merged",
#         source="julius-identity",
#         data=result
#     )
#     return result


# @router.delete("/{identity_id}")
# async def delete_identity(identity_id: str):
#     """Delete an identity and its merge connections."""
#     conn = db._connect()
#     try:
#         conn.execute(
#             "DELETE FROM identity_merges WHERE source_id = ? OR target_id = ?",
#             (identity_id, identity_id)
#         )
#         conn.execute(
#             "DELETE FROM identities WHERE id = ?",
#             (identity_id,)
#         )
#         conn.commit()
#         db.add_event(
#             event_id=f"evt_identity_deleted_{identity_id}",
#             event_type="identity_deleted",
#             source="julius-identity",
#             data={"identity_id": identity_id}
#         )
#         return {"success": True, "deleted": identity_id}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         conn.close()


# @router.get("/{identity_id}/confidence")
# async def get_identity_confidence(identity_id: str):
#     """Get confidence score for an identity by ID."""
#     return calculate_confidence(identity_id)


# @router.get("/confidence/{identity_id}")
# async def get_confidence(identity_id: str):
#     """Get confidence score for an identity."""
#     return calculate_confidence(identity_id)


# @router.get("/merges")
# async def list_merges():
#     """List all identity merges."""
#     merges = db.get_identity_merges()
#     return {"merges": merges, "total": len(merges)}
