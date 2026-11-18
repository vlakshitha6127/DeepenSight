"""End-to-end integration tests for Typer CLI commands."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from depsight.cli.main import app

runner = CliRunner(env={"COLUMNS": "240"})
BASELINE = "examples/fictional_payment_service/architecture_baseline.yaml"
IMPROVED = "examples/fictional_payment_service/architecture_improved.yaml"
SCENARIO = "examples/fictional_payment_service/scenarios/identity_access_failure.yaml"


def test_cli_validate():
    result = runner.invoke(app, ["validate", BASELINE])
    assert result.exit_code == 0
    assert "Schema and referential integrity valid" in result.stdout
    assert "Providers" in result.stdout


def test_cli_scenarios():
    result = runner.invoke(app, ["scenarios", BASELINE])
    assert result.exit_code == 0
    assert "SCN-01-SINGLE-COMPONENT" in result.stdout
    assert "SCN-04-IDENTITY-ACCESS-FAILURE" in result.stdout


def test_cli_analyze_all():
    result = runner.invoke(app, ["analyze", BASELINE])
    assert result.exit_code == 0
    assert "Scenario Evaluation" in result.stdout
    assert "YES" in result.stdout  # Joint failure detected for identity / DNS


def test_cli_analyze_single_scenario():
    result = runner.invoke(app, ["analyze", BASELINE, "--scenario", SCENARIO])
    assert result.exit_code == 0
    assert "SCN-04-IDENTITY-ACCESS-FAILURE" in result.stdout
    assert "UNAVAILABLE" in result.stdout


def test_cli_cut_sets():
    result = runner.invoke(app, ["cut-sets", BASELINE, "--max-size", "2"])
    assert result.exit_code == 0
    assert "shared-iam-directory" in result.stdout
    assert "shared-edge-dns" in result.stdout


def test_cli_coverage():
    result = runner.invoke(app, ["coverage", BASELINE])
    assert result.exit_code == 0
    assert "Evidence Coverage Statement" in result.stdout
    assert "Primary Arrangement" in result.stdout
    assert "Backup Arrangement" in result.stdout


def test_cli_diff():
    result = runner.invoke(app, ["diff", BASELINE, IMPROVED])
    assert result.exit_code == 0
    assert "shared-iam-directory" in result.stdout
    assert "fixed" in result.stdout or "resolved" in result.stdout


def test_cli_report_generation(tmp_path: Path):
    html_out = tmp_path / "test_report.html"
    json_out = tmp_path / "test_report.json"
    pdf_out = tmp_path / "test_report.pdf"

    res_html = runner.invoke(app, ["report", BASELINE, "--format", "html", "--output", str(html_out)])
    assert res_html.exit_code == 0
    assert html_out.exists()
    assert "<!DOCTYPE html>" in html_out.read_text(encoding="utf-8")

    res_json = runner.invoke(app, ["report", BASELINE, "--format", "json", "--output", str(json_out)])
    assert res_json.exit_code == 0
    assert json_out.exists()
    assert "report_id" in json_out.read_text(encoding="utf-8")

    res_pdf = runner.invoke(app, ["report", BASELINE, "--format", "pdf", "--output", str(pdf_out)])
    assert res_pdf.exit_code == 0
    assert pdf_out.exists()
    assert pdf_out.stat().st_size > 1000
