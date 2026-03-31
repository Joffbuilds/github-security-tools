#!/usr/bin/env python3
"""
dependabot_org_summary.py

Purpose
-------
Fetch current open High + Critical GitHub Dependabot alerts for a selected org
and generate a simple, readable security summary.

Design goals
------------
- No hardcoded org names
- No hardcoded tokens
- Browser-based GitHub authentication fallback
- Safe for publishing publicly
- Easy for non-experts to run
- Output that helps engineering leaders quickly assess backlog health

What it writes
--------------
- dependabot_alerts_raw.json
- dependabot_alerts_raw.csv
- dependabot_repo_summary.csv
- dependabot_org_summary.md

Important
---------
These output files contain org-specific security data. Review before sharing.
Do not commit generated output from private organizations into a public repo.

Requirements
------------
- Python 3.9+
- GitHub CLI (`gh`) installed

Examples
--------
Interactive org selection:
    python3 dependabot_org_summary.py

Explicit org:
    python3 dependabot_org_summary.py --org your-github-org

Redacted output for screenshots / public demos:
    python3 dependabot_org_summary.py --org your-github-org --redact
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple


# GitHub REST API version header.
# Keep this easy to find and update in one place if needed.
API_VERSION = "2026-03-10"


@dataclass
class AlertRow:
    """Normalized representation of one Dependabot alert."""

    number: Any
    repo: str
    severity: str
    package: str
    ecosystem: str
    manifest_path: str
    ghsa_id: str
    cve: str
    summary: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    days_open: Optional[int]
    html_url: str


def run_cmd(cmd: List[str], capture: bool = True, check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command safely without invoking a shell.

    Why this helper exists:
    - Keeps subprocess behavior consistent
    - Avoids copy/pasting subprocess.run everywhere
    - Makes error handling easier to reason about
    """
    return subprocess.run(
        cmd,
        text=True,
        capture_output=capture,
        check=check,
    )


def ensure_python_ok() -> None:
    """Exit early if the Python version is too old."""
    if sys.version_info < (3, 9):
        print("ERROR: Python 3.9+ is required.", file=sys.stderr)
        sys.exit(2)


def ensure_gh_installed() -> None:
    """Exit early if GitHub CLI is not available."""
    if shutil.which("gh") is None:
        print("ERROR: GitHub CLI ('gh') is not installed.", file=sys.stderr)
        print("Install it first, then re-run this script.", file=sys.stderr)
        print("Website: https://cli.github.com/", file=sys.stderr)
        sys.exit(2)


def ensure_authenticated() -> None:
    """
    Make sure the user is authenticated with GitHub CLI.

    If not authenticated, start browser-based login. This is friendlier than
    requiring users to create/export a token manually.
    """
    status = subprocess.run(
        ["gh", "auth", "status"],
        text=True,
        capture_output=True,
    )

    if status.returncode == 0:
        return

    print("\nGitHub CLI is not authenticated.")
    print("Starting browser login flow...\n")

    try:
        subprocess.run(
            ["gh", "auth", "login", "--web", "--hostname", "github.com"],
            check=True,
        )
    except subprocess.CalledProcessError:
        print("ERROR: GitHub login failed.", file=sys.stderr)
        sys.exit(2)

    status_after = subprocess.run(
        ["gh", "auth", "status"],
        text=True,
        capture_output=True,
    )
    if status_after.returncode != 0:
        print("ERROR: Authentication still not available after login.", file=sys.stderr)
        sys.exit(2)


def gh_api_json(endpoint: str, paginate: bool = False) -> Any:
    """
    Call GitHub API through `gh api` and parse the response as JSON.

    We use GitHub CLI rather than raw requests because:
    - it reuses the user's existing auth
    - it supports pagination cleanly
    - it avoids token-handling complexity
    """
    cmd = [
        "gh",
        "api",
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        f"X-GitHub-Api-Version: {API_VERSION}",
    ]

    if paginate:
        # `--paginate` fetches all pages.
        # `--slurp` returns all pages as one JSON array of arrays.
        cmd.extend(["--paginate", "--slurp"])

    cmd.append(endpoint)

    result = run_cmd(cmd)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print("ERROR: Failed to parse GitHub API response as JSON.", file=sys.stderr)
        print(result.stdout[:1000], file=sys.stderr)
        raise exc


