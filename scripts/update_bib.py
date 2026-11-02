#!/usr/bin/env python3
"""
update_bib.py
-------------
Unified, idempotent maintenance and validation pipeline for publications.bib:
  1. Field hygiene, missing date_added assignment, thesis/preprint venue fallbacks.
  2. Peer-review classification (yes / no / thesis) and automatic promotion of
     preprints that have subsequently been published in peer-reviewed venues.
  3. Incremental affiliation (dvrk_site), venue, and abstract backfilling via
     cached OpenAlex, Crossref, and arXiv lookups with strict title+author checks.
  4. Incremental community cross-reference extraction (dvrk_cites) via Crossref.
  5. Integrity validation against custom_tags.json and canonical BibTeX formatting.

Usage:
    python3 scripts/update_bib.py                  # Full incremental update
    python3 scripts/update_bib.py --dry-run        # Preview changes without writing
    python3 scripts/update_bib.py --offline        # Format, sort, cached cites & validate
    python3 scripts/update_bib.py --check          # Read-only CI / PR validator
    python3 scripts/update_bib.py --check --strict-format
"""

from __future__ import annotations

import argparse
import collections
import datetime
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from bib_utils import (
    CACHE_DIR,
    CONTAINER_WORK_TYPES,
    CUSTOM_TAGS_PATH,
    DEFAULT_BIB_PATH,
    MASTHEAD_RE,
    PEER_REVIEW_OVERRIDES_PATH,
    PREPRINT_HOSTS,
    THESIS_PATTERNS,
    USER_AGENT,
    clean_abstract_text,
    clean_doi_preserve_case,
    compact_title_key,
    extract_arxiv_id,
    extract_surnames,
    format_bib_string,
    load_bib,
    load_custom_tags,
    load_peer_review_overrides,
    match_sites,
    normalize_doi,
    normalize_title,
    reconstruct_openalex_abstract,
    redirect_or_prune_cites,
    title_similarity,
    write_bib,
)

