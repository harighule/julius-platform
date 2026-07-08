"""
JULIUS — Unified Database Manager
Single SQLite DB for auth, scans, events, identities, behavioral data.
"""

import sqlite3
import hashlib
import hmac
import secrets
import os
import struct
import time
import base64
import threading
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..config import DB_PATH, ADMIN_DEFAULT_PASSWORD, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_PANTHEON_ATTRIBUTION_COLUMNS = (
    ("actor_user_id", "INTEGER"),
    ("actor_username", "TEXT"),
    ("actor_role", "TEXT"),
    ("client_ip", "TEXT"),
    ("user_agent", "TEXT"),
    ("subject_claims_json", "TEXT"),
)


def _migrate_pantheon_attribution_columns(conn: sqlite3.Connection) -> None:
    """Add PR-3 attribution columns to existing Pantheon tables (SQLite ALTER)."""

    def _cols(table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r["name"]) for r in rows}

    for col, decl in _PANTHEON_ATTRIBUTION_COLUMNS:
        if col not in _cols("pantheon_events"):
            conn.execute(f"ALTER TABLE pantheon_events ADD COLUMN {col} {decl}")
    for col, decl in _PANTHEON_ATTRIBUTION_COLUMNS:
        if col not in _cols("pantheon_audit_chain"):
            conn.execute(f"ALTER TABLE pantheon_audit_chain ADD COLUMN {col} {decl}")


_PANTHEON_ACCESS_POLICY_SEED = (
    ("pantheon.events.publish", "operator", "POST /api/v1/pantheon/events"),
    ("pantheon.events.list", "read_only", "GET /api/v1/pantheon/events"),
    ("pantheon.audit.append", "auditor", "POST /api/v1/pantheon/audit/append"),
    ("pantheon.audit.verify", "auditor", "GET /api/v1/pantheon/audit/verify"),
    ("pantheon.audit.snapshot", "auditor", "POST /api/v1/pantheon/audit/snapshot"),
    ("pantheon.audit.root_latest", "read_only", "GET /api/v1/pantheon/audit/root/latest"),
    ("pantheon.audit.recent_read", "auditor", "GET /api/v1/pantheon/audit/recent"),
    ("pantheon.conditions.evaluate", "operator", "POST /api/v1/pantheon/conditions/evaluate"),
    ("pantheon.taxon.compute", "operator", "POST /api/v1/pantheon/taxon/compute"),
    ("pantheon.access_policy.read", "read_only", "GET /api/v1/pantheon/access-policy"),
    ("pantheon.access_policy.write", "admin", "PUT /api/v1/pantheon/access-policy/{key}"),
    ("pantheon.modules.health_read", "read_only", "GET /api/v1/pantheon/modules/health"),
    ("pantheon.conditions.registry_read", "read_only", "GET /api/v1/pantheon/conditions/registry"),
    ("pantheon.taxon.receipts_read", "read_only", "GET /api/v1/pantheon/taxon/receipts"),
    ("pantheon.conditions.dry_run", "auditor", "POST /api/v1/pantheon/conditions/dry-run"),
)


def _seed_pantheon_access_policy(conn: sqlite3.Connection) -> None:
    for key, role, desc in _PANTHEON_ACCESS_POLICY_SEED:
        conn.execute(
            """INSERT OR IGNORE INTO pantheon_access_policy (policy_key, min_role, enabled, description)
               VALUES (?, ?, 1, ?)""",
            (key, role, desc),
        )


