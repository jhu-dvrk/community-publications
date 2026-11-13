#!/usr/bin/env python3
"""
Synchronize dVRK site metadata in custom_tags.json with the canonical site list
maintained at https://dvrk.readthedocs.io/main/pages/introduction/groups.html.

Parses the upstream fixed-column reStructuredText table (`groups.rst`), updates
`year_added`, `years`, and `url` fields on matching `dvrk_site` entries in
custom_tags.json, and flags any newly added upstream groups that do not yet have
a canonical `id`/`country`/alias mapping.

Usage:
    python3 scripts/sync_dvrk_sites.py              # Sync custom_tags.json from ReadTheDocs
    python3 scripts/sync_dvrk_sites.py --dry-run    # Preview diff and unmapped groups
    python3 scripts/sync_dvrk_sites.py --check      # Exit non-zero if out of sync
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass

GROUPS_RST_URLS = (
    "https://dvrk.readthedocs.io/main/_sources/pages/introduction/groups.rst.txt",
    "https://raw.githubusercontent.com/jhu-dvrk/dvrk-readthedocs/main/docs/pages/introduction/groups.rst",
)
CUSTOM_TAGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_tags.json"
)
USER_AGENT = "dvrk-community-publications/1.0 (+https://github.com/jhu-dvrk/community-publications)"

# Upstream `groups.rst` names that intentionally map to an existing site ID
# whose display name or campus split differs from the verbatim table label.
UPSTREAM_NAME_TO_SITE_ID = {
    "chinese university of hong kong": "CUHK",
    "hospital for sick kids, toronto": "SKCH",
    "imperial college": "ICL",
    "intuitive surgical research": "ISS",
    "max planck institute": "MPI",
    "óbuda university, budapest": "OU",
    "obuda university, budapest": "OU",
    "stanford medicine": "SU",
    "stanford university": "SU",
    "u.c. berkeley": "UCB",
    "u.c. san diego": "UCSD",
    "university college, london": "UCL",
    "university of illinois, chicago": "UIC",
    "university of naples": "UNFII",
    "university of texas austin arts": "UTA",
    "university of texas austin hero": "UTA",
    "university of torino": "UNITO",
    "university w. ontario cstar": "UWO",
    "vanderbilt university arma": "VU",
    "vanderbilt university maple": "VU",
    "worcester polytechnic inst.": "WPI",
    "the university of utah": "UU",
    "cleveland clinic": "CCF",
    "dgist (korea)": "DGIST",
    "georgia institute of technology": "GT",
    "albert einstein hospital (brazil)": "HIAE",
    "houston methodist": "HMRI",
    "hochschule reutlingen": "HR",
    "italian institute of technology": "IIT",
    "korea university": "KU",
    "management center innsbruck": "MCI",
    "national institutes of health": "NIH",
    "new york university": "NYU",
    "university of southern denmark": "SDU",
    "surgnova.com": "SURGNOVA",
    "university of maryland": "UMD",
    "university of rennes": "UR",
    "university of toronto": "UTOR",
    "university of twente": "UTW",
    "wake forest": "WFU",
    "yonsei university": "YU",
    "ben gurion university": "BGUN",
}


@dataclass
class UpstreamGroup:
    """Single numbered group parsed from the upstream dVRK groups.rst table."""

    num: int
    name: str
    url: str
    years: list[int]
    pis: list[str]
    systems: list[str]

    @property
    def year_added(self) -> int | None:
        return min(self.years) if self.years else None


def fetch_groups_rst(local_file: str | None = None) -> str:
    """Load groups.rst content from a local file or upstream ReadTheDocs/GitHub."""
    if local_file:
        with open(local_file, "r", encoding="utf-8") as f:
            return f.read()

    last_err: Exception | None = None
    for url in GROUPS_RST_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Failed to fetch upstream groups.rst: {last_err}")


def _clean_rst_text(raw: str) -> tuple[str, str]:
    """Strip RST link syntax, footnotes, and backslash escapes; return (text, url)."""
    url = ""
    match = re.search(r"`([^`<]+)<([^>]+)>`_", raw)
    if match:
        label = match.group(1).strip()
        url = match.group(2).strip()
        remainder = (raw[: match.start()] + raw[match.end() :]).strip()
        text = f"{label} {remainder}".strip() if remainder else label
    else:
        text = raw.strip()
    text = re.sub(r"\s*\[#f\d+\]_", "", text)
    text = text.replace(r"\.", ".")
    return " ".join(text.split()), url


def parse_groups_rst(rst_text: str) -> list[UpstreamGroup]:
    """Parse the fixed-column simple table in groups.rst into UpstreamGroup records."""
    lines = rst_text.splitlines()
    rule_re = re.compile(r"^={3,}(\s+={2,})+\s*$")
    sep_idxs = [idx for idx, line in enumerate(lines) if rule_re.match(line)]
    if len(sep_idxs) < 3:
        raise ValueError("Could not locate simple-table header/footer delimiters in groups.rst.")

    spans = [(m.start(), m.end()) for m in re.finditer(r"=+", lines[sep_idxs[0]])]
    if len(spans) < 5:
        raise ValueError(f"Expected at least 5 table columns, found {len(spans)}.")

    rows: list[dict] = []
    current: dict | None = None
    for line in lines[sep_idxs[1] + 1 : sep_idxs[2]]:
        cols = [line[s:e].strip() if len(line) > s else "" for s, e in spans]
        cols[-1] = line[spans[-1][0] :].strip() if len(line) > spans[-1][0] else ""
        num_str, yr_str, uni_str, pi_str, sys_str = cols[0], cols[1], cols[2], cols[3], cols[4]

        if num_str and num_str != "\\":
            if current is not None:
                rows.append(current)
            current = {
                "num": int(num_str),
                "years": [int(yr_str)] if yr_str.isdigit() else [],
                "raw_uni": uni_str,
                "pis": [pi_str] if pi_str else [],
                "systems": [sys_str] if sys_str else [],
            }
        elif current is not None:
            if yr_str.isdigit():
                current["years"].append(int(yr_str))
            if uni_str:
                current["raw_uni"] = f"{current['raw_uni']} {uni_str}".strip()
            if pi_str:
                current["pis"].append(pi_str)
            if sys_str:
                current["systems"].append(sys_str)

    if current is not None:
        rows.append(current)

    parsed: list[UpstreamGroup] = []
    for row in rows:
        name, url = _clean_rst_text(row["raw_uni"])
        pis = [_clean_rst_text(p)[0] for p in row["pis"] if _clean_rst_text(p)[0]]
        systems = [_clean_rst_text(s)[0] for s in row["systems"] if _clean_rst_text(s)[0]]
        parsed.append(
            UpstreamGroup(
                num=row["num"],
                name=name,
                url=url,
                years=sorted(set(row["years"])),
                pis=pis,
                systems=systems,
            )
        )
    return parsed


def _resolve_site_id(group: UpstreamGroup, by_id: dict[str, dict], by_name: dict[str, str]) -> str | None:
    """Resolve an UpstreamGroup row to a known site ID in custom_tags.json."""
    low = group.name.lower()
    mapped = UPSTREAM_NAME_TO_SITE_ID.get(low)
    if mapped and mapped in by_id:
        return mapped
    if low in by_name:
        return by_name[low]
    for site in by_id.values():
        for alias in site.get("aliases") or []:
            if alias.lower() in low:
                return site["id"]
    return None


def sync_sites(
    custom_tags_path: str = CUSTOM_TAGS_PATH,
    local_file: str | None = None,
    dry_run: bool = False,
    check_only: bool = False,
) -> int:
    """Reconcile custom_tags.json `dvrk_site` entries against upstream groups.rst."""
    with open(custom_tags_path, "r", encoding="utf-8") as f:
        tags_data = json.load(f)

    sites: list[dict] = tags_data.get("dvrk_site", [])
    by_id = {s["id"]: s for s in sites}
    by_name = {s["name"].lower(): s["id"] for s in sites}

    rst_text = fetch_groups_rst(local_file=local_file)
    groups = parse_groups_rst(rst_text)

    aggregated: dict[str, list[UpstreamGroup]] = {}
    unmapped: list[UpstreamGroup] = []
    for group in groups:
        sid = _resolve_site_id(group, by_id, by_name)
        if sid:
            aggregated.setdefault(sid, []).append(group)
        else:
            unmapped.append(group)

    changes: list[str] = []
    for sid, matched_groups in sorted(aggregated.items()):
        site = by_id[sid]
        merged_years = sorted({y for g in matched_groups for y in g.years})
        earliest = min(merged_years) if merged_years else None
        urls = [g.url for g in matched_groups if g.url]

        if earliest is not None and site.get("year_added") != earliest:
            changes.append(f"{sid}: year_added {site.get('year_added')!r} -> {earliest}")
            site["year_added"] = earliest
        if merged_years and site.get("years") != merged_years:
            changes.append(f"{sid}: years {site.get('years')!r} -> {merged_years}")
            site["years"] = merged_years
        if urls and not site.get("url"):
            changes.append(f"{sid}: url None -> {urls[0]}")
            site["url"] = urls[0]

    sorted_sites = sorted(sites, key=lambda s: s["id"])
    if sorted_sites != sites:
        changes.append("Reordered dvrk_site list alphabetically by id")
        tags_data["dvrk_site"] = sorted_sites

    print(f"Parsed {len(groups)} group(s) from upstream groups.rst; matched {len(aggregated)} site ID(s).")
    if unmapped:
        print(f"\n⚠️ {len(unmapped)} unmapped group(s) in groups.rst (add id/country/aliases to custom_tags.json):")
        for g in unmapped:
            print(f"  • #{g.num} ({g.year_added}): {g.name} [PIs: {', '.join(g.pis)}]")

    if changes:
        print(f"\nDetected {len(changes)} site metadata update(s):")
        for c in changes:
            print(f"  • {c}")
    else:
        print("All mapped dvrk_site entries match upstream groups.rst. ✅")

    if check_only:
        return 1 if (unmapped or changes) else 0

    if changes and not dry_run:
        with open(custom_tags_path, "w", encoding="utf-8") as f:
            json.dump(tags_data, f, indent=4, ensure_ascii=False)
            f.write("\n")
        print(f"Updated {custom_tags_path}. ✅")
    elif dry_run and changes:
        print("[Dry Run] No files were modified.")

    return 1 if unmapped else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync dvrk_site entries in custom_tags.json from dvrk.readthedocs.io.")
    parser.add_argument("--tags", default=CUSTOM_TAGS_PATH, help="Path to custom_tags.json")
    parser.add_argument("--file", default=None, help="Optional local groups.rst file path (offline)")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without modifying files")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if unmapped groups or drift exist")
    args = parser.parse_args()
    sys.exit(sync_sites(args.tags, local_file=args.file, dry_run=args.dry_run, check_only=args.check))


if __name__ == "__main__":
    main()
