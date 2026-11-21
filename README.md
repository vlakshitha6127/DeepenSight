# DepenSight: Evidence-Driven Dependency Analysis Platform

[![Engine Tests](https://img.shields.io/badge/pytest-24%20passed-success)](tests/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![Specification](https://img.shields.io/badge/spec-v1.0%20Consolidated-navy)](DepenSight%20%E2%80%94%20Final%20Consolidated%20Specification%20(v1.0).pdf)
[![License](https://img.shields.io/badge/license-Proprietary-slate.svg)](#)

> **"If this dependency fails, will our backup still work, and what evidence supports that conclusion?"**

---

## 1. Product Overview & Problem Statement

Enterprises and financial institutions invest millions in secondary backup arrangements (multi-region, secondary cloud, warm-standby data centers) under the assumption that if the primary arrangement fails, the backup will preserve business continuity.

In reality, primary and backup configurations frequently share hidden, unvetted, or unverified upstream dependencies:
- A shared Identity Provider / SSO directory (e.g. corporate Okta/Entra ID tenant).
- A shared authoritative DNS or global CDN control plane.
- An undocumented common database replica or cloud-region transit backbone.
- Third-party payment rails or API gateways.

When that shared component fails, **both primary and backup collapse simultaneously**, defeating the entire continuity investment.

**DepenSight** is a customer-run, evidence-driven dependency analysis platform designed to:
1. Model critical services and their primary, backup, and upstream dependencies.
2. Separate confirmed facts from inferred, unverified, disputed, and superseded relationships.
3. Formally evaluate component states using **Three-Valued Logic (`UP`, `DOWN`, `UNKNOWN`)** and service outcomes (`AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `INDETERMINATE`).
4. Perform **minimal common-cause cut-set analysis** with size pruning and evidence limitations.
5. Provide a deterministic fixed-point propagation algorithm for cyclic dependencies.
6. Evaluate canonical outage scenarios (regional, provider, identity, DNS, dual degradation).
7. Execute before-and-after **Assessment Diffs** to demonstrate resilience improvements.
8. Enforce **byte-identical reproducibility** with deterministic canonical hashing.

---

## 2. Core Pillars & Design Guardrails

1. **Three-Valued Honesty (`UP`, `DOWN`, `UNKNOWN`):** Missing evidence is **never** interpreted as independence. An undocumented dependency produces `INDETERMINATE`, never a silent pass.
2. **Strict Separation of Component State & Service Outcomes:** Node operational health is evaluated independently from arrangement-level service outcomes. A failed mandatory dependency strictly establishes `UNAVAILABLE` even if other branches are unknown.
3. **Formal Fixed-Point Convergence for Cycles:** Cyclic dependencies are evaluated over a complete finite semi-lattice $\mathcal{L} = (\{\text{UP}, \text{UNKNOWN}, \text{DOWN}\}, \sqsubseteq)$ under monotone operator updates. Termination is mathematically proven by the lattice's finite height ($H = 2n$), not an arbitrary cap.
4. **Common-Cause Minimal Cut Sets:** Identifies the smallest combinations of components (Size 1, Size 2, etc.) whose failure takes down both arrangements. Cut sets are classified as **CONFIRMED** (all relationships verified) or **POSSIBLE** (inferred or unverified dependencies present).
5. **No Universal Resilience Scores:** DepenSight strictly avoids synthetic percentage scores (e.g., "95% resilient"). It reports exact cut sets, evidence coverage breakdowns, and causal failure paths.
6. **Customer-Run Trust Model (Phase 1–2):** Pure Python library and local CLI/UI. Sensitive architecture configurations never leave the client environment; zero external AI calls are made to evaluate outcomes.

---

## 3. System Architecture

```
+-----------------------------------------------------------------------------------+
|                               DepenSight Platform                                 |
+-----------------------------------------------------------------------------------+
|  [CLI: depsight]  <----->  [Local Review UI: React + React Flow + Tailwind]        |
|                                   | (Local Engine Bridge / Static API)            |
+-----------------------------------------------------------------------------------+
|                                Analytical Engine                                  |
|  +---------------------+   +---------------------+   +--------------------------+ |
|  |   Domain Models     |   |   Graph Evaluator   |   |   Cut-Set Analyzer       | |
|  | - Pydantic Schemas  |   | - NetworkX DiGraph  |   | - Minimal Cut Sets (1..N)| |
|  | - 3-Valued Logic    |   | - Failure Propagate |   | - Confirmed vs. Possible | |
|  | - Evidence Grading  |   | - Monotone Fixed-Pt |   | - Supporting Paths       | |
|  +---------------------+   +---------------------+   +--------------------------+ |
|  +---------------------+   +---------------------+   +--------------------------+ |
|  |   Scenario Library  |   |  Evidence Coverage  |   |  Assessment Diff Engine  | |
|  | - 7 Standard Lib    |   | - Confirmed/Inferred|   | - Snapshot delta         | |
|  | - Custom Scenarios  |   | - Staleness metrics |   | - Fixed/new cut sets     | |
|  +---------------------+   +---------------------+   +--------------------------+ |
+-----------------------------------------------------------------------------------+
|                         Persistence & Reporting Layer                             |
|  - YAML / JSON Serializer (deterministic keys & stable sorting)                    |
|  - HTML & PDF Backup Independence Report Generator (ReportLab)                     |
+-----------------------------------------------------------------------------------+
```

---

## 4. Technology Stack

- **Core Engine:** Python 3.11+
- **Graph Framework:** NetworkX 3.x
- **Data Validation & Schemas:** Pydantic v2
- **CLI Framework:** Typer + Rich
- **Serialization:** PyYAML, standard `json` (deterministic canonical formatting)
- **Reporting:** Structured HTML Report Generator & ReportLab PDF Exporter
- **Testing:** pytest (comprehensive test suites)
- **Frontend / Review UI:** React 18, TypeScript, Vite, Tailwind CSS, React Flow (`@xyflow/react`), Lucide React

---

## 5. Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Node.js v18+ and npm (for the local UI)

### 1. Python Environment Setup
```bash
# Clone the repository
git clone https://github.com/vlakshitha6127/DeepenSight.git
cd DeepenSight

# Install Python dependencies
py -m pip install -e .
py -m pip install pydantic pyyaml networkx typer rich reportlab pytest fastapi uvicorn
```

---

## 6. CLI Usage & Demonstration Workflow

DepenSight provides a Typer CLI. Below is the demonstration workflow using the reference fictional payment architecture.

### Step 1: Validate Architecture Schema
```bash
py -m depsight.cli.main validate examples/fictional_payment_service/architecture_baseline.yaml
```

### Step 2: List Standard Scenarios
```bash
py -m depsight.cli.main scenarios examples/fictional_payment_service/architecture_baseline.yaml
```

### Step 3: Execute Scenario Analysis & Expose Common-Mode Identity Failure
```bash
# Evaluate all scenarios
py -m depsight.cli.main analyze examples/fictional_payment_service/architecture_baseline.yaml

# Evaluate specific shared identity provider failure
py -m depsight.cli.main analyze examples/fictional_payment_service/architecture_baseline.yaml --scenario examples/fictional_payment_service/scenarios/identity_access_failure.yaml
```
*Output demonstrates that when `shared-iam-directory` fails, BOTH Primary and Backup collapse (`Joint Failure: YES`), with causal paths clearly identified.*

### Step 4: Compute Minimal Common-Cause Cut Sets
```bash
py -m depsight.cli.main cut-sets examples/fictional_payment_service/architecture_baseline.yaml --max-size 2
```
*Exposes `shared-edge-dns` (CONFIRMED) and `shared-iam-directory` (POSSIBLE, due to unverified backup relationship evidence).*

### Step 5: Check Evidence Coverage & Staleness
```bash
py -m depsight.cli.main coverage examples/fictional_payment_service/architecture_baseline.yaml
```

### Step 6: Compare Baseline vs. Improved Architecture (Assessment Diff)
```bash
py -m depsight.cli.main diff examples/fictional_payment_service/architecture_baseline.yaml examples/fictional_payment_service/architecture_improved.yaml
```
*Shows `shared-iam-directory` resolved, cut sets eliminated, and scenario SCN-04 improved from joint failure to backup survival.*

### Step 7: Export Backup Independence Reports (HTML & PDF)
```bash
# Generate HTML Report
py -m depsight.cli.main report examples/fictional_payment_service/architecture_baseline.yaml --format html --output output/report.html

# Generate PDF Report
py -m depsight.cli.main report examples/fictional_payment_service/architecture_baseline.yaml --format pdf --output output/report.pdf
```

---

## 7. Running Tests

Run the complete automated test suite covering all 13 reference acceptance criteria:
```bash
py -m pytest tests/ -v
```

### Tested Scenarios:
1. `test_rule_all_mandatory_failure`: Mandatory ALL dependency failure propagation.
2. `test_rule_any_alternative_survival`: Independent alternative survival under ANY rule.
3. `test_rule_any_all_alternatives_failed`: Total alternative failure under ANY rule.
4. `test_rule_optional_component_failure`: Degradation semantics under OPTIONAL rule.
5. `test_unknown_dependency_evaluates_to_indeterminate`: Indeterminate outcome under UNKNOWN rule.
6. `test_failed_mandatory_with_unknown_still_unavailable`: Mandatory failure precedence over unknowns.
7. `test_cyclic_dependencies_terminate_deterministically`: Monotone fixed-point termination on cyclic graphs.
8. `test_minimal_cutsets_against_brute_force`: Cut-set algorithm verified against brute-force enumeration.
9. `test_cutset_confirmed_vs_possible_classification`: Evidence grading on cut sets.
10. `test_standard_7_scenarios_execute`: Complete execution of the 7 standard scenarios.
11. `test_staleness_and_conflicting_evidence`: Staleness (>180d) and DISPUTED evidence handling.
12. `test_coverage_calculator_proportions`: Accurate evidence metrics without synthetic resilience scores.
13. `test_assessment_diff_baseline_vs_improved`: Accurate delta detection on architecture improvements.
14. `test_byte_identical_reproducibility_with_fixed_timestamp`: Byte-identical serialization and SHA-256 match.
15. `test_reproducibility_excluding_volatile_timestamps`: Nondeterministic metadata normalization.
16. `test_cli_*`: Full end-to-end integration tests for all CLI commands.

---

## 8. Fictional Architecture Reference (`ApexPay`)

The repository includes a complete, realistic reference architecture in `examples/fictional_payment_service/`:
- `architecture_baseline.yaml` (v1.0.0): AWS eu-west-1 primary, Azure westeurope backup. Hidden single points of failure on shared Okta tenant and Cloudflare edge DNS.
- `architecture_improved.yaml` (v1.1.0): Remediated architecture decoupling Azure backup to an independent, verified Azure Entra ID standby tenant.
- `scenarios/`: YAML definitions for single component, regional outage, provider disruption, identity failure, and dual degradation.

---

## 9. Security & Trust Architecture

- **Local Execution:** Operates entirely within the customer perimeter.
- **No External AI Calls:** Analytical conclusions are strictly generated by deterministic rule graph algorithms.
- **Customer Privacy:** Raw customer architecture and credentials are excluded from version control via `.gitignore`.
- **Reproducibility:** Canonical JSON serialization and SHA-256 digests enable independent verification by auditors.

---

## 10. Repository Structure

```
DeepenSight/
├── .gitignore
├── DEVELOPMENT_STATUS.md
├── pyproject.toml
├── README.md
├── depsight/
│   ├── __init__.py
│   ├── cli/
│   │   └── main.py
│   ├── engine/
│   │   ├── models.py
│   │   ├── graph.py
│   │   ├── evaluator.py
│   │   ├── propagation.py
│   │   ├── cutsets.py
│   │   ├── scenarios.py
│   │   ├── evidence.py
│   │   ├── coverage.py
│   │   ├── diff.py
│   │   ├── reproducibility.py
│   │   └── server.py
│   ├── reporting/
│   │   ├── html_report.py
│   │   └── pdf_report.py
│   └── validators/
│       └── schema.py
├── examples/
│   └── fictional_payment_service/
│       ├── architecture_baseline.yaml
│       ├── architecture_improved.yaml
│       ├── scenarios/
│       └── README.md
├── tests/
│   ├── test_cli.py
│   ├── test_cutsets.py
│   ├── test_diff.py
│   ├── test_evidence_and_coverage.py
│   ├── test_graph_and_rules.py
│   ├── test_propagation_cycles.py
│   ├── test_reproducibility.py
│   └── test_scenarios.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    └── src/
```
