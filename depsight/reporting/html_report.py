"""HTML report generator for the Backup Independence Report."""

from __future__ import annotations
from typing import Dict, Any
from depsight.engine.models import AssessmentReport
from depsight.engine.reproducibility import serialize_canonical_json, compute_sha256


def generate_html_report(report: AssessmentReport) -> str:
    """Generate professional, self-contained HTML assessment report."""
    canonical_json = serialize_canonical_json(report)
    sha256_hash = compute_sha256(canonical_json)

    # Scenarios summary
    scenarios_html = ""
    for scn in report.scenario_outcomes:
        p_badge_cls = "badge-danger" if scn.primary_result.outcome.value == "UNAVAILABLE" else ("badge-warning" if scn.primary_result.outcome.value == "DEGRADED" else "badge-success")
        b_badge_cls = "badge-danger" if scn.backup_result.outcome.value == "UNAVAILABLE" else ("badge-warning" if scn.backup_result.outcome.value == "DEGRADED" else "badge-success")
        joint_cls = "text-danger font-bold" if scn.both_unavailable else "text-muted"

        causal_html = ""
        if scn.primary_result.causal_path:
            causal_html += f"<div><span class='font-semibold'>Primary Causal Path:</span> {' &rarr; '.join(scn.primary_result.causal_path)}</div>"
        if scn.backup_result.causal_path:
            causal_html += f"<div><span class='font-semibold'>Backup Causal Path:</span> {' &rarr; '.join(scn.backup_result.causal_path)}</div>"

        scenarios_html += f"""
        <tr class="{'bg-red-50' if scn.both_unavailable else ''}">
            <td class="font-mono text-sm font-semibold">{scn.scenario_id}</td>
            <td>
                <div class="font-semibold text-slate-900">{scn.scenario_name}</div>
                <div class="text-xs text-slate-500 mt-1">{causal_html}</div>
            </td>
            <td><span class="badge {p_badge_cls}">{scn.primary_result.outcome.value}</span></td>
            <td><span class="badge {b_badge_cls}">{scn.backup_result.outcome.value}</span></td>
            <td class="{joint_cls}">{'YES - JOINT FAILURE' if scn.both_unavailable else 'No'}</td>
        </tr>
        """

    # Cut sets HTML
    cutsets_html = ""
    for cs in report.common_cause_cut_sets:
        badge_cls = "badge-confirmed" if cs.classification.value == "CONFIRMED" else "badge-possible"
        comps_str = " + ".join([f"<code class='comp-code'>{c}</code>" for c in cs.components])

        paths_str = ""
        for arr, paths in cs.supporting_paths.items():
            paths_str += f"<div class='text-xs text-slate-600 mt-1'><span class='font-medium text-slate-800 uppercase'>{arr}:</span> {'; '.join(paths)}</div>"

        limits_str = ""
        if cs.evidence_limitations:
            limits_str = f"<div class='text-xs text-amber-700 bg-amber-50 p-1.5 rounded mt-1 border border-amber-200'><strong>Evidence Limitations:</strong> {'; '.join(cs.evidence_limitations)}</div>"

        cutsets_html += f"""
        <tr>
            <td class="font-mono text-center font-bold text-slate-700">Size {cs.size}</td>
            <td>
                <div>{comps_str}</div>
                {paths_str}
                {limits_str}
            </td>
            <td><span class="badge {badge_cls}">{cs.classification.value}</span></td>
            <td class="text-xs text-slate-600">{', '.join(cs.shared_failure_domains) or 'None (Logical/Cross-Domain)'}</td>
        </tr>
        """

    # Findings HTML
    findings_html = ""
    for f in report.findings:
        sev_cls = "badge-danger" if f.severity == "HIGH" else ("badge-warning" if f.severity == "MEDIUM" else "badge-info")
        findings_html += f"""
        <tr>
            <td class="font-mono text-xs font-semibold">{f.id}</td>
            <td><span class="badge {sev_cls}">{f.severity}</span></td>
            <td>
                <div class="font-semibold text-slate-900">{f.title}</div>
                <div class="text-sm text-slate-600 mt-1">{f.description}</div>
                <div class="text-xs font-medium text-indigo-700 mt-1.5"><strong>Action:</strong> {f.recommendation}</div>
            </td>
            <td class="text-xs font-mono">{f.evidence_status.value}</td>
        </tr>
        """

    # Assumptions & Limitations HTML
    assumptions_html = "".join([f"<li class='text-sm text-slate-700 py-1'>{a}</li>" for a in report.assumptions])
    questions_html = "".join([f"<li class='text-sm text-slate-700 py-1'>{q}</li>" for q in report.open_questions])
    limitations_html = "".join([f"<li class='text-sm text-slate-700 py-1'>{l}</li>" for l in report.limitations])

    # Shared components & domains
    shared_comps_str = ", ".join(report.scope.get("shared_components", [])) or "None identified"
    shared_domains_str = ", ".join(report.scope.get("shared_failure_domains", [])) or "None identified"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DepenSight — Backup Independence Report: {report.service_name}</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        line-height: 1.5;
        color: #1e293b;
        background-color: #f8fafc;
        padding: 2.5rem 1rem;
    }}
    .container {{
        max-width: 1050px;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        padding: 3rem;
    }}
    header {{
        border-bottom: 2px solid #0f172a;
        padding-bottom: 1.5rem;
        margin-bottom: 2rem;
    }}
    .eyebrow {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 700;
        color: #0284c7;
        margin-bottom: 0.25rem;
    }}
    h1 {{ font-size: 1.85rem; font-weight: 700; color: #0f172a; margin-bottom: 0.5rem; }}
    .meta-bar {{
        display: flex;
        flex-wrap: wrap;
        gap: 1.5rem;
        font-size: 0.85rem;
        color: #64748b;
        margin-top: 0.75rem;
    }}
    .meta-bar strong {{ color: #334155; }}
    h2 {{
        font-size: 1.25rem;
        font-weight: 600;
        color: #0f172a;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 0.4rem;
    }}
    p {{ margin-bottom: 0.75rem; font-size: 0.95rem; color: #334155; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0 1.5rem 0;
        font-size: 0.9rem;
    }}
    th, td {{
        padding: 0.65rem 0.85rem;
        border: 1px solid #e2e8f0;
        text-align: left;
        vertical-align: top;
    }}
    th {{
        background-color: #f1f5f9;
        font-weight: 600;
        color: #0f172a;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .badge {{
        display: inline-block;
        padding: 0.2rem 0.55rem;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }}
    .badge-success {{ background-color: #dcfce7; color: #166534; }}
    .badge-warning {{ background-color: #fef3c7; color: #92400e; }}
    .badge-danger {{ background-color: #fee2e2; color: #991b1b; }}
    .badge-info {{ background-color: #e0f2fe; color: #075985; }}
    .badge-confirmed {{ background-color: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }}
    .badge-possible {{ background-color: #ffedd5; color: #9a3412; border: 1px solid #fed7aa; }}
    .comp-code {{
        background: #f1f5f9;
        padding: 0.15rem 0.35rem;
        border-radius: 3px;
        font-size: 0.85rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        color: #0f172a;
    }}
    .grid-2 {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1.25rem;
        margin: 1.25rem 0;
    }}
    .card {{
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 1.25rem;
    }}
    .card-title {{
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #475569;
        margin-bottom: 0.5rem;
    }}
    .stat-number {{ font-size: 1.6rem; font-weight: 700; color: #0f172a; }}
    ul {{ margin-left: 1.5rem; margin-bottom: 1rem; }}
    .hash-footer {{
        margin-top: 3rem;
        padding-top: 1.5rem;
        border-top: 1px solid #e2e8f0;
        font-size: 0.75rem;
        color: #64748b;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        word-break: break-all;
    }}
</style>
</head>
<body>
<div class="container">
    <header>
        <div class="eyebrow">DepenSight &bull; Backup Independence Assessment</div>
        <h1>{report.title}</h1>
        <div class="meta-bar">
            <div><strong>Report ID:</strong> {report.report_id}</div>
            <div><strong>Generated At:</strong> {report.generated_at}</div>
            <div><strong>Engine:</strong> v{report.engine_version}</div>
            <div><strong>Ruleset:</strong> {report.ruleset_version}</div>
            <div><strong>Evidence Cutoff:</strong> {report.evidence_cutoff_date}</div>
        </div>
    </header>

    <h2>1. Executive Summary & Assessment Scope</h2>
    <p>This report documents the evidence-driven dependency evaluation of critical service <strong>{report.service_name}</strong> to answer: <em>"If this dependency fails, will our backup still work, and what evidence supports that conclusion?"</em></p>
    
    <div class="grid-2">
        <div class="card">
            <div class="card-title">Arrangements Under Review</div>
            <p class="text-sm"><strong>Primary Arrangement:</strong> {report.scope['primary_arrangement']['name']} (Root: <code class="comp-code">{report.scope['primary_arrangement']['root_component_id']}</code>, Upstream Nodes: {report.scope['primary_arrangement']['upstream_components_count']})</p>
            <p class="text-sm"><strong>Backup Arrangement:</strong> {report.scope['backup_arrangement']['name']} (Root: <code class="comp-code">{report.scope['backup_arrangement']['root_component_id']}</code>, Upstream Nodes: {report.scope['backup_arrangement']['upstream_components_count']})</p>
        </div>
        <div class="card">
            <div class="card-title">Identified Shared Dependencies</div>
            <p class="text-sm"><strong>Shared Components:</strong> {shared_comps_str}</p>
            <p class="text-sm"><strong>Shared Failure Domains:</strong> {shared_domains_str}</p>
        </div>
    </div>

    <h2>2. Common-Cause Minimal Cut Sets</h2>
    <p>The minimal sets of components whose simultaneous failure makes <strong>both</strong> primary and backup arrangements Unavailable.</p>
    <table>
        <thead>
            <tr>
                <th style="width: 10%;">Order</th>
                <th style="width: 50%;">Cut Set Components & Supporting Paths</th>
                <th style="width: 15%;">Classification</th>
                <th style="width: 25%;">Shared Failure Domain</th>
            </tr>
        </thead>
        <tbody>
            {cutsets_html}
        </tbody>
    </table>

    <h2>3. Outage Scenario Evaluations</h2>
    <p>Deterministic evaluation results across defined outage conditions:</p>
    <table>
        <thead>
            <tr>
                <th style="width: 18%;">Scenario ID</th>
                <th style="width: 42%;">Scenario Description & Causal Path</th>
                <th style="width: 13%;">Primary</th>
                <th style="width: 13%;">Backup</th>
                <th style="width: 14%;">Joint Outage?</th>
            </tr>
        </thead>
        <tbody>
            {scenarios_html}
        </tbody>
    </table>

    <h2>4. Evidence Coverage & Quality Statement</h2>
    <p>Per specification Section 7.6.1, this represents evidence completeness and quality, never a universal resilience score.</p>
    <div class="grid-2">
        <div class="card">
            <div class="card-title">Overall Evidence Coverage</div>
            <div class="stat-number">{report.overall_coverage.confirmed_percentage}% <span style="font-size:0.85rem; font-weight:normal; color:#64748b;">Confirmed</span></div>
            <p class="text-xs text-slate-500 mt-2">
                Total Relationships: {report.overall_coverage.total_relationships} | 
                Inferred/Unverified: {report.overall_coverage.inferred_or_unverified_percentage}% | 
                Stale (&gt;180d): {report.overall_coverage.stale_count} | 
                Unknown Rules: {report.overall_coverage.unknown_rule_count}
            </p>
        </div>
        <div class="card">
            <div class="card-title">Arrangement Breakdown</div>
            <p class="text-sm"><strong>Primary Coverage:</strong> {report.primary_coverage.confirmed_percentage}% Confirmed ({report.primary_coverage.inferred_or_unverified_count} unverified/inferred)</p>
            <p class="text-sm"><strong>Backup Coverage:</strong> {report.backup_coverage.confirmed_percentage}% Confirmed ({report.backup_coverage.inferred_or_unverified_count} unverified/inferred)</p>
        </div>
    </div>

    <h2>5. Defensible Findings</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 12%;">ID</th>
                <th style="width: 12%;">Severity</th>
                <th style="width: 62%;">Finding & Required Action</th>
                <th style="width: 14%;">Evidence</th>
            </tr>
        </thead>
        <tbody>
            {findings_html}
        </tbody>
    </table>

    <h2>6. Explicit Assumptions</h2>
    <ul>
        {assumptions_html}
    </ul>

    <h2>7. Open Questions for Review</h2>
    <ul>
        {questions_html}
    </ul>

    <h2>8. Limitations & Boundary Conditions</h2>
    <ul>
        {limitations_html}
    </ul>

    <div class="hash-footer">
        <div><strong>REPRODUCIBILITY & INTEGRITY ATTESTATION:</strong></div>
        <div>Engine Version: {report.engine_version} | Ruleset: {report.ruleset_version}</div>
        <div>Deterministic Canonical SHA-256 Digest: {sha256_hash}</div>
    </div>
</div>
</body>
</html>
"""
