import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase
import os
import re
import sys

# Map of full/alternative month spellings -> standard 3-letter BibTeX macro
_MONTH_MAP = {
    'january': 'jan',  'february': 'feb', 'march': 'mar',
    'april':   'apr',  'may':      'may', 'june':  'jun',
    'july':    'jul',  'august':   'aug', 'september': 'sep',
    'october': 'oct',  'november': 'nov', 'december':  'dec',
    '1': 'jan', '2': 'feb',  '3': 'mar', '4': 'apr',
    '5': 'may', '6': 'jun',  '7': 'jul', '8': 'aug',
    '9': 'sep', '10': 'oct', '11': 'nov', '12': 'dec',
}

def normalize_months(content):
    """Replace bare/full month names with braced 3-letter equivalents.

    BibTeX string macros only cover jan..dec; full names like 'june' trigger
    a KeyError in bibtexparser.  This converts both unbraced references
    (month = june) and braced full names (month = {June}) to the safe form
    (month = {jun}).
    """
    def _replace(m):
        raw = m.group(1).strip().strip('{}"\' ')
        normalized = _MONTH_MAP.get(raw.lower())
        if normalized:
            return f'month = {{{normalized}}}'
        # Already safe (e.g. {Jun} with capital) — just ensure braces
        return f'month = {{{raw}}}'

    return re.sub(
        r'month\s*=\s*(\{?[^,\}\n]+\}?)',
        _replace,
        content,
        flags=re.IGNORECASE,
    )


def enforce_one_field_per_line(content):
    """Guarantee exactly one BibTeX field per output line.

    bibtexparser writes one field per line, but raw entries appended from
    doi.org or other sources may have field values that span multiple lines
    (e.g. long author lists, abstracts with paragraph breaks).

    We detect continuation lines by tracking open-brace depth: while the
    accumulated depth is >0, the next non-blank line is joined onto the
    current field line rather than started as a new one.
    """
    FIELD_RE = re.compile(r'^\s+[\w][\w\-]*\s*=')
    ENTRY_RE = re.compile(r'^@')
    CLOSE_RE = re.compile(r'^\s*\}')

    lines = content.split('\n')
    out = []
    depth = 0  # net unclosed { from the current field line

    for line in lines:
        stripped = line.strip()

        if not stripped:
            out.append(line)
            depth = 0
            continue

        is_new_field = bool(FIELD_RE.match(line))
        is_entry_start = bool(ENTRY_RE.match(line))
        is_entry_close = bool(CLOSE_RE.match(line))

        if depth > 0 and not is_new_field and not is_entry_start and not is_entry_close:
            # Continuation line — merge with previous field line
            out[-1] = out[-1].rstrip() + ' ' + stripped
        else:
            out.append(line)
            depth = 0  # reset for new line

        # Update brace depth (ignoring \{ and \} escapes)
        unescaped = re.sub(r'\\[{}]', '', (stripped if depth > 0 else line))
        depth += unescaped.count('{') - unescaped.count('}')
        depth = max(depth, 0)

    return '\n'.join(out)

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
        raw_content = bibtex_file.read()

    raw_content = normalize_months(raw_content)
    bib_database = bibtexparser.loads(raw_content, parser=parser)

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
    
    output = writer.write(bib_database)
    output = enforce_one_field_per_line(output)

    with open(file_path, 'w', encoding='utf-8') as bibtex_file:
        bibtex_file.write(output)

    print(f"Successfully cleaned up and sorted {len(bib_database.entries)} entries in {file_path}.")

if __name__ == "__main__":
    # Default to publications.bib in the parent directory if not specified
    target = os.path.join(os.path.dirname(__file__), '..', 'publications.bib')
    if len(sys.argv) > 1:
        target = sys.argv[1]
    
    cleanup_bib(target)
