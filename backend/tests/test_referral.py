"""
JULIUS — Referral System Tests
===============================
Covers:
  1. Referral code generation: unique, correctly formatted.
  2. Apply referral: links partners correctly.
  3. Referral bonus calculation: 5% of commission.
  4. Multi-level bonus: correct distribution up to 3 levels.
  5. Cooldown period: bonus not applied before cooldown expires.
  6. Invalid referral code: rejected.
  7. Self-referral: prevented.
  8. Referral analytics: correct totals.
  9. Duplicate referral application: rejected.
 10. Referral tree: correct structure.
 11. Referral earnings: correct summary.
 12. process_referral_bonuses: no referrer in chain → empty dict.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    """
    Fresh ReferralService backed by a temp SQLite DB.
    Monkeypatches config constants for deterministic behaviour.
    """
    import backend.config as cfg  # noqa

    monkeypatch.setattr(cfg, "VEIL_REFERRAL_BONUS_PERCENT", 0.05, raising=False)
    monkeypatch.setattr(cfg, "VEIL_REFERRAL_MAX_LEVELS", 3, raising=False)
    monkeypatch.setattr(cfg, "VEIL_REFERRAL_COOLDOWN_DAYS", 7, raising=False)

    db_file = str(tmp_path / "test_referral.db")

    from backend.guardian.referral import ReferralService

    service = ReferralService(db_path=db_file)
    # Override config from monkeypatch (service reads at __init__)
    service.referral_bonus = 0.05
    service.max_levels = 3
    service.cooldown_days = 7
    return service


@pytest.fixture()
def partner_a():
    return str(uuid.uuid4())


@pytest.fixture()
def partner_b():
    return str(uuid.uuid4())


@pytest.fixture()
def partner_c():
    return str(uuid.uuid4())


@pytest.fixture()
def partner_d():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Helper: register a partner code and optionally apply it under someone
# ---------------------------------------------------------------------------

def _setup_referral(svc, referrer_id, referred_id, past_cooldown=False):
    """
    Register a code for referrer_id, then apply it for referred_id.
    If past_cooldown=True, force the cooldown_until into the past so
    bonuses can be processed immediately.
    """
    code = svc.generate_referral_code(referrer_id)
    svc.register_partner_code(referrer_id, code)

    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code=code, partner_id=referred_id)
    result = svc.apply_referral(req)
    assert result, "Referral apply should succeed"

    if past_cooldown:
        # Move cooldown_until into the past
        past = _iso(_utcnow() - timedelta(days=8))
        with sqlite3.connect(svc.db_path) as conn:
            conn.execute(
                "UPDATE referrals SET cooldown_until = ? WHERE referred_partner_id = ?",
                (past, referred_id),
            )

    return code


# ---------------------------------------------------------------------------
# Test 1 — Referral code generation: unique, correctly formatted
# ---------------------------------------------------------------------------


def test_generate_referral_code_format(svc, partner_a):
    """Generated code must start with 'JULIUS-' and have 8 trailing chars."""
    code = svc.generate_referral_code(partner_a)
    assert code.startswith("JULIUS-"), f"Code should start with 'JULIUS-', got: {code}"
    suffix = code[len("JULIUS-"):]
    assert len(suffix) == 8, f"Suffix should be 8 chars, got {len(suffix)}: {suffix}"
    assert suffix == suffix.upper(), "Suffix should be uppercase"


def test_generate_referral_code_unique(svc, partner_a, partner_b):
    """Two different partners should get different codes."""
    code_a = svc.generate_referral_code(partner_a)
    svc.register_partner_code(partner_a, code_a)

    code_b = svc.generate_referral_code(partner_b)
    svc.register_partner_code(partner_b, code_b)

    assert code_a != code_b, "Referral codes must be unique across partners"


# ---------------------------------------------------------------------------
# Test 2 — Apply referral: links partners correctly
# ---------------------------------------------------------------------------


def test_apply_referral_links_partners(svc, partner_a, partner_b):
    """After applying, the referral row should link referrer → referred."""
    code = svc.generate_referral_code(partner_a)
    svc.register_partner_code(partner_a, code)

    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code=code, partner_id=partner_b)
    success = svc.apply_referral(req)
    assert success, "apply_referral should return True for a valid code"

    # Verify DB link
    with sqlite3.connect(svc.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM referrals WHERE referred_partner_id = ?",
            (partner_b,),
        ).fetchone()

    assert row is not None, "A referral row should exist for the referred partner"
    assert row["referrer_partner_id"] == partner_a
    assert row["referred_partner_id"] == partner_b
    assert row["status"] == "active"
    assert row["cooldown_until"] is not None, "Cooldown timestamp should be set"


# ---------------------------------------------------------------------------
# Test 3 — Referral bonus calculation: 5% of commission
# ---------------------------------------------------------------------------


def test_referral_bonus_calculation(svc, partner_a):
    """calculate_referral_bonus should return exactly 5% of commission."""
    commission = 10.0
    bonus = svc.calculate_referral_bonus(partner_a, commission)
    assert abs(bonus - 0.5) < 1e-9, f"5% of 10.0 should be 0.5, got {bonus}"

    commission2 = 0.002
    bonus2 = svc.calculate_referral_bonus(partner_a, commission2)
    assert abs(bonus2 - 0.0001) < 1e-9, f"5% of 0.002 should be 0.0001, got {bonus2}"


# ---------------------------------------------------------------------------
# Test 4 — Multi-level bonus: correct distribution up to 3 levels
# ---------------------------------------------------------------------------


def test_multi_level_bonus_three_levels(svc, partner_a, partner_b, partner_c, partner_d):
    """
    Chain: A → B → C → D  (A referred B, B referred C, C referred D)
    When D earns commission, bonuses should flow: C gets L1, B gets L2, A gets L3.
    """
    # Set up chain (A→B→C→D), all past cooldown
    _setup_referral(svc, partner_a, partner_b, past_cooldown=True)
    _setup_referral(svc, partner_b, partner_c, past_cooldown=True)
    _setup_referral(svc, partner_c, partner_d, past_cooldown=True)

    commission = 100.0
    payments = svc.process_referral_bonuses(
        partner_id=partner_d, commission=commission
    )

    # L1 bonus to C: 5% of 100 = 5.0
    assert partner_c in payments, "L1 referrer (C) should receive a bonus"
    assert abs(payments[partner_c] - 5.0) < 1e-9, f"L1 bonus wrong: {payments[partner_c]}"

    # L2 bonus to B: 5% of 100 = 5.0
    assert partner_b in payments, "L2 referrer (B) should receive a bonus"
    assert abs(payments[partner_b] - 5.0) < 1e-9, f"L2 bonus wrong: {payments[partner_b]}"

    # L3 bonus to A: 5% of 100 = 5.0
    assert partner_a in payments, "L3 referrer (A) should receive a bonus"
    assert abs(payments[partner_a] - 5.0) < 1e-9, f"L3 bonus wrong: {payments[partner_a]}"


def test_multi_level_stops_at_max_levels(svc):
    """Chain deeper than max_levels should not distribute beyond level 3."""
    # 5-level chain: E→D→C→B→A
    ids = [str(uuid.uuid4()) for _ in range(5)]
    # ids[0] is top-level, ids[4] is the earner
    for i in range(len(ids) - 1):
        _setup_referral(svc, ids[i], ids[i + 1], past_cooldown=True)

    payments = svc.process_referral_bonuses(
        partner_id=ids[4], commission=100.0
    )

    # Only 3 levels should be paid (ids[3], ids[2], ids[1])
    assert len(payments) == 3, f"Should pay exactly 3 levels, got {len(payments)}"
    assert ids[0] not in payments, "Level 4 referrer should NOT receive a bonus"


# ---------------------------------------------------------------------------
# Test 5 — Cooldown period: bonus not applied before cooldown expires
# ---------------------------------------------------------------------------


def test_cooldown_prevents_bonus(svc, partner_a, partner_b):
    """
    When the referral is still in cooldown, process_referral_bonuses should
    return an empty dict (no bonuses paid).
    """
    # Set up WITHOUT clearing cooldown
    code = svc.generate_referral_code(partner_a)
    svc.register_partner_code(partner_a, code)

    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code=code, partner_id=partner_b)
    svc.apply_referral(req)

    # cooldown_until is in the future (7 days from now)
    payments = svc.process_referral_bonuses(
        partner_id=partner_b, commission=100.0
    )
    assert payments == {}, (
        "No bonuses should be paid while referral is in cooldown, "
        f"got: {payments}"
    )


def test_bonus_paid_after_cooldown(svc, partner_a, partner_b):
    """After cooldown expires, bonuses should be distributed normally."""
    _setup_referral(svc, partner_a, partner_b, past_cooldown=True)

    payments = svc.process_referral_bonuses(
        partner_id=partner_b, commission=50.0
    )
    assert partner_a in payments, "Bonus should be paid after cooldown"
    assert abs(payments[partner_a] - 2.5) < 1e-9  # 5% of 50


# ---------------------------------------------------------------------------
# Test 6 — Invalid referral code: rejected
# ---------------------------------------------------------------------------


def test_invalid_referral_code_rejected(svc, partner_b):
    """apply_referral with a non-existent code should return False."""
    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code="JULIUS-BADCODE", partner_id=partner_b)
    result = svc.apply_referral(req)
    assert result is False, "Invalid referral code should be rejected"


def test_expired_or_used_code_rejected(svc, partner_a, partner_b, partner_c):
    """A code that has already been applied should be rejected for a third partner."""
    code = _setup_referral(svc, partner_a, partner_b)

    from backend.models.referral_models import ApplyReferralRequest

    # Try to reuse the same code for partner_c
    req = ApplyReferralRequest(referral_code=code, partner_id=partner_c)
    result = svc.apply_referral(req)
    assert result is False, "Already-used referral code should be rejected"


# ---------------------------------------------------------------------------
# Test 7 — Self-referral: prevented
# ---------------------------------------------------------------------------


def test_self_referral_prevented(svc, partner_a):
    """A partner cannot apply their own referral code."""
    code = svc.generate_referral_code(partner_a)
    svc.register_partner_code(partner_a, code)

    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code=code, partner_id=partner_a)
    result = svc.apply_referral(req)
    assert result is False, "Self-referral should be prevented"


# ---------------------------------------------------------------------------
# Test 8 — Referral analytics: correct totals
# ---------------------------------------------------------------------------


def test_referral_analytics_totals(svc, partner_a, partner_b, partner_c):
    """get_analytics should return accurate counts and total bonus paid."""
    _setup_referral(svc, partner_a, partner_b, past_cooldown=True)
    _setup_referral(svc, partner_a, partner_c, past_cooldown=True)

    # Process bonuses for both referred partners
    svc.process_referral_bonuses(partner_id=partner_b, commission=100.0)
    svc.process_referral_bonuses(partner_id=partner_c, commission=200.0)

    analytics = svc.get_analytics()

    assert analytics["total_referrals_created"] == 2, (
        f"Expected 2 total referrals, got {analytics['total_referrals_created']}"
    )
    assert analytics["active_referrals"] == 2, (
        f"Expected 2 active, got {analytics['active_referrals']}"
    )
    # Total bonus: 5% of 100 + 5% of 200 = 5 + 10 = 15
    expected_bonus = 5.0 + 10.0
    assert abs(analytics["total_referral_bonus_paid"] - expected_bonus) < 1e-9, (
        f"Expected total bonus {expected_bonus}, got {analytics['total_referral_bonus_paid']}"
    )
    assert analytics["referral_bonus_percent"] == 0.05
    assert analytics["max_levels"] == 3


def test_analytics_empty_db(svc):
    """Analytics on an empty DB should return zeros without raising."""
    analytics = svc.get_analytics()
    assert analytics["total_referrals_created"] == 0
    assert analytics["active_referrals"] == 0
    assert analytics["total_referral_bonus_paid"] == 0.0
    assert analytics["top_referrers"] == []


# ---------------------------------------------------------------------------
# Test 9 — Duplicate referral application: rejected
# ---------------------------------------------------------------------------


def test_duplicate_referral_rejected(svc, partner_a, partner_b, partner_c):
    """A partner that has already been referred cannot be referred again."""
    _setup_referral(svc, partner_a, partner_b)

    # partner_c tries to refer partner_b again
    code_c = svc.generate_referral_code(partner_c)
    svc.register_partner_code(partner_c, code_c)

    from backend.models.referral_models import ApplyReferralRequest

    req = ApplyReferralRequest(referral_code=code_c, partner_id=partner_b)
    result = svc.apply_referral(req)
    assert result is False, "Should reject applying a second referral to an already-referred partner"


# ---------------------------------------------------------------------------
# Test 10 — Referral tree: correct structure
# ---------------------------------------------------------------------------


def test_referral_tree_structure(svc, partner_a, partner_b, partner_c):
    """get_referral_tree should return a nested dict matching the referral chain."""
    # A → B → C
    _setup_referral(svc, partner_a, partner_b)
    _setup_referral(svc, partner_b, partner_c)

    tree = svc.get_referral_tree(partner_a)

    assert tree.root == partner_a
    assert partner_b in tree.tree, "B should appear as direct child of A"

    b_node = tree.tree[partner_b]
    assert "children" in b_node
    assert partner_c in b_node["children"], "C should appear as child of B"


def test_referral_tree_depth_capped(svc):
    """Tree depth must not exceed max_levels even for deeper chains."""
    ids = [str(uuid.uuid4()) for _ in range(6)]
    for i in range(5):
        _setup_referral(svc, ids[i], ids[i + 1])

    tree = svc.get_referral_tree(ids[0])
    assert tree.depth <= 3, f"Tree depth {tree.depth} exceeds max_levels=3"


# ---------------------------------------------------------------------------
# Test 11 — Referral earnings summary
# ---------------------------------------------------------------------------


def test_referral_earnings_summary(svc, partner_a, partner_b):
    """get_referral_earnings should reflect bonuses already paid."""
    _setup_referral(svc, partner_a, partner_b, past_cooldown=True)
    svc.process_referral_bonuses(partner_id=partner_b, commission=200.0)

    earnings = svc.get_referral_earnings(partner_a)

    assert earnings["partner_id"] == partner_a
    assert earnings["total_referred"] == 1
    assert earnings["active_referred"] == 1
    expected = 200.0 * 0.05  # 10.0
    assert abs(earnings["total_bonus_earned"] - expected) < 1e-9, (
        f"Expected {expected}, got {earnings['total_bonus_earned']}"
    )
    assert len(earnings["payments"]) >= 1, "Payment records should be present"


# ---------------------------------------------------------------------------
# Test 12 — process_referral_bonuses with no referrer → empty dict
# ---------------------------------------------------------------------------


def test_no_referrer_returns_empty(svc, partner_a):
    """A partner with no referrer should produce no bonus payments."""
    payments = svc.process_referral_bonuses(partner_id=partner_a, commission=500.0)
    assert payments == {}, (
        f"Expected empty payments dict for un-referred partner, got {payments}"
    )
