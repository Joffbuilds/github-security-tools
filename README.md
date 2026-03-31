# github-security-tools

A collection of lightweight security utilities for understanding GitHub org risk, remediation priorities, and backlog health.

This repository is designed to grow over time. Each tool lives in its own directory with focused documentation, examples, and implementation details.

---

## Current tools

### [Dependabot Org Summary](tools/dependabot-org-summary/README.md)

Generate a clear, org-wide view of **open High + Critical Dependabot alerts**.

It surfaces the signals that matter most when you're trying to understand dependency risk at scale:

- total open High + Critical alerts
- Critical vs High breakdown
- aging backlog (30 / 60 / 90+ days)
- repository concentration
- dependency hotspots across repos
- ecosystem distribution

Use it when you want a fast answer to questions like:

- Where is risk concentrated?
- What should be prioritized next?
- Is the backlog growing or aging?
- Which dependencies are repeatedly causing issues?

**Tool path:** `tools/dependabot-org-summary/`

---

## Quick start

For the current tool:

```bash
python3 tools/dependabot-org-summary/dependabot_org_summary.py
```

For setup, requirements, usage, output details, and examples, see the tool-specific README:

[Open the Dependabot Org Summary docs](tools/dependabot-org-summary/README.md)

---

## Design principles

This repository is built around a few simple ideas:

- **Focused tools** — each utility should solve one problem well
- **Low setup** — minimal configuration, fast to run
- **Actionable output** — useful for engineers, leads, and security workflows
- **Scalable structure** — easy to expand without becoming messy

---

## Notes

- Tool-specific requirements and usage instructions live inside each tool directory
- Output generated from private organizations should be reviewed before sharing publicly
- Future tools can be added under `tools/` using the same pattern

---

## License

MIT
