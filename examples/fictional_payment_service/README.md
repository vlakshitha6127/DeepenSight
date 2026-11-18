# Fictional Payment Service Reference Architecture: ApexPay

This directory contains the reference fictional architecture for **ApexPay Core Settlement Service**, designed to demonstrate common-mode dependency failure, minimal cut sets, evidence grading, and before/after assessment diffs.

## The Architecture
- **Primary Service:** Runs on AWS eu-west-1 (`apexpay-primary-api`, `primary-settlement-engine`, `primary-ledger-db`, `primary-redis-cache`).
- **Backup Service:** Runs on Azure westeurope (`apexpay-backup-api`, `backup-settlement-engine`, `backup-ledger-db`).
- **Payment Processors:** Redundant external gateways (`ext-gateway-stripe` or `ext-gateway-adyen`) evaluated under rule **ANY**.
- **The Hidden Trap:** Both AWS Primary and Azure Backup share an identity directory (`shared-iam-directory`, Okta Tenant 01) and edge DNS (`shared-edge-dns`, Cloudflare).
- **Evidence Grading:** The backup arrangement's link to the shared Okta tenant is backed only by an unverified Slack thread (`UNVERIFIED`), causing the resulting cut set to be classified as **POSSIBLE**, while DNS is **CONFIRMED**.

## Baseline vs. Improved
1. `architecture_baseline.yaml`: Baseline snapshot exhibiting common-cause cut sets on `shared-iam-directory` and `shared-edge-dns`. Under an Identity failure scenario, BOTH primary and backup evaluate to `UNAVAILABLE`.
2. `architecture_improved.yaml`: Improved snapshot where Azure Backup is decoupled to use an independent, verified Azure Entra ID standby directory (`isolated-iam-backup-tenant`). The cut set is eliminated, and under identical scenario runs, the backup survives!

## Example CLI Commands

```bash
# Validate architecture
py -m depsight.cli.main validate examples/fictional_payment_service/architecture_baseline.yaml

# Evaluate scenarios
py -m depsight.cli.main analyze examples/fictional_payment_service/architecture_baseline.yaml

# Evaluate specific identity failure scenario
py -m depsight.cli.main analyze examples/fictional_payment_service/architecture_baseline.yaml --scenario examples/fictional_payment_service/scenarios/identity_access_failure.yaml

# Find minimal common-cause cut sets
py -m depsight.cli.main cut-sets examples/fictional_payment_service/architecture_baseline.yaml

# Inspect evidence coverage statement
py -m depsight.cli.main coverage examples/fictional_payment_service/architecture_baseline.yaml

# Compare baseline vs improved architecture
py -m depsight.cli.main diff examples/fictional_payment_service/architecture_baseline.yaml examples/fictional_payment_service/architecture_improved.yaml

# Generate HTML report
py -m depsight.cli.main report examples/fictional_payment_service/architecture_baseline.yaml --format html
```
