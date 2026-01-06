// Shared configuration for dVRK Publications
// This file contains mappings and constants used across the application

const CONFIG = {
    // Research field code to full name mapping
    // As defined in README.md
    FIELD_MAP: {
        'AU': 'Automation',
        'TR': 'Training, skill assessment and gesture recognition',
        'HW': 'Hardware implementation and integration',
        'SS': 'System simulation and modelling',
        'IM': 'Imaging and vision',
        'RE': 'Reviews'
    },

    // Data type code to full name mapping
    // As defined in README.md
    DATA_TYPE_MAP: {
        'RI': 'Raw Images',
        'KD': 'Kinematic Data',
        'DD': 'Dynamic Data',
        'SD': 'System Data',
        'ED': 'External Data'
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
            '\\"a': 'ä', '\\"e': 'ë', '\\"i': 'ï', '\\"o': 'ö', '\\"u': 'ü',
            '\\"A': 'Ä', '\\"E': 'Ë', '\\"I': 'Ï', '\\"O': 'Ö', '\\"U': 'Ü',
            '\\"y': 'ÿ', '\\"Y': 'Ÿ',

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
            "l": 'ł', "L": 'Ł'
        };

        let result = text;

        // Handle patterns like {\\'{a}} or {\\'a}
        result = result.replace(/\{\\(['`^"~])(\{([a-zA-Z])\}|([a-zA-Z]))\}/g, (match, accent, group, letter1, letter2) => {
            const letter = letter1 || letter2;
            const key = accent + letter;
            return latexMap[key] || match;
        });

        // Handle patterns like \\'{a} or \\'a
        result = result.replace(/\\(['`^"~])\{?([a-zA-Z])\}?/g, (match, accent, letter) => {
            const key = accent + letter;
            return latexMap[key] || match;
        });

        // Handle special commands like \\c{c}, \\aa, \\o, etc.
        result = result.replace(/\\(c|aa|AA|o|O|ae|AE|oe|OE|ss|l|L)(\{([a-zA-Z])\}|\s([a-zA-Z])|(?![a-zA-Z]))/g, (match, cmd, group, letter1, letter2) => {
            if (letter1 || letter2) {
                const key = cmd + '{' + (letter1 || letter2) + '}';
                return latexMap[key] || latexMap[cmd + ' ' + (letter1 || letter2)] || match;
            }
            return latexMap[cmd] || match;
        });

        // Remove any remaining curly braces (used for capitalization preservation in BibTeX)
        result = result.replace(/\{([^\\\}]+)\}/g, '$1');

        return result;
    },

    // Calculate year range from publications array
    calculateYearRange(publications) {
        if (!publications || publications.length === 0) return 'N/A';
        const years = publications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
        if (years.length === 0) return 'N/A';
        return `${Math.min(...years)} - ${Math.max(...years)}`;
    },

    // Calculate total unique authors from publications array
    calculateTotalAuthors(publications) {
        if (!publications || publications.length === 0) return 0;
        const authors = new Set();
        publications.forEach(pub => {
            if (pub.author) {
                pub.author.split(' and ').forEach(author => {
                    authors.add(author.trim());
                });
            }
        });
        return authors.size;
    }
};
