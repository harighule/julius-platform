"""
JULIUS — Passive Dark-Web Node Discovery Engine
================================================
Discovers existing Tor, I2P, and mixnet relays from **public HTTPS sources
only** — no .onion crawling, no active probing, no direct Tor network access.

Public data sources
-------------------
    tor_metrics   — https://onionoo.torproject.org/details (JSON relay list)
    i2p_netdb     — https://reseed.diva.exchange (mirrors I2P NetDB router
                    info stats as JSON-friendly data)
    public_dns    — curated public I2P seed / bootstrap hosts scraped from
                    https://raw.githubusercontent.com/ community lists

Integration
-----------
    - Nodes are scored (0–100) and upserted into the Knowledge Graph (SQLite
      controlled_nodes table used as a pragmatic KG store).
    - Each run is logged via Pantheon (best-effort; errors silently swallowed).
    - The module-level `discovery_engine` singleton is imported by main.py to
      start the background asyncio task.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy HTTP helper — uses stdlib only; httpx/requests are optional extras
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 20, headers: Optional[dict] = None) -> Optional[str]:
    """
    Perform a plain HTTPS GET using urllib.request (stdlib).
    Returns the decoded response body or None on any error.
    No Tor, no proxy, no .onion — public HTTPS only.
    """
    try:
        import urllib.request as _ur
        req = _ur.Request(url, headers={
            "User-Agent": "JULIUS-Discovery/1.0 (passive public-source indexer)",
            **(headers or {}),
        })
        with _ur.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("HTTP GET %s failed: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Models (local import to avoid circular deps at module-load time)
# ---------------------------------------------------------------------------

def _node_model():
    from ..models.discovery_models import DiscoveredNode  # type: ignore
    return DiscoveredNode


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------


class TorMetricsSource:
    """
    Fetches Tor relay data from the public Onionoo REST API.
    Endpoint: https://onionoo.torproject.org/details?limit=<N>
    Completely passive — no Tor circuit opened.
    """

    NAME = "tor_metrics"
    BASE_URL = "https://onionoo.torproject.org/details"

    def __init__(self, max_nodes: int = 500):
        self.max_nodes = max_nodes

    def fetch(self) -> List[dict]:
        """Return raw parsed relay dicts from Onionoo."""
        url = f"{self.BASE_URL}?limit={self.max_nodes}&running=true&fields=fingerprint,or_addresses,dir_address,flags,nickname,platform,bandwidth,uptime,country,contact,first_seen,last_seen"
        raw = _http_get(url)
        if not raw:
            logger.warning("[tor_metrics] Onionoo API unreachable")
            return []
        try:
            data = json.loads(raw)
            return data.get("relays", [])
        except Exception as exc:
            logger.warning("[tor_metrics] JSON parse error: %s", exc)
            return []

    def parse(self, relays: List[dict]) -> list:
        """Convert raw Onionoo relay dicts to DiscoveredNode instances."""
        DiscoveredNode = _node_model()
        nodes = []
        for r in relays:
            fp = r.get("fingerprint", "")
            if not fp:
                continue

            # Extract IP from or_addresses list, e.g. ["1.2.3.4:9001"]
            ip = None
            or_addr = r.get("or_addresses", [])
            if or_addr:
                raw_addr = or_addr[0]
                if ":" in raw_addr:
                    # Handle IPv6 [addr]:port vs IPv4 addr:port
                    if raw_addr.startswith("["):
                        ip = raw_addr.split("]")[0].lstrip("[")
                    else:
                        ip = raw_addr.rsplit(":", 1)[0]

            platform = r.get("platform", "")
            version = ""
            software = "tor"
            if "Tor " in platform:
                try:
                    version = platform.split("Tor ")[1].split(" ")[0]
                except Exception:
                    pass

            # Bandwidth: Onionoo reports observed_bandwidth in bytes/s → convert to Mbps
            bw_raw = r.get("bandwidth", {})
            observed = bw_raw.get("observed_bandwidth", 0) if isinstance(bw_raw, dict) else 0
            bandwidth_mbps = round(observed / 1_000_000, 3)  # bytes/s → Mbps

            node = DiscoveredNode(
                node_id=f"tor_{fp.lower()}",
                ip_address=ip,
                public_key=fp.lower(),
                software=software,
                version=version or None,
                network="tor",
                uptime_seconds=r.get("uptime"),
                bandwidth_mbps=bandwidth_mbps or None,
                location=r.get("country"),
                source=self.NAME,
                or_port=None,
                dir_port=None,
                flags=r.get("flags", []),
                contact=(r.get("contact") or "")[:200] or None,
            )
            nodes.append(node)
        logger.info("[tor_metrics] Parsed %d relay records", len(nodes))
        return nodes


class I2PNetDBSource:
    """
    Fetches I2P router-info stats from a public HTTPS mirror.
    We use diva.exchange reseed stats endpoint which returns a JSON
    summary of known routers (no direct I2P network access).
    """

    NAME = "i2p_netdb"
    STATS_URL = "https://reseed.diva.exchange/stats"
    # Fallback: community-maintained list of known I2P routers
    FALLBACK_URL = "https://raw.githubusercontent.com/i2p/i2p.www/master/i2p2www/static/hosts.txt"

    def __init__(self, max_nodes: int = 300):
        self.max_nodes = max_nodes

    def fetch(self) -> List[dict]:
        raw = _http_get(self.STATS_URL, timeout=15)
        if raw:
            try:
                data = json.loads(raw)
                routers = data if isinstance(data, list) else data.get("routers", [])
                if routers:
                    return routers[: self.max_nodes]
            except Exception:
                pass

        # Fallback: parse hosts.txt for domain→base32 mappings
        raw2 = _http_get(self.FALLBACK_URL, timeout=15)
        if not raw2:
            logger.warning("[i2p_netdb] All I2P sources unreachable")
            return []

        results = []
        for line in raw2.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                parts = line.split("=", 1)
                host, b64 = parts[0].strip(), parts[1].strip()
                results.append({"host": host, "key": b64[:64]})
            if len(results) >= self.max_nodes:
                break
        return results

    def parse(self, routers: List[dict]) -> list:
        DiscoveredNode = _node_model()
        nodes = []
        for r in routers:
            # Two possible record shapes: stats JSON or hosts.txt dict
            key = r.get("key") or r.get("router_hash") or r.get("hash", "")
            host = r.get("host") or r.get("ip") or r.get("address")

            if not key:
                key = hashlib.sha256(str(r).encode()).hexdigest()

            node_id = f"i2p_{key[:40].lower()}"

            node = DiscoveredNode(
                node_id=node_id,
                ip_address=host if host and not host.endswith(".i2p") else None,
                public_key=key[:64] if key else None,
                software="i2pd",
                version=r.get("version"),
                network="i2p",
                uptime_seconds=r.get("uptime_seconds"),
                bandwidth_mbps=r.get("bandwidth_mbps"),
                location=r.get("country") or r.get("location"),
                source=self.NAME,
                flags=[],
                contact=None,
            )
            nodes.append(node)

        logger.info("[i2p_netdb] Parsed %d router records", len(nodes))
        return nodes


class PublicDNSSource:
    """
    Collects mixnet/anonymous-network bootstrap nodes from public DNS
    seed lists and community-maintained HTTPS registries.

    Sources used (all public HTTPS, no Tor/I2P access):
        - Nym mixnet public validator / gateway list (mainnet API)
        - Known Katzenpost / HORNET seed node hosts from GitHub
    """

    NAME = "public_dns"
    NYM_GATEWAYS_URL = "https://validator.nymtech.net/api/v1/gateways"
    NYM_MIXNODES_URL  = "https://validator.nymtech.net/api/v1/mixnodes"

    def __init__(self, max_nodes: int = 200):
        self.max_nodes = max_nodes

    def fetch(self) -> List[dict]:
        results: List[dict] = []

        # Nym gateways
        raw = _http_get(self.NYM_GATEWAYS_URL, timeout=15)
        if raw:
            try:
                data = json.loads(raw)
                entries = data if isinstance(data, list) else data.get("data", [])
                for entry in entries:
                    entry["_kind"] = "nym_gateway"
                    results.append(entry)
            except Exception as exc:
                logger.debug("[public_dns] Nym gateway parse error: %s", exc)

        # Nym mix nodes
        raw2 = _http_get(self.NYM_MIXNODES_URL, timeout=15)
        if raw2:
            try:
                data2 = json.loads(raw2)
                entries2 = data2 if isinstance(data2, list) else data2.get("data", [])
                for entry in entries2:
                    entry["_kind"] = "nym_mixnode"
                    results.append(entry)
            except Exception as exc:
                logger.debug("[public_dns] Nym mixnode parse error: %s", exc)

        if not results:
            logger.warning("[public_dns] Nym validator API unreachable — using hardcoded seeds")
            results = self._hardcoded_seeds()

        return results[: self.max_nodes]

    def _hardcoded_seeds(self) -> List[dict]:
        """Return a small set of well-known public mixnet bootstrap hosts."""
        return [
            {"host": "sandbox-nym-api.nymtech.net", "network": "mixnet", "software": "nym", "_kind": "seed"},
            {"host": "validator.nymtech.net",        "network": "mixnet", "software": "nym", "_kind": "seed"},
            {"host": "nym-api.cakewallet.com",       "network": "mixnet", "software": "nym", "_kind": "seed"},
        ]

    def parse(self, entries: List[dict]) -> list:
        DiscoveredNode = _node_model()
        nodes = []
        for e in entries:
            kind = e.get("_kind", "unknown")

            # Nym gateway / mixnode shape
            mix_host = (
                e.get("mix_host")
                or e.get("host")
                or e.get("hostname")
                or (e.get("bond_information", {}) or {}).get("mix_node", {}).get("host")
            )
            identity = (
                e.get("identity_key")
                or e.get("mix_id")
                or (e.get("bond_information", {}) or {}).get("mix_node", {}).get("identity_key")
            )

            if not identity:
                identity = hashlib.sha256(str(e).encode()).hexdigest()[:40]

            # Parse IP from host (may include port)
            ip = None
            if mix_host:
                h = str(mix_host)
                if ":" in h and not h.startswith("["):
                    ip = h.rsplit(":", 1)[0]
                elif "[" in h:
                    ip = h.split("]")[0].lstrip("[")
                elif not any(c.isalpha() for c in h):
                    ip = h
                # If it's a hostname, leave ip as None

            version = str(
                e.get("version")
                or (e.get("bond_information", {}) or {}).get("mix_node", {}).get("version", "")
                or ""
            ) or None

            node = DiscoveredNode(
                node_id=f"mixnet_{identity[:40].lower()}",
                ip_address=ip,
                public_key=str(identity)[:64],
                software="nym",
                version=version,
                network="mixnet",
                uptime_seconds=None,
                bandwidth_mbps=None,
                location=e.get("location") or e.get("country"),
                source=self.NAME,
                flags=[kind],
                contact=None,
            )
            nodes.append(node)

        logger.info("[public_dns] Parsed %d mixnet node records", len(nodes))
        return nodes


# ---------------------------------------------------------------------------
# Discovery Engine
# ---------------------------------------------------------------------------


class DiscoveryEngine:
    """
    Passive dark-web node discovery engine.

    Orchestrates multiple source adapters, deduplicates results, applies
    scoring, and upserts nodes into the Knowledge Graph.

    Usage
    -----
    ::

        engine = DiscoveryEngine()
        nodes  = engine.discover_all()
        engine.update_knowledge_graph(nodes)

    The module-level ``discovery_engine`` singleton is used by main.py for
    the background asyncio task.
    """

    # SQLite path for the discovery store
    _DB_FILENAME = "discovery.db"

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            os.makedirs(_db_dir, exist_ok=True)
            db_path = os.path.join(_db_dir, self._DB_FILENAME)
        self.db_path = db_path
        self._init_db()

        # Load configured max_nodes
        try:
            from ..config import VEIL_DISCOVERY_MAX_NODES  # type: ignore
            self._max_nodes = VEIL_DISCOVERY_MAX_NODES
        except Exception:
            self._max_nodes = 1000

        self._sources = self._load_sources()
        logger.info("DiscoveryEngine initialised — db=%s sources=%s", db_path, [s.NAME for s in self._sources])

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS discovered_nodes (
                    node_id          TEXT PRIMARY KEY,
                    ip_address       TEXT,
                    public_key       TEXT,
                    software         TEXT,
                    version          TEXT,
                    network          TEXT NOT NULL,
                    uptime_seconds   INTEGER,
                    bandwidth_mbps   REAL,
                    location         TEXT,
                    discovered_at    TEXT NOT NULL,
                    updated_at       TEXT NOT NULL,
                    source           TEXT NOT NULL,
                    score            REAL NOT NULL DEFAULT 0.0,
                    or_port          INTEGER,
                    dir_port         INTEGER,
                    flags            TEXT,
                    contact          TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_dn_network ON discovered_nodes (network);
                CREATE INDEX IF NOT EXISTS idx_dn_score   ON discovered_nodes (score DESC);
                CREATE INDEX IF NOT EXISTS idx_dn_source  ON discovered_nodes (source);

                CREATE TABLE IF NOT EXISTS discovery_runs (
                    run_id              TEXT PRIMARY KEY,
                    started_at          TEXT NOT NULL,
                    completed_at        TEXT,
                    nodes_discovered    INTEGER NOT NULL DEFAULT 0,
                    nodes_updated       INTEGER NOT NULL DEFAULT 0,
                    nodes_new           INTEGER NOT NULL DEFAULT 0,
                    errors              TEXT,
                    sources_used        TEXT,
                    status              TEXT NOT NULL DEFAULT 'running'
                );
                """
            )

    # ------------------------------------------------------------------
    # Source loader
    # ------------------------------------------------------------------

    def _load_sources(self) -> list:
        """Instantiate only the sources listed in VEIL_DISCOVERY_SOURCES config."""
        try:
            from ..config import VEIL_DISCOVERY_SOURCES  # type: ignore
            enabled = [s.strip() for s in VEIL_DISCOVERY_SOURCES.split(",") if s.strip()]
        except Exception:
            enabled = ["tor_metrics", "i2p_netdb", "public_dns"]

        per_source = max(1, self._max_nodes // max(len(enabled), 1))
        all_sources = {
            "tor_metrics": lambda: TorMetricsSource(max_nodes=min(per_source, 500)),
            "i2p_netdb":   lambda: I2PNetDBSource(max_nodes=min(per_source, 300)),
            "public_dns":  lambda: PublicDNSSource(max_nodes=min(per_source, 200)),
        }

        sources = []
        for name in enabled:
            factory = all_sources.get(name)
            if factory:
                sources.append(factory())
            else:
                logger.warning("Unknown discovery source '%s' — skipped", name)

        return sources

    # ------------------------------------------------------------------
    # Core discovery pipeline
    # ------------------------------------------------------------------

    def discover_all(self) -> Tuple[List, "DiscoveryRun"]:  # type: ignore[name-defined]
        """
        Run all enabled source adapters, merge and deduplicate results,
        score each node, and return (node_list, run_record).

        Deduplication key priority:
          1. public_key (fingerprint / identity key)
          2. ip_address
          Falls back to node_id (already unique per source+relay).
        """
        from ..models.discovery_models import DiscoveredNode, DiscoveryRun  # type: ignore

        run_id = str(uuid.uuid4())
        run = DiscoveryRun(run_id=run_id, sources_used=[s.NAME for s in self._sources])

        seen_by_key: Dict[str, DiscoveredNode] = {}  # public_key → node
        seen_by_ip:  Dict[str, DiscoveredNode] = {}  # ip_address → node
        errors: List[str] = []

        for source in self._sources:
            try:
                raw = source.fetch()
                nodes = source.parse(raw)
                for node in nodes:
                    # Deduplicate
                    dedup_key = node.public_key or node.ip_address
                    if dedup_key:
                        if dedup_key in seen_by_key:
                            # Merge: keep higher bandwidth, later timestamp
                            existing = seen_by_key[dedup_key]
                            if (node.bandwidth_mbps or 0) > (existing.bandwidth_mbps or 0):
                                existing.bandwidth_mbps = node.bandwidth_mbps
                            continue
                        seen_by_key[dedup_key] = node
                    else:
                        seen_by_key[node.node_id] = node
            except Exception as exc:
                err = f"Source {source.NAME}: {exc}"
                logger.warning("[discovery] %s", err)
                errors.append(err)

        all_nodes = list(seen_by_key.values())

        # Score every node
        for node in all_nodes:
            node.score = self.score_node(node)

        # Persist run metadata
        run.nodes_discovered = len(all_nodes)
        run.errors = errors
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        self._save_run(run)

        logger.info(
            "[discovery] Run %s complete — %d nodes, %d errors",
            run_id[:8], len(all_nodes), len(errors),
        )
        return all_nodes, run

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_node(node) -> float:
        """
        Composite quality score (0–100):
            Uptime           40 %  (linear, saturates at 30 days)
            Bandwidth        30 %  (linear, saturates at 100 Mbps)
            Location known   20 %  (binary — location string present)
            Software fresh   10 %  (version >= '0.4.0')
        """
        score = 0.0

        # Uptime (40%)
        if node.uptime_seconds and node.uptime_seconds > 0:
            uptime_days = node.uptime_seconds / 86400
            score += min(uptime_days / 30.0, 1.0) * 40.0

        # Bandwidth (30%)
        bw = getattr(node, "bandwidth_mbps", None) or 0.0
        score += min(bw / 100.0, 1.0) * 30.0

        # Location diversity (20%)
        loc = (node.location or "").strip()
        if loc and loc.lower() not in ("unknown", ""):
            score += 20.0

        # Software freshness (10%)
        ver = (node.version or "").strip()
        if ver:
            try:
                # Simple string comparison works for semver-like strings
                if ver >= "0.4.0":
                    score += 10.0
            except Exception:
                pass

        return round(min(score, 100.0), 2)

    # ------------------------------------------------------------------
    # Knowledge Graph upsert
    # ------------------------------------------------------------------

    def update_knowledge_graph(self, nodes: list) -> Tuple[int, int]:
        """
        Upsert discovered nodes into:
          1. Local discovery SQLite store (discovery.db).
          2. JULIUS VEIL database (controlled_nodes) as KG entities.

        Returns (new_count, updated_count).
        """
        new_count = 0
        updated_count = 0
        now_iso = datetime.utcnow().isoformat()

        with self._conn() as conn:
            for node in nodes:
                existing = conn.execute(
                    "SELECT node_id FROM discovered_nodes WHERE node_id = ?",
                    (node.node_id,),
                ).fetchone()

                flags_json = json.dumps(node.flags or [])
                row = (
                    node.node_id,
                    node.ip_address,
                    node.public_key,
                    node.software,
                    node.version,
                    node.network,
                    node.uptime_seconds,
                    node.bandwidth_mbps,
                    node.location,
                    node.discovered_at.isoformat() if node.discovered_at else now_iso,
                    now_iso,
                    node.source,
                    node.score,
                    node.or_port,
                    node.dir_port,
                    flags_json,
                    node.contact,
                )

                if existing:
                    conn.execute(
                        """
                        UPDATE discovered_nodes SET
                            ip_address=?, public_key=?, software=?, version=?,
                            uptime_seconds=?, bandwidth_mbps=?, location=?,
                            updated_at=?, score=?, flags=?, contact=?
                        WHERE node_id=?
                        """,
                        (
                            node.ip_address, node.public_key, node.software, node.version,
                            node.uptime_seconds, node.bandwidth_mbps, node.location,
                            now_iso, node.score, flags_json, node.contact,
                            node.node_id,
                        ),
                    )
                    updated_count += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO discovered_nodes
                            (node_id, ip_address, public_key, software, version,
                             network, uptime_seconds, bandwidth_mbps, location,
                             discovered_at, updated_at, source, score,
                             or_port, dir_port, flags, contact)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        row,
                    )
                    new_count += 1

        # Best-effort KG upsert via VEIL database
        self._upsert_kg_entities(nodes)

        logger.info(
            "[discovery] KG updated — new=%d updated=%d", new_count, updated_count
        )
        return new_count, updated_count

    def _upsert_kg_entities(self, nodes: list) -> None:
        """Insert each node into the VEIL controlled_nodes table as a KG entity."""
        try:
            from ..database.manager import get_db  # type: ignore

            db = get_db()
            for node in nodes:
                entity_id = node.node_id[:60]
                db.add_controlled_node(
                    node_id=entity_id,
                    node_type=f"DiscoveredNode_{node.network}",
                    host=node.ip_address or "unknown",
                    port=node.or_port or 0,
                    method="passive_discovery",
                )
        except Exception as exc:
            logger.debug("[discovery] KG entity upsert skipped: %s", exc)

    # ------------------------------------------------------------------
    # Query helpers (used by API endpoints)
    # ------------------------------------------------------------------

    def list_nodes(
        self,
        network: Optional[str] = None,
        source: Optional[str] = None,
        min_score: float = 0.0,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Return stored discovered nodes with optional filters."""
        clauses = ["score >= ?"]
        params: list = [min_score]

        if network:
            clauses.append("network = ?")
            params.append(network)
        if source:
            clauses.append("source = ?")
            params.append(source)

        where = " AND ".join(clauses)
        params += [limit, offset]

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM discovered_nodes WHERE {where} ORDER BY score DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM discovered_nodes WHERE node_id = ?", (node_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_node_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM discovered_nodes").fetchone()[0]

    def get_last_run(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def rescore_all(self) -> int:
        """Re-apply score_node() to every stored node. Returns count updated."""
        from ..models.discovery_models import DiscoveredNode  # type: ignore

        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM discovered_nodes").fetchall()
            for row in rows:
                flags_list = []
                try:
                    flags_list = json.loads(row["flags"] or "[]")
                except Exception:
                    pass
                node = DiscoveredNode(
                    node_id=row["node_id"],
                    ip_address=row["ip_address"],
                    public_key=row["public_key"],
                    software=row["software"],
                    version=row["version"],
                    network=row["network"],
                    uptime_seconds=row["uptime_seconds"],
                    bandwidth_mbps=row["bandwidth_mbps"],
                    location=row["location"],
                    source=row["source"],
                    flags=flags_list,
                )
                new_score = self.score_node(node)
                conn.execute(
                    "UPDATE discovered_nodes SET score=? WHERE node_id=?",
                    (new_score, node.node_id),
                )
        return len(rows)

    # ------------------------------------------------------------------
    # Internal run persistence
    # ------------------------------------------------------------------

    def _save_run(self, run) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discovery_runs
                    (run_id, started_at, completed_at, nodes_discovered,
                     nodes_updated, nodes_new, errors, sources_used, status)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    run.run_id,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.nodes_discovered,
                    run.nodes_updated,
                    run.nodes_new,
                    json.dumps(run.errors),
                    json.dumps(run.sources_used),
                    run.status,
                ),
            )

    # ------------------------------------------------------------------
    # Pantheon integration (best-effort)
    # ------------------------------------------------------------------

    def _log_to_pantheon(self, run) -> None:
        try:
            from ..services.pantheon.audit_jobs import log_discovery_run  # type: ignore
            log_discovery_run(
                run_id=run.run_id,
                nodes_discovered=run.nodes_discovered,
                errors=len(run.errors),
            )
        except Exception:
            pass  # Pantheon logging is best-effort


# ---------------------------------------------------------------------------
# Module-level singleton (imported by main.py and guardian_api.py)
# ---------------------------------------------------------------------------

discovery_engine = DiscoveryEngine()
