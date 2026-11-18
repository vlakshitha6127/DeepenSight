"""DepenSight Command-Line Interface (CLI) powered by Typer and Rich."""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

import depsight
from depsight.validators.schema import (
    load_model_from_file,
    load_scenario_from_file,
    SchemaValidationError,
)
from depsight.engine.evaluator import IndependenceEvaluator
from depsight.engine.scenarios import ScenarioEngine
from depsight.engine.cutsets import CutSetAnalyzer
from depsight.engine.coverage import EvidenceCoverageCalculator
from depsight.engine.diff import AssessmentDiffEngine
from depsight.engine.reproducibility import serialize_canonical_json
from depsight.reporting.html_report import generate_html_report
from depsight.reporting.pdf_report import export_pdf_report

app = typer.Typer(
    name="depsight",
    help="DepenSight: Evidence-Driven Dependency Analysis Platform CLI",
    add_completion=False,
)
console = Console(width=240, force_terminal=False)


@app.command()
def validate(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
):
    """Validate architecture model schema, entities, and referential integrity."""
    try:
        model = load_model_from_file(model_path)
        console.print(f"[bold green][OK] Schema and referential integrity valid:[/bold green] {model.service.name} (v{model.metadata.version})")

        table = Table(title="Model Overview", show_header=True, header_style="bold cyan")
        table.add_column("Entity Category", style="dim")
        table.add_column("Count", justify="right")
        table.add_column("Sample Items")

        table.add_row("Providers", str(len(model.providers)), ", ".join(p.id for p in model.providers[:3]))
        table.add_row("Deployments", str(len(model.deployments)), ", ".join(d.id for d in model.deployments[:3]))
        table.add_row("Failure Domains", str(len(model.failure_domains)), ", ".join(fd.id for fd in model.failure_domains[:3]))
        table.add_row("Components", str(len(model.components)), ", ".join(c.id for c in model.components[:4]))
        table.add_row("Dependencies", str(len(model.dependencies)), f"{len(model.dependencies)} edges")
        table.add_row("Dependency Groups", str(len(model.dependency_groups)), ", ".join(g.id for g in model.dependency_groups[:3]))

        console.print(table)
    except SchemaValidationError as e:
        console.print(f"[bold red]Validation Error in {model_path}:[/bold red]\n{e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def scenarios(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
):
    """List standard outage scenarios configured for this architecture model."""
    try:
        model = load_model_from_file(model_path)
        engine = ScenarioEngine(model)
        scns = engine.get_standard_scenarios()

        table = Table(title="Canonical Outage Scenarios", show_header=True, header_style="bold cyan")
        table.add_column("Scenario ID", style="bold")
        table.add_column("Scenario Name")
        table.add_column("Failed Fault Targets")
        table.add_column("Description")

        for scn in scns:
            targets = []
            if scn.failed_component_ids:
                targets.extend(f"comp:{c}" for c in scn.failed_component_ids)
            if scn.failed_failure_domain_ids:
                targets.extend(f"domain:{fd}" for fd in scn.failed_failure_domain_ids)
            table.add_row(scn.id, scn.name, ", ".join(targets), scn.description)

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error listing scenarios:[/bold red] {e}")
        sys.exit(1)