AFFILIATION_CACHE_PATH = os.path.join(CACHE_DIR, "affiliation_cache.json")
REFERENCE_CACHE_PATH = os.path.join(CACHE_DIR, "reference_cache.json")


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def load_json_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_json_cache(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def load_reference_cache(path: str = REFERENCE_CACHE_PATH) -> dict[str, list]:
    raw = load_json_cache(path)
    out: dict[str, list] = {}
    for doi, val in raw.items():
        if isinstance(val, dict) and val.get("status") == "ok":
            out[doi] = val.get("references", [])
    return out


def save_reference_cache(cache: dict[str, list], path: str = REFERENCE_CACHE_PATH) -> None:
    payload = {doi: {"status": "ok", "references": refs} for doi, refs in sorted(cache.items())}
    save_json_cache(path, payload)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def is_thesis(entry: dict) -> bool:
    etype = (entry.get("ENTRYTYPE") or "").lower()
    if etype in ("phdthesis", "mastersthesis"):
        return True
    doi = (entry.get("doi") or "").lower()
    url = (entry.get("url") or "").lower()
    return any(pat in doi or pat in url for pat in THESIS_PATTERNS)


def is_preprint_venue(venue_name: str | None) -> bool:
    if not venue_name:
        return True
    v_low = venue_name.lower()
    return any(host in v_low for host in PREPRINT_HOSTS)


def is_candidate_preprint(entry: dict) -> bool:
    j = (entry.get("journal") or "").lower()
    b = (entry.get("booktitle") or "").lower()
    h = (entry.get("howpublished") or "").lower()
    doi = (entry.get("doi") or "").lower()
    url = (entry.get("url") or "").lower()
    eprint = (entry.get("eprint") or "").lower()
    archiveprefix = (entry.get("archiveprefix") or "").lower()
    etype = (entry.get("ENTRYTYPE") or "").lower()

    venue = f"{j} {b}".strip()
    if venue and not any(host in venue for host in PREPRINT_HOSTS):
        return False

    if any(host in j or host in b or host in h or host in doi or host in url for host in PREPRINT_HOSTS):
        return True
    if archiveprefix == "arxiv" or eprint:
        return True
    if etype == "misc" and not (b or j):
        return True
    return False


# ---------------------------------------------------------------------------
# Upstream API helpers (OpenAlex, Crossref, arXiv)
# ---------------------------------------------------------------------------

def fetch_crossref_work(doi: str) -> dict | None:
    clean = normalize_doi(doi)
    if not clean or clean.startswith("10.48550/arxiv"):
        return None
    try:
        r = requests.get(
            f"https://api.crossref.org/works/{requests.utils.quote(clean, safe='')}",
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("message", {})
    except Exception:
        pass
    return None


def fetch_openalex_work(target: str) -> dict | None:
    """Fetch a single OpenAlex work by DOI URL (e.g. 'https://doi.org/10.1109/...')."""
    try:
        r = requests.get(
            f"https://api.openalex.org/works/{target}",
            params={
                "select": "id,doi,title,display_name,type,publication_year,primary_location,authorships,abstract_inverted_index"
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def batch_fetch_openalex_dois(dois: list[str]) -> dict[str, dict]:
    """Batch-fetch OpenAlex works for a list of normalized DOIs."""
    unique = sorted({normalize_doi(d) for d in dois if normalize_doi(d)})
    results: dict[str, dict] = {}
    batch_size = 40
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i + batch_size]
        filt = "|".join(f"https://doi.org/{d}" for d in batch)
        try:
            r = requests.get(
                "https://api.openalex.org/works",
                params={
                    "filter": f"doi:{filt}",
                    "per-page": 50,
                    "select": "id,doi,title,display_name,type,publication_year,primary_location,authorships,abstract_inverted_index",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if r.status_code == 200:
                for w in r.json().get("results", []):
                    d = normalize_doi(w.get("doi"))
                    if d:
                        results[d] = w
        except Exception:
            pass
        time.sleep(0.1)
    return results


def extract_openalex_institutions(work: dict, paper_year: str | None = None) -> list[str]:
    """Extract author institution names from an OpenAlex work (with author-profile fallback)."""
    institutions: list[str] = []
    for authorship in work.get("authorships") or []:
        for inst in authorship.get("institutions") or []:
            name = (inst or {}).get("display_name") or ""
            if name:
                institutions.append(name)
        for raw_aff in authorship.get("raw_affiliation_strings") or []:
            if raw_aff:
                institutions.append(raw_aff)

    if institutions:
        return institutions

    target_years = None
    if paper_year:
        try:
            py = int(paper_year)
            target_years = {py, py - 1, py + 1}
        except ValueError:
            pass

    for authorship in (work.get("authorships") or [])[:8]:
        author_id = ((authorship.get("author") or {}).get("id") or "")
        if not author_id:
            continue
        api_url = author_id.replace("https://openalex.org/", "https://api.openalex.org/")
        try:
            r = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=6)
            if r.status_code == 200:
                a_data = r.json()
                if target_years:
                    for aff in a_data.get("affiliations") or []:
                        years = set(aff.get("years") or [])
                        if years & target_years:
                            name = ((aff.get("institution") or {}).get("display_name") or "")
                            if name:
                                institutions.append(name)
                else:
                    for inst in a_data.get("last_known_institutions") or []:
                        name = (inst or {}).get("display_name") or ""
                        if name:
                            institutions.append(name)
            time.sleep(0.08)
        except Exception:
            pass

    return institutions


def fetch_arxiv_abstract_by_id_or_title(arxiv_id: str | None, title: str, authors: str) -> tuple[str | None, str]:
    """Query arXiv Atom API by ID or exact title to retrieve (arxiv_id, abstract)."""
    params = (
        {"id_list": arxiv_id, "max_results": 1}
        if arxiv_id
        else {"search_query": f'ti:"{re.sub(r"[{}]", "", title).strip()}"', "max_results": 3}
    )
    bib_surnames = extract_surnames(authors)
    try:
        r = requests.get(
            "https://export.arxiv.org/api/query",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code == 200:
            for entry_xml in re.findall(r"<entry>([\s\S]*?)</entry>", r.text):
                tm = re.search(r"<title>([\s\S]*?)</title>", entry_xml)
                sm = re.search(r"<summary>([\s\S]*?)</summary>", entry_xml)
                im = re.search(r"<id>https?://arxiv\.org/abs/([^<\s]+)</id>", entry_xml)
                if not tm or not im:
                    continue
                min_sim = 0.70 if arxiv_id else 0.88
                if title_similarity(title, tm.group(1)) >= min_sim:
                    xml_authors = " and ".join(re.findall(r"<name>([\s\S]*?)</name>", entry_xml))
                    if arxiv_id or not bib_surnames or (bib_surnames & extract_surnames(xml_authors)):
                        aid = re.sub(r"v\d+$", "", im.group(1).strip())
                        abstract = clean_abstract_text(sm.group(1) if sm else "")
                        return aid, abstract
    except Exception:
        pass
    return None, ""


def check_published_promotion(entry: dict) -> dict | None:
    """Check whether a candidate preprint has been formally published in a peer-reviewed venue."""
    title = entry.get("title", "")
    existing_doi = clean_doi_preserve_case(entry.get("doi"))
    arxiv_id = extract_arxiv_id(entry)

    # 1. Non-preprint DOI on Crossref
    if existing_doi and not any(p in existing_doi.lower() for p in PREPRINT_HOSTS):
        cr = fetch_crossref_work(existing_doi)
        if cr:
            ct = (cr.get("title") or [""])[0]
            wtype = cr.get("type") or ""
            if title_similarity(title, ct) >= 0.65 and wtype in ("journal-article", "proceedings-article", "book-chapter"):
                venue = html.unescape((cr.get("container-title") or [""])[0]).strip()
                if venue and not is_preprint_venue(venue):
                    issued = ((cr.get("issued") or {}).get("date-parts") or [[None]])[0]
                    return {
                        "doi": existing_doi,
                        "venue": venue,
                        "work_type": wtype,
                        "year": issued[0] if issued else None,
                    }

    # 2. OpenAlex lookup via non-preprint DOI or arXiv DOI
    target = None
    if existing_doi and not any(p in existing_doi.lower() for p in PREPRINT_HOSTS):
        target = f"https://doi.org/{existing_doi}"
    elif arxiv_id:
        target = f"https://doi.org/10.48550/arxiv.{arxiv_id}"

    if target:
        data = fetch_openalex_work(target)
        if data:
            wt = data.get("title") or data.get("display_name") or ""
            if title_similarity(title, wt) >= 0.65:
                canonical_doi = clean_doi_preserve_case(data.get("doi"))
                src = ((data.get("primary_location") or {}).get("source") or {})
                source_name = (src.get("display_name") or "").strip()
                source_type = src.get("type") or ""
                if (
                    source_name
                    and source_type != "repository"
                    and "..." not in source_name
                    and not is_preprint_venue(source_name)
                ):
                    is_pub = (
                        (canonical_doi and not any(p in canonical_doi.lower() for p in PREPRINT_HOSTS))
                        or source_type in ("journal", "conference")
                    )
                    if is_pub:
                        return {
                            "doi": canonical_doi or existing_doi,
                            "venue": source_name,
                            "work_type": data.get("type") or "",
                            "year": data.get("publication_year"),
                        }
    return None


def fetch_references_crossref(doi: str) -> list[dict] | None:
    """Fetch referenced DOIs and article titles from Crossref for dvrk_cites matching."""
    msg = fetch_crossref_work(doi)
    if msg is None:
        return None
    extracted: list[dict] = []
    for ref in msg.get("reference") or []:
        r_doi = normalize_doi(ref.get("DOI"))
        r_title = (ref.get("article-title") or "").strip()
        if r_doi or r_title:
            extracted.append({"doi": r_doi, "title": r_title})
    return extracted


# ---------------------------------------------------------------------------
# Integrity Validation (--check)
# ---------------------------------------------------------------------------

def validate_bib(
    entries: list[dict],
    custom_tags: dict[str, set[str]],
    strict_format: bool = False,
    raw_file_text: str | None = None,
    formatted_text: str | None = None,
) -> tuple[list[str], list[str]]:
    """
    Validate bibliography entries.
    Returns (errors, advisories). Errors fail CI (--check); advisories inform PR authors.
    """
    errors: list[str] = []
    advisories: list[str] = []

    seen_ids: set[str] = set()
    doi_map: dict[str, list[dict]] = collections.defaultdict(list)
    valid_ids = {e.get("ID", "") for e in entries if e.get("ID")}

    for idx, e in enumerate(entries, 1):
        eid = (e.get("ID") or "").strip()
        if not eid:
            errors.append(f"Entry #{idx} is missing a citation key (ID).")
            continue

        if eid in seen_ids:
            errors.append(f"Duplicate citation key '{eid}'.")
        seen_ids.add(eid)

        # Required core bibliographic fields
        for req in ("author", "title", "year"):
            if not (e.get(req) or "").strip():
                errors.append(f"[{eid}] Missing required field '{req}'.")

        # Venue presence
        has_venue = any((e.get(vf) or "").strip() for vf in ("journal", "booktitle", "howpublished", "school"))
        if not has_venue:
            msg = f"[{eid}] Missing venue field (journal, booktitle, howpublished, or school)."
            if strict_format or e.get("peer_reviewed") == "yes":
                errors.append(msg)
            else:
                advisories.append(msg)

        # DOI uniqueness & container check
        ndoi = normalize_doi(e.get("doi"))
        if ndoi:
            doi_map[ndoi].append(e)

        # Custom tag code validation against custom_tags.json
        for tag_field, allowed_codes in custom_tags.items():
            raw_val = (e.get(tag_field) or "").strip()
            if not raw_val:
                if tag_field == "peer_reviewed":
                    if strict_format:
                        errors.append(f"[{eid}] Missing 'peer_reviewed' field.")
                    else:
                        advisories.append(f"[{eid}] Missing 'peer_reviewed' (will be auto-assigned by update_bib.py).")
                continue
            tokens = [raw_val] if tag_field == "peer_reviewed" else [t.strip() for t in raw_val.split(" and ") if t.strip()]
            for tok in tokens:
                if tok not in allowed_codes:
                    errors.append(
                        f"[{eid}] Unknown {tag_field} code '{tok}' (valid: {', '.join(sorted(allowed_codes))})."
                    )

        if not (e.get("date_added") or "").strip():
            if strict_format:
                errors.append(f"[{eid}] Missing 'date_added' field.")
            else:
                advisories.append(f"[{eid}] Missing 'date_added' (will be auto-assigned by update_bib.py).")

        # dvrk_cites referential integrity
        raw_cites = (e.get("dvrk_cites") or "").strip()
        if raw_cites:
            for c in [x.strip() for x in raw_cites.split(" and ") if x.strip()]:
                if c == eid:
                    errors.append(f"[{eid}] Self-citation in dvrk_cites ('{c}').")
                elif c not in valid_ids:
                    errors.append(f"[{eid}] Dangling dvrk_cites reference '{c}' not found in publications.bib.")

        # Abstract masthead check
        cur_abs = (e.get("abstract") or "").strip()
        if cur_abs and MASTHEAD_RE.search(cur_abs):
            errors.append(f"[{eid}] Abstract matches journal/conference masthead boilerplate.")

    for ndoi, group in doi_map.items():
        if len(group) > 1:
            all_chapters = all(
                (g.get("ENTRYTYPE") or "").lower() in ("inbook", "incollection")
                and ("10.1007/978-" in ndoi or "10.1016/c" in ndoi)
                for g in group
            )
            if not all_chapters:
                keys = ", ".join(g["ID"] for g in group)
                errors.append(f"Duplicate DOI '{ndoi}' shared across entries: {keys}.")

    if strict_format and raw_file_text is not None and formatted_text is not None:
        if raw_file_text != formatted_text:
            errors.append(
                "publications.bib is not canonically sorted/formatted. Run 'python3 scripts/update_bib.py --offline'."
            )

    return errors, advisories


# ---------------------------------------------------------------------------
# Unified Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    bib_path: str = DEFAULT_BIB_PATH,
    dry_run: bool = False,
    offline: bool = False,
    check_only: bool = False,
    strict_format: bool = False,
    refresh_misses: bool = False,
    write_citations_json: bool = False,
) -> int:
    with open(bib_path, "r", encoding="utf-8") as f:
        raw_file_text = f.read()

    bib_db = load_bib(bib_path)
    entries = bib_db.entries
    custom_tags = load_custom_tags(CUSTOM_TAGS_PATH)
    print(f"Loaded {len(entries)} entries from {bib_path}")

    if check_only:
        formatted = format_bib_string(bib_db, sort=True) if strict_format else None
        errors, advisories = validate_bib(
            entries,
            custom_tags,
            strict_format=strict_format,
            raw_file_text=raw_file_text,
            formatted_text=formatted,
        )
        for adv in advisories:
            print(f"  [ADVISORY] {adv}")
        if errors:
            print(f"\nValidation FAILED with {len(errors)} error(s):")
            for err in errors:
                print(f"  ✗ {err}")
            return 1
        print(f"Validation PASSED ({len(entries)} entries, {len(advisories)} advisories). ✅")
        return 0

    overrides = load_peer_review_overrides(PEER_REVIEW_OVERRIDES_PATH)
    key_overrides = overrides.get("keys", {})
    venue_overrides = overrides.get("venues", {})
    today_iso = datetime.date.today().isoformat()

    promotions: list[tuple[str, str, str, str]] = []
    sites_tagged = 0
    abstracts_filled = 0
    venues_filled = 0

    # --- Stage 1 & 2: Field Hygiene, Peer-Review Tagging & Preprint Promotion ---
    for e in entries:
        eid = e["ID"]
        etype = (e.get("ENTRYTYPE") or "").lower()

        # Normalize DOI format (strip https://doi.org/ prefix if pasted in raw BibTeX)
        if e.get("doi"):
            e["doi"] = clean_doi_preserve_case(e["doi"])

        # Unescape HTML entities in venues and strip leading 'Abstract:' prefix
        for vf in ("journal", "booktitle"):
            if e.get(vf):
                e[vf] = " ".join(html.unescape(e[vf]).split())
        if e.get("abstract"):
            cleaned_abs = re.sub(r"^\s*Abstract(?:[\s:.\-—]+(?=[A-Z]))", "", e["abstract"].strip())
            if len(cleaned_abs) > 60:
                e["abstract"] = cleaned_abs

        if not (e.get("date_added") or "").strip():
            e["date_added"] = today_iso

        # Classify peer_reviewed
        if eid in key_overrides:
            e["peer_reviewed"] = key_overrides[eid]
        elif is_thesis(e) or e.get("peer_reviewed") == "thesis":
            e["peer_reviewed"] = "thesis"
        elif is_candidate_preprint(e):
            promoted = check_published_promotion(e) if not offline else None
            if promoted and promoted.get("venue"):
                old_v = e.get("journal") or e.get("booktitle") or e.get("howpublished") or "Preprint"
                new_v = promoted["venue"]
                new_doi = promoted.get("doi") or e.get("doi", "")
                wtype = promoted.get("work_type") or ""
                promotions.append((eid, old_v, new_v, new_doi))
                e["peer_reviewed"] = "yes"
                if "journal" in wtype or etype == "article":
                    e["journal"] = new_v
                    e["ENTRYTYPE"] = "article"
                    e.pop("booktitle", None)
                else:
                    e["booktitle"] = new_v
                    e["ENTRYTYPE"] = "inproceedings"
                    e.pop("journal", None)
                if new_doi:
                    e["doi"] = new_doi
                if promoted.get("year"):
                    e["year"] = str(promoted["year"])
                if "howpublished" in e and any(h in e["howpublished"].lower() for h in PREPRINT_HOSTS):
                    del e["howpublished"]
            else:
                e["peer_reviewed"] = "no"
        else:
            v_combined = f"{e.get('journal', '')} {e.get('booktitle', '')}".strip().lower()
            matched_ov = None
            for v_pat, v_stat in venue_overrides.items():
                if v_pat.lower() in v_combined:
                    matched_ov = v_stat
                    break
            e["peer_reviewed"] = matched_ov or "yes"

        # Standardize theses & preprint venue fallbacks
        etype = (e.get("ENTRYTYPE") or "").lower()
        if e.get("peer_reviewed") == "thesis":
            if etype not in ("phdthesis", "mastersthesis"):
                e["ENTRYTYPE"] = "phdthesis"
            if not e.get("school") and e.get("publisher"):
                e["school"] = re.sub(r"\s+Library$", "", e["publisher"].strip(), flags=re.IGNORECASE)
                venues_filled += 1
        elif e.get("peer_reviewed") == "no":
            aid = extract_arxiv_id(e)
            if aid and not e.get("arxiv"):
                e["arxiv"] = f"https://arxiv.org/abs/{aid}"
            for vf in ("journal", "booktitle"):
                if (e.get(vf) or "").strip().lower() in ("arxiv", "arxiv preprint", "arxiv.org"):
                    e[vf] = f"arXiv preprint arXiv:{aid}" if aid else "arXiv preprint"
            if not (e.get("journal") or e.get("booktitle") or e.get("howpublished")):
                if aid:
                    e["howpublished"] = f"arXiv preprint arXiv:{aid}"
                    venues_filled += 1
                elif "21203/rs" in (e.get("doi") or "").lower() or "researchsquare" in (e.get("url") or "").lower():
                    e["howpublished"] = "Research Square preprint"
                    venues_filled += 1

    # --- Stage 3: Incremental Affiliation, Venue & Abstract Backfill ---
    if not offline:
        aff_cache = load_json_cache(AFFILIATION_CACHE_PATH)
        aff_cache_dirty = False

        # Identify entries that actually need OpenAlex/Crossref/arXiv lookups
        needs_work: list[dict] = []
        dois_to_batch: list[str] = []

        for e in entries:
            missing_site = not (e.get("dvrk_site") or "").strip()
            missing_abs = not (e.get("abstract") or "").strip()
            missing_venue = not any((e.get(vf) or "").strip() for vf in ("journal", "booktitle", "howpublished", "school"))
            if not (missing_site or missing_abs or missing_venue):
                continue

            doi_raw = clean_doi_preserve_case(e.get("doi"))
            ndoi = normalize_doi(doi_raw)

            # Check if cached affiliation already covers a site-only miss
            if missing_site and not missing_abs and not missing_venue and doi_raw in aff_cache:
                cached_entry = aff_cache[doi_raw]
                cached_affs = cached_entry.get("affiliations", []) if isinstance(cached_entry, dict) else cached_entry
                if cached_affs or not refresh_misses:
                    matched = match_sites(cached_affs)
                    if matched:
                        e["dvrk_site"] = " and ".join(sorted(matched))
                        sites_tagged += 1
                    continue

            needs_work.append(e)
            if ndoi and not ndoi.startswith("10.48550/arxiv"):
                dois_to_batch.append(ndoi)

        oa_map = batch_fetch_openalex_dois(dois_to_batch) if dois_to_batch else {}

        for e in needs_work:
            title = e.get("title", "")
            authors = e.get("author", "")
            doi_raw = clean_doi_preserve_case(e.get("doi"))
            ndoi = normalize_doi(doi_raw)
            etype = (e.get("ENTRYTYPE") or "").lower()

            missing_site = not (e.get("dvrk_site") or "").strip()
            missing_abs = not (e.get("abstract") or "").strip()
            missing_venue = not any((e.get(vf) or "").strip() for vf in ("journal", "booktitle", "howpublished", "school"))

            oa_work = oa_map.get(ndoi) if ndoi else None
            if oa_work and title_similarity(title, oa_work.get("title") or oa_work.get("display_name")) < 0.65:
                oa_work = None

            cr_work = None

            # 3a. Affiliation backfill
            if missing_site and doi_raw:
                insts: list[str] = []
                w_title = ""
                if oa_work:
                    insts = extract_openalex_institutions(oa_work, e.get("year"))
                    w_title = oa_work.get("title") or ""
                if not insts:
                    cr_work = fetch_crossref_work(doi_raw)
                    if cr_work and title_similarity(title, (cr_work.get("title") or [""])[0]) >= 0.65:
                        w_title = (cr_work.get("title") or [""])[0]
                        for auth in cr_work.get("author") or []:
                            for aff in auth.get("affiliation") or []:
                                if aff.get("name"):
                                    insts.append(aff["name"])
                aff_cache[doi_raw] = {"title": w_title, "affiliations": insts}
                aff_cache_dirty = True
                matched = match_sites(insts)
                if matched:
                    e["dvrk_site"] = " and ".join(sorted(matched))
                    sites_tagged += 1

            # 3b. Missing venue backfill (prefer Crossref container-title)
            if missing_venue and e.get("peer_reviewed") == "yes" and doi_raw:
                if cr_work is None:
                    cr_work = fetch_crossref_work(doi_raw)
                v_name = ""
                wtype = ""
                if cr_work and title_similarity(title, (cr_work.get("title") or [""])[0]) >= 0.65:
                    v_name = html.unescape((cr_work.get("container-title") or [""])[0]).strip()
                    wtype = cr_work.get("type") or ""
                if not v_name and oa_work:
                    src = ((oa_work.get("primary_location") or {}).get("source") or {})
                    if src.get("type") != "repository":
                        cand_v = (src.get("display_name") or "").strip()
                        if "..." not in cand_v:
                            v_name = cand_v
                            wtype = oa_work.get("type") or ""
                if v_name:
                    v_name = " ".join(v_name.split())
                    if etype == "article" or "journal" in wtype:
                        e["journal"] = v_name
                    else:
                        e["booktitle"] = v_name
                    venues_filled += 1

            # 3c. Missing abstract backfill
            if missing_abs:
                cand_abs = ""
                if oa_work:
                    cand_abs = reconstruct_openalex_abstract(oa_work.get("abstract_inverted_index"))
                if not cand_abs and doi_raw:
                    if cr_work is None:
                        cr_work = fetch_crossref_work(doi_raw)
                    if cr_work and title_similarity(title, (cr_work.get("title") or [""])[0]) >= 0.65:
                        cand_abs = clean_abstract_text(cr_work.get("abstract"))
                if not cand_abs and (e.get("peer_reviewed") == "no" or extract_arxiv_id(e)):
                    aid, arx_abs = fetch_arxiv_abstract_by_id_or_title(extract_arxiv_id(e), title, authors)
                    cand_abs = arx_abs
                    if aid and not e.get("arxiv"):
                        e["arxiv"] = f"https://arxiv.org/abs/{aid}"
                if cand_abs and len(cand_abs) >= 60 and not MASTHEAD_RE.search(cand_abs):
                    e["abstract"] = cand_abs
                    abstracts_filled += 1

        if aff_cache_dirty and not dry_run:
            save_json_cache(AFFILIATION_CACHE_PATH, aff_cache)

    # --- Stage 4: Internal Community Cross-References (dvrk_cites) ---
    ref_cache = load_reference_cache(REFERENCE_CACHE_PATH)
    uncached_dois = [
        normalize_doi(e.get("doi"))
        for e in entries
        if normalize_doi(e.get("doi"))
        and not normalize_doi(e.get("doi")).startswith("10.48550/arxiv")
        and normalize_doi(e.get("doi")) not in ref_cache
    ]

    if uncached_dois and not offline:
        unique_uncached = sorted(set(uncached_dois))
        print(f"Fetching Crossref reference lists for {len(unique_uncached)} new DOI(s)...")
        fetched_any = False
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_references_crossref, d): d for d in unique_uncached}
            for fut in as_completed(futures):
                d = futures[fut]
                try:
                    refs = fut.result()
                    if refs is not None:
                        ref_cache[d] = refs
                        fetched_any = True
                except Exception:
                    pass
        if fetched_any and not dry_run:
            save_reference_cache(ref_cache, REFERENCE_CACHE_PATH)

    doi_to_ids: dict[str, list[str]] = collections.defaultdict(list)
    title_to_ids: dict[str, list[str]] = collections.defaultdict(list)
    entry_by_id: dict[str, dict] = {}

    for e in entries:
        pid = e["ID"]
        entry_by_id[pid] = e
        nd = normalize_doi(e.get("doi"))
        ct = compact_title_key(e.get("title"))
        if nd:
            doi_to_ids[nd].append(pid)
        if ct and len(ct) > 15:
            title_to_ids[ct].append(pid)

    unique_dois = {d: ids[0] for d, ids in doi_to_ids.items() if len(ids) == 1}
    citations_report = {pid: {"cites": [], "cited_by": []} for pid in entry_by_id}
    new_cite_links = 0

    for e in entries:
        pid = e["ID"]
        nd = normalize_doi(e.get("doi"))
        matched_targets: set[str] = set()

        if nd and nd in ref_cache:
            for ref in ref_cache[nd]:
                r_doi = normalize_doi(ref.get("doi"))
                r_ct = compact_title_key(ref.get("title"))
                target_id = None
                if r_doi and r_doi in unique_dois:
                    cand_id = unique_dois[r_doi]
                    if r_ct and r_ct != compact_title_key(entry_by_id[cand_id].get("title")):
                        target_id = None
                    else:
                        target_id = cand_id
                elif not r_doi and len(r_ct) > 20:
                    cands = title_to_ids.get(r_ct, [])
                    if len(cands) == 1:
                        target_id = cands[0]

                if target_id and target_id != pid:
                    matched_targets.add(target_id)

        existing_cites = [
            c.strip()
            for c in (e.get("dvrk_cites") or "").split(" and ")
            if c.strip() and c.strip() in entry_by_id and c.strip() != pid
        ]
        combined = sorted(set(existing_cites) | matched_targets)
        if len(combined) > len(existing_cites):
            new_cite_links += len(combined) - len(existing_cites)

        if combined:
            e["dvrk_cites"] = " and ".join(combined)
            for t_id in combined:
                citations_report[pid]["cites"].append(t_id)
                citations_report[t_id]["cited_by"].append(pid)
        elif "dvrk_cites" in e:
            del e["dvrk_cites"]

    pruned_cites = redirect_or_prune_cites(entries)

    if write_citations_json and not dry_run:
        total_edges = sum(len(v["cites"]) for v in citations_report.values())
        with open("citations.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": {
                        "total_papers": len(entries),
                        "total_citations": total_edges,
                    },
                    "citations": citations_report,
                },
                f,
                indent=2,
            )

    # --- Stage 5: Validation & Canonical Write ---
    errors, _ = validate_bib(entries, custom_tags, strict_format=False)
    pr_counts = collections.Counter(e.get("peer_reviewed", "") for e in entries)

    print("\n--- Pipeline Summary ---")
    print(f"Total publications:    {len(entries)} (peer-reviewed: {pr_counts['yes']}, preprints: {pr_counts['no']}, theses: {pr_counts['thesis']})")
    print(f"Preprints promoted:    {len(promotions)}")
    print(f"Sites backfilled:      {sites_tagged}")
    print(f"Venues backfilled:     {venues_filled}")
    print(f"Abstracts backfilled:  {abstracts_filled}")
    print(f"New citation links:    {new_cite_links} (pruned: {pruned_cites})")

    if promotions:
        print("\nPromoted Preprints:")
        for eid, old_v, new_v, new_d in promotions:
            print(f"  • {eid}: '{old_v}' -> '{new_v}' (DOI: {new_d})")

    if errors:
        print(f"\n⚠️ Validation detected {len(errors)} error(s):")
        for err in errors:
            print(f"  ✗ {err}")
        return 1

    if not dry_run:
        write_bib(bib_path, bib_db, sort=True)
        print(f"\nSuccessfully updated and formatted {bib_path}. ✅")
    else:
        print("\n[Dry Run] No files were modified.")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified maintenance, enrichment, and validation pipeline for publications.bib."
    )
    parser.add_argument("--bib", default=DEFAULT_BIB_PATH, help="Path to publications.bib")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without modifying files")
    parser.add_argument("--offline", action="store_true", help="Skip network requests; format, sort, apply caches, and validate")
    parser.add_argument("--check", action="store_true", help="Read-only validation mode for CI and Pull Requests")
    parser.add_argument("--strict-format", action="store_true", help="With --check, also require canonical sorting/formatting and all auto-fields")
    parser.add_argument("--refresh-misses", action="store_true", help="Retry cached empty affiliation lookups")
    parser.add_argument("--write-citations-json", action="store_true", help="Export citation graph summary to citations.json")
    args = parser.parse_args()

    sys.exit(
        run_pipeline(
            bib_path=args.bib,
            dry_run=args.dry_run,
            offline=args.offline,
            check_only=args.check,
            strict_format=args.strict_format,
            refresh_misses=args.refresh_misses,
            write_citations_json=args.write_citations_json,
        )
    )


if __name__ == "__main__":
    main()

