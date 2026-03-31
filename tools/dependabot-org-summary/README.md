# Dependabot Org Summary

> Generate a clear, actionable view of your organization’s open High + Critical Dependabot alerts.

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
4. Generates structured outputs and insights

### Key insights

- Total open alerts (High + Critical)
- Severity breakdown (Critical vs High)
- Aging distribution (0–6d, 7–29d, 30–59d, 60–89d, 90+d)
- Repository-level alert counts
- Backlog concentration (top repos)
- Package hotspots (repeated vulnerable dependencies)
- Ecosystem breakdown (npm, pip, rubygems, go, etc.)

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

### Quick start

```bash
python3 dependabot_org_summary.py
```

You will be prompted to select an organization.

---

### Specify an organization

```bash
python3 dependabot_org_summary.py --org <org-name>
```

---

### Redacted output (for demos / sharing)

```bash
python3 dependabot_org_summary.py --org <org-name> --redact
```

This will:
- replace repository names (`repo-001`, etc.)
- remove URLs
- make output safer for screenshots or public sharing

---

### Optional flags

```bash
--outdir <path>   # custom output directory
--quiet           # minimal console output
--redact          # anonymize repo names + URLs
```

---

## Output

The script generates:

```
dependabot_summary_<org>/
```

### Files

| File | Description |
|------|------------|
| `dependabot_org_summary.md` | readable summary report |
| `dependabot_repo_summary.csv` | repository-level metrics |
| `dependabot_alerts_raw.csv` | normalized dataset |
| `dependabot_alerts_raw.json` | raw alert export |

---

## Example signals

Typical output surfaces:

- total open High + Critical alerts  
- percentage of Critical vs High  
- alerts older than 30 / 60 / 90 days  
- which repositories carry the most risk  
- which dependencies are repeated across repos  
- ecosystem-level exposure distribution  

---

## Design

This tool prioritizes:

- **Speed** — runs in seconds  
- **Clarity** — minimal noise, high signal  
- **Actionability** — outputs directly usable for prioritization  
- **Portability** — no tokens or setup beyond GitHub CLI  

---

## Privacy

This tool does not store:
- credentials  
- tokens  
- user identity  

However, generated output may include:
- repository names  
- dependency metadata  
- vulnerability identifiers  

Do not commit output files from private organizations.

---

## License

MIT
