"""
JULIUS Report Generator — Compiles workflow results into structured reports.
"""

import json
import os
from datetime import datetime
from typing import Optional

from ..config import SANDBOX_ROOT


def _dedupe_vulnerabilities(vulnerabilities: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for vuln in vulnerabilities:
        if not isinstance(vuln, dict):
            continue
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


def generate_report(db, workflow_id: int, fmt: str = "json") -> Optional[str]:
    """Generate a report from a completed workflow and save to sandbox."""
    workflow = db.get_workflow_with_steps(workflow_id)
    if not workflow:
        return None

    report = {
        "title": workflow["name"],
        "workflow_id": workflow_id,
        "status": workflow.get("status", "unknown"),
        "generated_at": datetime.utcnow().isoformat(),
        "summary": _generate_summary(workflow),
        "sections": _compile_sections(workflow),
        "recommendations": _generate_recommendations(workflow),
    }

    filename = f"report_{workflow_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    if fmt == "md":
        content = _to_markdown(report)
        filepath = os.path.join(SANDBOX_ROOT, f"{filename}.md")
    else:
        content = json.dumps(report, indent=2)
        filepath = os.path.join(SANDBOX_ROOT, f"{filename}.json")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def _generate_summary(workflow: dict) -> str:
    steps = workflow.get("steps", [])
    completed = sum(1 for s in steps if s.get("status") == "completed")
    failed = sum(1 for s in steps if s.get("status") == "failed")
    return (
        f"Workflow '{workflow['name']}' executed {len(steps)} steps. "
        f"{completed} completed successfully, {failed} failed. "
        f"Final status: {workflow.get('status', 'unknown')}."
    )


def _compile_sections(workflow: dict) -> list:
    sections = []
    for step in workflow.get("steps", []):
        result = step.get("result_json", {})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = {"raw": result}

        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and isinstance(item.get("vulnerabilities"), list):
                    item["vulnerabilities"] = _dedupe_vulnerabilities(item["vulnerabilities"])
        elif isinstance(result, dict) and isinstance(result.get("vulnerabilities"), list):
            result["vulnerabilities"] = _dedupe_vulnerabilities(result["vulnerabilities"])

        sections.append({
            "step": step["step_index"],
            "service": step["service"],
            "action": step["action"],
            "status": step["status"],
            "started_at": step.get("started_at"),
            "completed_at": step.get("completed_at"),
            "findings": result,
        })
    return sections


def _generate_recommendations(workflow: dict) -> list:
    recs = []
    for step in workflow.get("steps", []):
        result = step.get("result_json", {})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = {}

        if step["service"] == "scan":
            open_count = result.get("open_ports", 0)
            if isinstance(open_count, list):
                open_count = len(open_count)
            vuln_count = result.get("vulnerabilities", 0)
            if isinstance(vuln_count, list):
                vuln_count = len(vuln_count)
            if open_count > 5:
                recs.append(f"Reduce attack surface: {open_count} open ports found. Review and close unnecessary services.")
            if vuln_count > 0:
                recs.append(f"Patch {vuln_count} vulnerabilities detected during scan.")

        elif step["service"] == "darkweb":
            results_count = result.get("results", 0)
            if results_count > 0:
                recs.append(f"Dark web exposure detected: {results_count} mentions found. Investigate leaked data.")

        elif step["service"] == "behavioral":
            alerts = result.get("recent_alerts", 0)
            if alerts > 0:
                recs.append(f"Review {alerts} recent behavioral alerts for potential threats.")

    if not recs:
        recs.append("No critical findings. Continue regular monitoring.")
    return recs


def _to_markdown(report: dict) -> str:
    lines = [
        f"# {report['title']}",
        f"",
        f"**Generated:** {report['generated_at']}",
        f"**Workflow ID:** {report['workflow_id']}",
        f"**Status:** {report['status']}",
        f"",
        f"## Summary",
        f"",
        report["summary"],
        f"",
        f"## Steps",
        f"",
    ]

    for section in report["sections"]:
        lines.append(f"### Step {section['step']}: {section['service']}/{section['action']}")
        lines.append(f"")
        lines.append(f"- **Status:** {section['status']}")
        if section.get("started_at"):
            lines.append(f"- **Started:** {section['started_at']}")
        if section.get("completed_at"):
            lines.append(f"- **Completed:** {section['completed_at']}")
        lines.append(f"")
        lines.append("```json")
        lines.append(json.dumps(section["findings"], indent=2)[:2000])
        lines.append("```")
        lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    for i, rec in enumerate(report["recommendations"], 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    return "\n".join(lines)
