from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ModuleTier = Literal["core", "addendum"]
ModuleStatus = Literal["planned", "scaffolded", "active"]


@dataclass(frozen=True)
class PantheonModuleContract:
    module_id: str
    name: str
    tier: ModuleTier
    capability: str
    owner_service_path: str
    owner_router_path: str
    feature_flag: str
    status: ModuleStatus = "planned"


MODULE_CONTRACTS: list[PantheonModuleContract] = [
    PantheonModuleContract("nexus_gate", "NEXUS GATE", "core", "Conditioned payment orchestration", "backend/services/pantheon/nexus_gate", "backend/routers/pantheon.py", "PANTHEON_NEXUS_GATE_ENABLED"),
    PantheonModuleContract("salarium", "SALARIUM", "core", "Payroll orchestration and control", "backend/services/pantheon/salarium", "backend/routers/pantheon.py", "PANTHEON_SALARIUM_ENABLED"),
    PantheonModuleContract("dole_os", "DOLE OS", "core", "Benefit transfer orchestration", "backend/services/pantheon/dole_os", "backend/routers/pantheon.py", "PANTHEON_DOLE_OS_ENABLED"),
    PantheonModuleContract("ledgr", "LEDGR", "core", "Government procurement ledger", "backend/services/pantheon/ledgr", "backend/routers/pantheon.py", "PANTHEON_LEDGR_ENABLED"),
    PantheonModuleContract("axis", "AXIS", "core", "Transfer intelligence and routing", "backend/services/pantheon/axis", "backend/routers/pantheon.py", "PANTHEON_AXIS_ENABLED"),
    PantheonModuleContract("veridian", "VERIDIAN", "core", "Milestone verification and escrow", "backend/services/pantheon/veridian", "backend/routers/pantheon.py", "PANTHEON_VERIDIAN_ENABLED"),
    PantheonModuleContract("govprice", "GOVPRICE", "core", "Price intelligence and anomalies", "backend/services/pantheon/govprice", "backend/routers/pantheon.py", "PANTHEON_GOVPRICE_ENABLED"),
    PantheonModuleContract("cassini", "CASSINI", "core", "Fiscal risk analytics", "backend/services/pantheon/cassini", "backend/routers/pantheon.py", "PANTHEON_CASSINI_ENABLED"),
    PantheonModuleContract("lexis_fiscal", "LEXIS FISCAL", "core", "Regulatory and policy logic", "backend/services/pantheon/lexis_fiscal", "backend/routers/pantheon.py", "PANTHEON_LEXIS_FISCAL_ENABLED"),
    PantheonModuleContract("oracle_sovereign", "ORACLE SOVEREIGN", "core", "Treasury optimization", "backend/services/pantheon/oracle_sovereign", "backend/routers/pantheon.py", "PANTHEON_ORACLE_SOVEREIGN_ENABLED"),
    PantheonModuleContract("aurum", "AURUM", "core", "Asset and land intelligence", "backend/services/pantheon/aurum", "backend/routers/pantheon.py", "PANTHEON_AURUM_ENABLED"),
    PantheonModuleContract("aegis_ai", "AEGIS AI", "core", "Cross-domain AI risk scoring", "backend/services/pantheon/aegis_ai", "backend/routers/pantheon.py", "PANTHEON_AEGIS_AI_ENABLED"),
    PantheonModuleContract("prism_audit", "PRISM AUDIT", "addendum", "Immutable cryptographic audit chain", "backend/services/pantheon/prism_audit", "backend/routers/pantheon.py", "PANTHEON_PRISM_AUDIT_ENABLED", "scaffolded"),
    PantheonModuleContract("helix_cbdc", "HELIX CBDC", "addendum", "Programmable CBDC controls", "backend/services/pantheon/helix_cbdc", "backend/routers/pantheon.py", "PANTHEON_HELIX_CBDC_ENABLED"),
    PantheonModuleContract("taxon", "TAXON", "addendum", "Real-time transaction taxation", "backend/services/pantheon/taxon", "backend/routers/pantheon.py", "PANTHEON_TAXON_ENABLED"),
    PantheonModuleContract("oracle_policy", "ORACLE POLICY", "addendum", "Policy simulation and forecast", "backend/services/pantheon/oracle_policy", "backend/routers/pantheon.py", "PANTHEON_ORACLE_POLICY_ENABLED"),
    PantheonModuleContract("fortress", "FORTRESS", "addendum", "Access control matrix", "backend/services/pantheon/fortress", "backend/routers/pantheon.py", "PANTHEON_FORTRESS_ENABLED", "scaffolded"),
    PantheonModuleContract("sentinel_procurement", "SENTINEL PROCUREMENT", "addendum", "Procurement risk sentinels", "backend/services/pantheon/sentinel_procurement", "backend/routers/pantheon.py", "PANTHEON_SENTINEL_PROCUREMENT_ENABLED"),
    PantheonModuleContract("atlas_compliance", "ATLAS COMPLIANCE", "addendum", "Regulatory compliance automation", "backend/services/pantheon/atlas_compliance", "backend/routers/pantheon.py", "PANTHEON_ATLAS_COMPLIANCE_ENABLED"),
    PantheonModuleContract("meridian_grants", "MERIDIAN GRANTS", "addendum", "Grant allocation governance", "backend/services/pantheon/meridian_grants", "backend/routers/pantheon.py", "PANTHEON_MERIDIAN_GRANTS_ENABLED"),
    PantheonModuleContract("nebula_subsidy", "NEBULA SUBSIDY", "addendum", "Subsidy targeting intelligence", "backend/services/pantheon/nebula_subsidy", "backend/routers/pantheon.py", "PANTHEON_NEBULA_SUBSIDY_ENABLED"),
    PantheonModuleContract("vanguard_customs", "VANGUARD CUSTOMS", "addendum", "Customs and tariff controls", "backend/services/pantheon/vanguard_customs", "backend/routers/pantheon.py", "PANTHEON_VANGUARD_CUSTOMS_ENABLED"),
    PantheonModuleContract("citadel_identity", "CITADEL IDENTITY", "addendum", "Identity trust and recovery", "backend/services/pantheon/citadel_identity", "backend/routers/pantheon.py", "PANTHEON_CITADEL_IDENTITY_ENABLED"),
    PantheonModuleContract("horizon_liquidity", "HORIZON LIQUIDITY", "addendum", "Liquidity stress controls", "backend/services/pantheon/horizon_liquidity", "backend/routers/pantheon.py", "PANTHEON_HORIZON_LIQUIDITY_ENABLED"),
    PantheonModuleContract("phoenix_recovery", "PHOENIX RECOVERY", "addendum", "Continuity and failover governance", "backend/services/pantheon/phoenix_recovery", "backend/routers/pantheon.py", "PANTHEON_PHOENIX_RECOVERY_ENABLED"),
    PantheonModuleContract("obsidian_fraudnet", "OBSIDIAN FRAUDNET", "addendum", "Fraud graph and collusion detection", "backend/services/pantheon/obsidian_fraudnet", "backend/routers/pantheon.py", "PANTHEON_OBSIDIAN_FRAUDNET_ENABLED"),
    PantheonModuleContract("stratos_oversight", "STRATOS OVERSIGHT", "addendum", "Oversight authority analytics", "backend/services/pantheon/stratos_oversight", "backend/routers/pantheon.py", "PANTHEON_STRATOS_OVERSIGHT_ENABLED"),
]


def list_module_contracts() -> list[dict]:
    return [asdict(module) for module in MODULE_CONTRACTS]

