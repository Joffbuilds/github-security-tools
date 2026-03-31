# Dependabot Org Summary

> Generate a clear, actionable view of your organization’s **open High + Critical Dependabot alerts**.

---

## Overview

This tool pulls **all open High + Critical Dependabot alerts** across a GitHub organization and transforms them into a structured summary.

Instead of navigating repository-by-repository or relying on dashboards, it provides a **single, consolidated view** of dependency risk across the entire org.

The output is designed to answer practical questions like:

- Where is risk concentrated?
- What should be prioritized next?
- Is the backlog growing or aging?
- Which dependencies are repeatedly causing issues?

---

## What it does

The script:

1. Authenticates using GitHub CLI (`gh`)
2. Fetches all open High + Critical Dependabot alerts for an organization
3. Normalizes and processes the data
4. Generates:

### Key insights
- Total open alerts (High + Critical)
- Severity breakdown (Critical vs High)
- Aging distribution (0–6d, 7–29d, 30–59d, 60–89d, 90+d)
- Repository-level alert counts
- Backlog concentration (top repos)
- Package hotspots (repeated vulnerable dependencies)
- Ecosystem breakdown (npm, pip, rubygems, go, etc.)

### Output files
- `dependabot_org_summary.md` → human-readable report
- `dependabot_repo_summary.csv` → repo-level metrics
- `dependabot_alerts_raw.csv` → normalized dataset
- `dependabot_alerts_raw.json` → raw export

---

## Why this tool exists

GitHub provides visibility at the repository level, but it is difficult to understand **organization-wide risk posture**.

This tool focuses on **signal over noise**, helping surface:

- **Aging backlog** (persistent risk)
- **Concentration** (where effort will have the most impact)
- **Systemic issues** (shared dependencies across repos)

It is designed to support:
- prioritization
- coordination across teams
- fast, data-informed decision making

---

## Requirements

- Python **3.9+**
- GitHub CLI (`gh`)  
  https://cli.github.com/

---

## Authentication

This tool uses your existing GitHub CLI session.

If you are not authenticated, it will automatically:
- trigger a **browser-based login**
- reuse your session for API access

No tokens or environment variables are required.

---

## Usage

### Interactive org selection (recommended)

```bash
python3 dependabot_org_summary.py

You will be prompted to select an organization.

Specify an organization
python3 dependabot_org_summary.py --org <org-name>
Redacted output (for sharing / demos)
python3 dependabot_org_summary.py --org <org-name> --redact

This will:

replace repository names (repo-001, etc.)
remove URLs
make output safer for screenshots or public sharing
Optional flags
--outdir <path>   # custom output directory
--quiet           # minimal console output
--redact          # anonymize repo names + URLs
Output

The script generates a directory:

dependabot_summary_<org>/

Inside:

File	Description
dependabot_org_summary.md	readable summary report
dependabot_repo_summary.csv	repository-level stats
dependabot_alerts_raw.csv	normalized alert data
dependabot_alerts_raw.json	raw alert payload
Example insights

Typical output surfaces:

total open High + Critical alerts
percentage of Critical vs High
number of alerts older than 30 / 60 / 90 days
which repositories carry the most risk
which dependencies are repeated across repos
which ecosystems dominate exposure
Design principles
Fast — runs in seconds
Minimal setup — relies only on gh
Actionable output — designed for real prioritization
Org-level focus — avoids repo-by-repo noise
Privacy considerations

This tool does not store:

credentials
tokens
user identity

However, generated output may include:

repository names
dependency metadata
vulnerability identifiers

Do not commit output files from private organizations to public repositories.

Notes
Requires appropriate permissions to view Dependabot alerts at the org level
Behavior depends on GitHub API access granted to your account
Works best for organizations actively using Dependabot alerts