def init_db():
    """Create all tables and seed defaults."""
    with _lock:
        conn = _connect()

        # ── Users ──────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                username              TEXT UNIQUE NOT NULL,
                email                 TEXT UNIQUE,
                password_hash         TEXT NOT NULL,
                salt                  TEXT NOT NULL,
                role                  TEXT NOT NULL DEFAULT 'user',
                api_key               TEXT UNIQUE,
                is_active             INTEGER NOT NULL DEFAULT 1,
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until          TEXT,
                totp_secret           TEXT,
                totp_enabled          INTEGER NOT NULL DEFAULT 0,
                created_at            TEXT NOT NULL,
                last_login            TEXT
            )
        """)

        # ── JWT blacklist ──────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS token_blacklist (
                token_hash TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL
            )
        """)

        # ── MFA pending sessions ───────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mfa_pending (
                mfa_token   TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                expires_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # ── IP rate limit ──────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ip_rate_limit (
                ip_address  TEXT PRIMARY KEY,
                attempts    INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_attempt TEXT
            )
        """)

        # ── Scans ─────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id          TEXT PRIMARY KEY,
                target      TEXT NOT NULL,
                scan_type   TEXT NOT NULL DEFAULT 'quick',
                status      TEXT NOT NULL DEFAULT 'pending',
                results     TEXT,
                started_at  TEXT NOT NULL,
                completed_at TEXT,
                created_by  TEXT
            )
        """)

        # ── Vulnerabilities ────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vulnerabilities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id     TEXT,
                host        TEXT NOT NULL,
                port        INTEGER,
                service     TEXT,
                severity    TEXT NOT NULL DEFAULT 'info',
                title       TEXT NOT NULL,
                description TEXT,
                cve_id      TEXT,
                detected_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            )
        """)

        # ── Exploits ──────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exploits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                target      TEXT NOT NULL,
                exploit_type TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                result      TEXT,
                started_at  TEXT NOT NULL,
                completed_at TEXT,
                created_by  TEXT
            )
        """)

        # ── Events ────────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id          TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                source      TEXT NOT NULL,
                data        TEXT,
                timestamp   TEXT NOT NULL
            )
        """)

        # ── Identities ────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS identities (
                id          TEXT PRIMARY KEY,
                name        TEXT,
                platform    TEXT,
                email       TEXT,
                phone       TEXT,
                handle      TEXT,
                extra       TEXT,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Identity merges ───────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS identity_merges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   TEXT NOT NULL,
                target_id   TEXT NOT NULL,
                merged_at   TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES identities(id),
                FOREIGN KEY (target_id) REFERENCES identities(id)
            )
        """)

        # ── Behavioral patterns ───────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS behavioral_patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                pattern_type TEXT NOT NULL DEFAULT 'behavioral',
                description TEXT,
                rules       TEXT,
                severity    TEXT NOT NULL DEFAULT 'medium',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Behavioral alerts ─────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS behavioral_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id  INTEGER,
                alert_type  TEXT NOT NULL,
                severity    TEXT NOT NULL DEFAULT 'medium',
                message     TEXT NOT NULL,
                data        TEXT,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (pattern_id) REFERENCES behavioral_patterns(id)
            )
        """)

        # ── Insights workflows ────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                trigger_type TEXT NOT NULL DEFAULT 'manual',
                actions     TEXT,
                status      TEXT NOT NULL DEFAULT 'idle',
                is_active   INTEGER NOT NULL DEFAULT 1,
                last_run    TEXT,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Workflow execution steps ─────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                step_index  INTEGER NOT NULL,
                service     TEXT NOT NULL,
                action      TEXT NOT NULL,
                params      TEXT,
                status      TEXT NOT NULL DEFAULT 'pending',
                result_json TEXT,
                started_at  TEXT,
                completed_at TEXT,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            )
        """)

        # ── Cognitive Short-Term Memory (STM) ────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_stm (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                tool_used   TEXT,
                intent      TEXT,
                importance  REAL NOT NULL DEFAULT 0.5,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Cognitive Long-Term Memory (LTM) ─────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cognitive_ltm (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL DEFAULT 'episodic',
                summary     TEXT NOT NULL,
                source_sessions TEXT,
                importance  REAL NOT NULL DEFAULT 0.5,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Learned Skills (what tools work for what queries) ─────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_skills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern     TEXT NOT NULL,
                tool_name   TEXT NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 0,
                fail_count  INTEGER NOT NULL DEFAULT 0,
                avg_latency_ms REAL NOT NULL DEFAULT 0,
                last_used   TEXT,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Knowledge Base (facts learned from interactions) ──────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fact        TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'general',
                confidence  REAL NOT NULL DEFAULT 0.8,
                source      TEXT,
                times_used  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)

        # ── Event subscribers ────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_subscribers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                subscriber_id TEXT NOT NULL UNIQUE,
                callback_url TEXT,
                filter_json TEXT,
                created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                active      INTEGER NOT NULL DEFAULT 1
            )
        """)

        # ── Network allowlist ────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_allowlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cidr_range  TEXT NOT NULL UNIQUE,
                label       TEXT,
                added_by    TEXT,
                notes       TEXT,
                created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                active      INTEGER NOT NULL DEFAULT 1
            )
        """)

        # ── Audit log ────────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                user_id     INTEGER,
                username    TEXT,
                action      TEXT NOT NULL,
                resource    TEXT NOT NULL,
                details     TEXT,
                ip_address  TEXT,
                user_agent  TEXT
            )
        """)

        # ── Pantheon events (durable control plane stream) ───────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pantheon_events (
                event_id         TEXT PRIMARY KEY,
                module           TEXT NOT NULL,
                event_type       TEXT NOT NULL,
                entity_id        TEXT NOT NULL,
                timestamp        TEXT NOT NULL,
                trace_id         TEXT NOT NULL,
                payload          TEXT NOT NULL,
                idempotency_key  TEXT NOT NULL UNIQUE,
                integrity_hash   TEXT,
                actor_user_id    INTEGER,
                actor_username   TEXT,
                actor_role       TEXT,
                client_ip        TEXT,
                user_agent       TEXT,
                subject_claims_json TEXT
            )
        """)

        # ── Pantheon PRISM audit chain (append-only baseline) ────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pantheon_audit_chain (
                seq         INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id   TEXT NOT NULL UNIQUE,
                module      TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                entity_id   TEXT NOT NULL,
                payload     TEXT NOT NULL,
                timestamp   INTEGER NOT NULL,
                prev_hash   TEXT NOT NULL,
                record_hash TEXT NOT NULL,
                actor_user_id    INTEGER,
                actor_username   TEXT,
                actor_role       TEXT,
                client_ip        TEXT,
                user_agent       TEXT,
                subject_claims_json TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pantheon_audit_roots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_at   TEXT NOT NULL,
                root_hash     TEXT NOT NULL,
                record_count  INTEGER NOT NULL,
                valid         INTEGER NOT NULL DEFAULT 1,
                verification_note TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS pantheon_access_policy (
                policy_key  TEXT PRIMARY KEY,
                min_role    TEXT NOT NULL,
                enabled     INTEGER NOT NULL DEFAULT 1,
                description TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_cache (
                key         TEXT PRIMARY KEY,
                value       TEXT,
                updated_at  TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS darkweb_investigations (
                id                TEXT PRIMARY KEY,
                query             TEXT,
                status            TEXT,
                started_at        TEXT NOT NULL,
                completed_at      TEXT,
                raw_results_count INTEGER NOT NULL DEFAULT 0,
                filtered_count    INTEGER NOT NULL DEFAULT 0,
                scraped_count     INTEGER NOT NULL DEFAULT 0,
                raw_results       TEXT,
                filtered_results  TEXT,
                scraped_content   TEXT,
                analysis          TEXT,
                error             TEXT
            )
        """)

        _migrate_pantheon_attribution_columns(conn)
        _seed_pantheon_access_policy(conn)

        conn.commit()

        # Seed default admin
        row = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if not row:
            salt = secrets.token_hex(32)
            pw_hash = hashlib.pbkdf2_hmac(
                "sha256", ADMIN_DEFAULT_PASSWORD.encode(), salt.encode(), 100000
            ).hex()
            api_key = f"ak_{secrets.token_urlsafe(32)}"
            conn.execute(
                """INSERT INTO users
                   (username, email, password_hash, salt, role, api_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("admin", "admin@julius.local", pw_hash, salt, "admin", api_key,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()

        # Seed behavioral patterns (real detection rules, not demo data)
        row = conn.execute("SELECT COUNT(*) as c FROM behavioral_patterns").fetchone()
        if row["c"] == 0:
            _seed_behavioral_patterns(conn)

        conn.close()


def _seed_behavioral_patterns(conn):
    """Seed real behavioral detection patterns with proper event_type filters."""
    now = datetime.utcnow().isoformat()
    patterns = [
        ("Port Scan Detection", "network",
         "Alerts when many ports are discovered on a single host in a short window",
         '{"threshold": 15, "window_seconds": 120, "condition": {"event_type": "port_discovered"}}',
         "high", now),
        ("Brute Force Login", "auth",
         "Alerts on repeated failed login attempts from the auth subsystem",
         '{"threshold": 5, "window_seconds": 300, "condition": {"event_type": "login_failed"}}',
         "critical", now),
        ("Exploit Execution", "security",
         "Alerts when exploit modules are executed against targets",
         '{"threshold": 3, "window_seconds": 600, "condition": {"event_type": "exploit_completed"}}',
         "high", now),
        ("External Connection Spike", "network",
         "Alerts when many external connections are detected in a short window",
         '{"threshold": 8, "window_seconds": 120, "condition": {"event_type": "external_connection"}}',
         "medium", now),
        ("Dark Web Activity", "osint",
         "Alerts when dark web searches are performed",
         '{"threshold": 5, "window_seconds": 600, "condition": {"event_type": "darkweb_search"}}',
         "medium", now),
    ]
    conn.executemany(
        "INSERT INTO behavioral_patterns (name, pattern_type, description, rules, severity, created_at) VALUES (?,?,?,?,?,?)",
        patterns
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════
# Password helpers
# ═══════════════════════════════════════════════════════════════════════════

def hash_password(password: str, salt: Optional[str] = None):
    if salt is None:
        salt = secrets.token_hex(32)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100000
    ).hex()
    return pw_hash, salt


# ═══════════════════════════════════════════════════════════════════════════
# TOTP (RFC 6238)
# ═══════════════════════════════════════════════════════════════════════════

def generate_totp_secret() -> str:
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode()


def _hotp(secret_b32: str, counter: int) -> int:
    key = base64.b32decode(secret_b32, casefold=True)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    off = h[-1] & 0x0F
    code = struct.unpack(">I", h[off:off + 4])[0] & 0x7FFFFFFF
    return code % 1_000_000


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    try:
        code_int = int(code.replace(" ", ""))
    except (ValueError, TypeError):
        return False
    counter = int(time.time()) // 30
    for delta in range(-window, window + 1):
        if _hotp(secret_b32, counter + delta) == code_int:
            return True
    return False


def totp_uri(secret_b32: str, username: str, issuer: str = "JULIUS") -> str:
    return (
        f"otpauth://totp/{issuer}:{username}"
        f"?secret={secret_b32}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )


# ═══════════════════════════════════════════════════════════════════════════
# IP brute-force protection
# ═══════════════════════════════════════════════════════════════════════════

IP_MAX_ATTEMPTS = 20
IP_LOCKOUT_MINUTES = 30


def check_ip_allowed(ip: str) -> Dict[str, Any]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT attempts, locked_until FROM ip_rate_limit WHERE ip_address = ?", (ip,)
        ).fetchone()
        conn.close()
    if not row:
        return {"allowed": True, "locked_until": None}
    if row["locked_until"]:
        if datetime.utcnow() < datetime.fromisoformat(row["locked_until"]):
            return {"allowed": False, "locked_until": row["locked_until"]}
        _reset_ip(ip)
    return {"allowed": True, "locked_until": None}


def record_ip_failure(ip: str):
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT attempts FROM ip_rate_limit WHERE ip_address = ?", (ip,)
        ).fetchone()
        now = datetime.utcnow().isoformat()
        if not row:
            conn.execute(
                "INSERT INTO ip_rate_limit (ip_address, attempts, last_attempt) VALUES (?, 1, ?)",
                (ip, now),
            )
        else:
            new_attempts = row["attempts"] + 1
            locked_until = None
            if new_attempts >= IP_MAX_ATTEMPTS:
                locked_until = (datetime.utcnow() + timedelta(minutes=IP_LOCKOUT_MINUTES)).isoformat()
            conn.execute(
                "UPDATE ip_rate_limit SET attempts = ?, locked_until = ?, last_attempt = ? WHERE ip_address = ?",
                (new_attempts, locked_until, now, ip),
            )
        conn.commit()
        conn.close()


def record_ip_success(ip: str):
    _reset_ip(ip)


def _reset_ip(ip: str):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE ip_rate_limit SET attempts = 0, locked_until = NULL WHERE ip_address = ?", (ip,)
        )
        conn.commit()
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# JWT helpers
# ═══════════════════════════════════════════════════════════════════════════

def create_jwt_token(user_id: int, username: str, role: str) -> str:
    import jwt as pyjwt
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token.decode("utf-8") if isinstance(token, bytes) else token


def verify_jwt_token(token: str) -> Dict[str, Any]:
    import jwt as pyjwt
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if is_token_blacklisted(token_hash):
        return {"success": False, "error": "Token has been revoked"}
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "success": True,
            "user_id": payload["user_id"],
            "username": payload["username"],
            "role": payload["role"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def revoke_token(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)).isoformat()
    blacklist_token(token_hash, expires_at)


# ═══════════════════════════════════════════════════════════════════════════
# User CRUD
# ═══════════════════════════════════════════════════════════════════════════

def create_user(username: str, password: str, role: str = "user",
                email: Optional[str] = None) -> Dict[str, Any]:
    if not username or len(username) < 3:
        return {"success": False, "error": "Username must be at least 3 characters"}
    if not password or len(password) < 8:
        return {"success": False, "error": "Password must be at least 8 characters"}
    pw_hash, salt = hash_password(password)
    api_key = f"ak_{secrets.token_urlsafe(32)}"
    try:
        with _lock:
            conn = _connect()
            conn.execute(
                """INSERT INTO users
                   (username, email, password_hash, salt, role, api_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (username, email, pw_hash, salt, role, api_key,
                 datetime.utcnow().isoformat()),
            )
            conn.commit()
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()["id"]
            conn.close()
        return {"success": True, "user_id": user_id, "api_key": api_key}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Username or email already exists"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def authenticate(username: str, password: str) -> Dict[str, Any]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()
        if not row:
            conn.close()
            return {"success": False, "error": "Invalid credentials"}
        user = dict(row)
        if user["locked_until"]:
            if datetime.utcnow() < datetime.fromisoformat(user["locked_until"]):
                conn.close()
                remaining = (datetime.fromisoformat(user["locked_until"]) - datetime.utcnow()).seconds // 60
                return {"success": False, "error": f"Account locked. Try again in {remaining} min."}
            else:
                conn.execute(
                    "UPDATE users SET locked_until = NULL, failed_login_attempts = 0 WHERE id = ?",
                    (user["id"],),
                )
                conn.commit()
        pw_hash, _ = hash_password(password, user["salt"])
        if not secrets.compare_digest(pw_hash, user["password_hash"]):
            failed = user["failed_login_attempts"] + 1
            locked_until = None
            if failed >= 5:
                locked_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            conn.execute(
                "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                (failed, locked_until, user["id"]),
            )
            conn.commit()
            conn.close()
            return {"success": False, "error": "Invalid credentials"}
        conn.execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user["id"]),
        )
        conn.commit()
        conn.close()
    return {
        "success": True,
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "api_key": user["api_key"],
        "totp_enabled": bool(user["totp_enabled"]),
        "totp_secret": user["totp_secret"],
    }


# ── MFA Sessions ──────────────────────────────────────────────────────────

def create_mfa_session(user_id: int) -> str:
    mfa_token = secrets.token_urlsafe(32)
    expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM mfa_pending WHERE expires_at < ?", (datetime.utcnow().isoformat(),))
        conn.execute(
            "INSERT INTO mfa_pending (mfa_token, user_id, expires_at) VALUES (?, ?, ?)",
            (mfa_token, user_id, expires_at),
        )
        conn.commit()
        conn.close()
    return mfa_token


def consume_mfa_session(mfa_token: str) -> Optional[int]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT user_id, expires_at FROM mfa_pending WHERE mfa_token = ?", (mfa_token,)
        ).fetchone()
        if not row:
            conn.close()
            return None
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            conn.execute("DELETE FROM mfa_pending WHERE mfa_token = ?", (mfa_token,))
            conn.commit()
            conn.close()
            return None
        user_id = row["user_id"]
        conn.execute("DELETE FROM mfa_pending WHERE mfa_token = ?", (mfa_token,))
        conn.commit()
        conn.close()
    return user_id


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
    return dict(row) if row else None


def enable_totp(user_id: int, secret: str):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?",
            (secret, user_id),
        )
        conn.commit()
        conn.close()


def disable_totp(user_id: int):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?",
            (user_id,),
        )
        conn.commit()
        conn.close()


def blacklist_token(token_hash: str, expires_at: str):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR IGNORE INTO token_blacklist (token_hash, expires_at) VALUES (?, ?)",
            (token_hash, expires_at),
        )
        conn.commit()
        conn.close()


def is_token_blacklisted(token_hash: str) -> bool:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT token_hash FROM token_blacklist WHERE token_hash = ?", (token_hash,)
        ).fetchone()
        conn.close()
    return row is not None


def get_all_users() -> List[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, username, email, role, api_key, is_active, totp_enabled, created_at, last_login FROM users"
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Scan CRUD
# ═══════════════════════════════════════════════════════════════════════════

def create_scan(scan_id: str, target: str, scan_type: str = "quick", created_by: str = "system") -> Dict:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO scans (id, target, scan_type, status, started_at, created_by) VALUES (?,?,?,?,?,?)",
            (scan_id, target, scan_type, "running", datetime.utcnow().isoformat(), created_by)
        )
        conn.commit()
        conn.close()
    return {"id": scan_id, "status": "running"}


def update_scan(scan_id: str, status: str, results: dict = None):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE scans SET status = ?, results = ?, completed_at = ? WHERE id = ?",
            (status, json.dumps(results) if results else None, datetime.utcnow().isoformat(), scan_id)
        )
        conn.commit()
        conn.close()


def get_scan(scan_id: str) -> Optional[Dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("results"):
        try:
            d["results"] = json.loads(d["results"])
        except Exception:
            pass
    return d


def get_recent_scans(limit: int = 20) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM scans ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("results"):
            try:
                d["results"] = json.loads(d["results"])
            except Exception:
                pass
        results.append(d)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Vulnerability CRUD
# ═══════════════════════════════════════════════════════════════════════════

def add_vulnerability(scan_id: str, host: str, port: int, service: str,
                      severity: str, title: str, description: str = "", cve_id: str = None) -> int:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            """INSERT INTO vulnerabilities
               (scan_id, host, port, service, severity, title, description, cve_id, detected_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (scan_id, host, port, service, severity, title, description, cve_id,
             datetime.utcnow().isoformat())
        )
        vuln_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return vuln_id


def get_vulnerabilities(scan_id: str = None, severity: str = None, limit: int = 100) -> List[Dict]:
    with _lock:
        conn = _connect()
        query = "SELECT * FROM vulnerabilities WHERE 1=1"
        params = []
        if scan_id:
            query += " AND scan_id = ?"
            params.append(scan_id)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════════════════════

def add_event(event_id: str, event_type: str, source: str, data: dict = None) -> Dict:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO events (id, event_type, source, data, timestamp) VALUES (?,?,?,?,?)",
            (event_id, event_type, source, json.dumps(data or {}), datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    return {"id": event_id, "event_type": event_type}


def get_recent_events(limit: int = 50, event_type: str = None) -> List[Dict]:
    with _lock:
        conn = _connect()
        if event_type:
            rows = conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                pass
        results.append(d)
    return results


def save_live_tool_result(key: str, value: dict) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO live_cache (key, value, updated_at) VALUES (?,?,?)",
            (key, json.dumps(value), datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()


def get_live_tool_result(key: str) -> Optional[Dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT value FROM live_cache WHERE key = ?", (key,)).fetchone()
        conn.close()
    if not row:
        return None
    try:
        value = row["value"]
    except Exception:
        return None
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def get_live_tool_snapshot() -> Dict[str, Any]:
    return {
        "ip_lookup": get_live_tool_result("ip_lookup"),
        "dns_lookup": get_live_tool_result("dns_lookup"),
        "cves": get_live_tool_result("cves"),
    }


def save_darkweb_investigation(inv: Dict[str, Any]) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO darkweb_investigations (id, query, status, started_at, completed_at, raw_results_count, filtered_count, scraped_count, raw_results, filtered_results, scraped_content, analysis, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                inv.get("id"),
                inv.get("query"),
                inv.get("status"),
                inv.get("started_at"),
                inv.get("completed_at"),
                inv.get("raw_results_count", 0),
                inv.get("filtered_count", 0),
                inv.get("scraped_count", 0),
                json.dumps(inv.get("raw_results", [])),
                json.dumps(inv.get("filtered_results", [])),
                json.dumps(inv.get("scraped_content", {})),
                inv.get("analysis"),
                inv.get("error"),
            )
        )
        conn.commit()
        conn.close()


def get_darkweb_investigation(inv_id: str) -> Optional[Dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM darkweb_investigations WHERE id = ?", (inv_id,)).fetchone()
        conn.close()
    if not row:
        return None
    d = dict(row)
    for key in ("raw_results", "filtered_results", "scraped_content"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d


def get_darkweb_investigations(limit: int = 50) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM darkweb_investigations ORDER BY started_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        for key in ("raw_results", "filtered_results", "scraped_content"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    pass
        results.append(d)
    return results


def get_event_stats() -> Dict:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        conn.close()
    return {
        "total_events": total,
        "event_types": {r["event_type"]: r["count"] for r in rows}
    }


# ═══════════════════════════════════════════════════════════════════════════
# Pantheon durable events
# ═══════════════════════════════════════════════════════════════════════════

def add_pantheon_event(event: Dict[str, Any]) -> Dict[str, Any]:
    claims = event.get("subject_claims_json")
    if not claims:
        claims_obj = {
            "user_id": event.get("actor_user_id"),
            "username": event.get("actor_username"),
            "role": event.get("actor_role"),
        }
        claims = json.dumps(claims_obj, separators=(",", ":"), sort_keys=True)
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT OR IGNORE INTO pantheon_events
               (event_id, module, event_type, entity_id, timestamp, trace_id, payload, idempotency_key, integrity_hash,
                actor_user_id, actor_username, actor_role, client_ip, user_agent, subject_claims_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event["event_id"],
                event["module"],
                event["event_type"],
                event["entity_id"],
                event["timestamp"],
                event["trace_id"],
                json.dumps(event.get("payload", {})),
                event["idempotency_key"],
                event.get("integrity_hash", ""),
                event.get("actor_user_id"),
                event.get("actor_username"),
                event.get("actor_role"),
                event.get("client_ip"),
                (event.get("user_agent") or "")[:500] if event.get("user_agent") else None,
                claims,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pantheon_events WHERE idempotency_key = ?",
            (event["idempotency_key"],),
        ).fetchone()
        conn.close()
    stored = dict(row) if row else dict(event)
    try:
        stored["payload"] = json.loads(stored.get("payload") or "{}")
    except Exception:
        stored["payload"] = {}
    return stored


def get_recent_pantheon_events(
    limit: int = 100,
    module: Optional[str] = None,
    event_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    clauses: list[str] = []
    params: list[Any] = []
    mod = (module or "").strip()
    et = (event_type or "").strip()
    eid = (entity_id or "").strip()
    if mod:
        clauses.append("module = ?")
        params.append(mod)
    if et:
        clauses.append("event_type = ?")
        params.append(et)
    if eid:
        clauses.append("entity_id = ?")
        params.append(eid)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM pantheon_events{where} ORDER BY timestamp DESC LIMIT ?"
    params.append(safe_limit)
    with _lock:
        conn = _connect()
        rows = conn.execute(sql, tuple(params)).fetchall()
        conn.close()
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except Exception:
            item["payload"] = {}
        result.append(item)
    return result


def get_pantheon_event_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM pantheon_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        conn.close()
    if not row:
        return None
    item = dict(row)
    try:
        item["payload"] = json.loads(item.get("payload") or "{}")
    except Exception:
        item["payload"] = {}
    return item


def get_pantheon_event_by_event_id(event_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM pantheon_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        conn.close()
    if not row:
        return None
    item = dict(row)
    try:
        item["payload"] = json.loads(item.get("payload") or "{}")
    except Exception:
        item["payload"] = {}
    return item


def get_pantheon_taxon_receipt_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent TAXON `tax.computed` rows from the durable Pantheon event stream."""
    safe_limit = max(1, min(limit, 200))
    with _lock:
        conn = _connect()
        rows = conn.execute(
            """SELECT * FROM pantheon_events
               WHERE module = ? AND event_type = ?
               ORDER BY timestamp DESC LIMIT ?""",
            ("taxon", "tax.computed", safe_limit),
        ).fetchall()
        conn.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except Exception:
            item["payload"] = {}
        out.append(item)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Pantheon PRISM baseline chain
# ═══════════════════════════════════════════════════════════════════════════

def append_pantheon_audit_record(record: Dict[str, Any]) -> Dict[str, Any]:
    claims = record.get("subject_claims_json")
    if not claims:
        claims_obj = {
            "user_id": record.get("actor_user_id"),
            "username": record.get("actor_username"),
            "role": record.get("actor_role"),
        }
        claims = json.dumps(claims_obj, separators=(",", ":"), sort_keys=True)
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT INTO pantheon_audit_chain
               (record_id, module, event_type, entity_id, payload, timestamp, prev_hash, record_hash,
                actor_user_id, actor_username, actor_role, client_ip, user_agent, subject_claims_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["record_id"],
                record["module"],
                record["event_type"],
                record["entity_id"],
                json.dumps(record["payload"]),
                record["timestamp"],
                record["prev_hash"],
                record["record_hash"],
                record.get("actor_user_id"),
                record.get("actor_username"),
                record.get("actor_role"),
                record.get("client_ip"),
                (record.get("user_agent") or "")[:500] if record.get("user_agent") else None,
                claims,
            ),
        )
        conn.commit()
        conn.close()
    return record


def get_last_pantheon_audit_hash() -> str:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT record_hash FROM pantheon_audit_chain ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        conn.close()
    return row["record_hash"] if row else "0" * 64


def get_pantheon_audit_records() -> List[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM pantheon_audit_chain ORDER BY seq ASC"
        ).fetchall()
        conn.close()
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except Exception:
            item["payload"] = {}
        result.append(item)
    return result


def get_recent_pantheon_audit_entries(limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Newest-first tail of the PRISM chain (bounded). Optional event_type filter."""
    safe_limit = min(max(int(limit), 1), 200)
    et = (event_type or "").strip() or None
    cols = (
        "seq, record_id, module, event_type, entity_id, payload, timestamp, "
        "prev_hash, record_hash, actor_username, actor_role"
    )
    with _lock:
        conn = _connect()
        if et:
            rows = conn.execute(
                f"SELECT {cols} FROM pantheon_audit_chain WHERE event_type = ? ORDER BY seq DESC LIMIT ?",
                (et, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cols} FROM pantheon_audit_chain ORDER BY seq DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        conn.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            pl = json.loads(item.get("payload") or "{}")
        except Exception:
            pl = {}
        raw = json.dumps(pl, separators=(",", ":"), sort_keys=True)
        if len(raw) > 4096:
            item["payload"] = {"_truncated": True, "_preview_chars": 4096, "preview": raw[:4096]}
        else:
            item["payload"] = pl
        out.append(item)
    return out


def create_pantheon_audit_root_snapshot(valid: bool, verification_note: str = "") -> Dict[str, Any]:
    records = get_pantheon_audit_records()
    root_hash = records[-1]["record_hash"] if records else "0" * 64
    now = datetime.utcnow().isoformat()
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            """INSERT INTO pantheon_audit_roots
               (snapshot_at, root_hash, record_count, valid, verification_note)
               VALUES (?,?,?,?,?)""",
            (now, root_hash, len(records), 1 if valid else 0, verification_note),
        )
        snapshot_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return {
        "id": snapshot_id,
        "snapshot_at": now,
        "root_hash": root_hash,
        "record_count": len(records),
        "valid": bool(valid),
        "verification_note": verification_note,
    }


def get_latest_pantheon_audit_root() -> Optional[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM pantheon_audit_roots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
    if not row:
        return None
    item = dict(row)
    item["valid"] = bool(item.get("valid", 0))
    return item


# ═══════════════════════════════════════════════════════════════════════════
# Pantheon DB-driven access policy
# ═══════════════════════════════════════════════════════════════════════════

def get_pantheon_policy_min_role(policy_key: str) -> Optional[str]:
    """Return configured min_role when an enabled row exists; else None (caller uses code fallback)."""
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT min_role FROM pantheon_access_policy WHERE policy_key = ? AND enabled = 1",
            (policy_key,),
        ).fetchone()
        conn.close()
    if not row:
        return None
    return str(row["min_role"])


def list_pantheon_access_policies() -> List[Dict[str, Any]]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT policy_key, min_role, enabled, description FROM pantheon_access_policy ORDER BY policy_key ASC"
        ).fetchall()
        conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["enabled"] = bool(d.get("enabled", 1))
        out.append(d)
    return out


def upsert_pantheon_access_policy(
    policy_key: str,
    min_role: str,
    enabled: int = 1,
    description: str = "",
) -> Dict[str, Any]:
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT INTO pantheon_access_policy (policy_key, min_role, enabled, description)
               VALUES (?,?,?,?)
               ON CONFLICT(policy_key) DO UPDATE SET
                 min_role = excluded.min_role,
                 enabled = excluded.enabled,
                 description = excluded.description""",
            (policy_key, min_role, 1 if enabled else 0, description or None),
        )
        conn.commit()
        row = conn.execute(
            "SELECT policy_key, min_role, enabled, description FROM pantheon_access_policy WHERE policy_key = ?",
            (policy_key,),
        ).fetchone()
        conn.close()
    item = dict(row)
    item["enabled"] = bool(item.get("enabled", 0))
    return item


# ═══════════════════════════════════════════════════════════════════════════
# Identity CRUD
# ═══════════════════════════════════════════════════════════════════════════

def get_identities() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM identities ORDER BY created_at DESC").fetchall()
        conn.close()
    return [dict(r) for r in rows]


def add_identity(identity: Dict) -> Dict:
    import uuid
    new_id = f"id-{uuid.uuid4().hex}"
    extra = identity.get("extra")
    if extra is not None and not isinstance(extra, str):
        extra = json.dumps(extra)
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT OR IGNORE INTO identities (id, name, platform, email, phone, handle, extra, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_id, identity.get("name"), identity.get("platform"),
             identity.get("email"), identity.get("phone"), identity.get("handle"), extra,
             datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    return {"status": "added", "id": new_id}


def upsert_identity(identity: Dict) -> Dict:
    import uuid

    extra = identity.get("extra")
    if extra is not None and not isinstance(extra, str):
        extra = json.dumps(extra)

    platform = identity.get("platform")
    handle = identity.get("handle")
    email = identity.get("email")
    created_at = identity.get("created_at") or datetime.utcnow().isoformat()

    with _lock:
        conn = _connect()
        row = None
        if platform and handle:
            row = conn.execute(
                "SELECT id FROM identities WHERE platform = ? AND handle = ?",
                (platform, handle),
            ).fetchone()
        elif platform and email:
            row = conn.execute(
                "SELECT id FROM identities WHERE platform = ? AND email = ?",
                (platform, email),
            ).fetchone()

        if row:
            identity_id = row["id"]
            conn.execute(
                """UPDATE identities
                   SET name = ?, email = ?, phone = ?, handle = ?, extra = ?
                   WHERE id = ?""",
                (
                    identity.get("name"),
                    email,
                    identity.get("phone"),
                    handle,
                    extra,
                    identity_id,
                ),
            )
            status = "updated"
        else:
            identity_id = f"id-{uuid.uuid4().hex}"
            conn.execute(
                """INSERT INTO identities
                   (id, name, platform, email, phone, handle, extra, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    identity_id,
                    identity.get("name"),
                    platform,
                    email,
                    identity.get("phone"),
                    handle,
                    extra,
                    created_at,
                ),
            )
            status = "added"

        conn.commit()
        conn.close()

    return {"status": status, "id": identity_id}


def merge_identities(source_id: str, target_id: str) -> Dict:
    with _lock:
        conn = _connect()
        src = conn.execute("SELECT id FROM identities WHERE id = ?", (source_id,)).fetchone()
        tgt = conn.execute("SELECT id FROM identities WHERE id = ?", (target_id,)).fetchone()
        if not src:
            conn.close()
            return {"status": "error", "message": f"Source {source_id} not found"}
        if not tgt:
            conn.close()
            return {"status": "error", "message": f"Target {target_id} not found"}
        conn.execute(
            "INSERT INTO identity_merges (source_id, target_id, merged_at) VALUES (?,?,?)",
            (source_id, target_id, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    return {"status": "merged", "source": source_id, "target": target_id}


def get_identity_merges() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM identity_merges ORDER BY merged_at DESC").fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Behavioral CRUD
# ═══════════════════════════════════════════════════════════════════════════

def get_behavioral_patterns() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM behavioral_patterns ORDER BY created_at DESC").fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("rules"):
            try:
                d["rules"] = json.loads(d["rules"])
            except Exception:
                pass
        results.append(d)
    return results


def add_behavioral_pattern(name: str, pattern_type: str, description: str,
                           rules: dict = None, severity: str = "medium") -> Dict:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO behavioral_patterns (name, pattern_type, description, rules, severity, created_at) VALUES (?,?,?,?,?,?)",
            (name, pattern_type, description, json.dumps(rules or {}), severity,
             datetime.utcnow().isoformat())
        )
        pid = cursor.lastrowid
        conn.commit()
        conn.close()
    return {"id": pid, "name": name}


def get_behavioral_alerts(limit: int = 50) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM behavioral_alerts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except Exception:
                pass
        results.append(d)
    return results


def add_behavioral_alert(pattern_id: int, alert_type: str, severity: str,
                         message: str, data: dict = None) -> int:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO behavioral_alerts (pattern_id, alert_type, severity, message, data, created_at) VALUES (?,?,?,?,?,?)",
            (pattern_id, alert_type, severity, message, json.dumps(data or {}),
             datetime.utcnow().isoformat())
        )
        aid = cursor.lastrowid
        conn.commit()
        conn.close()
    return aid


def update_behavioral_pattern(pattern_id: int, updates: Dict):
    with _lock:
        conn = _connect()
        sets, vals = [], []
        for key in ("name", "pattern_type", "description", "severity", "is_active"):
            if key in updates:
                sets.append(f"{key} = ?")
                vals.append(updates[key])
        if "rules" in updates:
            sets.append("rules = ?")
            vals.append(json.dumps(updates["rules"]) if isinstance(updates["rules"], dict) else updates["rules"])
        if sets:
            vals.append(pattern_id)
            conn.execute(f"UPDATE behavioral_patterns SET {', '.join(sets)} WHERE id = ?", vals)
            conn.commit()
        conn.close()


def delete_behavioral_pattern(pattern_id: int):
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM behavioral_patterns WHERE id = ?", (pattern_id,))
        conn.commit()
        conn.close()


def delete_behavioral_alert(alert_id: int):
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM behavioral_alerts WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# Workflow CRUD
# ═══════════════════════════════════════════════════════════════════════════

def get_workflows() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("actions"):
            try:
                d["actions"] = json.loads(d["actions"])
            except Exception:
                pass
        results.append(d)
    return results


def add_workflow(name: str, description: str, trigger_type: str = "manual",
                 actions: list = None) -> Dict:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO workflows (name, description, trigger_type, actions, status, created_at) VALUES (?,?,?,?,?,?)",
            (name, description, trigger_type, json.dumps(actions or []), "idle",
             datetime.utcnow().isoformat())
        )
        wid = cursor.lastrowid
        conn.commit()
        conn.close()
    return {"id": wid, "name": name}


def get_workflow(workflow_id: int) -> Optional[Dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("actions"):
        try:
            d["actions"] = json.loads(d["actions"])
        except Exception:
            pass
    return d


def update_workflow_status(workflow_id: int, status: str):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE workflows SET status = ?, last_run = ? WHERE id = ?",
            (status, datetime.utcnow().isoformat(), workflow_id)
        )
        conn.commit()
        conn.close()


def add_workflow_step(workflow_id: int, step_index: int, service: str, action: str, params: dict = None) -> int:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO workflow_steps (workflow_id, step_index, service, action, params, status) VALUES (?,?,?,?,?,?)",
            (workflow_id, step_index, service, action, json.dumps(params or {}), "pending")
        )
        sid = cursor.lastrowid
        conn.commit()
        conn.close()
    return sid


def update_workflow_step(workflow_id: int, step_index: int, status: str, result: Any = None):
    now = datetime.utcnow().isoformat()
    with _lock:
        conn = _connect()
        if status == "running":
            conn.execute(
                "UPDATE workflow_steps SET status = ?, started_at = ? WHERE workflow_id = ? AND step_index = ?",
                (status, now, workflow_id, step_index)
            )
        else:
            conn.execute(
                "UPDATE workflow_steps SET status = ?, result_json = ?, completed_at = ? WHERE workflow_id = ? AND step_index = ?",
                (status, json.dumps(result) if result else None, now, workflow_id, step_index)
            )
        conn.commit()
        conn.close()


def get_workflow_steps(workflow_id: int) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY step_index", (workflow_id,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        for key in ("params", "result_json"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    pass
        results.append(d)
    return results


def get_workflow_with_steps(workflow_id: int) -> Optional[Dict]:
    wf = get_workflow(workflow_id)
    if not wf:
        return None
    wf["steps"] = get_workflow_steps(workflow_id)
    return wf


# ═══════════════════════════════════════════════════════════════════════════
# Exploit CRUD
# ═══════════════════════════════════════════════════════════════════════════

def create_exploit(target: str, exploit_type: str) -> int:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO exploits (target, exploit_type, status, started_at) VALUES (?,?,?,?)",
            (target, exploit_type, "running", datetime.utcnow().isoformat())
        )
        exploit_id = cursor.lastrowid
        conn.commit()
        conn.close()
    return exploit_id


def update_exploit(exploit_id: int, status: str, result: dict = None):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE exploits SET status = ?, result = ?, completed_at = ? WHERE id = ?",
            (status, json.dumps(result) if result else None,
             datetime.utcnow().isoformat(), exploit_id)
        )
        conn.commit()
        conn.close()


def get_exploit(exploit_id: int) -> Optional[Dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM exploits WHERE id = ?", (exploit_id,)).fetchone()
        conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("result"):
        try:
            d["result"] = json.loads(d["result"])
        except Exception:
            pass
    return d


def get_exploit_history(limit: int = 20) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM exploits ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except Exception:
                pass
        results.append(d)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Event Subscribers (persistent)
# ═══════════════════════════════════════════════════════════════════════════

def add_subscriber(event_type: str, subscriber_id: str, callback_url: str = None, filter_json: str = None) -> Dict:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO event_subscribers (event_type, subscriber_id, callback_url, filter_json, created_at) VALUES (?,?,?,?,?)",
                (event_type, subscriber_id, callback_url, filter_json, datetime.utcnow().isoformat())
            )
            conn.commit()
        except Exception:
            conn.execute(
                "UPDATE event_subscribers SET event_type=?, callback_url=?, filter_json=?, active=1 WHERE subscriber_id=?",
                (event_type, callback_url, filter_json, subscriber_id)
            )
            conn.commit()
        conn.close()
    return {"status": "subscribed", "subscriber_id": subscriber_id}


def remove_subscriber(subscriber_id: str):
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM event_subscribers WHERE subscriber_id = ?", (subscriber_id,))
        conn.commit()
        conn.close()


def get_active_subscribers(event_type: str = None) -> List[Dict]:
    with _lock:
        conn = _connect()
        if event_type:
            rows = conn.execute(
                "SELECT * FROM event_subscribers WHERE active = 1 AND event_type = ?", (event_type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM event_subscribers WHERE active = 1").fetchall()
        conn.close()
    return [dict(r) for r in rows]


def get_all_subscribers() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM event_subscribers ORDER BY created_at DESC").fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Network Allowlist (persistent)
# ═══════════════════════════════════════════════════════════════════════════

def add_allowlist_entry(cidr: str, label: str, added_by: str = "admin", notes: str = "") -> Dict:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO network_allowlist (cidr_range, label, added_by, notes, created_at) VALUES (?,?,?,?,?)",
                (cidr, label, added_by, notes, datetime.utcnow().isoformat())
            )
            conn.commit()
            conn.close()
            return {"status": "added", "cidr": cidr}
        except Exception:
            conn.close()
            return {"status": "exists", "cidr": cidr}


def remove_allowlist_entry(cidr: str):
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM network_allowlist WHERE cidr_range = ?", (cidr,))
        conn.commit()
        conn.close()


def get_active_allowlist() -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM network_allowlist WHERE active = 1 ORDER BY created_at").fetchall()
        conn.close()
    return [dict(r) for r in rows]


def log_audit(user_id: int = None, username: str = None, action: str = "",
              resource: str = "", details: str = None, ip_address: str = None, user_agent: str = None):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO audit_log (timestamp, user_id, username, action, resource, details, ip_address, user_agent) VALUES (?,?,?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(), user_id, username, action, resource, details, ip_address, user_agent)
        )
        conn.commit()
        conn.close()


def get_audit_log(limit: int = 100) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def cleanup_old_rate_limits(max_age_seconds: int = 86400):
    cutoff = (datetime.utcnow() - timedelta(seconds=max_age_seconds)).isoformat()
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM ip_rate_limit WHERE last_attempt < ? AND locked_until IS NULL", (cutoff,))
        conn.commit()
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# System stats
# ═══════════════════════════════════════════════════════════════════════════

def get_system_stats() -> Dict:
    with _lock:
        conn = _connect()
        scans = conn.execute("SELECT COUNT(*) as c FROM scans").fetchone()["c"]
        vulns = conn.execute("SELECT COUNT(*) as c FROM vulnerabilities").fetchone()["c"]
        events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        identities = conn.execute("SELECT COUNT(*) as c FROM identities").fetchone()["c"]
        alerts = conn.execute("SELECT COUNT(*) as c FROM behavioral_alerts").fetchone()["c"]
        users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        conn.close()
    return {
        "total_scans": scans,
        "total_vulnerabilities": vulns,
        "total_events": events,
        "total_identities": identities,
        "total_alerts": alerts,
        "total_users": users,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Cognitive Memory — STM
# ═══════════════════════════════════════════════════════════════════════════

def stm_store(session_id: str, role: str, content: str,
              tool_used: str = None, intent: str = None, importance: float = 0.5):
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO cognitive_stm (session_id, role, content, tool_used, intent, importance, created_at) VALUES (?,?,?,?,?,?,?)",
            (session_id, role, content[:2000], tool_used, intent, importance, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()


def stm_recall(session_id: str, limit: int = 20) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM cognitive_stm WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        conn.close()
    return [dict(r) for r in reversed(rows)]


def stm_recall_recent(limit: int = 30) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM cognitive_stm ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    return [dict(r) for r in reversed(rows)]


# ═══════════════════════════════════════════════════════════════════════════
# Cognitive Memory — LTM
# ═══════════════════════════════════════════════════════════════════════════

def ltm_store(memory_type: str, summary: str, source_sessions: str = "",
              importance: float = 0.5) -> int:
    with _lock:
        conn = _connect()
        cursor = conn.execute(
            "INSERT INTO cognitive_ltm (memory_type, summary, source_sessions, importance, created_at) VALUES (?,?,?,?,?)",
            (memory_type, summary, source_sessions, importance, datetime.utcnow().isoformat())
        )
        mid = cursor.lastrowid
        conn.commit()
        conn.close()
    return mid


def ltm_recall(limit: int = 10, memory_type: str = None) -> List[Dict]:
    with _lock:
        conn = _connect()
        if memory_type:
            rows = conn.execute(
                "SELECT * FROM cognitive_ltm WHERE memory_type = ? ORDER BY importance DESC, access_count DESC LIMIT ?",
                (memory_type, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cognitive_ltm ORDER BY importance DESC, access_count DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def ltm_search(query: str, limit: int = 5) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM cognitive_ltm WHERE summary LIKE ? ORDER BY importance DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        # Bump access count
        for r in rows:
            conn.execute(
                "UPDATE cognitive_ltm SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), r["id"])
            )
        conn.commit()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Learned Skills
# ═══════════════════════════════════════════════════════════════════════════

def skill_record(pattern: str, tool_name: str, success: bool, latency_ms: float = 0):
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT id, success_count, fail_count, avg_latency_ms FROM learned_skills WHERE pattern = ? AND tool_name = ?",
            (pattern.lower(), tool_name)
        ).fetchone()
        now = datetime.utcnow().isoformat()
        if row:
            sc = row["success_count"] + (1 if success else 0)
            fc = row["fail_count"] + (0 if success else 1)
            total = sc + fc
            avg_lat = (row["avg_latency_ms"] * (total - 1) + latency_ms) / total if total > 0 else latency_ms
            conn.execute(
                "UPDATE learned_skills SET success_count=?, fail_count=?, avg_latency_ms=?, last_used=? WHERE id=?",
                (sc, fc, avg_lat, now, row["id"])
            )
        else:
            conn.execute(
                "INSERT INTO learned_skills (pattern, tool_name, success_count, fail_count, avg_latency_ms, last_used, created_at) VALUES (?,?,?,?,?,?,?)",
                (pattern.lower(), tool_name, 1 if success else 0, 0 if success else 1, latency_ms, now, now)
            )
        conn.commit()
        conn.close()


def skill_lookup(pattern: str, limit: int = 5) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM learned_skills WHERE pattern LIKE ? ORDER BY success_count DESC LIMIT ?",
            (f"%{pattern.lower()}%", limit)
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def skill_top(limit: int = 10) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM learned_skills ORDER BY success_count DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Base
# ═══════════════════════════════════════════════════════════════════════════

def knowledge_store(fact: str, category: str = "general", confidence: float = 0.8, source: str = "") -> int:
    with _lock:
        conn = _connect()
        existing = conn.execute(
            "SELECT id, confidence FROM knowledge_base WHERE fact = ?", (fact,)
        ).fetchone()
        if existing:
            new_confidence = max(existing["confidence"], confidence)
            conn.execute(
                "UPDATE knowledge_base SET confidence = ?, times_used = times_used + 1 WHERE id = ?",
                (new_confidence, existing["id"])
            )
            conn.commit()
            conn.close()
            return existing["id"]
        cursor = conn.execute(
            "INSERT INTO knowledge_base (fact, category, confidence, source, created_at) VALUES (?,?,?,?,?)",
            (fact, category, confidence, source, datetime.utcnow().isoformat())
        )
        kid = cursor.lastrowid
        conn.commit()
        conn.close()
    return kid


def knowledge_search(query: str, limit: int = 5) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM knowledge_base WHERE fact LIKE ? ORDER BY confidence DESC, times_used DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        for r in rows:
            conn.execute("UPDATE knowledge_base SET times_used = times_used + 1 WHERE id = ?", (r["id"],))
        conn.commit()
        conn.close()
    return [dict(r) for r in rows]


def knowledge_all(limit: int = 20) -> List[Dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM knowledge_base ORDER BY confidence DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
# Memory consolidation stats
# ═══════════════════════════════════════════════════════════════════════════

def cognitive_stats() -> Dict:
    with _lock:
        conn = _connect()
        stm_count = conn.execute("SELECT COUNT(*) as c FROM cognitive_stm").fetchone()["c"]
        ltm_count = conn.execute("SELECT COUNT(*) as c FROM cognitive_ltm").fetchone()["c"]
        skills_count = conn.execute("SELECT COUNT(*) as c FROM learned_skills").fetchone()["c"]
        knowledge_count = conn.execute("SELECT COUNT(*) as c FROM knowledge_base").fetchone()["c"]
        conn.close()
    return {
        "short_term_memories": stm_count,
        "long_term_memories": ltm_count,
        "learned_skills": skills_count,
        "knowledge_facts": knowledge_count,
    }


# Auto-initialize on import
init_db()
