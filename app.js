const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            searchQuery: '',
            selectedYear: '',
            selectedType: '',
            selectedField: '',
            selectedDataType: '',
            currentPage: 1,
            itemsPerPage: 50
        };
    },
    computed: {
        availableYears() {
            const years = [...new Set(this.publications.map(p => p.year))];
            return years.sort((a, b) => b - a);
        },
        availableFields() {
            const fieldMap = {
                'AU': 'Automation',
                'TR': 'Training, skill assessment and gesture recognition',
                'HW': 'Hardware implementation and integration',
                'SS': 'System simulation and modelling',
                'IM': 'Imaging and vision',
                'RE': 'Reviews'
            };
            const fields = new Set();
            this.publications.forEach(pub => {
                if (pub.research_field) {
                    pub.research_field.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        if (trimmed && fieldMap[trimmed]) {
                            fields.add(fieldMap[trimmed]);
                        }
                    });
                }
            });
            return Array.from(fields).sort();
        },
        availableDataTypes() {
            const dataTypeMap = {
                'RI': 'Raw Images',
                'KD': 'Kinematic Data',
                'DD': 'Dynamic Data',
                'SD': 'System Data',
                'ED': 'External Data'
            };
            const dataTypes = new Set();
            this.publications.forEach(pub => {
                if (pub.data_type) {
                    pub.data_type.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        if (trimmed && dataTypeMap[trimmed]) {
                            dataTypes.add(dataTypeMap[trimmed]);
                        }
                    });
                }
            });
            return Array.from(dataTypes).sort();
        },
        filteredPublications() {
            let filtered = this.publications;

            // Search filter
            if (this.searchQuery) {
                const query = this.searchQuery.toLowerCase();
                filtered = filtered.filter(pub => {
                    return (
                        pub.title?.toLowerCase().includes(query) ||
                        pub.author?.toLowerCase().includes(query) ||
                        pub.journal?.toLowerCase().includes(query) ||
                        pub.booktitle?.toLowerCase().includes(query)
                    );
                });
            }

            // Year filter
            if (this.selectedYear) {
                filtered = filtered.filter(pub => pub.year === this.selectedYear);
            }

            // Type filter
            if (this.selectedType) {
                filtered = filtered.filter(pub => pub.type === this.selectedType);
            }

            // Field filter
            if (this.selectedField) {
                filtered = filtered.filter(pub => {
                    if (!pub.research_field) return false;
                    const fields = this.parseFields(pub.research_field);
                    return fields.includes(this.selectedField);
                });
            }

            // Data type filter
            if (this.selectedDataType) {
                filtered = filtered.filter(pub => {
                    if (!pub.data_type) return false;
                    const types = this.parseDataTypes(pub.data_type);
                    return types.includes(this.selectedDataType);
                });
            }

            return filtered;
        },
        paginatedPublications() {
            const start = (this.currentPage - 1) * this.itemsPerPage;
            const end = start + this.itemsPerPage;
            return this.filteredPublications.slice(start, end);
        },
        totalPages() {
            return Math.ceil(this.filteredPublications.length / this.itemsPerPage);
        },
        totalAuthors() {
            const authors = new Set();
            this.filteredPublications.forEach(pub => {
                if (pub.author) {
                    pub.author.split(' and ').forEach(author => {
                        authors.add(author.trim());
                    });
                }
            });
            return authors.size;
        },
        yearRange() {
            if (this.filteredPublications.length === 0) return 'N/A';
            const years = this.filteredPublications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
            return `${Math.min(...years)} - ${Math.max(...years)}`;
        }
    },
    methods: {
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
                '\"a': 'ä', '\"e': 'ë', '\"i': 'ï', '\"o': 'ö', '\"u': 'ü',
                '\"A': 'Ä', '\"E': 'Ë', '\"I': 'Ï', '\"O': 'Ö', '\"U': 'Ü',
                '\"y': 'ÿ', '\"Y': 'Ÿ',

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

            // Handle patterns like {\'{a}} or {\'a}
            result = result.replace(/\{\\(['`^"~])(\{([a-zA-Z])\}|([a-zA-Z]))\}/g, (match, accent, group, letter1, letter2) => {
                const letter = letter1 || letter2;
                const key = accent + letter;
                return latexMap[key] || match;
            });

            // Handle patterns like \'{a} or \'a
            result = result.replace(/\\(['`^"~])\{?([a-zA-Z])\}?/g, (match, accent, letter) => {
                const key = accent + letter;
                return latexMap[key] || match;
            });

            // Handle special commands like \c{c}, \aa, \o, etc.
            result = result.replace(/\\(c|aa|AA|o|O|ae|AE|oe|OE|ss|l|L)(\{([a-zA-Z])\}|\s([a-zA-Z])|(?![a-zA-Z]))/g, (match, cmd, group, letter1, letter2) => {
                if (letter1 || letter2) {
                    const key = cmd + '{' + (letter1 || letter2) + '}';
                    return latexMap[key] || latexMap[cmd + ' ' + (letter1 || letter2)] || match;
                }
                return latexMap[cmd] || match;
            });

            // Remove any remaining curly braces (used for capitalization preservation in BibTeX)
            result = result.replace(/\{([^\\}]+)\}/g, '$1');

            return result;
        },
        async loadPublications() {
            try {
                // Fetch the BibTeX file
                const response = await fetch('publications.bib');
                const bibtexText = await response.text();

                // Parse BibTeX using bibtex-parse-js
                const parsed = bibtexParse.toJSON(bibtexText);

                // Extract individual BibTeX entries
                const bibtexEntries = this.extractBibtexEntries(bibtexText);

                // Convert to our format and sort by year
                this.publications = parsed
                    .filter(entry => entry.entryTags && entry.entryTags.title && entry.entryTags.year)
                    .map(entry => {
                        const tags = entry.entryTags;
                        return {
                            id: entry.citationKey,
                            type: entry.entryType,
                            title: this.convertLatexToUnicode(tags.title ? tags.title.replace(/[{}]/g, '') : ''),
                            author: this.convertLatexToUnicode(tags.author || ''),
                            year: tags.year || '',
                            journal: this.convertLatexToUnicode(tags.journal || ''),
                            booktitle: this.convertLatexToUnicode(tags.booktitle || ''),
                            volume: tags.volume || '',
                            number: tags.number || '',
                            pages: tags.pages || '',
                            publisher: this.convertLatexToUnicode(tags.publisher || ''),
                            doi: tags.doi || '',
                            url: tags.url || '',
                            research_field: tags.research_field || '',
                            data_type: tags.data_type || '',
                            bibtexText: bibtexEntries[entry.citationKey] || '',
                            showBibtex: false
                        };
                    })
                    .sort((a, b) => parseInt(b.year) - parseInt(a.year));

            } catch (error) {
                console.error('Error loading publications:', error);
            }
        },
        extractBibtexEntries(bibtexText) {
            const entries = {};
            const regex = /@(\w+)\{([^,]+),[\s\S]*?\n\}/g;
            let match;

            while ((match = regex.exec(bibtexText)) !== null) {
                const citationKey = match[2];
                entries[citationKey] = match[0];
            }

            return entries;
        },
        toggleBibtex(pub) {
            pub.showBibtex = !pub.showBibtex;
        },
        downloadBibtex() {
            // Collect BibTeX entries for filtered publications
            const bibtexEntries = this.filteredPublications
                .map(pub => pub.bibtexText)
                .filter(text => text)
                .join('\n\n');

            // Create blob and download
            const blob = new Blob([bibtexEntries], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dvrk-publications-${this.filteredPublications.length}.bib`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        formatAuthors(authors) {
            if (!authors) return '';
            // Split by ' and ' and join with ' and ' for display
            return authors.split(' and ').join(' and ');
        },
        formatType(type) {
            const typeMap = {
                'article': 'Journal',
                'inproceedings': 'Conference',
                'incollection': 'Book Chapter',
                'misc': 'Other'
            };
            return typeMap[type] || type;
        },
        parseFields(fields) {
            if (!fields) return [];

            // Mapping from codes to full names as defined in README.md
            const fieldMap = {
                'AU': 'Automation',
                'TR': 'Training, skill assessment and gesture recognition',
                'HW': 'Hardware implementation and integration',
                'SS': 'System simulation and modelling',
                'IM': 'Imaging and vision',
                'RE': 'Reviews'
            };

            return fields.split(' and ')
                .map(f => f.trim())
                .filter(f => f)
                .map(code => fieldMap[code] || code);
        },
        parseDataTypes(dataTypes) {
            if (!dataTypes) return [];

            // Mapping from codes to full names as defined in README.md
            const dataTypeMap = {
                'RI': 'Raw Images',
                'KD': 'Kinematic Data',
                'DD': 'Dynamic Data',
                'SD': 'System Data',
                'ED': 'External Data'
            };

            return dataTypes.split(' and ')
                .map(dt => dt.trim())
                .filter(dt => dt)
                .map(code => dataTypeMap[code] || code);
        },
        getFieldDescription(fieldName) {
            const descriptions = {
                'Automation': 'This field refers to all the works automating any aspect of robotic surgery in order to improve the surgical workflow or to optimize the performance in a certain task.',
                'Training, skill assessment and gesture recognition': 'Publications where new training platforms and protocols were designed and evaluated, as well as research efforts towards learning enhancement by multi-sensory training augmentation, skill assessment, and workflow analysis.',
                'Hardware implementation and integration': 'All works that have contributed to develop the dVRK system, as well as further modifications of its software and hardware to make surgery more affordable and capable to interface with other surgical equipment.',
                'System simulation and modelling': 'Studies that focused on the integration of the dVRK into simulation environments, optimizing simulation to obtain realistic robot interactions, and robot parametrization.',
                'Imaging and vision': 'Publications related to the processing of images acquired by the endoscopic camera, including camera calibration, detection, segmentation, tracking, spatial mapping, and image augmentation.',
                'Reviews': 'Review papers that cite the dVRK platform.'
            };
            return descriptions[fieldName] || '';
        },
        getDataTypeDescription(dataTypeName) {
            const descriptions = {
                'Raw Images': 'The left and right video stream from the da Vinci stereo endoscope or any other cameras',
                'Kinematic Data': 'Information associated to the kinematics of the dVRK (including ECM, MTMs, PSMs and SUJ)',
                'Dynamic Data': 'Information associated to the dynamics of the dVRK (including ECM, MTMs, PSMs)',
                'System Data': 'Data associated to the robot teleoperation states, as signals coming from foot pedals, head sensor for operator presence detection, etc.',
                'External Data': 'All data associated with additional technologies that were used along with the dVRK, such as eye trackers, force sensors, different imaging technologies, etc.'
            };
            return descriptions[dataTypeName] || '';
        },
        resetFilters() {
            this.searchQuery = '';
            this.selectedYear = '';
            this.selectedType = '';
            this.selectedField = '';
            this.selectedDataType = '';
            this.currentPage = 1;
        }
    },
    watch: {
        filteredPublications() {
            this.currentPage = 1;
        }
    },
    mounted() {
        this.loadPublications();
    }
}).mount('#app');
