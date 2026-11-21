"""Local lightweight server bridging the core Python analytical engine to the Review UI."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

import depsight
from depsight.validators.schema import load_model_from_file, load_scenario_from_file
from depsight.engine.models import ArchitectureModel, Scenario, ScenarioResult, AssessmentReport
from depsight.engine.evaluator import IndependenceEvaluator
from depsight.engine.scenarios import ScenarioEngine
from depsight.engine.cutsets import CutSetAnalyzer
from depsight.engine.coverage import EvidenceCoverageCalculator
from depsight.engine.evidence import EvidenceInspector
from depsight.engine.diff import AssessmentDiffEngine
from depsight.reporting.html_report import generate_html_report
from depsight.reporting.pdf_report import export_pdf_report

app = FastAPI(
    title="DepenSight Engine Local API",
    description="Local analytical bridge for evidence-driven dependency and backup independence review",
    version=depsight.__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASELINE_PATH = Path("examples/fictional_payment_service/architecture_baseline.yaml")
IMPROVED_PATH = Path("examples/fictional_payment_service/architecture_improved.yaml")


def get_model(variant: str = "baseline") -> ArchitectureModel:
    path = IMPROVED_PATH if variant.lower() == "improved" else BASELINE_PATH
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Architecture model not found: {path}")
    return load_model_from_file(path)


@app.get("/api/status")
def get_status():
    return {
        "status": "operational",
        "engine_version": depsight.__version__,
        "ruleset_version": depsight.__ruleset_version__,
        "local_execution": True,
        "trust_model": "Customer-run, zero external cloud transmission",
    }


@app.get("/api/model")
def get_active_model(variant: str = Query("baseline", description="baseline or improved")):
    model = get_model(variant)
    return model.model_dump(mode="json")


@app.get("/api/scenarios")
def get_scenarios(variant: str = Query("baseline")):
    model = get_model(variant)
    engine = ScenarioEngine(model)
    scns = engine.get_standard_scenarios()
    return [s.model_dump(mode="json") for s in scns]


class RunScenarioRequest(BaseModel):
    variant: str = "baseline"
    scenario_id: Optional[str] = None
    failed_component_ids: Optional[List[str]] = None
    failed_failure_domain_ids: Optional[List[str]] = None
    assumptions: Optional[List[str]] = None


@app.post("/api/scenarios/run")
def run_scenario(req: RunScenarioRequest):
    model = get_model(req.variant)
    engine = ScenarioEngine(model)

    if req.failed_component_ids or req.failed_failure_domain_ids:
        scenario = Scenario(
            id=req.scenario_id or "CUSTOM-SCENARIO",
            name=f"Interactive Simulation: {', '.join((req.failed_component_ids or []) + (req.failed_failure_domain_ids or []))}",
            description="User-configured scenario execution via Local Review UI",
            failed_component_ids=req.failed_component_ids or [],
            failed_failure_domain_ids=req.failed_failure_domain_ids or [],
            assumptions=req.assumptions or ["Interactive user-initiated simulation."],
        )
    elif req.scenario_id:
        scenarios = {s.id: s for s in engine.get_standard_scenarios()}
        if req.scenario_id not in scenarios:
            raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario_id}' not found.")
        scenario = scenarios[req.scenario_id]
    else:
        scenario = engine.get_standard_scenarios()[0]

    result = engine.engine.evaluate_scenario(scenario)
    return result.model_dump(mode="json")


@app.get("/api/cutsets")
def get_cutsets(variant: str = Query("baseline"), max_size: int = Query(2)):
    model = get_model(variant)
    analyzer = CutSetAnalyzer(model)
    cutsets = analyzer.compute_minimal_cut_sets(max_size=max_size)
    return [cs.model_dump(mode="json") for cs in cutsets]


@app.get("/api/coverage")
def get_coverage(variant: str = Query("baseline"), cutoff_date: Optional[str] = Query(None)):
    model = get_model(variant)
    calc = EvidenceCoverageCalculator(model)
    overall = calc.calculate_coverage(cutoff_date_str=cutoff_date)
    primary = calc.calculate_primary_coverage(cutoff_date_str=cutoff_date)
    backup = calc.calculate_backup_coverage(cutoff_date_str=cutoff_date)
    return {
        "overall": overall.model_dump(mode="json"),
        "primary": primary.model_dump(mode="json"),
        "backup": backup.model_dump(mode="json"),
    }


@app.get("/api/evidence/gaps")
def get_evidence_gaps(variant: str = Query("baseline"), cutoff_date: Optional[str] = Query(None)):
    model = get_model(variant)
    inspector = EvidenceInspector(model)
    gaps = inspector.get_evidence_gaps(cutoff_date_str=cutoff_date)
    findings = inspector.generate_findings(cutoff_date_str=cutoff_date)
    return {
        "gaps": gaps,
        "findings": [f.model_dump(mode="json") for f in findings],
    }


@app.get("/api/diff")
def get_assessment_diff(max_size: int = Query(2)):
    before_model = get_model("baseline")
    after_model = get_model("improved")
    diff_engine = AssessmentDiffEngine(before_model, after_model)
    diff_res = diff_engine.compute_diff(max_cutset_size=max_size)
    return diff_res.model_dump(mode="json")


@app.get("/api/report")
def get_report(variant: str = Query("baseline"), format: str = Query("json"), max_size: int = Query(2)):
    model = get_model(variant)
    evaluator = IndependenceEvaluator(model)
    report = evaluator.run_assessment(max_cutset_size=max_size)

    if format.lower() == "html":
        html = generate_html_report(report)
        return HTMLResponse(content=html, media_type="text/html")
    elif format.lower() == "pdf":
        out_path = Path(f"output/report_{model.service.id}_{variant}.pdf")
        export_pdf_report(report, out_path)
        return FileResponse(path=str(out_path), filename=out_path.name, media_type="application/pdf")
    else:
        return report.model_dump(mode="json")


# Mount static files if frontend is built
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
