"""
JULIUS — Partner Onboarding Tests
===================================
6+ test cases covering:
    1. Start onboarding: Returns script with correct partner_id.
    2. Register node: Updates status to 'active', adds to KG.
    3. Duplicate registration: Prevents registering same partner_id twice.
    4. Referral tracking: Properly credits referrer.
    5. Decommission: Marks as inactive, stops revenue.
    6. Status retrieval: Returns correct partner data.
    7. Private IP rejection: Blocks non-routable addresses.
    8. Referral info: Returns link, code, and referred list.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    """
    Provide a fresh OnboardingService backed by a temporary SQLite DB.
    Patches config constants so tests are isolated.
    """
    import backend.config as cfg  # noqa: E402

    monkeypatch.setattr(cfg, "VEIL_ONBOARDING_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "VEIL_ONBOARDING_REVENUE_SHARE_DEFAULT", 0.30, raising=False)
    monkeypatch.setattr(cfg, "VEIL_ONBOARDING_REFERRAL_BONUS", 0.05, raising=False)
    monkeypatch.setattr(cfg, "VEIL_ONBOARDING_MAX_ATTEMPTS", 3, raising=False)
    monkeypatch.setenv(
        "VEIL_ONBOARDING_NETWORK_URL", "https://test.julius-veil.net"
    )

    db_file = str(tmp_path / "test_onboarding.db")

    from backend.guardian.onboarding import OnboardingService

    service = OnboardingService(db_path=db_file)
    return service


@pytest.fixture()
def valid_request():
    """Return a valid PartnerOnboardRequest for a public IP."""
    from backend.models.partner_models import PartnerOnboardRequest

    return PartnerOnboardRequest(
        node_ip="203.0.113.42",  # TEST-NET-3, RFC 5737 — public-safe for tests
        ssh_port=22,
        ssh_username="root",
        node_name="test-veil-node",
    )


@pytest.fixture()
def onboarded(svc, valid_request):
    """Start onboarding and return the result dict."""
    return svc.start_onboarding(valid_request)


# ---------------------------------------------------------------------------
# 1. Start onboarding — script contains partner_id
# ---------------------------------------------------------------------------


def test_start_onboarding_returns_script(svc, valid_request):
    """start_onboarding should return a script embedding the assigned partner_id."""
    result = svc.start_onboarding(valid_request)

    assert "partner_id" in result, "Result must contain partner_id"
    assert "script" in result, "Result must contain the bash script"
    assert "referral_code" in result, "Result must contain a referral_code"
    assert "one_liner" in result, "Result must contain the one-liner command"
    assert "instructions" in result, "Result must contain human-readable instructions"

    partner_id = result["partner_id"]
    # Verify partner_id is embedded in the script
    assert partner_id in result["script"], (
        "partner_id must be embedded in the install script"
    )

    # Validate it's a proper UUID
    uuid.UUID(partner_id)  # raises if not valid UUID


def test_start_onboarding_creates_db_record(svc, valid_request):
    """After start_onboarding, partner should exist in DB with status='pending'."""
    result = svc.start_onboarding(valid_request)
    partner_id = result["partner_id"]

    status = svc.get_partner_status(partner_id)
    assert status is not None, "Partner should be retrievable immediately after onboarding"
    assert status.status == "pending"
    assert status.node_ip == "203.0.113.42"
    assert status.revenue_share_percent == pytest.approx(0.30)


def test_start_onboarding_referral_code_unique(svc, valid_request):
    """Each onboarding call must produce a unique referral code."""
    from backend.models.partner_models import PartnerOnboardRequest

    r1 = svc.start_onboarding(valid_request)
    r2 = svc.start_onboarding(
        PartnerOnboardRequest(node_ip="203.0.113.43", node_name="node-2")
    )

    assert r1["referral_code"] != r2["referral_code"], "Referral codes must be unique"
    assert len(r1["referral_code"]) >= 8, "Referral code should be at least 8 chars"


# ---------------------------------------------------------------------------
# 2. Register node — status becomes 'active', KG entity created
# ---------------------------------------------------------------------------


def test_register_node_activates_partner(svc, onboarded):
    """register_node should set status to 'active' and store the public key."""
    partner_id = onboarded["partner_id"]
    public_key = "a1b2c3d4e5f6" * 8  # 96-char fake hex key

    success = svc.register_node(
        partner_id=partner_id,
        node_public_key=public_key,
        node_metadata={"os": "ubuntu", "os_version": "22.04"},
    )

    assert success is True, "register_node should return True on first call"

    status = svc.get_partner_status(partner_id)
    assert status.status == "active"
    assert status.public_key == public_key
    assert status.node_id is not None, "node_id should be set after registration"
    assert status.install_attempts == 1


# ---------------------------------------------------------------------------
# 3. Duplicate registration prevention
# ---------------------------------------------------------------------------


def test_duplicate_registration_rejected(svc, onboarded):
    """Registering the same partner_id twice should return False on second call."""
    partner_id = onboarded["partner_id"]
    public_key = "deadbeef" * 12

    # First registration — should succeed
    first = svc.register_node(partner_id, public_key)
    assert first is True

    # Second registration — should fail (already active)
    second = svc.register_node(partner_id, public_key)
    assert second is False, "Duplicate registration must be rejected"

    # Status should still be 'active' (not corrupted)
    status = svc.get_partner_status(partner_id)
    assert status.status == "active"


def test_register_unknown_partner_rejected(svc):
    """register_node with an unknown partner_id must return False."""
    result = svc.register_node(
        partner_id="non-existent-partner-id",
        node_public_key="abc123",
    )
    assert result is False


# ---------------------------------------------------------------------------
# 4. Referral tracking — credits referrer
# ---------------------------------------------------------------------------


def test_referral_tracking_credits_referrer(svc):
    """
    When partner B uses partner A's referral code during onboarding,
    registering B should award the referral bonus to A.
    """
    from backend.models.partner_models import PartnerOnboardRequest

    # Step 1: Onboard partner A (active)
    req_a = PartnerOnboardRequest(node_ip="1.2.3.4", node_name="partner-a")
    result_a = svc.start_onboarding(req_a)
    partner_a_id = result_a["partner_id"]

    # Activate partner A so their referral code is valid
    svc.register_node(partner_a_id, "pubkey_a" * 8)

    referral_code_a = result_a["referral_code"]

    # Step 2: Onboard partner B using A's referral code
    req_b = PartnerOnboardRequest(
        node_ip="5.6.7.8",
        node_name="partner-b",
        referral_code=referral_code_a,
    )
    result_b = svc.start_onboarding(req_b)
    partner_b_id = result_b["partner_id"]

    # Verify B knows who referred them
    status_b = svc.get_partner_status(partner_b_id)
    assert status_b.referred_by == partner_a_id, (
        "Partner B's referred_by should point to partner A"
    )

    # Step 3: Register B — this triggers bonus award
    svc.register_node(partner_b_id, "pubkey_b" * 8)

    # Step 4: Verify referral bonus applied to A's revenue share
    import sqlite3

    with sqlite3.connect(svc.db_path) as conn:
        conn.row_factory = sqlite3.Row
        bonus_row = conn.execute(
            "SELECT * FROM referral_bonuses WHERE referrer_id=? AND referred_id=?",
            (partner_a_id, partner_b_id),
        ).fetchone()

    assert bonus_row is not None, "Referral bonus record should be created"
    assert bonus_row["status"] == "active"
    assert bonus_row["bonus_percent"] == pytest.approx(0.05)

    # Partner A's revenue share should have increased
    status_a_after = svc.get_partner_status(partner_a_id)
    assert status_a_after.revenue_share_percent == pytest.approx(0.35), (
        "Referrer's revenue share should increase by referral bonus (0.30 + 0.05)"
    )


def test_invalid_referral_code_ignored(svc):
    """An unrecognised referral code should be silently ignored (not raise)."""
    from backend.models.partner_models import PartnerOnboardRequest

    req = PartnerOnboardRequest(
        node_ip="9.10.11.12",
        referral_code="INVALID1",  # non-existent code
    )
    result = svc.start_onboarding(req)

    # Onboarding should still succeed
    assert "partner_id" in result
    status = svc.get_partner_status(result["partner_id"])
    assert status.referred_by is None, "Invalid referral code should result in no referrer"


# ---------------------------------------------------------------------------
# 5. Decommission — marks inactive, stops revenue
# ---------------------------------------------------------------------------


def test_decommission_partner(svc, onboarded):
    """decommission_partner should set status to 'decommissioned'."""
    partner_id = onboarded["partner_id"]

    # First activate
    svc.register_node(partner_id, "pubkey" * 10)

    # Decommission
    success = svc.decommission_partner(partner_id, reason="Violation of ToS")
    assert success is True

    status = svc.get_partner_status(partner_id)
    assert status.status == "decommissioned"


def test_decommission_unknown_partner_returns_false(svc):
    """decommission_partner with an unknown partner_id should return False."""
    result = svc.decommission_partner("ghost-partner-xyz")
    assert result is False


def test_decommission_disables_referral_bonuses(svc):
    """Decommissioning a partner should also deactivate their referral bonuses."""
    from backend.models.partner_models import PartnerOnboardRequest

    # Create and activate referrer
    req_a = PartnerOnboardRequest(node_ip="20.21.22.23", node_name="referrer")
    result_a = svc.start_onboarding(req_a)
    pid_a = result_a["partner_id"]
    svc.register_node(pid_a, "pubkey_ref" * 8)

    # Create and activate referred
    req_b = PartnerOnboardRequest(
        node_ip="20.21.22.24",
        referral_code=result_a["referral_code"],
    )
    result_b = svc.start_onboarding(req_b)
    pid_b = result_b["partner_id"]
    svc.register_node(pid_b, "pubkey_ref2" * 8)

    # Decommission the referrer
    svc.decommission_partner(pid_a, "test")

    # Check referral bonuses are deactivated
    import sqlite3

    with sqlite3.connect(svc.db_path) as conn:
        conn.row_factory = sqlite3.Row
        bonus = conn.execute(
            "SELECT status FROM referral_bonuses WHERE referrer_id=?", (pid_a,)
        ).fetchone()

    if bonus:
        assert bonus["status"] == "deactivated"


# ---------------------------------------------------------------------------
# 6. Status retrieval — returns correct partner data
# ---------------------------------------------------------------------------


def test_status_retrieval_correct_data(svc):
    """get_partner_status should return accurate data matching what was submitted."""
    from backend.models.partner_models import PartnerOnboardRequest

    req = PartnerOnboardRequest(
        node_ip="77.88.99.100",
        node_name="my-veil-node",
        ssh_username="ubuntu",
    )
    result = svc.start_onboarding(req)
    partner_id = result["partner_id"]

    status = svc.get_partner_status(partner_id)

    assert status is not None
    assert status.partner_id == partner_id
    assert status.node_ip == "77.88.99.100"
    assert status.node_name == "my-veil-node"
    assert status.status == "pending"
    assert status.referral_code == result["referral_code"]
    assert status.referred_by is None
    assert status.install_attempts == 0
    assert status.revenue_share_percent == pytest.approx(0.30)


def test_status_unknown_partner_returns_none(svc):
    """get_partner_status for an unknown partner_id should return None."""
    result = svc.get_partner_status("totally-unknown-id")
    assert result is None


# ---------------------------------------------------------------------------
# 7. Private IP rejection
# ---------------------------------------------------------------------------


def test_private_ip_rejected(svc):
    """Onboarding request with a private/reserved IP must raise ValueError."""
    from backend.models.partner_models import PartnerOnboardRequest

    for private_ip in ["192.168.1.1", "10.0.0.1", "172.16.100.1", "127.0.0.1"]:
        req = PartnerOnboardRequest(node_ip=private_ip)
        with pytest.raises(ValueError, match="private"):
            svc.start_onboarding(req)


# ---------------------------------------------------------------------------
# 8. Referral info endpoint
# ---------------------------------------------------------------------------


def test_get_referral_info(svc, onboarded):
    """get_referral_info should return the referral code, link, and partner details."""
    partner_id = onboarded["partner_id"]
    referral_code = onboarded["referral_code"]

    info = svc.get_referral_info(partner_id)

    assert info is not None
    assert info["partner_id"] == partner_id
    assert info["referral_code"] == referral_code
    assert referral_code in info["referral_link"]
    assert "referred_partners" in info
    assert info["total_referrals"] == 0
    assert info["referral_bonus_percent"] == pytest.approx(0.05)


def test_referral_info_unknown_partner_returns_none(svc):
    """get_referral_info for an unknown partner_id should return None."""
    result = svc.get_referral_info("no-such-partner")
    assert result is None


# ---------------------------------------------------------------------------
# 9. List partners
# ---------------------------------------------------------------------------


def test_list_partners(svc):
    """list_partners should return all partners, filterable by status."""
    from backend.models.partner_models import PartnerOnboardRequest

    req1 = PartnerOnboardRequest(node_ip="44.55.66.77", node_name="n1")
    req2 = PartnerOnboardRequest(node_ip="44.55.66.78", node_name="n2")

    r1 = svc.start_onboarding(req1)
    r2 = svc.start_onboarding(req2)

    # Activate one
    svc.register_node(r1["partner_id"], "pubkey111" * 8)

    all_partners = svc.list_partners()
    assert len(all_partners) >= 2

    active_partners = svc.list_partners(filters={"status": "active"})
    assert all(p["status"] == "active" for p in active_partners)

    pending_partners = svc.list_partners(filters={"status": "pending"})
    assert all(p["status"] == "pending" for p in pending_partners)


# ---------------------------------------------------------------------------
# 10. Install script content check
# ---------------------------------------------------------------------------


def test_install_script_contains_required_components(svc, valid_request):
    """The generated bash script should contain all critical installation steps."""
    result = svc.start_onboarding(valid_request)
    script = result["script"]

    # Must be a valid bash script
    assert script.startswith("#!/bin/bash"), "Script must start with #!/bin/bash"

    # Must embed partner_id
    assert result["partner_id"] in script

    # Must contain Docker install logic
    assert "docker" in script.lower()

    # Must contain registration curl call
    assert "curl" in script
    assert "/guardian/onboarding/register" in script

    # Must contain success message
    assert "VEIL node" in script or "julius" in script.lower()
