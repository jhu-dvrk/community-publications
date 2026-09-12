"""
extract_citations.py
--------------------
Extracts internal citations between all papers in publications.bib.
For each paper:
1. Queries Crossref (and cached references) for referenced works.
2. Matches referenced DOIs against all papers in publications.bib.
3. Builds the internal citation references.
4. Writes `dvrk_cites = {ID1 and ID2 and ...}` directly to publications.bib.

Safety policy: an exact, unique DOI or normalized-title match becomes an
automatic link.  A title must map to exactly one database entry; ambiguous
title-only matches are never written to the BibTeX file.
   (The companion `cited_by` relationship is computed dynamically on the fly by app.js).
"""

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
import urllib.request
import urllib.parse
import json
import time
import os
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_PATH = "cache/reference_cache.json"
BIB_PATH = "publications.bib"
HEADERS = {'User-Agent': 'dVRK-Community-Citation-Extractor/1.0 (mailto:deguet@jhu.edu)'}

def load_cache():
    """Return successful cached lookups only.

    Older versions stored a bare list and also stored failures as ``[]``.  A bare
    list remains usable for compatibility, but an empty legacy value is retried:
    there is no way to tell whether it is a real empty bibliography or a timeout.
    """
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                raw_cache = json.load(f)
                cache = {}
                for doi, value in raw_cache.items():
                    if isinstance(value, dict) and value.get("status") == "ok":
                        cache[doi] = value.get("references", [])
                    elif isinstance(value, list) and value:
                        cache[doi] = value
                return cache
        except Exception:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        # Store an explicit success state.  Network errors are intentionally not
        # cached, so a temporary Crossref outage cannot suppress future links.
        json.dump(
            {doi: {"status": "ok", "references": refs}
             for doi, refs in sorted(cache.items())}, f, indent=2)

def normalize_title(t):
    if not t:
        return ""
    t = re.sub(r'[{}\'"\\]', '', t)
    t = re.sub(r'[^a-zA-Z0-9]', '', t).lower()
    return t

def normalize_doi(doi):
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE).strip().lower()
    return doi

def fetch_references_crossref(doi):
    """Fetch referenced DOIs and article titles from CrossRef."""
    clean_doi = normalize_doi(doi)
    if not clean_doi or clean_doi.startswith('10.48550/arxiv'):
        return None
    url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi, safe='')}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            msg = data.get('message', {})
            raw_refs = msg.get('reference', [])
            extracted = []
            for r in raw_refs:
                r_doi = normalize_doi(r.get('DOI', ''))
                r_title = r.get('article-title', '').strip()
                if r_doi or r_title:
                    extracted.append({
                        'doi': r_doi,
                        'title': r_title
                    })
            return extracted
    except Exception:
        return None

def title_review_candidates(ref_title, title_to_ids):
    """Return only exact, unambiguous normalized-title matches.

    ``normalize_title`` is case-insensitive, so e.g. ``Da Vinci`` and
    ``da Vinci`` match.  The uniqueness requirement protects against title
    collisions in the local bibliography.
    """
    normalized = normalize_title(ref_title)
    if len(normalized) <= 20:
        return []
    ids = title_to_ids.get(normalized, [])
    return ids if len(ids) == 1 else []


