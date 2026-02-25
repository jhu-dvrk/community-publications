import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
import os
import sys
import json
import re

def update_sites(bib_file, mapping_file):
    if not os.path.exists(bib_file):
        print(f"Error: {bib_file} not found.")
        return

    if not os.path.exists(mapping_file):
        print(f"Error: {mapping_file} not found.")
        return

    with open(mapping_file, 'r', encoding='utf-8') as mf:
        author_mapping = json.load(mf)

    FIELD_ORDER = [
        'author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number',
        'pages', 'month', 'publisher', 'doi', 'url', 'ieeexplore',
        'semanticscholar', 'arxiv', 'pdf', 'openaccesspdf',
        'research_field', 'data_type', 'dvrk_site', 'abstract', 'keywords'
    ]

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    
    with open(bib_file, 'r', encoding='utf-8') as f:
        bib_database = bibtexparser.load(f, parser=parser)

    managed_sites = set()
    for site_str in author_mapping.values():
        sites_in_val = [s.strip() for s in site_str.split(' and ') if s.strip()]
        managed_sites.update(sites_in_val)

    updated_count = 0
    for entry in bib_database.entries:
        author_str = entry.get('author', '')
        # Normalize whitespace in author string for better matching
        author_str = re.sub(r'\s+', ' ', author_str).strip()
        
        current_site_str = entry.get('dvrk_site', '')
        
        current_sites = set(s.strip() for s in current_site_str.split(' and ') if s.strip())
        original_sites = set(current_sites)

        final_sites = current_sites - managed_sites

        if author_str:
            for author_full_name, site_str_to_add in author_mapping.items():
                patterns = []
                if ',' in author_full_name:
                    last, first_part = [x.strip() for x in author_full_name.split(',', 1)]
                    patterns.append(re.escape(f"{last}, {first_part}"))
                    patterns.append(re.escape(f"{first_part} {last}"))
                    
                    first_names = [n.strip() for n in first_part.split() if n.strip()]
                    if first_names:
                        initials_with_dot = " ".join([f"{n[0]}." for n in first_names])
                        patterns.append(re.escape(f"{last}, {initials_with_dot}"))
                        patterns.append(re.escape(f"{initials_with_dot} {last}"))
                        
                        compact_initials = "".join([f"{n[0]}." for n in first_names])
                        patterns.append(re.escape(f"{last}, {compact_initials}"))
                        patterns.append(re.escape(f"{compact_initials} {last}"))

                        if len(first_names) > 1:
                            first_initial = f"{first_names[0][0]}."
                            patterns.append(re.escape(f"{last}, {first_initial}"))
                            patterns.append(re.escape(f"{first_initial} {last}"))
                else:
                    patterns = [re.escape(author_full_name)]

                found_match = False
                for p in patterns:
                    # Use lookahead/lookbehind for boundaries to handle names correctly
                    # (especially those with dots or other non-word characters).
                    if re.search(r'(?<!\w)' + p + r'(?!\w)', author_str, re.IGNORECASE):
                        found_match = True
                        break

                if found_match:
                    sites_to_add = [s.strip() for s in site_str_to_add.split(' and ') if s.strip()]
                    final_sites.update(sites_to_add)

        if final_sites != original_sites:
            if not final_sites:
                if 'dvrk_site' in entry:
                    del entry['dvrk_site']
            else:
                sorted_sites = sorted(list(final_sites))
                if 'JHU' in sorted_sites:
                    sorted_sites.remove('JHU')
                    sorted_sites.insert(0, 'JHU')
                entry['dvrk_site'] = ' and '.join(sorted_sites)
            updated_count += 1

    def sort_key(entry):
        year = entry.get('year', '0')
        try:
            year_val = -int(year)
        except ValueError:
            year_val = -9999 if 'appear' in year.lower() else 0
        title = entry.get('title', '').lower()
        return (year_val, title)

    bib_database.entries.sort(key=sort_key)

    writer = BibTexWriter()
    writer.indent = '  '
    writer.add_trailing_comma = True
    writer.order_entries_by = None
    writer.display_order = FIELD_ORDER
    with open(bib_file, 'w', encoding='utf-8') as f:
        f.write(writer.write(bib_database))

    if updated_count > 0:
        print(f"Successfully updated {updated_count} entries in {bib_file}.")
    else:
        print(f"No updates to sites needed in {bib_file}.")

if __name__ == "__main__":
    scripts_dir = os.path.dirname(__file__)
    default_bib = os.path.join(scripts_dir, '..', 'publications.bib')
    default_mapping = os.path.join(scripts_dir, 'author_sites.json')
    bib_target = sys.argv[1] if len(sys.argv) > 1 else default_bib
    mapping_target = sys.argv[2] if len(sys.argv) > 2 else default_mapping
    update_sites(bib_target, mapping_target)
