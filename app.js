const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            searchQuery: '',
            startYear: '',
            endYear: '',
            selectedType: '',
            selectedField: '',
            selectedDataType: '',
            selectedSite: '',
            currentPage: 1,
            itemsPerPage: 50
        };
    },
    computed: {
        availableYears() {
            const years = [...new Set(this.publications.map(p => p.year))];
            return years.sort((a, b) => b - a);
        },
        availableStartYears() {
            if (!this.endYear) return this.availableYears;
            return this.availableYears.filter(year => parseInt(year) <= parseInt(this.endYear));
        },
        availableEndYears() {
            if (!this.startYear) return this.availableYears;
            return this.availableYears.filter(year => parseInt(year) >= parseInt(this.startYear));
        },
        availableFields() {
            const fields = new Set();
            this.publications.forEach(pub => {
                if (pub.research_field) {
                    pub.research_field.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        if (trimmed && CONFIG.FIELD_MAP[trimmed]) {
                            fields.add(CONFIG.FIELD_MAP[trimmed]);
                        }
                    });
                }
            });
            return Array.from(fields).sort();
        },
        availableDataTypes() {
            const dataTypes = new Set();
            this.publications.forEach(pub => {
                if (pub.data_type) {
                    pub.data_type.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        if (trimmed && CONFIG.DATA_TYPE_MAP[trimmed]) {
                            dataTypes.add(CONFIG.DATA_TYPE_MAP[trimmed]);
                        }
                    });
                }
            });
            return Array.from(dataTypes).sort();
        },
        availableSites() {
            const sites = new Map();
            this.publications.forEach(pub => {
                if (pub.dvrk_site) {
                    const parsedSites = this.parseSites(pub.dvrk_site);
                    parsedSites.forEach(s => {
                        sites.set(s.acronym, s.name);
                    });
                }
            });
            // Return array of objects for display {acronym, name}
            return Array.from(sites.entries())
                .map(([acronym, name]) => ({ acronym, name }))
                .sort((a, b) => a.name.localeCompare(b.name));
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

            // Year range filter
            if (this.startYear) {
                filtered = filtered.filter(pub => parseInt(pub.year) >= parseInt(this.startYear));
            }
            if (this.endYear) {
                filtered = filtered.filter(pub => parseInt(pub.year) <= parseInt(this.endYear));
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
            
            // Site filter
            if (this.selectedSite) {
                filtered = filtered.filter(pub => {
                    if (!pub.dvrk_site) return false;
                    const sites = this.parseSites(pub.dvrk_site);
                    return sites.some(site => site.acronym === this.selectedSite || site.name === this.selectedSite);
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
            return CONFIG.calculateTotalAuthors(this.filteredPublications);
        },
        yearRange() {
            return CONFIG.calculateYearRange(this.filteredPublications);
        }
    },
    methods: {
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
                            title: CONFIG.convertLatexToUnicode(tags.title || ''),
                            author: CONFIG.convertLatexToUnicode(tags.author || ''),
                            year: tags.year || '',
                            journal: CONFIG.convertLatexToUnicode(tags.journal || ''),
                            booktitle: CONFIG.convertLatexToUnicode(tags.booktitle || ''),
                            volume: tags.volume || '',
                            number: tags.number || '',
                            pages: tags.pages || '',
                            publisher: CONFIG.convertLatexToUnicode(tags.publisher || ''),
                            doi: tags.doi || '',
                            url: tags.url || '',
                            ieeexplore: tags.ieeexplore || '',
                            semanticscholar: tags.semanticscholar || '',
                            arxiv: tags.arxiv || '',
                            abstract: CONFIG.convertLatexToUnicode(tags.abstract || ''),
                            openaccesspdf: tags.openaccesspdf || '',
                            research_field: tags.research_field ? tags.research_field.replace(/[{}]/g, '') : '',
                            data_type: tags.data_type ? tags.data_type.replace(/[{}]/g, '') : '',
                            dvrk_site: tags.dvrk_site ? tags.dvrk_site.replace(/[{}]/g, '') : '',
                            bibtexText: bibtexEntries[entry.citationKey] || '',
                            showBibtex: false,
                            showAbstract: false
                        };
                    })
                    .sort((a, b) => parseInt(b.year) - parseInt(a.year));

                if (this.publications.length > 0 && this.availableYears.length > 0) {
                    if (!this.startYear) this.startYear = this.availableYears[this.availableYears.length - 1];
                    if (!this.endYear) this.endYear = this.availableYears[0];
                }

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
            if (pub.showBibtex) pub.showAbstract = false;
        },
        toggleAbstract(pub) {
            pub.showAbstract = !pub.showAbstract;
            if (pub.showAbstract) pub.showBibtex = false;
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

            return fields.split(' and ')
                .map(f => f.trim())
                .filter(f => f)
                .map(code => CONFIG.FIELD_MAP[code] || code);
        },
        parseDataTypes(dataTypes) {
            if (!dataTypes) return [];

            return dataTypes.split(' and ')
                .map(dt => dt.trim())
                .filter(dt => dt)
                .map(code => CONFIG.DATA_TYPE_MAP[code] || code);
        },
        parseSites(sites) {
            if (!sites) return [];
            return sites.split(' and ')
                .map(s => s.trim())
                .filter(s => s)
                .map(acronym => ({
                    acronym: acronym,
                    name: CONFIG.SITE_MAP[acronym] || acronym
                }));
        },
        getFieldDescription(fieldName) {
            return CONFIG.FIELD_DESCRIPTIONS[fieldName] || '';
        },
        getDataTypeDescription(dataTypeName) {
            return CONFIG.DATA_TYPE_DESCRIPTIONS[dataTypeName] || '';
        },
        resetFilters() {
            this.searchQuery = '';
            if (this.publications.length > 0 && this.availableYears.length > 0) {
                this.startYear = this.availableYears[this.availableYears.length - 1];
                this.endYear = this.availableYears[0];
            } else {
                this.startYear = '';
                this.endYear = '';
            }
            this.selectedType = '';
            this.selectedField = '';
            this.selectedDataType = '';
            this.selectedSite = '';
            this.currentPage = 1;
        },
        applyUrlFilters() {
            const urlParams = new URLSearchParams(window.location.search);

            if (urlParams.has('year')) {
                const y = urlParams.get('year');
                this.startYear = y;
                this.endYear = y;
            }
            if (urlParams.has('startYear')) {
                this.startYear = urlParams.get('startYear');
            }
            if (urlParams.has('endYear')) {
                this.endYear = urlParams.get('endYear');
            }
            if (urlParams.has('field')) {
                this.selectedField = decodeURIComponent(urlParams.get('field'));
            }
            if (urlParams.has('dataType')) {
                this.selectedDataType = decodeURIComponent(urlParams.get('dataType'));
            }
            if (urlParams.has('site')) {
                this.selectedSite = decodeURIComponent(urlParams.get('site'));
            }
        }
    },
    watch: {
        filteredPublications() {
            this.currentPage = 1;
        }
    },
    async mounted() {
        await CONFIG.init();
        this.loadPublications();
        this.applyUrlFilters();
    }
}).mount('#app');

