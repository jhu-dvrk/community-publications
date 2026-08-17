"""
tag_sites_from_affiliations.py
------------------------------
For each publication in publications.bib that lacks a dvrk_site field,
fetch author affiliations from OpenAlex (falling back to CrossRef) and match
them against known dVRK institution names.

Only assigns dvrk_site when at least one author's affiliation matches a
known dVRK site - no guessing or inference.

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
    "Case Western Reserve":             "CWRU",
    "Intuitive Surgical":               "ISS",
    "Stanford University":              "SU",
    "Sheikh Zayed Institute":           "SZIPS",
    "Children's National":              "SZIPS",
    "SickKids":                         "SKCH",
    "Hospital for Sick Children":       "SKCH",
    "Purdue University":                "PU",
    "University of Utah":               "UU",
    "University of Texas at Dallas":    "UTD",
    "Wayne State University":           "WSU",
    "Worcester Polytechnic":            "WPI",
    "Vanderbilt University":            "VU",
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
    "University College London":        "UCL",
    "University of Leeds":              "UL",

    # Hong Kong
    "Chinese University of Hong Kong":  "CUHK",
    "CUHK":                             "CUHK",

    # Italy
    "Politecnico di Milano":            "POLIMI",
    "Scuola Superiore Sant'Anna":       "SSSA",
    "Sant'Anna School":                 "SSSA",
    "University of Verona":             "UV",
    "Università degli Studi di Verona": "UV",
    "University of Naples Federico II": "UNFII",
    "Università degli Studi di Napoli Federico II": "UNFII",
    # Note: do NOT use bare "Federico II" - too broad (e.g. King Federico II of Prussia etc.)

    # Hungary
    "Óbuda University":                 "OU",
    "Obuda University":                 "OU",
    "Óbuda":                            "OU",

    # Israel
    "Ben-Gurion University":            "BGUN",
    "Ben Gurion University":            "BGUN",

    # Korea
    "Seoul National University":        "SNU",
}

CACHE_PATH = "cache/affiliation_cache.json"

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

def fetch_openalex(doi):
    """Returns list of all institution display_names for a paper, or None on error."""
    encoded = urllib.parse.quote(doi, safe='')
    url = f"https://api.openalex.org/works/doi:{encoded}?select=authorships"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'dVRK-Community-Checker/1.0 (mailto:deguet@jhu.edu)'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            institutions = []
            for authorship in data.get('authorships', []):
                for inst in authorship.get('institutions', []):
                    name = inst.get('display_name', '')
                    if name:
                        institutions.append(name)
            return institutions
    except Exception:
        return None

def fetch_crossref(doi):
    """Returns list of all affiliation strings for a paper, or None on error."""
    encoded = urllib.parse.quote(doi, safe='')
    url = f"https://api.crossref.org/works/{encoded}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'dVRK-Community-Checker/1.0 (mailto:deguet@jhu.edu)'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            affiliations = []
            for author in data.get('message', {}).get('author', []):
                for aff in author.get('affiliation', []):
                    name = aff.get('name', '')
                    if name:
                        affiliations.append(name)
            return affiliations
    except Exception:
        return None

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
                break  # Stop at first match for this institution
    return matched_sites

def main(refresh_misses=False):
    # Load bib
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open('publications.bib', 'r', encoding='utf-8') as f:
        db = bibtexparser.load(f, parser=parser)

    print(f"Loaded {len(db.entries)} entries.")

    # Load affiliation cache
    cache = load_cache()

    # Find entries missing dvrk_site
    missing_site = [e for e in db.entries if not e.get('dvrk_site') or not e['dvrk_site'].strip()]
    missing_with_doi = [e for e in missing_site if e.get('doi') and e['doi'].strip()]
    print(f"Entries missing dvrk_site: {len(missing_site)}")
    print(f"  Of which have a DOI: {len(missing_with_doi)}")

    tagged = 0
    skipped_no_doi = len(missing_site) - len(missing_with_doi)
    skipped_no_match = 0
    api_calls = 0

    for entry in missing_with_doi:
        doi = entry['doi'].strip()
        entry_id = entry['ID']

        # Check cache
        if doi in cache and not (refresh_misses and not cache[doi]):
            institutions = cache[doi]
        else:
            # Try OpenAlex first
            institutions = fetch_openalex(doi)
            if not institutions:
                # Fallback to CrossRef
                institutions = fetch_crossref(doi)
                time.sleep(0.3)
            if not institutions:
                institutions = []  # Cache the miss so we don't retry
            cache[doi] = institutions
            api_calls += 1
            time.sleep(0.3)

        if not institutions:
            skipped_no_match += 1
            continue

        # Match affiliations to dVRK sites
        matched_sites = match_sites(institutions)

        if matched_sites:
            site_str = " and ".join(sorted(matched_sites))
            entry['dvrk_site'] = site_str
            tagged += 1
            print(f"  TAGGED [{entry_id}]: {site_str}")
            print(f"    (from: {institutions[:2]})")
        else:
            skipped_no_match += 1

    # Save updated cache
    save_cache(cache)
    print(f"\n{'='*60}")
    print(f"API calls made: {api_calls} (rest from cache)")
    print(f"Tagged: {tagged}")
    print(f"Skipped (no DOI): {skipped_no_doi}")
    print(f"Skipped (no affiliation match): {skipped_no_match}")
    print(f"Still untagged: {len(missing_site) - tagged}")

    if tagged > 0:
        # Write back
        writer = BibTexWriter()
        writer.indent = '  '
        writer.order_entries_by = None
        writer.add_trailing_comma = True
        with open('publications.bib', 'w', encoding='utf-8') as f:
            f.write(writer.write(db))
        print("\nSaved publications.bib.")
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
    args = parser.parse_args()
    main(refresh_misses=args.refresh_misses)
