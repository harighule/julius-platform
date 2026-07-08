"""
JULIUS intelligence report service.

Aggregates data across modules and exports professional PDF and DOCX reports.
"""

from __future__ import annotations

import uuid
import zipfile
import traceback
import logging
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import SANDBOX_ROOT
from ..database import db
from ..routers import darkweb as darkweb_router
from ..routers import live as live_router
from ..routers import osint as osint_router

REPORTS_DIR = Path(SANDBOX_ROOT) / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.DEBUG)

_generated_reports: Dict[str, Dict[str, Any]] = {}

SEVERITY_BADGES = {
    "CRITICAL": {"fill": "C62828", "text": "FFFFFF", "pdf": colors.HexColor("#C62828")},
    "HIGH": {"fill": "EF6C00", "text": "FFFFFF", "pdf": colors.HexColor("#EF6C00")},
    "MEDIUM": {"fill": "F9A825", "text": "111827", "pdf": colors.HexColor("#F9A825")},
    "LOW": {"fill": "2E7D32", "text": "FFFFFF", "pdf": colors.HexColor("#2E7D32")},
    "INFO": {"fill": "1565C0", "text": "FFFFFF", "pdf": colors.HexColor("#1565C0")},
    "UNKNOWN": {"fill": "546E7A", "text": "FFFFFF", "pdf": colors.HexColor("#546E7A")},
}


def _utc_now() -> datetime:
    return datetime.utcnow()


def _safe_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_join(items: Any, default: str = "-") -> str:
    """Safely join any list of items to a string regardless of item type."""
    if not items:
        return default
    if not isinstance(items, list):
        return str(items) if items else default
    result = []
    for item in items:
        if item is None:
            continue
        elif isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            val = (
                item.get("address") or
                item.get("value") or
                item.get("ip") or
                item.get("name") or
                item.get("data") or
                (str(list(item.values())[0]) if item else default)
            )
            result.append(str(val))
        else:
            result.append(str(item))
    return ", ".join(result) if result else default


def _severity_key(value: Any) -> str:
    text = _safe_text(value, "UNKNOWN").upper()
    return text if text in SEVERITY_BADGES else "UNKNOWN"


def _severity_badge_pdf(value: Any) -> colors.Color:
    return SEVERITY_BADGES[_severity_key(value)]["pdf"]


def _severity_counts(items: Iterable[Dict[str, Any]], field: str) -> Dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0, "UNKNOWN": 0}
    for item in items:
        counts[_severity_key(item.get(field))] += 1
    return counts