@app.command()
def analyze(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
    scenario_path: Optional[Path] = typer.Option(None, "--scenario", "-s", help="Path to custom scenario file (optional)"),
):
    """Execute scenario failure propagation and evaluate primary vs backup survival."""
    try:
        model = load_model_from_file(model_path)
        engine = ScenarioEngine(model)

        if scenario_path:
            scn = load_scenario_from_file(scenario_path, model)
            results = [engine.engine.evaluate_scenario(scn)]
        else:
            results = engine.evaluate_all()

        table = Table(title=f"Scenario Evaluation: {model.service.name}", show_header=True, header_style="bold cyan")
        table.add_column("Scenario ID", style="bold")
        table.add_column("Primary Outcome")
        table.add_column("Backup Outcome")
        table.add_column("Joint Failure?", justify="center")
        table.add_column("Causal Path / Primary Reason")

        for r in results:
            p_style = "bold red" if r.primary_result.outcome.value == "UNAVAILABLE" else ("bold yellow" if r.primary_result.outcome.value == "DEGRADED" else "bold green")
            b_style = "bold red" if r.backup_result.outcome.value == "UNAVAILABLE" else ("bold yellow" if r.backup_result.outcome.value == "DEGRADED" else "bold green")
            joint_str = "[bold red]YES[/bold red]" if r.both_unavailable else "[dim]No[/dim]"

            causal_desc = ""
            if r.primary_result.causal_path and len(r.primary_result.causal_path) > 1:
                causal_desc += f"[dim]Primary Path:[/dim] {' -> '.join(r.primary_result.causal_path)}\n"
            if r.backup_result.causal_path and len(r.backup_result.causal_path) > 1:
                causal_desc += f"[dim]Backup Path:[/dim] {' -> '.join(r.backup_result.causal_path)}"
            if not causal_desc:
                causal_desc = r.primary_result.primary_failure_reason or ""

            table.add_row(
                r.scenario_id,
                f"[{p_style}]{r.primary_result.outcome.value}[/{p_style}]",
                f"[{b_style}]{r.backup_result.outcome.value}[/{b_style}]",
                joint_str,
                causal_desc.strip(),
            )

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Analysis Error:[/bold red] {e}")
        sys.exit(1)


