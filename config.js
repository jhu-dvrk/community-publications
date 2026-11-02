// Shared configuration for dVRK Publications
// This file contains mappings and constants used across the application

const CONFIG = {
    // These will be populated from custom_tags.json
    FIELD_MAP: {},
    DATA_TYPE_MAP: {},
    SITE_MAP: {},
    SITE_COUNTRY_MAP: {},
    PEER_REVIEW_MAP: {},
    FIELD_DESCRIPTIONS: {},
    DATA_TYPE_DESCRIPTIONS: {},
    PEER_REVIEW_DESCRIPTIONS: {},

    // Initialize configuration by loading custom_tags.json
    async init() {
        try {
            const response = await fetch('custom_tags.json');
            const data = await response.json();
            
            // Populate RESEARCH_FIELDS
            if (data.research_fields) {
                data.research_fields.forEach(field => {
                    this.FIELD_MAP[field.id] = field.name;
                    this.FIELD_DESCRIPTIONS[field.name] = field.description;
                });
            }
            
            // Populate DATA_TYPES
            if (data.data_types) {
                data.data_types.forEach(type => {
                    this.DATA_TYPE_MAP[type.id] = type.name;
                    this.DATA_TYPE_DESCRIPTIONS[type.name] = type.description;
                });
            }
            
            // Populate SITES
            if (data.dvrk_site) {
                data.dvrk_site.forEach(site => {
                    this.SITE_MAP[site.id] = site.name;
                    if (site.country) {
                        this.SITE_COUNTRY_MAP[site.id] = site.country;
                    }
                });
            }

            // Populate PEER_REVIEW
            if (data.peer_reviewed) {
                data.peer_reviewed.forEach(item => {
                    this.PEER_REVIEW_MAP[item.id] = item.name;
                    this.PEER_REVIEW_DESCRIPTIONS[item.name] = item.description;
                });
            }
            
            return true;
        } catch (error) {
            console.error('Error loading custom_tags.json:', error);
            return false;
        }
    },

    // Strip comments to prevent parser crashes
    cleanBibtexText(text) {
        if (!text) return '';
        
        let result = '';
        let pos = 0;
        
        while (pos < text.length) {
            // Find the next occurrence of @comment (case-insensitive)
            const nextComment = text.toLowerCase().indexOf('@comment', pos);
            if (nextComment === -1) {
                result += text.substring(pos);
                break;
            }
            
            // Append everything up to the @comment
            result += text.substring(pos, nextComment);
            
            // Advance pos to start scanning the comment
            pos = nextComment + 8; // length of '@comment'
            
            // Find the opening brace of the comment
            while (pos < text.length && /\s/.test(text[pos])) {
                pos++;
            }
            
            if (pos < text.length && text[pos] === '{') {
                pos++; // skip '{'
                let braceCount = 1;
                // Scan until braces are balanced
                while (pos < text.length && braceCount > 0) {
                    // If we see a new entry starting, stop parsing this comment to prevent runaway
                    if (text[pos] === '@' && (pos === 0 || text[pos-1] === '\n' || text[pos-1] === '\r')) {
                        break;
                    }
                    if (text[pos] === '{') {
                        braceCount++;
                    } else if (text[pos] === '}') {
                        braceCount--;
                    }
                    pos++;
                }
            }
        }
        
        return result;
    },

    // Convert LaTeX special characters to Unicode
    convertLatexToUnicode(text) {
        if (!text) return '';

        // Common LaTeX accent commands to Unicode mappings
        const latexMap = {
            // Acute accents
            "'a": 'á', "'e": 'é', "'i": 'í', "'o": 'ó', "'u": 'ú',
            "'A": 'Á', "'E": 'É', "'I": 'Í', "'O": 'Ó', "'U": 'Ú',
            "'y": 'ý', "'Y": 'Ý', "'c": 'ć', "'C": 'Ć',
            "'n": 'ń', "'N": 'Ń', "'s": 'ś', "'S": 'Ś',
            "'z": 'ź', "'Z": 'Ź',

            // Grave accents
            "`a": 'à', "`e": 'è', "`i": 'ì', "`o": 'ò', "`u": 'ù',
            "`A": 'À', "`E": 'È', "`I": 'Ì', "`O": 'Ò', "`U": 'Ù',

            // Circumflex
            "^a": 'â', "^e": 'ê', "^i": 'î', "^o": 'ô', "^u": 'û',
            "^A": 'Â', "^E": 'Ê', "^I": 'Î', "^O": 'Ô', "^U": 'Û',

            // Umlaut/diaeresis
            '"a': 'ä', '"e': 'ë', '"i': 'ï', '"o': 'ö', '"u': 'ü',
            '"A': 'Ä', '"E': 'Ë', '"I': 'Ï', '"O': 'Ö', '"U': 'Ü',
            '"y': 'ÿ', '"Y': 'Ÿ',

            // Tilde
            "~a": 'ã', "~n": 'ñ', "~o": 'õ',
            "~A": 'Ã', "~N": 'Ñ', "~O": 'Õ',

            // Cedilla
            "c{c}": 'ç', "c{C}": 'Ç',
            "c c": 'ç', "c C": 'Ç',

            // Ring
            "aa": 'å', "AA": 'Å',

            // Slash
            "o": 'ø', "O": 'Ø',

            // Other special characters
            "ae": 'æ', "AE": 'Æ',
            "oe": 'œ', "OE": 'Œ',
            "ss": 'ß',
            "l": 'ł', "L": 'Ł',

            // Symbols
            "textregistered": '®',
            "textcopyright": '©',
            "texttrademark": '™',
            "textdegree": '°',
            "pm": '±',

            // More accents and symbols
            "ua": 'ă', "uA": 'Ă', "ug": 'ğ', "uG": 'Ğ',
            "va": 'ǎ', "vc": 'č', "vC": 'Č', "vd": 'ď', "vD": 'Ď', "ve": 'ě', "vE": 'Ě',
            "vi": 'ǐ', "vl": 'ľ', "vL": 'Ľ', "vn": 'ň', "vN": 'Ň', "vr": 'ř', "vR": 'Ř',
            "vs": 'š', "vS": 'Š', "vt": 'ť', "vT": 'Ť', "vu": 'ǔ', "vz": 'ž', "vZ": 'Ž',
            ".I": 'İ', "Hi": 'ő', "Hu": 'ű', "i": 'ı'
        };

        let result = text;

        // Handle patterns like {\\'{a}} or {\\'a}
        result = result.replace(/\{\\+(['`^"~.Hvuv])(\{([a-zA-Z])\}|([a-zA-Z]))\}/g, (match, accent, group, letter1, letter2) => {
            const letter = letter1 || letter2;
            const key = accent + letter;
            return latexMap[key] || match;
        });

        // Handle patterns like \\'{a} or \\'a
        result = result.replace(/\\+(['`^"~.Hvuv])\{?([a-zA-Z])\}?/g, (match, accent, letter) => {
            const key = accent + letter;
            return latexMap[key] || match;
        });

        // Handle special commands like \\c{c}, \\aa, \\o, \\textregistered, etc.
        // Handles \\cmd, \\cmd{}, \\cmd{x}
        result = result.replace(/\\+(c|aa|AA|o|O|ae|AE|oe|OE|ss|l|L|textregistered|textcopyright|texttrademark|textdegree|pm|u|v|H|i)(\{([a-zA-Z])\}|\{\}|\s([a-zA-Z])|(?![a-zA-Z]))/g, (match, cmd, group, letter1, letter2) => {
            if (letter1 || letter2) {
                const key = cmd + '{' + (letter1 || letter2) + '}';
                return latexMap[key] || latexMap[cmd + ' ' + (letter1 || letter2)] || match;
            }
            return latexMap[cmd] || match;
        });

        // Final pass: remove any remaining curly braces
        result = result.replace(/[{}]/g, '');

        return result;
    },

    // Clean BibTeX howpublished field (unwrapping \url{...} and formatting bare arXiv URLs)
    cleanHowPublished(raw) {
        if (!raw) return '';
        const unwrapped = raw.trim().replace(/^\\url\{(.+)\}$/i, '$1').trim();
        const arxivMatch = unwrapped.match(/^https?:\/\/arxiv\.org\/(?:abs|pdf)\/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?$/i);
        if (arxivMatch) {
            return `arXiv preprint arXiv:${arxivMatch[1]}`;
        }
        return this.convertLatexToUnicode(unwrapped);
    },

    // Calculate year range from publications array
    calculateYearRange(publications) {
        if (!publications || publications.length === 0) return 'N/A';
        const years = publications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
        if (years.length === 0) return 'N/A';
        return `${Math.min(...years)} - ${Math.max(...years)}`;
    },

    // Normalize a name token by stripping diacritics and punctuation
    normalizeNameToken(str) {
        if (!str) return '';
        return str
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/ø/gi, 'o')
            .replace(/ł/gi, 'l')
            .replace(/ß/g, 'ss')
            .toLowerCase()
            .replace(/[^a-z0-9\s]/g, '')
            .trim();
    },

    // Calculate total unique authors from publications array with name/initial disambiguation
    calculateTotalAuthors(publications) {
        if (!publications || publications.length === 0) return 0;

        const fullClusters = new Set();        // "normLast::firstGiven"
        const fullByInitial = new Set();       // "normLast::firstInitial" covered by a full name
        const initialOnly = new Set();         // "normLast::firstInitial" seen only as initial
        const singleTokenAuthors = new Set();  // corporate / mononym authors

        publications.forEach(pub => {
            if (!pub.author) return;
            this.parseAuthorList(pub.author).forEach(({ first, last }) => {
                const normLast = this.normalizeNameToken(last).replace(/\s+/g, '');
                if (!normLast) return;

                const givenTokens = (first || '')
                    .split(/[\s\.\-]+/)
                    .map(t => this.normalizeNameToken(t))
                    .filter(Boolean);

                if (givenTokens.length === 0) {
                    singleTokenAuthors.add(normLast);
                    return;
                }

                const firstGiven = givenTokens[0];
                const firstInit = firstGiven[0];

                if (firstGiven.length > 1) {
                    fullClusters.add(`${normLast}::${firstGiven}`);
                    fullByInitial.add(`${normLast}::${firstInit}`);
                } else {
                    initialOnly.add(`${normLast}::${firstInit}`);
                }
            });
        });

        let count = fullClusters.size;
        initialOnly.forEach(initKey => {
            if (!fullByInitial.has(initKey)) {
                count++;
            }
        });
        singleTokenAuthors.forEach(lastKey => {
            const matchedFull = Array.from(fullClusters).some(k => k.startsWith(`${lastKey}::`));
            const matchedInit = Array.from(initialOnly).some(k => k.startsWith(`${lastKey}::`));
            if (!matchedFull && !matchedInit) {
                count++;
            }
        });

        return count;
    },

    MONTH_NUM: {
        jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
        jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
        january: 1, february: 2, march: 3, april: 4, june: 6,
        july: 7, august: 8, september: 9, october: 10, november: 11, december: 12
    },

    // Integer sort key for publication date: YYYYMMDD
    getPublicationDateSortKey(pub) {
        let year = parseInt(pub.year) || 0;
        let month = 0;
        let day = 0;

        if (pub.month) {
            const m = String(pub.month).toLowerCase().replace(/[{}"'\s]/g, '');
            if (this.MONTH_NUM[m]) {
                month = this.MONTH_NUM[m];
            } else {
                const sub = m.slice(0, 3);
                if (this.MONTH_NUM[sub]) month = this.MONTH_NUM[sub];
            }
        }

        if (pub.date) {
            const parts = String(pub.date).split('-');
            if (parts.length >= 2 && month === 0) month = parseInt(parts[1]) || 0;
            if (parts.length >= 3 && day === 0) day = parseInt(parts[2]) || 0;
        }

        return year * 10000 + month * 100 + day;
    },

    // Surname particles kept attached to last name in "First Middle van Last" forms
    SURNAME_PARTICLES: new Set(['van', 'von', 'de', 'del', 'della', 'di', 'da', 'dos', 'das', 'du', 'le', 'la', 'y', 'el', 'al']),

    // Parse BibTeX author string into array of { first, last, suffix, full }
    parseAuthorList(authorString) {
        if (!authorString) return [];
        return authorString
            .split(/\s+and\s+/i)
            .map(s => s.trim())
            .filter(Boolean)
            .map(raw => {
                if (raw.includes(',')) {
                    const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
                    if (parts.length >= 3) {
                        // BibTeX "von Last, Jr., First"
                        const last = parts[0];
                        const suffix = parts[1];
                        const first = parts.slice(2).join(' ');
                        return { last, first, suffix, full: `${first} ${last}, ${suffix}`.trim() };
                    }
                    const last = parts[0] || '';
                    const first = parts.slice(1).join(' ');
                    return { last, first, suffix: '', full: `${first} ${last}`.trim() };
                } else {
                    const parts = raw.split(/\s+/).filter(Boolean);
                    if (parts.length <= 1) {
                        return { last: raw, first: '', suffix: '', full: raw };
                    }
                    // Handle trailing suffix like "Jr." or "III" in "First Last Jr."
                    let suffix = '';
                    if (/^(jr\.?|sr\.?|ii|iii|iv)$/i.test(parts[parts.length - 1]) && parts.length >= 3) {
                        suffix = parts.pop();
                    }
                    const lastParts = [parts.pop()];
                    // Attach surname particles (e.g., "Beatrice Van Amsterdam", "Ferdinando Rodriguez y Baena")
                    while (parts.length > 1 && this.SURNAME_PARTICLES.has(parts[parts.length - 1].toLowerCase())) {
                        const particle = parts.pop();
                        lastParts.unshift(particle);
                        // Special case for Spanish/Italian "Rodriguez y Baena" where 'y' links two surnames
                        if (particle.toLowerCase() === 'y' && parts.length > 1) {
                            lastParts.unshift(parts.pop());
                        }
                    }
                    const last = lastParts.join(' ');
                    const first = parts.join(' ');
                    const full = suffix ? `${first} ${last}, ${suffix}`.trim() : `${first} ${last}`.trim();
                    return { last, first, suffix, full };
                }
            });
    },

    // Format BibTeX author string into consistent "First Last, First Last, and First Last" display
    formatAuthors(authorString) {
        const parsed = this.parseAuthorList(authorString);
        if (parsed.length === 0) return '';
        if (parsed.length === 1) return parsed[0].full;
        if (parsed.length === 2) return `${parsed[0].full} and ${parsed[1].full}`;
        const allButLast = parsed.slice(0, -1).map(a => a.full).join(', ');
        return `${allButLast}, and ${parsed[parsed.length - 1].full}`;
    },

    // Normalized sort key ("last, first") for sorting publications by first author surname
    getFirstAuthorSortKey(authorString) {
        const parsed = this.parseAuthorList(authorString);
        if (parsed.length === 0) return '';
        const firstAuth = parsed[0];
        const lastKey = this.normalizeNameToken(firstAuth.last);
        const firstKey = this.normalizeNameToken(firstAuth.first);
        return `${lastKey}, ${firstKey}`;
    },

    // Convert first/middle name(s) into initials (e.g. "Peter H." -> "P. H.")
    getInitials(name) {
        if (!name) return '';
        return name.split(/[\s\.-]+/).filter(Boolean).map(p => p[0].toUpperCase() + '.').join(' ');
    },

    // Format APA 7th Edition citation
    formatApa(pub) {
        const authors = this.parseAuthorList(pub.author);
        let authorStr = '';
        if (authors.length === 1) {
            authorStr = authors[0].last + (authors[0].first ? ', ' + this.getInitials(authors[0].first) : '');
        } else if (authors.length === 2) {
            authorStr = `${authors[0].last}, ${this.getInitials(authors[0].first)}, & ${authors[1].last}, ${this.getInitials(authors[1].first)}`;
        } else if (authors.length > 2) {
            const formatted = authors.map(a => a.last + (a.first ? ', ' + this.getInitials(a.first) : ''));
            if (formatted.length <= 20) {
                authorStr = formatted.slice(0, -1).join(', ') + ', & ' + formatted[formatted.length - 1];
            } else {
                authorStr = formatted.slice(0, 19).join(', ') + ', ... ' + formatted[formatted.length - 1];
            }
        }

        const yearStr = pub.year ? `(${pub.year}). ` : '';
        const titleStr = pub.title ? `${pub.title.replace(/\.$/, '')}. ` : '';
        let venueStr = '';
        if (pub.journal) {
            venueStr = pub.journal;
            if (pub.volume) venueStr += `, ${pub.volume}`;
            if (pub.number) venueStr += `(${pub.number})`;
            if (pub.pages) venueStr += `, ${pub.pages}`;
            venueStr += '. ';
        } else if (pub.booktitle) {
            venueStr = `In ${pub.booktitle}`;
            if (pub.pages) venueStr += ` (pp. ${pub.pages})`;
            if (pub.publisher) venueStr += `. ${pub.publisher}`;
            venueStr += '. ';
        }
        const doiStr = pub.doi ? `https://doi.org/${pub.doi}` : (pub.url || '');
        return ((authorStr ? authorStr + ' ' : '') + yearStr + titleStr + venueStr + doiStr).trim();
    },

    // Format IEEE citation
    formatIeee(pub) {
        const authors = this.parseAuthorList(pub.author);
        let authorStr = '';
        if (authors.length === 1) {
            authorStr = (authors[0].first ? this.getInitials(authors[0].first) + ' ' : '') + authors[0].last;
        } else if (authors.length === 2) {
            authorStr = (authors[0].first ? this.getInitials(authors[0].first) + ' ' : '') + authors[0].last + ' and ' +
                        (authors[1].first ? this.getInitials(authors[1].first) + ' ' : '') + authors[1].last;
        } else if (authors.length > 6) {
            authorStr = (authors[0].first ? this.getInitials(authors[0].first) + ' ' : '') + authors[0].last + ' et al.';
        } else if (authors.length > 2) {
            const formatted = authors.map(a => (a.first ? this.getInitials(a.first) + ' ' : '') + a.last);
            authorStr = formatted.slice(0, -1).join(', ') + ', and ' + formatted[formatted.length - 1];
        }

        const titleStr = pub.title ? `"${pub.title.replace(/[.,]$/, '')},"` : '';
        let venueStr = '';
        if (pub.journal) {
            venueStr = pub.journal;
            if (pub.volume) venueStr += `, vol. ${pub.volume}`;
            if (pub.number) venueStr += `, no. ${pub.number}`;
            if (pub.pages) venueStr += `, pp. ${pub.pages}`;
            if (pub.year) venueStr += `, ${pub.year}`;
            venueStr += '.';
        } else if (pub.booktitle) {
            venueStr = `in ${pub.booktitle}`;
            if (pub.year) venueStr += `, ${pub.year}`;
            if (pub.pages) venueStr += `, pp. ${pub.pages}`;
            venueStr += '.';
        } else if (pub.year) {
            venueStr = `${pub.year}.`;
        }

        const doiStr = pub.doi ? ` doi: ${pub.doi}.` : '';
        return [authorStr, titleStr, venueStr].filter(Boolean).join(' ') + doiStr;
    },

    // Generate universal RIS file format (for Zotero / EndNote / Mendeley)
    generateRis(pub) {
        const lines = [];
        const typeMap = {
            'article': 'JOUR',
            'inproceedings': 'CONF',
            'conference': 'CONF',
            'incollection': 'CHAP',
            'inbook': 'CHAP',
            'book': 'BOOK',
            'phdthesis': 'THES',
            'mastersthesis': 'THES',
            'techreport': 'RPRT',
            'misc': 'GEN'
        };
        lines.push('TY  - ' + (typeMap[pub.type?.toLowerCase()] || 'GEN'));
        if (pub.title) lines.push('TI  - ' + pub.title);
        const authors = this.parseAuthorList(pub.author);
        authors.forEach(a => lines.push('AU  - ' + a.last + (a.first ? ', ' + a.first : '')));
        if (pub.year) lines.push('PY  - ' + pub.year);
        if (pub.journal) lines.push('JO  - ' + pub.journal);
        if (pub.booktitle) lines.push('T2  - ' + pub.booktitle);
        if (pub.volume) lines.push('VL  - ' + pub.volume);
        if (pub.number) lines.push('IS  - ' + pub.number);
        if (pub.pages) {
            const p = pub.pages.split(/--|-/);
            if (p[0]) lines.push('SP  - ' + p[0].trim());
            if (p[1]) lines.push('EP  - ' + p[1].trim());
        }
        if (pub.publisher) lines.push('PB  - ' + pub.publisher);
        if (pub.doi) lines.push('DO  - ' + pub.doi);
        if (pub.url) lines.push('UR  - ' + pub.url);
        if (pub.abstract) lines.push('AB  - ' + pub.abstract);
        lines.push('ER  - ');
        return lines.join('\r\n');
    },

    // Theme management (Light / Dark mode)
    getStoredTheme() {
        const stored = localStorage.getItem('dvrk_theme');
        if (stored === 'dark' || stored === 'light') return stored;
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    },

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('dvrk_theme', theme);
        this.updateThemeToggleButtons(theme);
        window.dispatchEvent(new CustomEvent('dvrk-theme-changed', { detail: { theme } }));
    },

    toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || this.getStoredTheme();
        const next = current === 'dark' ? 'light' : 'dark';
        this.setTheme(next);
    },

    updateThemeToggleButtons(theme) {
        document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
            const icon = btn.querySelector('.theme-toggle-icon');
            const text = btn.querySelector('.theme-toggle-text');
            if (theme === 'dark') {
                if (icon) icon.textContent = '☀️';
                if (text) text.textContent = 'Light';
                btn.setAttribute('title', 'Switch to light mode');
                btn.setAttribute('aria-label', 'Switch to light mode');
            } else {
                if (icon) icon.textContent = '🌙';
                if (text) text.textContent = 'Dark';
                btn.setAttribute('title', 'Switch to dark mode');
                btn.setAttribute('aria-label', 'Switch to dark mode');
            }
        });
    },

    initTheme() {
        const theme = this.getStoredTheme();
        document.documentElement.setAttribute('data-theme', theme);
        this.updateThemeToggleButtons(theme);

        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                if (!localStorage.getItem('dvrk_theme')) {
                    this.setTheme(e.matches ? 'dark' : 'light');
                }
            });
        }

        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.theme-toggle-btn');
            if (btn) {
                e.preventDefault();
                this.toggleTheme();
            }
        });
    }
};

// Initialize theme immediately on script load
CONFIG.initTheme();