def main(apply=False, write_json=False, preserve_existing=True, offline=False,
         prune_missing=False):
    print("Loading publications.bib...")
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(BIB_PATH, 'r', encoding='utf-8') as f:
        db = bibtexparser.load(f, parser=parser)

    print(f"Loaded {len(db.entries)} publications.")

    # Build lookup dictionaries
    doi_to_ids = {}
    title_to_ids = {}
    papers_info = {}

    for e in db.entries:
        pid = e['ID']
        doi = normalize_doi(e.get('doi', ''))
        raw_title = e.get('title', '')
        norm_title = normalize_title(raw_title)

        if doi:
            doi_to_ids.setdefault(doi, []).append(pid)
        if norm_title and len(norm_title) > 15:
            title_to_ids.setdefault(norm_title, []).append(pid)

        papers_info[pid] = {
            'id': pid,
            'title': raw_title.replace('{', '').replace('}', '').strip(),
            'year': e.get('year', ''),
            'author': e.get('author', ''),
            'doi': doi,
            'dvrk_site': e.get('dvrk_site', '')
        }

    unique_dois = {doi: ids[0] for doi, ids in doi_to_ids.items() if len(ids) == 1}
    duplicate_dois = sum(1 for ids in doi_to_ids.values() if len(ids) > 1)
    print(f"Indexed {len(unique_dois)} unique DOIs and {len(title_to_ids)} titles "
          f"({duplicate_dois} duplicate DOI values excluded from matching).")

    cache = load_cache()
    print(f"Loaded cache with {len(cache)} entries.")

    entries_to_fetch = []
    for e in db.entries:
        doi = normalize_doi(e.get('doi', ''))
        if doi and doi not in cache:
            entries_to_fetch.append(doi)

    if entries_to_fetch and not offline:
        print(f"Need to fetch references for {len(entries_to_fetch)} DOIs.")
        new_cache = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_doi = {
                executor.submit(fetch_references_crossref, doi): doi
                for doi in entries_to_fetch
            }
            for future in as_completed(future_to_doi):
                doi = future_to_doi[future]
                completed += 1
                try:
                    refs = future.result()
                    if refs is not None:
                        new_cache[doi] = refs
                except Exception:
                    # Do not cache a failed request: it must be retried later.
                    pass

                if completed % 25 == 0 or completed == len(entries_to_fetch):
                    print(f"  Fetched {completed}/{len(entries_to_fetch)} DOIs...")
                time.sleep(0.05)

        cache.update(new_cache)
        save_cache(cache)
        print("Updated reference cache.")
    elif not entries_to_fetch:
        print("All reference lists found in local cache.")
    else:
        print(f"Offline mode: skipped {len(entries_to_fetch)} uncached DOI lookups.")

    # Match internal citations
    print("\nMatching internal community citations...")
    citations = {pid: {"cites": [], "cited_by": []} for pid in papers_info}
    total_edges = 0
    title_only_matches = []
    doi_title_conflicts = []

    for e in db.entries:
        pid = e['ID']
        doi = normalize_doi(e.get('doi', ''))
        if not doi or doi not in cache:
            continue

        refs = cache.get(doi, [])
        matched_targets = set()

        for r in refs:
            r_doi = normalize_doi(r.get('doi', ''))
            r_title = normalize_title(r.get('title', ''))

            target_id = None
            if r_doi and r_doi in unique_dois:
                target_id = unique_dois[r_doi]
                # If Crossref supplies both fields, reject an internally
                # contradictory record rather than trusting either field.
                if r_title:
                    target_title = normalize_title(papers_info[target_id]["title"])
                    if r_title != target_title:
                        doi_title_conflicts.append({
                            "source_id": pid, "target_id": target_id,
                            "reference_doi": r_doi, "reference_title": r.get("title", ""),
                            "target_title": papers_info[target_id]["title"],
                        })
                        target_id = None
            elif not r_doi and r_title:
                candidates = title_review_candidates(r.get("title", ""), title_to_ids)
                if candidates:
                    target_id = candidates[0]
                    title_only_matches.append({
                        "source_id": pid, "candidate_target_id": candidates[0],
                        "reference_title": r.get("title", ""),
                        "target_title": papers_info[candidates[0]]["title"],
                        "reason": "accepted: exact unique normalized title; no reference DOI",
                    })

            if target_id and target_id != pid:
                matched_targets.add(target_id)

        for target_id in sorted(matched_targets):
            citations[pid]["cites"].append(target_id)
            citations[target_id]["cited_by"].append(pid)
            total_edges += 1

    # Sort arrays for stability
    for pid in citations:
        citations[pid]["cites"].sort()
        citations[pid]["cited_by"].sort()

    # Assign dvrk_cites to BibTeX entries only after an explicit --apply.
    tagged_count = 0
    pruned_missing_count = 0
    for e in db.entries:
        pid = e['ID']
        cites_list = citations.get(pid, {}).get("cites", [])
        if preserve_existing and e.get('dvrk_cites'):
            existing_cites = [key.strip() for key in e['dvrk_cites'].split(' and ') if key.strip()]
            if prune_missing:
                valid_existing = [key for key in existing_cites if key in papers_info]
                pruned_missing_count += len(existing_cites) - len(valid_existing)
                existing_cites = valid_existing
            cites_list = sorted(set(cites_list + existing_cites))
        if cites_list:
            e['dvrk_cites'] = " and ".join(cites_list)
            tagged_count += 1
        elif 'dvrk_cites' in e:
            del e['dvrk_cites']

    papers_citing = sum(1 for p in citations.values() if p["cites"])
    papers_cited = sum(1 for p in citations.values() if p["cited_by"])

    print(f"\nInternal Citation Summary:")
    print(f"  Total internal citation links: {total_edges}")
    print(f"  Papers that cite other dVRK papers: {papers_citing}")
    print(f"  Papers cited by other dVRK papers: {papers_cited}")
    if prune_missing:
        print(f"  Missing citation keys pruned: {pruned_missing_count}")

    if apply:
        writer = BibTexWriter()
        writer.indent = '  '
        writer.order_entries_by = None
        writer.add_trailing_comma = True
        with open(BIB_PATH, 'w', encoding='utf-8') as f:
            f.write(writer.write(db))
        print(f"\nSuccessfully wrote dvrk_cites to {BIB_PATH} ({tagged_count} publications tagged).")
    else:
        print(f"\n[DRY RUN] Would update {tagged_count} publications in {BIB_PATH}. "
              "Re-run with --apply to write.")

    if write_json:
        json_output = {
            "summary": {
                "total_papers": len(papers_info),
                "total_citations": total_edges,
                "papers_citing": papers_citing,
                "papers_cited": papers_cited
            },
            "citations": citations,
            "review": {
                "title_only_matches": title_only_matches,
                "doi_title_conflicts": doi_title_conflicts,
            },
        }
        with open("citations.json", 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=2)
        print(f"Saved citations to citations.json.")

    print(f"  Title-only matches accepted: {len(title_only_matches)}")
    print(f"  DOI/title conflicts excluded: {len(doi_title_conflicts)}")

    # Top 5 most cited dVRK papers
    top_cited = sorted(citations.items(), key=lambda x: len(x[1]["cited_by"]), reverse=True)[:5]
    print("\nTop 5 Most Cited Papers within Community:")
    for pid, data in top_cited:
        info = papers_info[pid]
        print(f"  - [{pid}] ({len(data['cited_by'])} citations): {info['title'][:60]} ({info['year']})")

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Extract community citations and tag publications.bib with dvrk_cites.")
    arg_parser.add_argument("--apply", action="store_true", help="Write verified DOI matches to publications.bib (default is dry run).")
    arg_parser.add_argument("--dry-run", action="store_true", help="Deprecated; dry run is now the default.")
    arg_parser.add_argument("--write-json", action="store_true", help="Also export citation graph and title-only match details to citations.json.")
    arg_parser.add_argument("--replace-existing", action="store_true", help="Replace existing dvrk_cites rather than retaining them (review carefully).")
    arg_parser.add_argument("--offline", action="store_true", help="Use the local reference cache only; do not query Crossref.")
    arg_parser.add_argument("--prune-missing", action="store_true", help="Remove retained citation keys that are not entries in publications.bib.")
    args = arg_parser.parse_args()
    main(apply=args.apply and not args.dry_run, write_json=args.write_json,
         preserve_existing=not args.replace_existing, offline=args.offline,
         prune_missing=args.prune_missing)
