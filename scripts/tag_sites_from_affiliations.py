"""
tag_sites_from_affiliations.py
------------------------------
For each publication in publications.bib that lacks a dvrk_site field:
1. Validates the DOI or discovers it via arXiv ID, URL, or CrossRef title search.
2. Detects proceedings/mismatched DOIs and resolves the specific paper DOI.
3. Fetches author affiliations from OpenAlex (including author profiles if needed)
   and falls back to CrossRef.
4. Matches affiliations against known dVRK institution names.
5. Only assigns dvrk_site when at least one author's affiliation matches a
   known dVRK site - no guessing or inference.
6. Updates publications.bib with verified dvrk_site and corrected DOIs.

Results are cached in cache/affiliation_cache.json so the script can be
re-run incrementally without re-fetching already-processed entries.
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

# ---------------------------------------------------------------------------
# Institution name → dVRK site ID mapping
# Substrings matched case-insensitively. List multiple name variants per site.
# More specific strings must be listed before general ones to avoid false matches.
# ---------------------------------------------------------------------------
INSTITUTION_TO_SITE = {
    # USA
    "Johns Hopkins":                    "JHU",
    "Carnegie Mellon":                  "CMU",
    "Clemson University":               "CU",
    "Clemson":                          "CU",
    "Case Western Reserve":             "CWRU",
    "Case Western":                     "CWRU",
    "Intuitive Surgical":               "ISS",
    "Stanford University":              "SU",
    "Stanford":                         "SU",
    "Sheikh Zayed Institute":           "SZIPS",
    "Children's National":              "SZIPS",
    "SickKids":                         "SKCH",
    "Hospital for Sick Children":       "SKCH",
    "Purdue University":                "PU",
    "Purdue":                           "PU",
    "University of Utah":               "UU",
    "Univ. of Utah":                    "UU",
    "University of Texas at Dallas":    "UTD",
    "UT Dallas":                        "UTD",
    "Wayne State University":           "WSU",
    "Wayne State":                      "WSU",
    "Worcester Polytechnic Institute":  "WPI",
    "Worcester Polytechnic":            "WPI",
    "WPI":                              "WPI",
    "Vanderbilt University":            "VU",
    "Vanderbilt":                       "VU",
    "UC Berkeley":                      "UCB",
    "University of California, Berkeley": "UCB",
    "University of California Berkeley":  "UCB",
    "University of California San Diego": "UCSD",
    "University of California, San Diego": "UCSD",
    "UC San Diego":                     "UCSD",
    "UCSD":                             "UCSD",

    # Canada
    "University of Alberta":            "UA",
    "University of British Columbia":   "UBC",
    "University of Western Ontario":    "UWO",
    "Western University":               "UWO",

    # UK
    "Imperial College":                 "ICL",
    "The Hamlyn Centre":                "ICL",
    "Hamlyn Centre":                    "ICL",
    "Hamlyn Center":                    "ICL",
    "University College London":        "UCL",
    "University of Leeds":              "UL",

    # Hong Kong
    "Chinese University of Hong Kong":  "CUHK",
    "CUHK":                             "CUHK",

    # Italy
    "Politecnico di Milano":            "POLIMI",
    "PoliMi":                           "POLIMI",
    "University of Turin":              "UNITO",
    "University of Torino":             "UNITO",
    "Università degli Studi di Torino": "UNITO",
    "Universita degli Studi di Torino": "UNITO",
    "Scuola Superiore Sant'Anna":       "SSSA",
    "Sant'Anna School":                 "SSSA",
    "BioRobotics Institute":            "SSSA",
    "Biorobotics Institute":            "SSSA",
    "Istituto di BioRobotica":          "SSSA",
    "University of Verona":             "UV",
    "Università degli Studi di Verona": "UV",
    "Università di Verona":             "UV",
    "Universita di Verona":             "UV",
    "University of Naples Federico II": "UNFII",
    "Università degli Studi di Napoli Federico II": "UNFII",
    "Università di Napoli Federico II": "UNFII",
    "Universita di Napoli Federico II": "UNFII",

    # Hungary
    "Óbuda University":                 "OU",
    "Obuda University":                 "OU",
    "Óbuda":                            "OU",
    "Obuda":                            "OU",
    "Antal Bejczy Center":              "OU",

    # Israel
    "Ben-Gurion University":            "BGUN",
    "Ben Gurion University":            "BGUN",
    "Ben-Gurion":                       "BGUN",
    "Ben Gurion":                       "BGUN",

    # Korea
    "Seoul National University":        "SNU",

    # Germany
    "Max Planck":                       "MPI",
    "Max-Planck":                       "MPI",
    "MPI-IS":                           "MPI",
}

CACHE_PATH = "cache/affiliation_cache.json"
HEADERS = {'User-Agent': 'dVRK-Community-Checker/1.0 (mailto:deguet@jhu.edu)'}

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

def titles_match(t1, t2):
    """Check whether two paper titles refer to the same work."""
    if not t1 or not t2:
        return False
    c1 = re.sub(r'[^a-z0-9]', '', t1.lower())
    c2 = re.sub(r'[^a-z0-9]', '', t2.lower())
    if not c1 or not c2:
        return False
    return (c1 in c2) or (c2 in c1) or (len(c1) >= 20 and c1[:25] == c2[:25])

def extract_doi_from_entry(entry):
    """Extract and normalize DOI from doi, arxiv, or url fields."""
    doi = entry.get('doi', '').strip()
    if doi:
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
        doi = re.sub(r'^doi:\s*', '', doi, flags=re.IGNORECASE).strip()
        if doi:
            return doi

    # Check arxiv
    arxiv = entry.get('arxiv', '').strip()
    if arxiv:
        m = re.search(r'(\d{4}\.\d{4,5})', arxiv)
        if m:
            return f"10.48550/arXiv.{m.group(1)}"

    # Check url
    url = entry.get('url', '').strip()
    if url:
        m = re.search(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+', url)
        if m:
            return m.group(0).rstrip('.,;')

    return None

def search_crossref_doi_by_title(title):
    """Query CrossRef bibliographic search to find the DOI of a paper by title."""
    if not title:
        return None
    encoded = urllib.parse.quote(title)
    url = f"https://api.crossref.org/works?query.bibliographic={encoded}&rows=3"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('message', {}).get('items', [])
            for item in items:
                res_titles = item.get('title', [])
                if res_titles and titles_match(title, res_titles[0]):
                    return item.get('DOI')
    except Exception:
        pass
    return None

def fetch_openalex(doi, paper_year=None):
    """
    Returns (institutions, work_title) or (None, None).
    If work-level institutions are empty, inspects author profiles around publication year.
    """
    encoded = urllib.parse.quote(doi, safe='')
    url = f"https://api.openalex.org/works/doi:{encoded}?select=title,authorships"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            work_title = data.get('title', '')
            institutions = []
            for authorship in data.get('authorships', []):
                for inst in authorship.get('institutions', []):
                    name = inst.get('display_name', '')
                    if name:
                        institutions.append(name)

            if institutions:
                return institutions, work_title

            # If work has author profiles but no listed institutions, check author profiles around publication year
            target_years = None
            if paper_year:
                try:
                    py = int(paper_year)
                    target_years = {py, py - 1, py + 1}
                except ValueError:
                    pass

            for authorship in data.get('authorships', [])[:8]:
                author_id = authorship.get('author', {}).get('id')
                if not author_id:
                    continue
                api_url = author_id.replace('https://openalex.org/', 'https://api.openalex.org/')
                try:
                    a_req = urllib.request.Request(api_url, headers=HEADERS)
                    with urllib.request.urlopen(a_req, timeout=5) as a_resp:
                        a_data = json.loads(a_resp.read().decode('utf-8'))
                        if target_years:
                            for aff in a_data.get('affiliations', []) or []:
                                years = set(aff.get('years', []))
                                if years & target_years:
                                    name = aff.get('institution', {}).get('display_name')
                                    if name:
                                        institutions.append(name)
                        else:
                            for i in a_data.get('last_known_institutions', []) or []:
                                name = i.get('display_name')
                                if name:
                                    institutions.append(name)
                    time.sleep(0.1)
                except Exception:
                    pass

            return institutions, work_title
    except Exception:
        return None, None

def fetch_crossref(doi):
    """Returns (affiliations, work_title) or (None, None)."""
    encoded = urllib.parse.quote(doi, safe='')
    url = f"https://api.crossref.org/works/{encoded}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            msg = data.get('message', {})
            work_title = msg.get('title', [''])[0] if msg.get('title') else ''
            affiliations = []
            for author in msg.get('author', []):
                for aff in author.get('affiliation', []):
                    name = aff.get('name', '')
                    if name:
                        affiliations.append(name)
            return affiliations, work_title
    except Exception:
        return None, None

def match_sites(institution_names):
    """
    Given a list of institution name strings, return a set of matching dVRK site IDs.
    Only returns sites where the institution name substring appears in the affiliation string.
    """
    matched_sites = set()
    for inst_name in institution_names:
        inst_lower = inst_name.lower()
        for pattern, site_id in INSTITUTION_TO_SITE.items():
            if pattern.lower() in inst_lower:
                matched_sites.add(site_id)
                break  # Stop at first match for this institution string
    return matched_sites

def main(refresh_misses=False, dry_run=False):
    # Load bib
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open('publications.bib', 'r', encoding='utf-8') as f:
        db = bibtexparser.load(f, parser=parser)

    print(f"Loaded {len(db.entries)} entries from publications.bib.")

    # Load affiliation cache
    cache = load_cache()

    # Find entries missing dvrk_site
    missing_site = [e for e in db.entries if not e.get('dvrk_site') or not e['dvrk_site'].strip()]
    print(f"Entries missing dvrk_site: {len(missing_site)}\n")

    tagged = 0
    new_dois = 0
    skipped_no_match = 0
    api_calls = 0

    for entry in missing_site:
        entry_id = entry['ID']
        year = entry.get('year', '').strip()
        title = entry.get('title', '').replace('{', '').replace('}', '').strip()

        # Step 1: Extract candidate DOI from doi, arxiv, or url fields
        doi = extract_doi_from_entry(entry)
        work_title = None
        institutions = None

        # Check cache first if we have a DOI
        if doi and doi in cache and not (refresh_misses and not cache[doi]):
            cached_data = cache[doi]
            if isinstance(cached_data, dict):
                c_title = cached_data.get('title', '')
                if not c_title or titles_match(title, c_title):
                    institutions = cached_data.get('affiliations', [])
                    work_title = c_title
            elif isinstance(cached_data, list):
                # old cache didn't store title, so re-verify if refresh_misses or empty
                if cached_data:
                    institutions = cached_data

        # If we have institutions from cache, verify title match
        if institutions is not None and work_title and not titles_match(title, work_title):
            # Cached DOI was for a different paper (e.g. proceedings). Discard and re-search.
            institutions = None
            work_title = None

        # Step 2: If no valid cached data, fetch or discover DOI
        if institutions is None:
            if doi:
                # Try OpenAlex with existing DOI
                insts, w_title = fetch_openalex(doi, year)
                api_calls += 1
                time.sleep(0.2)

                # If OpenAlex returned a work, check if the title matches
                if w_title and not titles_match(title, w_title):
                    # Existing DOI is wrong/proceedings! Search CrossRef by title
                    print(f"  [DISCOVERY] Mismatched DOI {doi} for [{entry_id}], searching by title...")
                    found_doi = search_crossref_doi_by_title(title)
                    api_calls += 1
                    time.sleep(0.2)
                    if found_doi:
                        print(f"    -> Found specific paper DOI: {found_doi}")
                        doi = found_doi
                        insts, w_title = fetch_openalex(doi, year)
                        api_calls += 1
                        time.sleep(0.2)
                    else:
                        doi = None
                        insts = []
                        w_title = ''

                if not insts and doi:
                    # Fallback to CrossRef
                    cr_insts, cr_title = fetch_crossref(doi)
                    api_calls += 1
                    time.sleep(0.2)
                    if cr_title and titles_match(title, cr_title):
                        insts = cr_insts
                        w_title = cr_title

                institutions = insts if insts else []
                work_title = w_title or ''
            else:
                # No DOI in entry. Search CrossRef by title!
                found_doi = search_crossref_doi_by_title(title)
                api_calls += 1
                time.sleep(0.2)
                if found_doi:
                    print(f"  [DISCOVERY] Discovered DOI for [{entry_id}] (had no DOI): {found_doi}")
                    doi = found_doi
                    insts, w_title = fetch_openalex(doi, year)
                    api_calls += 1
                    time.sleep(0.2)
                    if not insts:
                        cr_insts, cr_title = fetch_crossref(doi)
                        api_calls += 1
                        time.sleep(0.2)
                        if cr_title and titles_match(title, cr_title):
                            insts = cr_insts
                            w_title = cr_title
                    institutions = insts if insts else []
                    work_title = w_title or ''
                else:
                    institutions = []
                    work_title = ''

            # Cache the result
            if doi:
                cache[doi] = {
                    "title": work_title,
                    "affiliations": institutions
                }

        # Step 3: Match affiliations against known dVRK sites
        matched_sites = match_sites(institutions) if institutions else set()

        if matched_sites:
            site_str = " and ".join(sorted(matched_sites))
            entry['dvrk_site'] = site_str
            tagged += 1

            # Update entry DOI if a new/corrected one was verified
            old_doi = entry.get('doi', '').strip()
            if doi and (not old_doi or old_doi != doi):
                entry['doi'] = doi
                new_dois += 1
                print(f"  TAGGED [{entry_id}]: {site_str} (Updated DOI: {doi})")
            else:
                print(f"  TAGGED [{entry_id}]: {site_str}")
            print(f"    (from affiliations: {institutions[:2]})")
        else:
            skipped_no_match += 1

    # Save updated cache
    save_cache(cache)

    print(f"\n{'='*60}")
    print(f"API calls made: {api_calls}")
    print(f"Newly tagged: {tagged}")
    print(f"DOIs discovered/corrected: {new_dois}")
    print(f"Skipped (no match / no affiliation data): {skipped_no_match}")
    print(f"Remaining untagged: {len(missing_site) - tagged}")

    if tagged > 0 and not dry_run:
        # Write back to publications.bib
        writer = BibTexWriter()
        writer.indent = '  '
        writer.order_entries_by = None
        writer.add_trailing_comma = True
        with open('publications.bib', 'w', encoding='utf-8') as f:
            f.write(writer.write(db))
        print("\nSuccessfully updated publications.bib.")
    elif dry_run:
        print("\n[DRY RUN] No changes written to publications.bib.")
    else:
        print("\nNo changes to write.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Assign dVRK sites from DOI-linked author affiliations."
    )
    parser.add_argument(
        "--refresh-misses",
        action="store_true",
        help="Retry cached empty affiliation lookups.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without modifying publications.bib.",
    )
    args = parser.parse_args()
    main(refresh_misses=args.refresh_misses, dry_run=args.dry_run)
