"""
JULIUS Cognitive Memory — Inspired by ECA (Emergent Cognitive Architecture).

Implements:
1. Short-Term Memory (STM) — Recent conversation turns, auto-injected into context
2. Long-Term Memory (LTM) — Consolidated summaries from past sessions
3. Learned Skills — Tracks which tools work for which query patterns (RL-inspired)
4. Knowledge Base — Facts discovered during interactions
5. Memory Consolidation — Periodically compresses STM into LTM summaries
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Lazy DB import
def _db():
    from ..database import db
    return db


# ═══════════════════════════════════════════════════════════════════════════
# STM — Working Memory (recent conversation context)
# ═══════════════════════════════════════════════════════════════════════════

def remember_interaction(session_id: str, role: str, content: str,
                         tool_used: str = None, intent: str = None):
    """Store a conversation turn in short-term memory."""
    importance = _compute_importance(content, tool_used)
    _db().stm_store(session_id, role, content, tool_used, intent, importance)


def get_working_memory(session_id: str, max_turns: int = 15) -> str:
    """Get recent conversation context formatted for the AI brain."""
    turns = _db().stm_recall(session_id, max_turns)
    if not turns:
        return ""
    lines = []
    for t in turns:
        prefix = "User" if t["role"] == "user" else "JULIUS"
        tool_tag = f" [used: {t['tool_used']}]" if t.get("tool_used") else ""
        lines.append(f"{prefix}{tool_tag}: {t['content'][:300]}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# LTM — Long-Term Memory (persistent knowledge from past sessions)
# ═══════════════════════════════════════════════════════════════════════════

def recall_relevant_memories(query: str, limit: int = 5) -> str:
    """Search long-term memory for relevant past knowledge."""
    memories = _db().ltm_search(query, limit)
    if not memories:
        return ""
    lines = [f"- [{m['memory_type']}] {m['summary']}" for m in memories]
    return "Relevant memories from past sessions:\n" + "\n".join(lines)


def get_all_ltm(limit: int = 10) -> List[Dict]:
    """Get most important long-term memories."""
    return _db().ltm_recall(limit)


# ═══════════════════════════════════════════════════════════════════════════
# Skills — Reinforcement Learning (what tools work for what)
# ═══════════════════════════════════════════════════════════════════════════

def record_tool_outcome(query: str, tool_name: str, success: bool, latency_ms: float = 0):
    """Record whether a tool call succeeded — builds the skill model."""
    # Extract a short pattern from the query
    pattern = _extract_pattern(query)
    _db().skill_record(pattern, tool_name, success, latency_ms)


def get_skill_hint(query: str) -> str:
    """Get a hint about which tools have worked for similar queries."""
    pattern = _extract_pattern(query)
    skills = _db().skill_lookup(pattern, 3)
    if not skills:
        return ""
    lines = []
    for s in skills:
        total = s["success_count"] + s["fail_count"]
        rate = round(s["success_count"] / max(total, 1) * 100)
        lines.append(f"- {s['tool_name']}: {rate}% success ({total} uses, avg {round(s['avg_latency_ms'])}ms)")
    return "Past experience suggests these tools work well:\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Base — Learned Facts
# ═══════════════════════════════════════════════════════════════════════════

def learn_fact(fact: str, category: str = "general", confidence: float = 0.8, source: str = ""):
    """Store a fact in the knowledge base."""
    _db().knowledge_store(fact, category, confidence, source)


def recall_knowledge(query: str, limit: int = 5) -> str:
    """Search the knowledge base for relevant facts."""
    facts = _db().knowledge_search(query, limit)
    if not facts:
        return ""
    lines = [f"- [{f['category']}] {f['fact']} (confidence: {f['confidence']})" for f in facts]
    return "Known facts:\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Memory Consolidation — STM → LTM
# ═══════════════════════════════════════════════════════════════════════════

_consolidation_running = False


def consolidate_memories():
    """
    Compress old STM entries into LTM summaries.
    Keeps STM lean, builds long-term knowledge.
    """
    global _consolidation_running
    if _consolidation_running:
        return
    _consolidation_running = True

    try:
        # Get all STM entries older than 30 minutes
        all_stm = _db().stm_recall_recent(200)
        if len(all_stm) < 10:
            return  # Not enough to consolidate

        # Group by session
        sessions: Dict[str, List] = {}
        for entry in all_stm:
            sid = entry.get("session_id", "unknown")
            if sid not in sessions:
                sessions[sid] = []
            sessions[sid].append(entry)

        for session_id, entries in sessions.items():
            if len(entries) < 5:
                continue  # Skip short sessions

            # Build a summary from the session
            user_msgs = [e["content"][:150] for e in entries if e["role"] == "user"]
            tools_used = list(set(e.get("tool_used", "") for e in entries if e.get("tool_used")))
            intents_seen = list(set(e.get("intent", "") for e in entries if e.get("intent")))

            summary_parts = []
            if user_msgs:
                summary_parts.append(f"User asked about: {'; '.join(user_msgs[:5])}")
            if tools_used:
                summary_parts.append(f"Tools used: {', '.join(tools_used)}")
            if intents_seen:
                summary_parts.append(f"Intents: {', '.join(intents_seen)}")

            summary = ". ".join(summary_parts)
            if summary:
                avg_importance = sum(e.get("importance", 0.5) for e in entries) / len(entries)
                _db().ltm_store(
                    memory_type="episodic",
                    summary=summary[:500],
                    source_sessions=session_id,
                    importance=min(1.0, avg_importance + 0.1)
                )
                logger.info(f"Consolidated session {session_id} ({len(entries)} turns) into LTM")

        # Auto-learn facts from scan results
        scans = _db().get_recent_scans(10)
        for scan in scans:
            if scan.get("results") and isinstance(scan["results"], dict):
                open_ports = scan["results"].get("open_ports", [])
                target = scan.get("target", "unknown")
                if open_ports:
                    ports_str = ", ".join([f"{p['port']}/{p['service']}" for p in open_ports])
                    learn_fact(
                        f"Host {target} has open ports: {ports_str}",
                        category="network",
                        confidence=0.95,
                        source=f"scan:{scan['id']}"
                    )

        logger.info("Memory consolidation complete")

    except Exception as e:
        logger.error(f"Memory consolidation error: {e}")
    finally:
        _consolidation_running = False


def start_consolidation_loop(interval_minutes: int = 5):
    """Start background memory consolidation loop."""
    def _loop():
        while True:
            time.sleep(interval_minutes * 60)
            try:
                consolidate_memories()
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}")

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    logger.info(f"Memory consolidation loop started (every {interval_minutes}min)")


# ═══════════════════════════════════════════════════════════════════════════
# Build Full Context for AI Brain
# ═══════════════════════════════════════════════════════════════════════════

def build_cognitive_context(session_id: str, user_message: str) -> str:
    """
    Build the full cognitive context to inject into the AutoGen brain.
    Combines: working memory + relevant LTM + skills + knowledge.
    """
    parts = []

    # 1. Working memory (recent conversation)
    wm = get_working_memory(session_id, 10)
    if wm:
        parts.append(f"=== WORKING MEMORY (recent conversation) ===\n{wm}")

    # 2. Relevant long-term memories
    ltm = recall_relevant_memories(user_message, 3)
    if ltm:
        parts.append(f"=== LONG-TERM MEMORY ===\n{ltm}")

    # 3. Skill hints (what tools worked before)
    skills = get_skill_hint(user_message)
    if skills:
        parts.append(f"=== LEARNED SKILLS ===\n{skills}")

    # 4. Relevant knowledge
    knowledge = recall_knowledge(user_message, 3)
    if knowledge:
        parts.append(f"=== KNOWLEDGE BASE ===\n{knowledge}")

    if not parts:
        return ""
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _compute_importance(content: str, tool_used: str = None) -> float:
    """Heuristic importance score (0-1)."""
    score = 0.5
    # Tool calls are more important
    if tool_used:
        score += 0.2
    # Longer content is slightly more important
    if len(content) > 200:
        score += 0.1
    # Security-related terms boost importance
    security_terms = {"vulnerability", "exploit", "attack", "breach", "critical", "alert", "scan"}
    if any(term in content.lower() for term in security_terms):
        score += 0.15
    return min(1.0, score)


def _extract_pattern(query: str) -> str:
    """Extract a short keyword pattern from a query for skill matching."""
    # Take first 3-4 meaningful words
    stop_words = {"the", "a", "an", "is", "are", "was", "and", "or", "to", "in", "on", "for", "my", "me", "what", "how", "show", "get", "list", "tell"}
    words = [w.lower() for w in query.split() if w.lower() not in stop_words and len(w) > 2]
    return " ".join(words[:4])