def list_user_orgs() -> List[str]:
    """
    Return orgs visible to the authenticated user.

    This keeps the script generic for users with access to multiple orgs.
    """
    data = gh_api_json("/user/orgs?per_page=100", paginate=True)

    orgs: List[str] = []

    if isinstance(data, list):
        for page in data:
            if isinstance(page, list):
                for item in page:
                    if isinstance(item, dict):
                        login = item.get("login")
                        if login:
                            orgs.append(str(login))

    return sorted(set(orgs))


def choose_org_interactively(orgs: List[str]) -> str:
    """
    Let the user pick an org interactively.

    This avoids requiring the user to know or type the org name exactly.
    """
    if not orgs:
        print("ERROR: No organizations were returned for this account.", file=sys.stderr)
        sys.exit(2)

    if len(orgs) == 1:
        print(f"Only one organization found: {orgs[0]}")
        return orgs[0]

    print("\nOrganizations available to this account:\n")
    for i, org in enumerate(orgs, start=1):
        print(f"  {i}. {org}")

    while True:
        raw = input("\nChoose an org by number: ").strip()

        if not raw.isdigit():
            print("Please enter a number.")
            continue

        idx = int(raw)
        if 1 <= idx <= len(orgs):
            return orgs[idx - 1]

        print("Selection out of range.")


