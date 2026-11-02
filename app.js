const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            searchQuery: '',
            searchInAbstract: false,
            sortBy: 'year_desc',
            startYear: '',
            endYear: '',
            selectedType: '',
            selectedPeerReviewed: '',
            selectedField: '',
            selectedDataType: '',
            selectedSite: '',
            selectedAuthor: '',
            currentPage: 1,
            itemsPerPage: 50,
            isInitializing: true,
            isApplyingUrl: false,
            isNavigatingToPublication: false,
            filterLinkCopied: false,
            publicationMap: {}
        };
    },
    computed: {
        availableYears() {
            const years = [...new Set(this.publications.map(p => p.year))];
            return years.sort((a, b) => b - a);
        },
        minAvailableYear() {
            return this.availableYears.length > 0 ? this.availableYears[this.availableYears.length - 1] : '';
        },
        maxAvailableYear() {
            return this.availableYears.length > 0 ? this.availableYears[0] : '';
        },
        isCustomYearRange() {
            if (!this.minAvailableYear || !this.maxAvailableYear) return false;
            const customStart = Boolean(this.startYear && String(this.startYear) !== String(this.minAvailableYear));
            const customEnd = Boolean(this.endYear && String(this.endYear) !== String(this.maxAvailableYear));
            return customStart || customEnd;
        },
        activeFilterChips() {
            const chips = [];
            if (this.selectedAuthor) {
                chips.push({
                    key: 'author',
                    kind: 'author',
                    prefix: 'Author',
                    value: this.selectedAuthor,
                    clear: () => { this.selectedAuthor = ''; }
                });
            }
            if (this.selectedField) {
                chips.push({
                    key: 'field',
                    kind: 'field',
                    prefix: 'Area',
                    value: this.selectedField,
                    clear: () => { this.selectedField = ''; }
                });
            }
            if (this.selectedDataType) {
                chips.push({
                    key: 'dataType',
                    kind: 'data',
                    prefix: 'Data',
                    value: this.selectedDataType,
                    clear: () => { this.selectedDataType = ''; }
                });
            }
            if (this.selectedSite) {
                chips.push({
                    key: 'site',
                    kind: 'site',
                    prefix: 'Site',
                    value: this.getSiteDisplayLabel(this.selectedSite),
                    clear: () => { this.selectedSite = ''; }
                });
            }
            if (this.selectedPeerReviewed) {
                chips.push({
                    key: 'peerReviewed',
                    kind: 'status',
                    prefix: 'Review',
                    value: this.formatPeerReviewedFilter(this.selectedPeerReviewed),
                    clear: () => { this.selectedPeerReviewed = ''; }
                });
            }
            if (this.selectedType) {
                chips.push({
                    key: 'type',
                    kind: 'type',
                    prefix: 'Type',
                    value: this.formatTypeFilter(this.selectedType),
                    clear: () => { this.selectedType = ''; }
                });
            }
            if (this.isCustomYearRange) {
                const yearVal = String(this.startYear) === String(this.endYear)
                    ? String(this.startYear)
                    : `${this.startYear}–${this.endYear}`;
                chips.push({
                    key: 'years',
                    kind: 'year',
                    prefix: 'Years',
                    value: yearVal,
                    clear: () => {
                        this.startYear = this.minAvailableYear;
                        this.endYear = this.maxAvailableYear;
                    }
                });
            }
            const trimmedQuery = (this.searchQuery || '').trim();
            if (trimmedQuery) {
                chips.push({
                    key: 'search',
                    kind: 'search',
                    prefix: this.searchInAbstract ? 'Search (+abstracts)' : 'Search',
                    value: `"${trimmedQuery}"`,
                    clear: () => { this.searchQuery = ''; }
                });
            }
            return chips;
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
                const query = this.searchQuery.toLowerCase().trim();
                filtered = filtered.filter(pub => {
                    const matchesBasic = (
                        pub.title?.toLowerCase().includes(query) ||
                        pub.author?.toLowerCase().includes(query) ||
                        pub.formattedAuthors?.toLowerCase().includes(query) ||
                        pub.journal?.toLowerCase().includes(query) ||
                        pub.booktitle?.toLowerCase().includes(query) ||
                        pub.howpublished?.toLowerCase().includes(query) ||
                        pub.school?.toLowerCase().includes(query) ||
                        pub.id?.toLowerCase().includes(query)
                    );
                    if (matchesBasic) return true;
                    if (this.searchInAbstract && pub.abstract) {
                        return pub.abstract.toLowerCase().includes(query);
                    }
                    return false;
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
                filtered = filtered.filter(pub => {
                    const t = (pub.type || '').toLowerCase();
                    if (this.selectedType === 'incollection') return t === 'incollection' || t === 'inbook';
                    if (this.selectedType === 'inproceedings') return t === 'inproceedings' || t === 'conference';
                    if (this.selectedType === 'phdthesis') return t === 'phdthesis' || t === 'mastersthesis';
                    return t === this.selectedType;
                });
            }

            // Peer-reviewed filter
            if (this.selectedPeerReviewed) {
                filtered = filtered.filter(pub => pub.peer_reviewed === this.selectedPeerReviewed);
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

            // Author filter
            if (this.selectedAuthor) {
                filtered = filtered.filter(pub => {
                    const list = pub.authorsList || CONFIG.parseAuthorList(pub.author);
                    return list.some(auth => CONFIG.authorsMatch(auth, this.selectedAuthor));
                });
            }

            // Apply sorting
            const sorted = [...filtered];
            switch (this.sortBy) {
                case 'year_asc':
                    sorted.sort((a, b) => {
                        const diff = CONFIG.getPublicationDateSortKey(a) - CONFIG.getPublicationDateSortKey(b);
                        return diff !== 0 ? diff : (a.title || '').localeCompare(b.title || '');
                    });
                    break;
                case 'date_added_desc':
                    sorted.sort((a, b) => {
                        const dateDiff = (b.date_added || '').localeCompare(a.date_added || '');
                        if (dateDiff !== 0) return dateDiff;
                        return CONFIG.getPublicationDateSortKey(b) - CONFIG.getPublicationDateSortKey(a);
                    });
                    break;
                case 'cites_desc':
                    sorted.sort((a, b) => {
                        const cA = a.cited_by ? a.cited_by.length : 0;
                        const cB = b.cited_by ? b.cited_by.length : 0;
                        if (cB !== cA) return cB - cA;
                        return CONFIG.getPublicationDateSortKey(b) - CONFIG.getPublicationDateSortKey(a);
                    });
                    break;
                case 'title_asc':
                    sorted.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
                    break;
                case 'author_asc':
                    sorted.sort((a, b) => {
                        const cmp = (a.authorSortKey || '').localeCompare(b.authorSortKey || '');
                        if (cmp !== 0) return cmp;
                        return CONFIG.getPublicationDateSortKey(b) - CONFIG.getPublicationDateSortKey(a);
                    });
                    break;
                case 'year_desc':
                default:
                    sorted.sort((a, b) => {
                        const diff = CONFIG.getPublicationDateSortKey(b) - CONFIG.getPublicationDateSortKey(a);
                        return diff !== 0 ? diff : (a.title || '').localeCompare(b.title || '');
                    });
                    break;
            }

            return sorted;
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
        totalAuthorsAll() {
            return CONFIG.calculateTotalAuthors(this.publications);
        },
        yearRange() {
            return CONFIG.calculateYearRange(this.filteredPublications);
        },
        totalInternalCitations() {
            return this.filteredPublications.reduce((acc, p) => acc + (p.cites ? p.cites.length : 0), 0);
        }
    },
    methods: {
        async loadPublications() {
            try {
                // Fetch the BibTeX file
                const bibResponse = await fetch('publications.bib');
                const bibtexText = await bibResponse.text();

                // Parse BibTeX using bibtex-parse-js
                const cleanedBibtexText = CONFIG.cleanBibtexText(bibtexText);
                const parsed = bibtexParse.toJSON(cleanedBibtexText);

                // Extract individual BibTeX entries
                const bibtexEntries = this.extractBibtexEntries(cleanedBibtexText);

                // Convert to our format and sort by year
                this.publications = parsed
                    .filter(entry => entry.entryTags && entry.entryTags.title && entry.entryTags.year)
                    .map(entry => {
                        const tags = entry.entryTags;
                        const rawCites = tags.dvrk_cites ? tags.dvrk_cites.replace(/[{}]/g, '') : '';
                        const cites = rawCites ? rawCites.split(' and ').map(s => s.trim()).filter(Boolean) : [];
                        const authorUnicode = CONFIG.convertLatexToUnicode(tags.author || '');
                        return {
                            id: entry.citationKey,
                            type: (entry.entryType || '').toLowerCase(),
                            title: CONFIG.convertLatexToUnicode(tags.title || ''),
                            author: authorUnicode,
                            authorsList: CONFIG.parseAuthorList(authorUnicode),
                            formattedAuthors: CONFIG.formatAuthors(authorUnicode),
                            authorSortKey: CONFIG.getFirstAuthorSortKey(authorUnicode),
                            year: tags.year || '',
                            month: tags.month || '',
                            date: tags.date || '',
                            journal: CONFIG.convertLatexToUnicode(tags.journal || ''),
                            booktitle: CONFIG.convertLatexToUnicode(tags.booktitle || ''),
                            howpublished: CONFIG.cleanHowPublished(tags.howpublished || ''),
                            school: CONFIG.convertLatexToUnicode(tags.school || ''),
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
                            peer_reviewed: tags.peer_reviewed ? tags.peer_reviewed.replace(/[{}]/g, '').toLowerCase().trim() : '',
                            dvrk_site: tags.dvrk_site ? tags.dvrk_site.replace(/[{}]/g, '') : '',
                            date_added: tags.date_added ? tags.date_added.replace(/[{}]/g, '') : '',
                            bibtexText: bibtexEntries[entry.citationKey] || '',
                            cites: cites,
                            cited_by: [],
                            showCites: false,
                            showCitedBy: false,
                            showBibtex: false,
                            showRis: false,
                            showAbstract: false,
                            bibCopied: false,
                            risCopied: false,
                            copied: false,
                            isHighlighted: false
                        };
                    })
                    .sort((a, b) => {
                        const diff = CONFIG.getPublicationDateSortKey(b) - CONFIG.getPublicationDateSortKey(a);
                        return diff !== 0 ? diff : (a.title || '').localeCompare(b.title || '');
                    });

                // Populate publication map for fast lookup
                this.publicationMap = {};
                this.publications.forEach(p => {
                    this.publicationMap[p.id] = p;
                });

                // Invert citations to compute cited_by dynamically
                this.publications.forEach(p => {
                    if (p.cites && p.cites.length > 0) {
                        p.cites.forEach(targetId => {
                            const target = this.publicationMap[targetId];
                            if (target) {
                                target.cited_by.push(p.id);
                            }
                        });
                    }
                });

                // Sort cited_by for consistent ordering
                this.publications.forEach(p => {
                    if (p.cited_by && p.cited_by.length > 1) {
                        p.cited_by.sort();
                    }
                });

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
            if (pub.showBibtex) {
                pub.showRis = false;
                pub.showAbstract = false;
                pub.showCites = false;
                pub.showCitedBy = false;
            }
        },
        toggleRis(pub) {
            pub.showRis = !pub.showRis;
            if (pub.showRis) {
                pub.showBibtex = false;
                pub.showAbstract = false;
                pub.showCites = false;
                pub.showCitedBy = false;
            }
        },
        toggleAbstract(pub) {
            pub.showAbstract = !pub.showAbstract;
            if (pub.showAbstract) {
                pub.showBibtex = false;
                pub.showRis = false;
                pub.showCites = false;
                pub.showCitedBy = false;
            }
        },
        toggleCites(pub) {
            pub.showCites = !pub.showCites;
            if (pub.showCites) {
                pub.showCitedBy = false;
                pub.showBibtex = false;
                pub.showRis = false;
                pub.showAbstract = false;
            }
        },
        toggleCitedBy(pub) {
            pub.showCitedBy = !pub.showCitedBy;
            if (pub.showCitedBy) {
                pub.showCites = false;
                pub.showBibtex = false;
                pub.showRis = false;
                pub.showAbstract = false;
            }
        },
        getRisText(pub) {
            if (!pub.risText) {
                pub.risText = CONFIG.generateRis(pub);
            }
            return pub.risText;
        },
        downloadSingleBibtex(pub) {
            const blob = new Blob([pub.bibtexText], { type: 'application/x-bibtex;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${pub.id}.bib`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        downloadRis(pub) {
            const risText = this.getRisText(pub);
            const blob = new Blob([risText], { type: 'application/x-research-info-systems;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${pub.id}.ris`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        downloadAllRis() {
            const risEntries = this.filteredPublications
                .map(pub => this.getRisText(pub))
                .join('\r\n\r\n');
            const blob = new Blob([risEntries], { type: 'application/x-research-info-systems;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dvrk-publications-${this.filteredPublications.length}.ris`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        copyText(text, pub, flagKey) {
            const onCopied = () => {
                pub[flagKey] = true;
                setTimeout(() => {
                    pub[flagKey] = false;
                }, 2000);
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(onCopied).catch(() => {
                    this.fallbackCopyText(text, onCopied);
                });
            } else {
                this.fallbackCopyText(text, onCopied);
            }
        },
        getPublicationById(id) {
            return this.publicationMap[id] || this.publications.find(p => p.id === id);
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
            return CONFIG.formatAuthors(authors);
        },
        formatType(type) {
            const typeMap = {
                'article': 'Journal',
                'inproceedings': 'Conference',
                'conference': 'Conference',
                'incollection': 'Book Chapter',
                'inbook': 'Book Chapter',
                'phdthesis': 'Thesis',
                'mastersthesis': 'Thesis',
                'techreport': 'Tech Report',
                'misc': 'Other'
            };
            return typeMap[(type || '').toLowerCase()] || type;
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
        getSiteDisplayLabel(siteValue) {
            if (!siteValue) return '';
            if (CONFIG.SITE_MAP[siteValue]) {
                return `${CONFIG.SITE_MAP[siteValue]} (${siteValue})`;
            }
            const match = this.availableSites.find(s => s.name === siteValue || s.acronym === siteValue);
            return match ? `${match.name} (${match.acronym})` : siteValue;
        },
        formatTypeFilter(typeVal) {
            const map = {
                article: 'Journal Articles',
                inproceedings: 'Conference Papers',
                incollection: 'Book Chapters',
                phdthesis: 'Theses',
                misc: 'Other'
            };
            return map[typeVal] || this.formatType(typeVal);
        },
        formatPeerReviewedFilter(val) {
            const map = {
                yes: 'Peer-Reviewed Only',
                no: 'Preprints / Unreviewed',
                thesis: 'Theses / Dissertations'
            };
            return map[val] || val;
        },
        isAuthorSelected(auth) {
            return Boolean(this.selectedAuthor && CONFIG.authorsMatch(auth, this.selectedAuthor));
        },
        isSiteSelected(site) {
            if (!this.selectedSite || !site) return false;
            return this.selectedSite === site.acronym || this.selectedSite === site.name;
        },
        scrollControlsIntoViewIfNeeded() {
            this.$nextTick(() => {
                const controlsEl = document.querySelector('.controls');
                if (controlsEl && controlsEl.getBoundingClientRect().top < -20) {
                    controlsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        },
        toggleAuthorFilter(authorFull) {
            if (!authorFull) return;
            if (this.selectedAuthor && CONFIG.authorsMatch(authorFull, this.selectedAuthor)) {
                this.selectedAuthor = '';
            } else {
                this.selectedAuthor = authorFull;
            }
            this.scrollControlsIntoViewIfNeeded();
        },
        toggleFieldFilter(field) {
            if (!field) return;
            this.selectedField = this.selectedField === field ? '' : field;
            this.scrollControlsIntoViewIfNeeded();
        },
        toggleDataTypeFilter(dataType) {
            if (!dataType) return;
            this.selectedDataType = this.selectedDataType === dataType ? '' : dataType;
            this.scrollControlsIntoViewIfNeeded();
        },
        toggleSiteFilter(acronym) {
            if (!acronym) return;
            const siteName = CONFIG.SITE_MAP[acronym];
            const isCurrent = this.selectedSite === acronym || (siteName && this.selectedSite === siteName);
            this.selectedSite = isCurrent ? '' : acronym;
            this.scrollControlsIntoViewIfNeeded();
        },
        togglePeerReviewedFilter(status) {
            if (!status) return;
            this.selectedPeerReviewed = this.selectedPeerReviewed === status ? '' : status;
            this.scrollControlsIntoViewIfNeeded();
        },
        clearHighlights() {
            this.publications.forEach(p => {
                if (p.isHighlighted) p.isHighlighted = false;
            });
        },
        onFilterChange() {
            if (this.isInitializing || this.isApplyingUrl || this.isNavigatingToPublication) return;
            this.clearHighlights();
            this.syncFiltersToUrl();
        },
        syncFiltersToUrl() {
            if (this.isInitializing || this.isApplyingUrl || this.isNavigatingToPublication) return;

            const params = new URLSearchParams();
            const q = (this.searchQuery || '').trim();
            if (q) params.set('q', q);
            if (this.searchInAbstract) params.set('inAbstract', '1');
            if (this.sortBy && this.sortBy !== 'year_desc') params.set('sort', this.sortBy);

            const minYear = this.minAvailableYear;
            const maxYear = this.maxAvailableYear;
            const hasCustomStart = Boolean(this.startYear && minYear && String(this.startYear) !== String(minYear));
            const hasCustomEnd = Boolean(this.endYear && maxYear && String(this.endYear) !== String(maxYear));

            if ((hasCustomStart || hasCustomEnd) && String(this.startYear) === String(this.endYear)) {
                params.set('year', String(this.startYear));
            } else {
                if (hasCustomStart) params.set('startYear', String(this.startYear));
                if (hasCustomEnd) params.set('endYear', String(this.endYear));
            }

            if (this.selectedType) params.set('type', this.selectedType);
            if (this.selectedPeerReviewed) params.set('peerReviewed', this.selectedPeerReviewed);
            if (this.selectedField) params.set('field', this.selectedField);
            if (this.selectedDataType) params.set('dataType', this.selectedDataType);
            if (this.selectedSite) params.set('site', this.selectedSite);
            if (this.selectedAuthor) params.set('author', this.selectedAuthor);

            const queryString = params.toString();
            const newUrl = `${window.location.pathname}${queryString ? '?' + queryString : ''}`;
            const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
            if (newUrl !== currentUrl) {
                window.history.replaceState(null, '', newUrl);
            }
        },
        copyFilterLink() {
            this.syncFiltersToUrl();
            const url = window.location.href;
            const onCopied = () => {
                this.filterLinkCopied = true;
                setTimeout(() => {
                    this.filterLinkCopied = false;
                }, 2000);
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(onCopied).catch(() => {
                    this.fallbackCopyText(url, onCopied);
                });
            } else {
                this.fallbackCopyText(url, onCopied);
            }
        },
        resetFilters() {
            this.searchQuery = '';
            this.searchInAbstract = false;
            this.sortBy = 'year_desc';
            if (this.publications.length > 0 && this.availableYears.length > 0) {
                this.startYear = this.availableYears[this.availableYears.length - 1];
                this.endYear = this.availableYears[0];
            } else {
                this.startYear = '';
                this.endYear = '';
            }
            this.selectedType = '';
            this.selectedPeerReviewed = '';
            this.selectedField = '';
            this.selectedDataType = '';
            this.selectedSite = '';
            this.selectedAuthor = '';
            this.currentPage = 1;
            this.clearHighlights();
            this.syncFiltersToUrl();
        },
        sharePublication(pub) {
            const url = `${window.location.origin}${window.location.pathname}?id=${encodeURIComponent(pub.id)}`;
            const onCopied = () => {
                pub.copied = true;
                setTimeout(() => {
                    pub.copied = false;
                }, 2000);
            };

            window.history.replaceState(null, '', url);

            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(onCopied).catch(() => {
                    this.fallbackCopyText(url, onCopied);
                });
            } else {
                this.fallbackCopyText(url, onCopied);
            }
        },
        fallbackCopyText(text, callback) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            try {
                document.execCommand('copy');
                if (callback) callback();
            } catch (err) {
                console.error('Failed to copy text: ', err);
            }
            document.body.removeChild(textArea);
        },
        navigateToPublication(id) {
            if (!id) return;
            const targetId = id.trim().toLowerCase();
            const pub = this.publications.find(p => p.id && p.id.toLowerCase() === targetId);
            if (!pub) return;

            this.isNavigatingToPublication = true;

            // Ensure publication is within start/end year range
            if (pub.year) {
                const yearNum = parseInt(pub.year);
                if (this.startYear && yearNum < parseInt(this.startYear)) {
                    this.startYear = pub.year;
                }
                if (this.endYear && yearNum > parseInt(this.endYear)) {
                    this.endYear = pub.year;
                }
            }

            // If hidden by other active filters, reset them so it is visible
            if (!this.filteredPublications.some(p => p.id && p.id.toLowerCase() === targetId)) {
                this.searchQuery = '';
                this.selectedType = '';
                this.selectedPeerReviewed = '';
                this.selectedField = '';
                this.selectedDataType = '';
                this.selectedSite = '';
                this.selectedAuthor = '';
                if (this.availableYears.length > 0) {
                    this.startYear = this.availableYears[this.availableYears.length - 1];
                    this.endYear = this.availableYears[0];
                }
            }

            if (!this.isInitializing && !this.isApplyingUrl) {
                const jumpUrl = `${window.location.pathname}?id=${encodeURIComponent(pub.id)}`;
                window.history.replaceState(null, '', jumpUrl);
            }

            // Calculate target pagination page
            const index = this.filteredPublications.findIndex(p => p.id && p.id.toLowerCase() === targetId);
            if (index !== -1) {
                this.currentPage = Math.floor(index / this.itemsPerPage) + 1;
            }

            // Highlight the target publication
            this.publications.forEach(p => { p.isHighlighted = false; });
            pub.isHighlighted = true;

            this.$nextTick(() => {
                setTimeout(() => {
                    this.isNavigatingToPublication = false;
                    const el = document.getElementById(pub.id);
                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 150);
            });
        },
        applyUrlFilters() {
            const urlParams = new URLSearchParams(window.location.search);
            const validSorts = new Set(['year_desc', 'year_asc', 'date_added_desc', 'cites_desc', 'title_asc', 'author_asc']);

            this.searchQuery = urlParams.get('q') || urlParams.get('search') || '';
            const inAbs = urlParams.get('inAbstract');
            this.searchInAbstract = inAbs === '1' || inAbs === 'true';

            const rawSort = urlParams.get('sort') || 'year_desc';
            this.sortBy = validSorts.has(rawSort) ? rawSort : 'year_desc';

            let startY = this.minAvailableYear;
            let endY = this.maxAvailableYear;
            if (urlParams.has('year')) {
                const y = urlParams.get('year');
                startY = y;
                endY = y;
            }
            if (urlParams.has('startYear')) {
                startY = urlParams.get('startYear');
            }
            if (urlParams.has('endYear')) {
                endY = urlParams.get('endYear');
            }
            this.startYear = startY;
            this.endYear = endY;

            this.selectedType = urlParams.get('type') || '';
            this.selectedPeerReviewed = urlParams.get('peerReviewed') || '';

            const rawField = urlParams.get('field') || '';
            if (rawField) {
                const mappedField = CONFIG.FIELD_MAP[rawField] || CONFIG.FIELD_MAP[rawField.toUpperCase()] || CONFIG.FIELD_MAP[rawField.toLowerCase()];
                const matchedField = this.availableFields.find(
                    f => f.toLowerCase() === (mappedField || rawField).toLowerCase()
                );
                this.selectedField = matchedField || mappedField || rawField;
            } else {
                this.selectedField = '';
            }

            const rawDataType = urlParams.get('dataType') || '';
            if (rawDataType) {
                const mappedDT = CONFIG.DATA_TYPE_MAP[rawDataType] || CONFIG.DATA_TYPE_MAP[rawDataType.toUpperCase()] || CONFIG.DATA_TYPE_MAP[rawDataType.toLowerCase()];
                const matchedDT = this.availableDataTypes.find(
                    dt => dt.toLowerCase() === (mappedDT || rawDataType).toLowerCase()
                );
                this.selectedDataType = matchedDT || mappedDT || rawDataType;
            } else {
                this.selectedDataType = '';
            }

            const rawSite = urlParams.get('site') || '';
            if (rawSite) {
                const siteMatch = this.availableSites.find(
                    s => s.acronym.toLowerCase() === rawSite.toLowerCase() || s.name.toLowerCase() === rawSite.toLowerCase()
                );
                this.selectedSite = siteMatch ? siteMatch.acronym : rawSite;
            } else {
                this.selectedSite = '';
            }

            this.selectedAuthor = urlParams.get('author') || '';

            const targetId = urlParams.get('id') || (window.location.hash ? window.location.hash.replace(/^#/, '') : null);
            if (targetId) {
                this.navigateToPublication(targetId);
            } else {
                this.clearHighlights();
            }
        }
    },
    watch: {
        filteredPublications() {
            if (!this.isNavigatingToPublication) {
                this.currentPage = 1;
            }
        },
        searchQuery() { this.onFilterChange(); },
        searchInAbstract() { this.onFilterChange(); },
        sortBy() { this.onFilterChange(); },
        startYear() { this.onFilterChange(); },
        endYear() { this.onFilterChange(); },
        selectedType() { this.onFilterChange(); },
        selectedPeerReviewed() { this.onFilterChange(); },
        selectedField() { this.onFilterChange(); },
        selectedDataType() { this.onFilterChange(); },
        selectedSite() { this.onFilterChange(); },
        selectedAuthor() { this.onFilterChange(); }
    },
    async mounted() {
        await CONFIG.init();
        await this.loadPublications();
        this.applyUrlFilters();
        this.$nextTick(() => {
            this.isInitializing = false;
        });
        window.addEventListener('popstate', () => {
            this.isApplyingUrl = true;
            this.applyUrlFilters();
            this.$nextTick(() => {
                this.isApplyingUrl = false;
            });
        });
        window.addEventListener('hashchange', () => {
            const hash = window.location.hash ? window.location.hash.replace(/^#/, '') : null;
            if (hash) {
                this.navigateToPublication(hash);
            }
        });
    }
}).mount('#app');

