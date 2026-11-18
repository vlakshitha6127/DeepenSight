"""PDF report generation for Backup Independence Report using ReportLab."""

from __future__ import annotations
from pathlib import Path
from typing import Union
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from depsight.engine.models import AssessmentReport
from depsight.engine.reproducibility import serialize_canonical_json, compute_sha256


def export_pdf_report(report: AssessmentReport, output_path: Union[str, Path]) -> Path:
    """Generate professional PDF Backup Independence Report."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "Heading2Custom",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748b"),
    )
    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    table_text = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )

    story = []

    # Title & Metadata
    canonical_json = serialize_canonical_json(report)
    sha256_hash = compute_sha256(canonical_json)

    story.append(Paragraph(f"<b>DEPENSIGHT &bull; BACKUP INDEPENDENCE REPORT</b>", meta_style))
    story.append(Paragraph(report.title, title_style))
    story.append(Paragraph(
        f"<b>Report ID:</b> {report.report_id} | <b>Generated:</b> {report.generated_at} | "
        f"<b>Engine:</b> v{report.engine_version} | <b>Ruleset:</b> {report.ruleset_version}",
        meta_style,
    ))
    story.append(Spacer(1, 12))

    # Executive Summary & Scope
    story.append(Paragraph("1. Executive Summary & Assessment Scope", h2_style))
    summary_text = (
        f"This report documents the evidence-driven dependency evaluation of critical service "
        f"<b>{report.service_name}</b> to answer: <i>'If this dependency fails, will our backup still work, "
        f"and what evidence supports that conclusion?'</i>"
    )
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 6))

    shared_comps_str = ", ".join(report.scope.get("shared_components", [])) or "None identified"
    scope_data = [
        [Paragraph("<b>Arrangement</b>", table_text), Paragraph("<b>Details</b>", table_text)],
        [
            Paragraph(f"Primary: {report.scope['primary_arrangement']['name']}", table_text),
            Paragraph(f"Root: {report.scope['primary_arrangement']['root_component_id']} (Upstream: {report.scope['primary_arrangement']['upstream_components_count']})", table_text)
        ],
        [
            Paragraph(f"Backup: {report.scope['backup_arrangement']['name']}", table_text),
            Paragraph(f"Root: {report.scope['backup_arrangement']['root_component_id']} (Upstream: {report.scope['backup_arrangement']['upstream_components_count']})", table_text)
        ],
        [
            Paragraph("Shared Components", table_text),
            Paragraph(shared_comps_str, table_text)
        ]
    ]
    t_scope = Table(scope_data, colWidths=[160, 380])
    t_scope.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_scope)
    story.append(Spacer(1, 10))

    # Minimal Cut Sets
    story.append(Paragraph("2. Common-Cause Minimal Cut Sets", h2_style))
    cs_data = [
        [
            Paragraph("<b>Size</b>", table_text),
            Paragraph("<b>Components & Supporting Paths</b>", table_text),
            Paragraph("<b>Classification</b>", table_text)
        ]
    ]
    for cs in report.common_cause_cut_sets:
        paths_desc = f"<b>{', '.join(cs.components)}</b>"
        if cs.evidence_limitations:
            paths_desc += f"<br/><font color='#b45309'>Limits: {'; '.join(cs.evidence_limitations)}</font>"
        cs_data.append([
            Paragraph(f"Size {cs.size}", table_text),
            Paragraph(paths_desc, table_text),
            Paragraph(f"<b>{cs.classification.value}</b>", table_text),
        ])

    t_cs = Table(cs_data, colWidths=[60, 380, 100])
    t_cs.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cs)
    story.append(Spacer(1, 10))

    # Outage Scenarios
    story.append(Paragraph("3. Scenario Evaluations", h2_style))
    scn_data = [
        [
            Paragraph("<b>Scenario</b>", table_text),
            Paragraph("<b>Primary</b>", table_text),
            Paragraph("<b>Backup</b>", table_text),
            Paragraph("<b>Joint Outage?</b>", table_text)
        ]
    ]
    for scn in report.scenario_outcomes:
        joint_str = "<font color='#dc2626'><b>YES</b></font>" if scn.both_unavailable else "No"
        scn_data.append([
            Paragraph(f"<b>{scn.scenario_name}</b><br/>{scn.scenario_id}", table_text),
            Paragraph(scn.primary_result.outcome.value, table_text),
            Paragraph(scn.backup_result.outcome.value, table_text),
            Paragraph(joint_str, table_text),
        ])

    t_scn = Table(scn_data, colWidths=[240, 100, 100, 100])
    t_scn.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_scn)
    story.append(Spacer(1, 10))

    # Evidence Coverage Statement
    story.append(Paragraph("4. Evidence Coverage Statement", h2_style))
    cov_text = (
        f"<b>Overall Coverage:</b> {report.overall_coverage.confirmed_percentage}% Confirmed | "
        f"{report.overall_coverage.inferred_or_unverified_percentage}% Inferred/Unverified | "
        f"Stale: {report.overall_coverage.stale_count} | Unknown Rules: {report.overall_coverage.unknown_rule_count}<br/>"
        f"<b>Primary Upstream:</b> {report.primary_coverage.confirmed_percentage}% Confirmed | "
        f"<b>Backup Upstream:</b> {report.backup_coverage.confirmed_percentage}% Confirmed"
    )
    story.append(Paragraph(cov_text, body_style))
    story.append(Spacer(1, 10))

    # Findings
    story.append(Paragraph("5. Key Defensible Findings", h2_style))
    f_data = [
        [
            Paragraph("<b>ID</b>", table_text),
            Paragraph("<b>Severity</b>", table_text),
            Paragraph("<b>Finding & Action</b>", table_text)
        ]
    ]
    for f in report.findings[:5]:  # Key findings
        f_data.append([
            Paragraph(f.id, table_text),
            Paragraph(f"<b>{f.severity}</b>", table_text),
            Paragraph(f"<b>{f.title}</b><br/>{f.description}<br/><b>Action:</b> {f.recommendation}", table_text)
        ])
    t_f = Table(f_data, colWidths=[70, 70, 400])
    t_f.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_f)
    story.append(Spacer(1, 14))

    # Hash
    story.append(Paragraph(f"<b>Deterministic Canonical SHA-256 Digest:</b> {sha256_hash}", meta_style))

    doc.build(story)
    return out