def flatten_paginated_response(data: Any) -> List[Dict[str, Any]]:
    """
    Normalize gh --paginate --slurp output into a flat list of objects.

    With `--slurp`, GitHub CLI returns something like:
        [ [page1_items...], [page2_items...] ]
    """
    if isinstance(data, list) and data and isinstance(data[0], list):
        flattened: List[Dict[str, Any]] = []
        for page in data:
            if isinstance(page, list):
                for item in page:
                    if isinstance(item, dict):
                        flattened.append(item)
        return flattened

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-like GitHub timestamps into timezone-aware datetimes."""
    if not value:
        return None

    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except Exception:
        return None


def safe_get(obj: Dict[str, Any], *keys: str, default: str = "") -> str:
    """
    Safely traverse nested dict keys and always return a string.

    Example:
        safe_get(alert, "repository", "full_name")
    """
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return str(cur) if cur is not None else default


def find_cve(identifiers: Any) -> str:
    """Extract the first CVE identifier, if present."""
    if not isinstance(identifiers, list):
        return ""

    for ident in identifiers:
        if isinstance(ident, dict) and ident.get("type") == "CVE":
            return str(ident.get("value", ""))

    return ""


def normalize_alerts(alerts: List[Dict[str, Any]]) -> List[AlertRow]:
    """
    Convert raw GitHub alert payloads into a simpler normalized structure.

    Why normalize:
    - GitHub API payloads are nested and verbose
    - normalized rows are easier to summarize and export
    """
    now = datetime.now(timezone.utc)
    rows: List[AlertRow] = []

    for alert in alerts:
        advisory = alert.get("security_advisory") or {}
        vulnerability = alert.get("security_vulnerability") or {}
        dependency = alert.get("dependency") or {}
        package = dependency.get("package") or {}

        created_at = parse_dt(alert.get("created_at"))
        updated_at = parse_dt(alert.get("updated_at"))
        days_open = (now - created_at).days if created_at else None

        severity = (
            safe_get(advisory, "severity")
            or safe_get(vulnerability, "severity")
            or "unknown"
        ).lower()

        repo = safe_get(alert, "repository", "full_name") or safe_get(alert, "repository", "name") or "unknown"
        pkg = safe_get(vulnerability, "package", "name") or safe_get(package, "name") or "unknown"
        ecosystem = safe_get(vulnerability, "package", "ecosystem") or safe_get(package, "ecosystem") or "unknown"

        rows.append(
            AlertRow(
                number=alert.get("number"),
                repo=repo,
                severity=severity,
                package=pkg,
                ecosystem=ecosystem,
                manifest_path=safe_get(dependency, "manifest_path"),
                ghsa_id=safe_get(advisory, "ghsa_id"),
                cve=find_cve(advisory.get("identifiers")),
                summary=safe_get(advisory, "summary"),
                created_at=created_at,
                updated_at=updated_at,
                days_open=days_open,
                html_url=str(alert.get("html_url", "")),
            )
        )

    return rows


def age_bucket(days: Optional[int]) -> str:
    """Bucket alert age into manager-friendly ranges."""
    if days is None:
        return "unknown"
    if days < 7:
        return "0-6d"
    if days < 30:
        return "7-29d"
    if days < 60:
        return "30-59d"
    if days < 90:
        return "60-89d"
    return "90d+"


def pct(numerator: int, denominator: int) -> float:
    """Return a rounded percentage, avoiding divide-by-zero."""
    return round((numerator / denominator) * 100.0, 1) if denominator else 0.0


def fetch_org_alerts(org: str) -> List[Dict[str, Any]]:
    """
    Fetch current open High + Critical Dependabot alerts for an org.

    This is the core GitHub API call the whole script depends on.
    """
    endpoint = f"/orgs/{org}/dependabot/alerts?state=open&severity=high,critical&per_page=100"

    try:
        data = gh_api_json(endpoint, paginate=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        print("\nERROR: Failed to fetch org-level Dependabot alerts.", file=sys.stderr)
        print(stderr, file=sys.stderr)
        print(
            "\nMost likely causes:\n"
            "  - you chose an org where you do not have enough access\n"
            "  - your GitHub auth does not have the needed permissions\n"
            "  - the org does not expose Dependabot alerts to your account\n",
            file=sys.stderr,
        )
        sys.exit(2)

    return flatten_paginated_response(data)


def redact_rows(rows: List[AlertRow]) -> List[AlertRow]:
    """
    Redact repo names and URLs for safer demos/screenshots.

    This does NOT make the data fully anonymous, but it reduces the most obvious
    identifiers when users want to share sample output publicly.
    """
    repo_aliases: Dict[str, str] = {}
    next_id = 1

    def alias_for(repo: str) -> str:
        nonlocal next_id
        if repo not in repo_aliases:
            repo_aliases[repo] = f"repo-{next_id:03d}"
            next_id += 1
        return repo_aliases[repo]

    redacted: List[AlertRow] = []

    for row in rows:
        redacted.append(
            AlertRow(
                number=row.number,
                repo=alias_for(row.repo),
                severity=row.severity,
                package=row.package,
                ecosystem=row.ecosystem,
                manifest_path="",
                ghsa_id=row.ghsa_id,
                cve=row.cve,
                summary=row.summary,
                created_at=row.created_at,
                updated_at=row.updated_at,
                days_open=row.days_open,
                html_url="",
            )
        )

    return redacted


def write_raw_csv(rows: List[AlertRow], path: Path) -> None:
    """Write normalized alert rows to CSV."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "alert_number",
                "repo",
                "severity",
                "package",
                "ecosystem",
                "manifest_path",
                "ghsa_id",
                "cve",
                "summary",
                "created_at",
                "updated_at",
                "days_open",
                "html_url",
            ]
        )

        for row in rows:
            writer.writerow(
                [
                    row.number,
                    row.repo,
                    row.severity,
                    row.package,
                    row.ecosystem,
                    row.manifest_path,
                    row.ghsa_id,
                    row.cve,
                    row.summary,
                    row.created_at.isoformat() if row.created_at else "",
                    row.updated_at.isoformat() if row.updated_at else "",
                    row.days_open if row.days_open is not None else "",
                    row.html_url,
                ]
            )


