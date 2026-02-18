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
                            research_field: tags.research_field || '',
                            data_type: tags.data_type || '',
                            bibtexText: bibtexEntries[entry.citationKey] || '',
                            showBibtex: false,
                            showAbstract: false
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
            this.startYear = '';
            this.endYear = '';
            this.selectedType = '';
            this.selectedField = '';
            this.selectedDataType = '';
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
        }
    },
    watch: {
        filteredPublications() {
            this.currentPage = 1;
        }
    },
    mounted() {
        this.loadPublications();
        this.applyUrlFilters();
    }
}).mount('#app');