def _parse_nvd_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _dedupe_vulnerabilities(vulnerabilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for vuln in vulnerabilities:
        key = (
            str(vuln.get("host", "")).strip().lower(),
            str(vuln.get("port", "")).strip(),
            str(vuln.get("service", "")).strip().lower(),
            str(vuln.get("title", "")).strip(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(vuln)
    return unique


def _group_identity_profiles(profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for identity in profiles:
        name = _safe_text(identity.get("name"), "Unknown")
        entry = grouped.setdefault(name, {
            "platforms": [],
            "emails": [],
            "phones": [],
            "handles": [],
        })
        platform = _safe_text(identity.get("platform"), "unknown")
        if platform not in entry["platforms"]:
            entry["platforms"].append(platform)
        email = _safe_text(identity.get("email"), "")
        if email and email not in entry["emails"]:
            entry["emails"].append(email)
        phone = _safe_text(identity.get("phone"), "")
        if phone and phone not in entry["phones"]:
            entry["phones"].append(phone)
        handle = _safe_text(identity.get("handle"), "")
        if handle and handle not in entry["handles"]:
            entry["handles"].append(handle)

    grouped_profiles: List[Dict[str, Any]] = []
    for name in sorted(grouped.keys(), key=lambda x: x.lower()):
        entry = grouped[name]
        grouped_profiles.append({
            "name": name,
            "platform": ", ".join(entry["platforms"]),
            "email": ", ".join(entry["emails"]) if entry["emails"] else "-",
            "phone": ", ".join(entry["phones"]) if entry["phones"] else "-",
            "handle": ", ".join(entry["handles"]) if entry["handles"] else "-",
        })
    return grouped_profiles


def _summarize_scan(scan: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    results = scan.get("results") if isinstance(scan.get("results"), dict) else {}
    open_ports = results.get("open_ports", []) if isinstance(results, dict) else []
    vulnerabilities = results.get("vulnerabilities", []) if isinstance(results, dict) else []
    return open_ports if isinstance(open_ports, list) else [], vulnerabilities if isinstance(vulnerabilities, list) else []


def _recommendations(report: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    if report["scanner"]["vulnerability_count"] > 0:
        recs.append("Prioritize patching externally exposed services with high and critical vulnerabilities.")
    if report["events"]["total_events"] > 50:
        recs.append("Review the elevated event volume and validate whether the recent spikes map to expected activity.")
    if report["darkweb"]["total"] > 0:
        recs.append("Follow up on dark web findings by validating exposed artifacts, credentials, and infrastructure references.")
    if report["threat_feeds"]["count"] > 0:
        recs.append("Block or monitor high-risk threat feed indicators in perimeter and endpoint controls.")
    if report["identities"]["count"] > 0:
        recs.append("Validate identity profiles against ongoing investigations and enrich them with confidence-scored link analysis.")
    if report["live_tools"].get("ip_lookup") or report["live_tools"].get("dns_lookup"):
        recs.append("Cross-check recent live tool lookups against scanner and event findings to confirm active exposure paths.")
    if not recs:
        recs.append("No immediate critical issues were detected. Maintain continuous monitoring and periodic reassessment.")
    return recs


async def _collect_report_data() -> Dict[str, Any]:
    try:
        scans = db.get_recent_scans(50)
    except Exception:
        print(f"ERROR fetching scans: {traceback.format_exc()}")
        scans = []

    try:
        vulnerabilities = db.get_vulnerabilities(limit=250)
    except Exception:
        print(f"ERROR fetching vulnerabilities: {traceback.format_exc()}")
        vulnerabilities = []

    try:
        event_stats = db.get_event_stats()
    except Exception:
        print(f"ERROR fetching event_stats: {traceback.format_exc()}")
        event_stats = {}

    try:
        recent_events = db.get_recent_events(100)
    except Exception:
        print(f"ERROR fetching recent_events: {traceback.format_exc()}")
        recent_events = []

    try:
        identities = db.get_identities()
    except Exception:
        print(f"ERROR fetching identities: {traceback.format_exc()}")
        identities = []

    grouped_identities = _group_identity_profiles(identities)

    try:
        darkweb = darkweb_router.get_investigation_report_snapshot(limit=20)
    except Exception:
        print(f"ERROR fetching darkweb snapshot: {traceback.format_exc()}")
        darkweb = {"total": 0, "completed": 0, "active": 0, "investigations": []}

    try:
        live_snapshot = live_router.get_live_report_snapshot() or {}
    except Exception:
        print(f"ERROR fetching live snapshot: {traceback.format_exc()}")
        live_snapshot = {}

    if not live_snapshot.get("cves"):
        try:
            live_snapshot["cves"] = await live_router.latest_cves_alias()
        except Exception:
            print(f"ERROR fetching CVEs: {traceback.format_exc()}")
            live_snapshot["cves"] = None

    try:
        last_ip_event = db.get_recent_events(1, event_type="ip_lookup")
        last_dns_event = db.get_recent_events(1, event_type="dns_lookup")
        live_snapshot["latest_ip_lookup"] = last_ip_event[0]["data"] if last_ip_event else live_snapshot.get("ip_lookup")
        live_snapshot["latest_dns_lookup"] = last_dns_event[0]["data"] if last_dns_event else live_snapshot.get("dns_lookup")
        live_snapshot["ip_lookups"] = db.get_recent_events(20, event_type="ip_lookup")
        live_snapshot["dns_lookups"] = db.get_recent_events(20, event_type="dns_lookup")
    except Exception:
        print(f"ERROR fetching live tool events: {traceback.format_exc()}")
        live_snapshot["latest_ip_lookup"] = None
        live_snapshot["latest_dns_lookup"] = None
        live_snapshot["ip_lookups"] = []
        live_snapshot["dns_lookups"] = []

    try:
        threat_payload = await osint_router.threat_feeds()
    except Exception:
        print(f"ERROR fetching threat_feeds: {traceback.format_exc()}")
        threat_payload = {"status": "error", "count": 0, "sources": {}, "data": [], "error": "fetch failed"}

    scanner_targets: List[Dict[str, Any]] = []
    scanner_open_ports = 0
    for scan in scans:
        try:
            open_ports, scan_vulns = _summarize_scan(scan)
            scanner_open_ports += len(open_ports)
            scanner_targets.append({
                "id": scan.get("id"),
                "target": scan.get("target"),
                "status": scan.get("status"),
                "started_at": scan.get("started_at"),
                "open_ports": open_ports,
                "open_port_count": len(open_ports),
                "vulnerability_count": len(scan_vulns),
            })
        except Exception:
            print(f"ERROR processing scan: {traceback.format_exc()}")
            continue

    threat_items = threat_payload.get("data", []) if isinstance(threat_payload.get("data"), list) else []
    threat_counts = _severity_counts(
        [{"risk_level": item.get("risk_level")} for item in threat_items],
        "risk_level",
    )

    vulnerabilities = _dedupe_vulnerabilities(vulnerabilities)
    vuln_counts = _severity_counts(vulnerabilities, "severity")

    summary = {
        "generated_at": _utc_now().isoformat(),
        "scan_count": len(scans),
        "open_port_count": scanner_open_ports,
        "vulnerability_count": len(vulnerabilities),
        "event_count": event_stats.get("total_events", 0),
        "darkweb_investigations": darkweb.get("total", 0),
        "threat_entries": len(threat_items),
        "identity_profiles": len(grouped_identities),
        "latest_cves": len((live_snapshot.get("cves") or {}).get("cves", [])) if isinstance(live_snapshot.get("cves"), dict) else 0,
    }

    report = {
        "title": "JULIUS INTELLIGENCE REPORT",
        "subtitle": "Cyber Threat Intelligence Analysis",
        "classification": "UNCLASSIFIED",
        "summary": summary,
        "scanner": {
            "targets": scanner_targets,
            "vulnerabilities": vulnerabilities,
            "vulnerability_counts": vuln_counts,
            "vulnerability_count": len(vulnerabilities),
        },
        "events": {
            "total_events": event_stats.get("total_events", 0),
            "distribution": event_stats.get("event_types", {}),
            "recent": recent_events[:25],
        },
        "darkweb": darkweb,
        "threat_feeds": {
            "count": len(threat_items),
            "sources": threat_payload.get("sources", {}),
            "severity_counts": threat_counts,
            "entries": threat_items[:40],
        },
        "identities": {
            "count": len(grouped_identities),
            "profiles": grouped_identities,
        },
        "live_tools": live_snapshot,
    }
    report["recommendations"] = _recommendations(report)
    return report


def _build_docx(report: Dict[str, Any], output_path: Path) -> None:
    core_created = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    body = []

    body.append(_docx_paragraph("JULIUS INTELLIGENCE REPORT", style="Title", align="center"))
    body.append(_docx_paragraph("Cyber Threat Intelligence Analysis", style="Subtitle", align="center"))
    body.append(_docx_spacer())
    body.append(_docx_paragraph(f"Date: {report['summary']['generated_at'][:10]}", align="center"))
    body.append(_docx_paragraph(f"Classification: {report['classification']}", align="center", bold=True))
    body.append(_docx_page_break())

    body.append(_docx_heading("Executive Summary", level=1))
    body.append(_docx_paragraph(
        "This report consolidates intelligence from the JULIUS platform across scanner, event, dark web, threat feed, identity, and live analysis modules."
    ))
    summary_rows = [
        ["Metric", "Value"],
        ["Network scans reviewed", report["summary"]["scan_count"]],
        ["Open ports observed", report["summary"]["open_port_count"]],
        ["Vulnerabilities identified", report["summary"]["vulnerability_count"]],
        ["Event bus entries", report["summary"]["event_count"]],
        ["Dark web investigations", report["summary"]["darkweb_investigations"]],
        ["Threat feed entries", report["summary"]["threat_entries"]],
        ["Identity profiles", report["summary"]["identity_profiles"]],
        ["Latest CVEs included", report["summary"]["latest_cves"]],
    ]
    body.append(_docx_table(summary_rows))

    body.append(_docx_heading("Network Scan Results", level=1))
    scan_rows = [["Target", "Status", "Open Ports", "Findings"]]
    for scan in report["scanner"]["targets"][:25]:
        try:
            ports = _safe_join([str(p.get("port")) for p in scan["open_ports"][:8]]) or "-"
            findings = f"{scan['vulnerability_count']} vulnerabilities"
            scan_rows.append([_safe_text(scan["target"]), _safe_text(scan["status"]), ports, findings])
        except Exception:
            continue
    body.append(_docx_table(scan_rows))

    body.append(_docx_heading("Vulnerability Assessment", level=1))
    vuln_rows = [["Severity", "Host", "Port", "Service", "Title", "CVE"]]
    for vuln in report["scanner"]["vulnerabilities"][:40]:
        try:
            vuln_rows.append([
                _severity_key(vuln.get("severity")),
                _safe_text(vuln.get("host")),
                _safe_text(vuln.get("port")),
                _safe_text(vuln.get("service")),
                _safe_text(vuln.get("title")),
                _safe_text(vuln.get("cve_id")),
            ])
        except Exception:
            continue
    body.append(_docx_table(vuln_rows, severity_column=0))

    body.append(_docx_heading("Event Bus Analysis", level=1))
    event_rows = [["Event Type", "Count"]]
    for event_type, count in sorted(report["events"]["distribution"].items()):
        event_rows.append([event_type, count])
    body.append(_docx_table(event_rows))

    body.append(_docx_heading("Dark Web Intelligence", level=1))
    body.append(_docx_paragraph(
        f"Investigations tracked: {report['darkweb']['total']} total, "
        f"{report['darkweb']['completed']} completed, {report['darkweb']['active']} active."
    ))
    dw_rows = [["Query", "Status", "Raw Results", "Filtered", "Scraped"]]
    for inv in report["darkweb"]["investigations"]:
        try:
            dw_rows.append([
                _safe_text(inv.get("query")),
                _safe_text(inv.get("status")),
                _safe_text(inv.get("raw_results_count")),
                _safe_text(inv.get("filtered_count")),
                _safe_text(inv.get("scraped_count")),
            ])
        except Exception:
            continue
    body.append(_docx_table(dw_rows))

    body.append(_docx_heading("Threat Intelligence Summary", level=1))
    threat_rows = [["Severity", "Count"]]
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"):
        threat_rows.append([severity, report["threat_feeds"]["severity_counts"].get(severity, 0)])
    body.append(_docx_table(threat_rows, severity_column=0))

    body.append(_docx_heading("Identity Profiles", level=1))
    identity_rows = [["Name", "Platform", "Email", "Phone", "Handle"]]
    for identity in report["identities"]["profiles"][:40]:
        try:
            identity_rows.append([
                _safe_text(identity.get("name")),
                _safe_text(identity.get("platform")),
                _safe_text(identity.get("email")),
                _safe_text(identity.get("phone")),
                _safe_text(identity.get("handle")),
            ])
        except Exception:
            continue
    body.append(_docx_table(identity_rows))

    body.append(_docx_heading("Live Tools", level=1))
    ip_lookup = report["live_tools"].get("latest_ip_lookup") or report["live_tools"].get("ip_lookup") or {}
    dns_lookup = report["live_tools"].get("latest_dns_lookup") or report["live_tools"].get("dns_lookup") or {}
    cves = ((report["live_tools"].get("cves") or {}).get("cves") or [])[:10]
    body.append(_docx_paragraph(
        f"Latest IP lookup: {_safe_text(ip_lookup.get('ip') if isinstance(ip_lookup, dict) else None)} | "
        f"Latest DNS lookup: {_safe_text(dns_lookup.get('domain') if isinstance(dns_lookup, dict) else None)} | "
        f"Latest CVEs tracked: {len(cves)}"
    ))

    ip_rows = [["IP Address", "Country", "City", "Organization", "Lat/Lon"]]
    for event in report["live_tools"].get("ip_lookups", []):
        try:
            data = event.get("data", {}) if isinstance(event, dict) else {}
            payload = data.get("result") or {} if isinstance(data, dict) else {}
            geo = payload.get("intel", {}).get("geolocation", {}) if isinstance(payload.get("intel"), dict) else {}
            latlon = "{}/{}".format(
                _safe_text(geo.get("lat") if isinstance(geo, dict) else None, "-"),
                _safe_text(geo.get("lon") if isinstance(geo, dict) else None, "-")
            )
            ip_rows.append([
                _safe_text(payload.get("ip") if isinstance(payload, dict) else None),
                _safe_text(geo.get("country") if isinstance(geo, dict) else None),
                _safe_text(geo.get("city") if isinstance(geo, dict) else None),
                _safe_text(geo.get("org") or geo.get("isp") if isinstance(geo, dict) else None),
                latlon,
            ])
        except Exception:
            print(f"IP row error: {traceback.format_exc()}")
            continue
    body.append(_docx_table(ip_rows))

    dns_rows = [["Domain", "Records Found", "IP Addresses"]]
    for event in report["live_tools"].get("dns_lookups", []):
        try:
            data = event.get("data", {}) if isinstance(event, dict) else {}
            payload = data.get("result") or {} if isinstance(data, dict) else {}
            records = payload.get("records") or [] if isinstance(payload, dict) else []
            records_text = _safe_join(records)[:120]
            record_count = len(records) if isinstance(records, list) else 0
            domain = _safe_text(payload.get("domain") if isinstance(payload, dict) else None)
            dns_rows.append([domain, str(record_count), records_text])
        except Exception:
            print(f"DNS row error: {traceback.format_exc()}")
            continue
    body.append(_docx_table(dns_rows))

    cve_rows = [["Severity", "CVE", "Published", "Description"]]
    for cve in cves:
        try:
            cve_rows.append([
                _severity_key(cve.get("severity")),
                _safe_text(cve.get("id")),
                _safe_text(cve.get("published")),
                _safe_text(cve.get("description"))[:110],
            ])
        except Exception:
            continue
    body.append(_docx_table(cve_rows, severity_column=0))

    body.append(_docx_heading("Conclusions and Recommendations", level=1))
    for idx, rec in enumerate(report["recommendations"], start=1):
        body.append(_docx_paragraph(f"{idx}. {rec}"))

    document_xml = _docx_document("".join(body))
    footer_xml = _docx_footer()
    header_xml = _docx_header()

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _docx_content_types())
        zf.writestr("_rels/.rels", _docx_root_rels())
        zf.writestr("docProps/core.xml", _docx_core_props(core_created))
        zf.writestr("docProps/app.xml", _docx_app_props())
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", _docx_styles())
        zf.writestr("word/settings.xml", _docx_settings())
        zf.writestr("word/header1.xml", header_xml)
        zf.writestr("word/footer1.xml", footer_xml)
        zf.writestr("word/_rels/document.xml.rels", _docx_document_rels())


def _build_pdf(report: Dict[str, Any], output_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="JTitle", fontSize=22, leading=28, alignment=TA_CENTER, textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name="JSub", fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="JHeading", fontSize=14, leading=18, alignment=TA_LEFT, textColor=colors.HexColor("#0f172a"), spaceAfter=8))
    styles.add(ParagraphStyle(name="JBody", fontSize=9, leading=13, alignment=TA_LEFT, textColor=colors.HexColor("#111827")))

    # Pre-build DNS table safely
    dns_table_data = [["Domain", "Records Found", "IP Addresses"]]
    try:
        for event in report["live_tools"].get("dns_lookups", []):
            try:
                data = event.get("data", {}) if isinstance(event, dict) else {}
                payload = data.get("result") or {} if isinstance(data, dict) else {}
                records = payload.get("records") or [] if isinstance(payload, dict) else []
                records_text = _safe_join(records)[:120]
                record_count = len(records) if isinstance(records, list) else 0
                domain = _safe_text(payload.get("domain") if isinstance(payload, dict) else None)
                dns_table_data.append([domain, str(record_count), records_text])
            except Exception:
                print(f"DNS row error: {traceback.format_exc()}")
                continue
    except Exception:
        print(f"DNS table error: {traceback.format_exc()}")
        dns_table_data = [["Domain", "Records Found", "IP Addresses"]]

    story: List[Any] = []

    try:
        print("Building cover page...")
        story.extend([
            Spacer(1, 50 * mm),
            Paragraph("JULIUS INTELLIGENCE REPORT", styles["JTitle"]),
            Spacer(1, 4 * mm),
            Paragraph("Cyber Threat Intelligence Analysis", styles["JSub"]),
            Spacer(1, 8 * mm),
            Paragraph(f"Date: {report['summary']['generated_at'][:10]}", styles["JSub"]),
            Paragraph(f"Classification: {report['classification']}", styles["JSub"]),
            PageBreak(),
        ])
    except Exception:
        print(f"FAILED at cover page: {traceback.format_exc()}")
        raise

    try:
        print("Building executive summary...")
        story.extend([
            Paragraph("Executive Summary", styles["JHeading"]),
            Paragraph(
                "This report consolidates intelligence from all major JULIUS modules into a single operational briefing for management review.",
                styles["JBody"],
            ),
            Spacer(1, 3 * mm),
            _pdf_table(
                [["Metric", "Value"]] + [
                    ["Network scans reviewed", report["summary"]["scan_count"]],
                    ["Open ports observed", report["summary"]["open_port_count"]],
                    ["Vulnerabilities identified", report["summary"]["vulnerability_count"]],
                    ["Event bus entries", report["summary"]["event_count"]],
                    ["Dark web investigations", report["summary"]["darkweb_investigations"]],
                    ["Threat feed entries", report["summary"]["threat_entries"]],
                    ["Identity profiles", report["summary"]["identity_profiles"]],
                    ["Latest CVEs included", report["summary"]["latest_cves"]],
                ]
            ),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at executive summary: {traceback.format_exc()}")
        raise

    try:
        print("Building network scan section...")
        scan_rows = [["Target", "Status", "Open Ports", "Findings"]]
        for scan in report["scanner"]["targets"][:20]:
            try:
                ports = _safe_join([str(p.get("port")) for p in scan["open_ports"][:8]]) or "-"
                scan_rows.append([
                    _safe_text(scan["target"]),
                    _safe_text(scan["status"]),
                    ports,
                    f"{scan['vulnerability_count']} vulnerabilities",
                ])
            except Exception:
                continue
        story.extend([
            Paragraph("Network Scan Results", styles["JHeading"]),
            _pdf_table(scan_rows, repeat_rows=1),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at network scan section: {traceback.format_exc()}")
        raise

    try:
        print("Building vulnerability assessment...")
        vuln_rows = [["Severity", "Host", "Port", "Service", "Title", "CVE"]]
        for vuln in report["scanner"]["vulnerabilities"][:30]:
            try:
                vuln_rows.append([
                    _severity_key(vuln.get("severity")),
                    _safe_text(vuln.get("host")),
                    _safe_text(vuln.get("port")),
                    _safe_text(vuln.get("service")),
                    _safe_text(vuln.get("title"))[:42],
                    _safe_text(vuln.get("cve_id")),
                ])
            except Exception:
                continue
        story.extend([
            Paragraph("Vulnerability Assessment", styles["JHeading"]),
            _pdf_table(vuln_rows, severity_column=0, repeat_rows=1),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at vulnerability assessment: {traceback.format_exc()}")
        raise

    try:
        print("Building event bus analysis...")
        story.extend([
            Paragraph("Event Bus Analysis", styles["JHeading"]),
            _pdf_table(
                [["Event Type", "Count"]] + [[k, v] for k, v in sorted(report["events"]["distribution"].items())],
                repeat_rows=1,
            ),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at event bus analysis: {traceback.format_exc()}")
        raise

    try:
        print("Building dark web intelligence...")
        dw_rows = [["Query", "Status", "Raw", "Filtered", "Scraped"]]
        for inv in report["darkweb"]["investigations"][:15]:
            try:
                dw_rows.append([
                    _safe_text(inv.get("query"))[:32],
                    _safe_text(inv.get("status")),
                    _safe_text(inv.get("raw_results_count")),
                    _safe_text(inv.get("filtered_count")),
                    _safe_text(inv.get("scraped_count")),
                ])
            except Exception:
                continue
        story.extend([
            Paragraph("Dark Web Intelligence", styles["JHeading"]),
            Paragraph(
                f"Investigations tracked: {report['darkweb']['total']} total, "
                f"{report['darkweb']['completed']} completed, {report['darkweb']['active']} active.",
                styles["JBody"],
            ),
            Spacer(1, 2 * mm),
            _pdf_table(dw_rows, repeat_rows=1),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at dark web intelligence: {traceback.format_exc()}")
        raise

    try:
        print("Building threat intelligence summary...")
        story.extend([
            Paragraph("Threat Intelligence Summary", styles["JHeading"]),
            _pdf_table(
                [["Severity", "Count"]] + [
                    [sev, report["threat_feeds"]["severity_counts"].get(sev, 0)]
                    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN")
                ],
                severity_column=0,
                repeat_rows=1,
            ),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at threat intelligence summary: {traceback.format_exc()}")
        raise

    try:
        print("Building identity profiles...")
        identity_rows = [["Name", "Platform", "Email", "Phone", "Handle"]]
        for identity in report["identities"]["profiles"][:30]:
            try:
                identity_rows.append([
                    _safe_text(identity.get("name")),
                    _safe_text(identity.get("platform")),
                    _safe_text(identity.get("email")),
                    _safe_text(identity.get("phone")),
                    _safe_text(identity.get("handle")),
                ])
            except Exception:
                continue
        story.extend([
            Paragraph("Identity Profiles", styles["JHeading"]),
            _pdf_table(identity_rows, repeat_rows=1),
            Spacer(1, 4 * mm),
        ])
    except Exception:
        print(f"FAILED at identity profiles: {traceback.format_exc()}")
        raise

    try:
        print("Building live tools section...")
        ip_lookup = report["live_tools"].get("latest_ip_lookup") or report["live_tools"].get("ip_lookup") or {}
        dns_lookup = report["live_tools"].get("latest_dns_lookup") or report["live_tools"].get("dns_lookup") or {}
        cves = (((report["live_tools"].get("cves") or {}).get("cves") or [])[:10])

        story.append(Paragraph("Live Tools", styles["JHeading"]))
        story.append(Paragraph(
            f"Latest IP lookup: {_safe_text(ip_lookup.get('ip') if isinstance(ip_lookup, dict) else None)} | "
            f"Latest DNS lookup: {_safe_text(dns_lookup.get('domain') if isinstance(dns_lookup, dict) else None)} | "
            f"Latest CVEs tracked: {len(cves)}",
            styles["JBody"],
        ))
        story.append(Spacer(1, 2 * mm))

        ip_rows = [["IP Address", "Country", "City", "Organization", "Lat/Lon"]]
        for event in report["live_tools"].get("ip_lookups", []):
            try:
                data = event.get("data", {}) if isinstance(event, dict) else {}
                payload = data.get("result") or {} if isinstance(data, dict) else {}
                geo = payload.get("intel", {}).get("geolocation", {}) if isinstance(payload.get("intel"), dict) else {}
                latlon = "{}/{}".format(
                    _safe_text(geo.get("lat") if isinstance(geo, dict) else None, "-"),
                    _safe_text(geo.get("lon") if isinstance(geo, dict) else None, "-"),
                )
                ip_rows.append([
                    _safe_text(payload.get("ip") if isinstance(payload, dict) else None),
                    _safe_text(geo.get("country") if isinstance(geo, dict) else None),
                    _safe_text(geo.get("city") if isinstance(geo, dict) else None),
                    _safe_text(geo.get("org") or geo.get("isp") if isinstance(geo, dict) else None),
                    latlon,
                ])
            except Exception:
                print(f"IP row error: {traceback.format_exc()}")
                continue

        story.append(_pdf_table(ip_rows, repeat_rows=1))
        story.append(Spacer(1, 2 * mm))
        story.append(_pdf_table(dns_table_data, repeat_rows=1))
        story.append(Spacer(1, 2 * mm))

        cve_rows = [["Severity", "CVE", "Published", "Description"]]
        for cve in cves:
            try:
                cve_rows.append([
                    _severity_key(cve.get("severity")),
                    _safe_text(cve.get("id")),
                    _safe_text(cve.get("published")),
                    _safe_text(cve.get("description"))[:66],
                ])
            except Exception:
                continue
        story.append(_pdf_table(cve_rows, severity_column=0, repeat_rows=1))
        story.append(Spacer(1, 4 * mm))
    except Exception:
        print(f"FAILED at live tools section: {traceback.format_exc()}")
        raise

    try:
        print("Building conclusions and recommendations...")
        story.append(Paragraph("Conclusions and Recommendations", styles["JHeading"]))
        for rec in report["recommendations"]:
            story.append(Paragraph(f"- {escape(rec)}", styles["JBody"]))
    except Exception:
        print(f"FAILED at recommendations: {traceback.format_exc()}")
        raise

    def on_page(canvas, pdf_doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(colors.HexColor("#0b1220"))
        canvas.rect(0, height - 22 * mm, width, 22 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(16 * mm, height - 12 * mm, "JULIUS INTELLIGENCE PLATFORM")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#cbd5e1"))
        canvas.drawRightString(width - 16 * mm, height - 12 * mm, f"Classification: {report['classification']}")
        canvas.setStrokeColor(colors.HexColor("#00d4ff"))
        canvas.setLineWidth(1)
        canvas.line(16 * mm, height - 15 * mm, width - 16 * mm, height - 15 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(16 * mm, 10 * mm, "JULIUS Intelligence Platform")
        canvas.drawRightString(width - 16 * mm, 10 * mm, f"Page {pdf_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def _pdf_table(rows: List[List[Any]], severity_column: int | None = None, repeat_rows: int = 0) -> Table:
    normalized = [[_safe_text(cell, "") for cell in row] for row in rows]
    table = Table(normalized, repeatRows=repeat_rows)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    if severity_column is not None:
        for row_idx in range(1, len(normalized)):
            severity = _severity_key(normalized[row_idx][severity_column])
            style.add("BACKGROUND", (severity_column, row_idx), (severity_column, row_idx), _severity_badge_pdf(severity))
            style.add("TEXTCOLOR", (severity_column, row_idx), (severity_column, row_idx), colors.white if severity != "MEDIUM" else colors.black)
            style.add("FONTNAME", (severity_column, row_idx), (severity_column, row_idx), "Helvetica-Bold")
    table.setStyle(style)
    return table


async def generate_full_report_bundle() -> Dict[str, Any]:
    logging.basicConfig(level=logging.DEBUG)
    try:
        report = await _collect_report_data()
        report_id = f"julius-report-{_utc_now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        pdf_path = REPORTS_DIR / f"{report_id}.pdf"
        docx_path = REPORTS_DIR / f"{report_id}.docx"

        _build_pdf(report, pdf_path)
        _build_docx(report, docx_path)

        metadata = {
            "report_id": report_id,
            "generated_at": report["summary"]["generated_at"],
            "summary": report["summary"],
            "docx_path": str(docx_path),
            "pdf_path": str(pdf_path),
        }
        _generated_reports[report_id] = metadata
        return {
            "report_id": report_id,
            "generated_at": metadata["generated_at"],
            "summary": metadata["summary"],
            "downloads": {
                "docx": f"/api/reports/full/{report_id}/docx",
                "pdf": f"/api/reports/full/{report_id}/pdf",
            },
        }
    except Exception:
        logging.error(f"FULL REPORT BUNDLE ERROR:\n{traceback.format_exc()}")
        raise


def get_generated_report_file(report_id: str, fmt: str) -> Tuple[Path, str]:
    meta = _generated_reports.get(report_id)
    if not meta:
        raise FileNotFoundError(report_id)

    if fmt == "pdf":
        path = Path(meta["pdf_path"])
        media_type = "application/pdf"
    elif fmt == "docx":
        path = Path(meta["docx_path"])
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise ValueError(fmt)

    if not path.exists():
        raise FileNotFoundError(str(path))
    return path, media_type


def _docx_document(body_xml: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body>"
        f"{body_xml}"
        '<w:sectPr>'
        '<w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1080" w:bottom="1080" w:left="1080" w:header="720" w:footer="720" w:gutter="0"/>'
        "</w:sectPr>"
        "</w:body></w:document>"
    )


def _docx_header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tr>'
        '<w:tc><w:tcPr><w:shd w:fill="0B1220"/></w:tcPr>'
        '<w:p><w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="22"/></w:rPr>'
        '<w:t>JULIUS Intelligence Platform</w:t></w:r></w:p>'
        '<w:p><w:r><w:rPr><w:color w:val="93C5FD"/><w:sz w:val="16"/></w:rPr>'
        '<w:t>JULIUS INTELLIGENCE REPORT</w:t></w:r></w:p>'
        "</w:tc></w:tr></w:tbl></w:hdr>"
    )


def _docx_footer() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:r><w:rPr><w:color w:val="64748B"/><w:sz w:val="16"/></w:rPr>'
        '<w:t>JULIUS Intelligence Platform</w:t></w:r>'
        '<w:r><w:tab/></w:r>'
        '<w:r><w:rPr><w:color w:val="64748B"/><w:sz w:val="16"/></w:rPr><w:t>Page </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>1</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p></w:ftr>"
    )


def _docx_content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _docx_root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _docx_document_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        "</Relationships>"
    )


def _docx_core_props(created: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>JULIUS Intelligence Report</dc:title>'
        '<dc:creator>JULIUS Intelligence Platform</dc:creator>'
        '<cp:lastModifiedBy>JULIUS Intelligence Platform</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _docx_app_props() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>JULIUS Intelligence Platform</Application>"
        "</Properties>"
    )


def _docx_settings() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:zoom w:percent="100"/></w:settings>'
    )


def _docx_styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="34"/><w:color w:val="0F172A"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:sz w:val="24"/><w:color w:val="475569"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="28"/><w:color w:val="0F172A"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="24"/><w:color w:val="0F172A"/></w:rPr></w:style>'
        "</w:styles>"
    )


def _docx_heading(text: str, level: int = 1) -> str:
    style = f"Heading{1 if level <= 1 else 2}"
    return _docx_paragraph(text, style=style)


def _docx_paragraph(text: str, style: str | None = None, align: str | None = None,
                    bold: bool = False) -> str:
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:p>{ppr_xml}<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(_safe_text(text, ''))}</w:t></w:r></w:p>"


def _docx_spacer() -> str:
    return "<w:p/>"


def _docx_page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _docx_table(rows: List[List[Any]], severity_column: int | None = None) -> str:
    tbl_rows = []
    for row_idx, row in enumerate(rows):
        cells = []
        for col_idx, cell in enumerate(row):
            text = escape(_safe_text(cell, ""))
            tc_pr = ""
            run_pr = ""
            if row_idx == 0:
                tc_pr = '<w:tcPr><w:shd w:fill="111827"/></w:tcPr>'
                run_pr = '<w:rPr><w:b/><w:color w:val="FFFFFF"/></w:rPr>'
            elif severity_column is not None and col_idx == severity_column:
                badge = SEVERITY_BADGES[_severity_key(cell)]
                tc_pr = f'<w:tcPr><w:shd w:fill="{badge["fill"]}"/></w:tcPr>'
                run_pr = f'<w:rPr><w:b/><w:color w:val="{badge["text"]}"/></w:rPr>'
            cells.append(f"<w:tc>{tc_pr}<w:p><w:r>{run_pr}<w:t>{text}</w:t></w:r></w:p></w:tc>")
        tbl_rows.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return (
        '<w:tbl><w:tblPr><w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
        f"</w:tblBorders></w:tblPr>{''.join(tbl_rows)}</w:tbl>"
    )