def write_dict_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    """Write a list of dictionaries to CSV."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def top_rows(counter: Counter, n: int) -> List[Tuple[Any, int]]:
    """Return the top N items from a Counter with stable sorting."""
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))[:n]


def build_repo_stats(rows: List[AlertRow]) -> List[Dict[str, Any]]:
    """
    Build per-repository summary stats.

    These are useful for answering:
    - Which repos have the most alerts?
    - Which repos have the most criticals?
    - Which repos have the oldest backlog?
    """
    by_repo: Dict[str, List[AlertRow]] = defaultdict(list)

    for row in rows:
        by_repo[row.repo].append(row)

    stats: List[Dict[str, Any]] = []

    for repo, alerts in by_repo.items():
        total_alerts = len(alerts)
        critical_alerts = sum(1 for alert in alerts if alert.severity == "critical")
        high_alerts = sum(1 for alert in alerts if alert.severity == "high")
        ages = [alert.days_open for alert in alerts if alert.days_open is not None]

        stats.append(
            {
                "repo": repo,
                "total_alerts": total_alerts,
                "critical_alerts": critical_alerts,
                "high_alerts": high_alerts,
                "median_days_open": round(median(ages), 1) if ages else "",
                "max_days_open": max(ages) if ages else "",
            }
        )

    stats.sort(
        key=lambda row: (
            -row["critical_alerts"],
            -row["total_alerts"],
            -int(row["max_days_open"] or 0),
            row["repo"],
        )
    )
    return stats


def render_markdown(org_label: str, rows: List[AlertRow]) -> str:
    """
    Render a human-readable markdown report.

    `org_label` may be the real org name or a generic label such as 'selected-org'
    when redaction is enabled.
    """
    total = len(rows)
    critical = sum(1 for row in rows if row.severity == "critical")
    high = sum(1 for row in rows if row.severity == "high")

    repos = sorted({row.repo for row in rows})
    packages = sorted({(row.ecosystem, row.package) for row in rows})

    ecosystems = Counter(row.ecosystem for row in rows)
    package_counter = Counter((row.ecosystem, row.package) for row in rows)
    repo_counter = Counter(row.repo for row in rows)
    repo_critical_counter = Counter(row.repo for row in rows if row.severity == "critical")
    age_counter = Counter(age_bucket(row.days_open) for row in rows)

    aged_30 = sum(1 for row in rows if (row.days_open or 0) >= 30)
    aged_60 = sum(1 for row in rows if (row.days_open or 0) >= 60)
    aged_90 = sum(1 for row in rows if (row.days_open or 0) >= 90)

    top5_repo_total = sum(count for _, count in top_rows(repo_counter, 5))
    top5_repo_concentration = pct(top5_repo_total, total)

    repo_stats = build_repo_stats(rows)
    top_repo_stats = repo_stats[:15]

    lines: List[str] = []

    lines.append(f"# Dependabot Org Summary: {org_label}")
    lines.append("")
    lines.append("## Executive KPIs")
    lines.append("")
    lines.append(f"- **Open High + Critical alerts:** {total}")
    lines.append(f"- **Critical:** {critical} ({pct(critical, total)}%)")
    lines.append(f"- **High:** {high}")
    lines.append(f"- **Repos affected:** {len(repos)}")
    lines.append(f"- **Unique package/ecosystem pairs affected:** {len(packages)}")
    lines.append(f"- **Ecosystems affected:** {len(ecosystems)}")
    lines.append(f"- **Alerts aged 30+ days:** {aged_30}")
    lines.append(f"- **Alerts aged 60+ days:** {aged_60}")
    lines.append(f"- **Alerts aged 90+ days:** {aged_90}")
    lines.append(f"- **Top 5 repo concentration:** {top5_repo_concentration}%")
    lines.append("")
    lines.append("## Broad-Audience Readout")
    lines.append("")
    lines.append(
        f"Current GitHub Dependabot exposure in **{org_label}** is **{total} open High/Critical alerts** "
        f"across **{len(repos)} repositories**. **{critical} are Critical** and **{aged_30} have been open 30+ days**, "
        "which is the clearest signal of where remediation urgency is starting to compound. "
        f"The backlog is partially concentrated: the **top 5 repositories account for {top5_repo_concentration}%** "
        "of current open High/Critical exposure, so targeted staffing or short-term swarming in a small number of places "
        "should materially improve the org-wide risk posture."
    )
    lines.append("")
    lines.append("## Manager Prioritization Signals")
    lines.append("")
    lines.append("- Repos with the highest **critical count**")
    lines.append("- Repos with the oldest **30+/60+/90+ day** alerts")
    lines.append("- Repos with the highest **total alert concentration**")
    lines.append("- Package hotspots repeated across multiple repos")
    lines.append("- Ecosystems carrying the most backlog")
    lines.append("")
    lines.append("## Top Repositories")
    lines.append("")
    lines.append("| Repo | Total | Critical | High | Median Days Open | Max Days Open |")
    lines.append("|---|---:|---:|---:|---:|---:|")

    for row in top_repo_stats:
        lines.append(
            f"| {row['repo']} | {row['total_alerts']} | {row['critical_alerts']} | "
            f"{row['high_alerts']} | {row['median_days_open']} | {row['max_days_open']} |"
        )

    lines.append("")
    lines.append("## Top Repositories by Critical Count")
    lines.append("")
    lines.append("| Repo | Critical Alerts |")
    lines.append("|---|---:|")

    for repo, count in top_rows(repo_critical_counter, 15):
        lines.append(f"| {repo} | {count} |")

    lines.append("")
    lines.append("## Ecosystem Breakdown")
    lines.append("")
    lines.append("| Ecosystem | Alerts |")
    lines.append("|---|---:|")

    for ecosystem, count in sorted(ecosystems.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {ecosystem} | {count} |")

    lines.append("")
    lines.append("## Top Package Hotspots")
    lines.append("")
    lines.append("| Ecosystem | Package | Alerts |")
    lines.append("|---|---|---:|")

    for (ecosystem, package), count in sorted(
        package_counter.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )[:20]:
        lines.append(f"| {ecosystem} | {package} | {count} |")

    lines.append("")
    lines.append("## Aging Distribution")
    lines.append("")
    lines.append("| Bucket | Alerts |")
    lines.append("|---|---:|")

    for bucket in ["0-6d", "7-29d", "30-59d", "60-89d", "90d+", "unknown"]:
        if bucket in age_counter:
            lines.append(f"| {bucket} | {age_counter[bucket]} |")

    lines.append("")
    lines.append("## Suggested Broad Update")
    lines.append("")
    lines.append(
        f"> We currently have **{total} open High/Critical Dependabot alerts** across **{len(repos)} repositories** "
        f"in **{org_label}**. Of those, **{critical} are Critical**, and **{aged_30} have been open 30+ days**, which identifies "
        "where remediation urgency is compounding. The backlog is concentrated, with the **top 5 repositories accounting for "
        f"{top5_repo_concentration}% of total exposure**, so targeted staffing in a small number of teams should produce "
        "the fastest org-wide reduction."
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Define and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a GitHub Dependabot High/Critical alert summary for an organization."
    )

    parser.add_argument(
        "--org",
        help="GitHub organization name. If omitted, the script will let you choose interactively.",
    )

    parser.add_argument(
        "--outdir",
        help="Output directory. Defaults to dependabot_summary_<org>.",
    )

    parser.add_argument(
        "--redact",
        action="store_true",
        help="Redact repository names and URLs in output files for safer demos/screenshots.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce console output.",
    )

    return parser.parse_args()


def main() -> int:
    """Program entry point."""
    args = parse_args()

    ensure_python_ok()
    ensure_gh_installed()
    ensure_authenticated()

    org = args.org.strip() if args.org else None

    if not org:
        orgs = list_user_orgs()
        org = choose_org_interactively(orgs)

    if not args.quiet:
        print(f"\nUsing org: {org}")
        print("Fetching current open High + Critical Dependabot alerts...")

    alerts = fetch_org_alerts(org)
    rows = normalize_alerts(alerts)

    # Use redacted rows if requested. This is helpful for screenshots, demos,
    # blog posts, public examples, or sharing sample outputs more safely.
    output_rows = redact_rows(rows) if args.redact else rows

    # When redacted, keep the heading generic instead of revealing the org name.
    org_label = "selected-org" if args.redact else org

    # Default output directory is relative, not absolute. This avoids printing
    # local machine usernames like /Users/<name>/... in logs.
    outdir = Path(args.outdir) if args.outdir else Path(f"dependabot_summary_{org_label}")
    outdir.mkdir(parents=True, exist_ok=True)

    raw_json_path = outdir / "dependabot_alerts_raw.json"
    raw_csv_path = outdir / "dependabot_alerts_raw.csv"
    repo_csv_path = outdir / "dependabot_repo_summary.csv"
    md_path = outdir / "dependabot_org_summary.md"

    raw_json_path.write_text(json.dumps([row.__dict__ for row in output_rows], indent=2, default=str), encoding="utf-8")
    write_raw_csv(output_rows, raw_csv_path)

    repo_stats = build_repo_stats(output_rows)
    write_dict_csv(repo_stats, repo_csv_path)

    markdown = render_markdown(org_label, output_rows)
    md_path.write_text(markdown, encoding="utf-8")

    if not args.quiet:
        print("\nDone.")
        print(f"Org: {org_label}")
        print(f"Open High + Critical alerts: {len(output_rows)}")
        print(f"Output directory: {outdir}")
        print("")
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