@app.command(name="cut-sets")
def cut_sets(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
    max_size: int = typer.Option(2, "--max-size", "-k", help="Maximum cut set size to evaluate (default 2)"),
):
    """Compute minimal common-cause cut sets whose failure disables both arrangements."""
    try:
        model = load_model_from_file(model_path)
        analyzer = CutSetAnalyzer(model)
        cutsets = analyzer.compute_minimal_cut_sets(max_size=max_size)

        table = Table(title=f"Minimal Common-Cause Cut Sets (Order 1..{max_size})", show_header=True, header_style="bold cyan")
        table.add_column("Size", justify="center")
        table.add_column("Components", style="bold")
        table.add_column("Classification", justify="center")
        table.add_column("Supporting Paths")
        table.add_column("Evidence Limitations")

        for cs in cutsets:
            cls_style = "bold blue" if cs.classification.value == "CONFIRMED" else "bold yellow"
            paths_lines = []
            for arr, paths in cs.supporting_paths.items():
                paths_lines.append(f"{arr.upper()}: {'; '.join(paths)}")

            table.add_row(
                str(cs.size),
                " + ".join(cs.components),
                f"[{cls_style}]{cs.classification.value}[/{cls_style}]",
                "\n".join(paths_lines),
                "\n".join(cs.evidence_limitations) if cs.evidence_limitations else "[dim]None (All Confirmed)[/dim]",
            )

        console.print(table)
        console.print(f"\n[dim]Total minimal common-cause cut sets found: {len(cutsets)}[/dim]")
    except Exception as e:
        console.print(f"[bold red]Cut-Set Computation Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def coverage(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
    cutoff_date: Optional[str] = typer.Option(None, "--cutoff-date", "-d", help="Evidence cutoff date (YYYY-MM-DD)"),
):
    """Compute evidence coverage metrics and quality breakdown."""
    try:
        model = load_model_from_file(model_path)
        calc = EvidenceCoverageCalculator(model)

        overall = calc.calculate_coverage(cutoff_date_str=cutoff_date)
        primary = calc.calculate_primary_coverage(cutoff_date_str=cutoff_date)
        backup = calc.calculate_backup_coverage(cutoff_date_str=cutoff_date)

        table = Table(title="Evidence Coverage Statement (Evidence Quality, Not Resilience)", show_header=True, header_style="bold cyan")
        table.add_column("Scope")
        table.add_column("Total Dependencies", justify="right")
        table.add_column("Confirmed (%)", justify="right")
        table.add_column("Inferred/Unverified (%)", justify="right")
        table.add_column("Stale (>180d)", justify="right")
        table.add_column("Unknown Rules", justify="right")

        for cov in [overall, primary, backup]:
            table.add_row(
                cov.scope_name,
                str(cov.total_relationships),
                f"{cov.confirmed_percentage}% ({cov.confirmed_count})",
                f"{cov.inferred_or_unverified_percentage}% ({cov.inferred_or_unverified_count})",
                f"{cov.stale_percentage}% ({cov.stale_count})",
                str(cov.unknown_rule_count),
            )

        console.print(table)
        console.print("[dim italic]Note: DepenSight does not synthesize a universal resilience score. Coverage measures evidence completeness.[/dim italic]")
    except Exception as e:
        console.print(f"[bold red]Coverage Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def report(
    model_path: Path = typer.Argument(..., help="Path to architecture model YAML/JSON file"),
    format: str = typer.Option("html", "--format", "-f", help="Output format: html, pdf, or json"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Target output file path"),
    max_cutset_size: int = typer.Option(2, "--max-cutset-size", "-k", help="Max cut set size"),
    cutoff_date: Optional[str] = typer.Option(None, "--cutoff-date", "-d", help="Evidence cutoff date"),
):
    """Generate deterministic, defensible Backup Independence Report."""
    try:
        model = load_model_from_file(model_path)
        evaluator = IndependenceEvaluator(model)
        rep = evaluator.run_assessment(
            max_cutset_size=max_cutset_size,
            evidence_cutoff_date=cutoff_date,
        )

        default_stem = f"backup_independence_report_{model.service.id}_{model.metadata.version}"

        if format.lower() == "html":
            out_file = output or Path(f"{default_stem}.html")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            html_content = generate_html_report(rep)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            console.print(f"[bold green][OK] HTML Report generated:[/bold green] {out_file.resolve()}")
        elif format.lower() == "pdf":
            out_file = output or Path(f"{default_stem}.pdf")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            export_pdf_report(rep, out_file)
            console.print(f"[bold green][OK] PDF Report generated:[/bold green] {out_file.resolve()}")
        elif format.lower() == "json":
            out_file = output or Path(f"{default_stem}.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            json_content = serialize_canonical_json(rep)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(json_content)
            console.print(f"[bold green][OK] Canonical JSON Report generated:[/bold green] {out_file.resolve()}")
        else:
            console.print(f"[bold red]Unsupported format:[/bold red] {format}. Choose html, pdf, or json.")
            sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Report Generation Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def diff(
    before_path: Path = typer.Argument(..., help="Path to baseline/before architecture model"),
    after_path: Path = typer.Argument(..., help="Path to updated/after architecture model"),
    max_cutset_size: int = typer.Option(2, "--max-size", "-k", help="Maximum cut set size to evaluate"),
):
    """Compare two architecture snapshots to evaluate impact of architectural improvements."""
    try:
        before_model = load_model_from_file(before_path)
        after_model = load_model_from_file(after_path)

        diff_engine = AssessmentDiffEngine(before_model, after_model)
        res = diff_engine.compute_diff(max_cutset_size=max_cutset_size)

        console.print(Panel(
            f"[bold]Assessment Diff:[/bold] Snapshot v{res.before_snapshot_version} -> v{res.after_snapshot_version}",
            style="bold cyan",
        ))

        table = Table(title="Architectural Changes & Resilience Impact", show_header=True, header_style="bold cyan")
        table.add_column("Category", style="dim")
        table.add_column("Change Type")
        table.add_column("Identifier", style="bold")
        table.add_column("Before")
        table.add_column("After")
        table.add_column("Description")

        for d in res.differences:
            c_type_style = "bold green" if d.change_type in ("fixed", "resolved", "improved") else ("bold red" if d.change_type in ("newly_introduced",) else "bold yellow")
            table.add_row(
                d.category,
                f"[{c_type_style}]{d.change_type}[/{c_type_style}]",
                d.identifier,
                str(d.before_state),
                str(d.after_state),
                d.description,
            )

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Diff Error:[/bold red] {e}")
        sys.exit(1)


@app.command()
def version():
    """Display DepenSight engine and ruleset versions."""
    console.print(f"[bold cyan]DepenSight[/bold cyan] v{depsight.__version__} (Ruleset: {depsight.__ruleset_version__})")


if __name__ == "__main__":
    app()
