import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase
import os
import sys

def cleanup_bib(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    # Recommended field order for consistent layout
    FIELD_ORDER = [
        'author', 'title', 'journal', 'booktitle', 'year', 'volume', 'number',
        'pages', 'month', 'publisher', 'doi', 'url', 'ieeexplore',
        'semanticscholar', 'arxiv', 'pdf', 'openaccesspdf',
        'research_field', 'data_type', 'dvrk_site', 'abstract', 'keywords'
    ]

    # Configure the parser to be flexible but maintain braces
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    
    with open(file_path, 'r', encoding='utf-8') as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file, parser=parser)

    # Cleanup and rename fields if needed
    for entry in bib_database.entries:
        # Rename dvrk_sites to dvrk_site if any remained
        if 'dvrk_sites' in entry:
            entry['dvrk_site'] = entry.pop('dvrk_sites')

        # Clean up field values (remove extra whitespace/newlines)
        for field in entry:
            if isinstance(entry[field], str):
                entry[field] = entry[field].replace('\n', ' ').strip()
                # Remove extra spaces from normalization
                while '  ' in entry[field]:
                    entry[field] = entry[field].replace('  ', ' ')

    # Sort entries: 1. Year (Descending), 2. Title (Ascending)
    def sort_key(entry):
        year = entry.get('year', '0')
        # If year is not a number (e.g., 'to appear'), handle it
        try:
            year_val = -int(year)
        except ValueError:
            year_val = -9999 if year.lower() == 'to appear' else 0
            
        title = entry.get('title', '').lower()
        return (year_val, title)

    bib_database.entries.sort(key=sort_key)

    # Configure the writer for nice formatting
    writer = BibTexWriter()
    writer.indent = '  '  # 2 space indent as requested
    writer.order_entries_by = None  # We've already sorted
    writer.display_order = FIELD_ORDER  # Use our standardized field order
    writer.add_trailing_comma = True  # Always add trailing comma to prevent corruption when appending
    
    with open(file_path, 'w', encoding='utf-8') as bibtex_file:
        bibtex_file.write(writer.write(bib_database))

    print(f"Successfully cleaned up and sorted {len(bib_database.entries)} entries in {file_path}.")

if __name__ == "__main__":
    # Default to publications.bib in the parent directory if not specified
    target = os.path.join(os.path.dirname(__file__), '..', 'publications.bib')
    if len(sys.argv) > 1:
        target = sys.argv[1]
    
    cleanup_bib(target)
