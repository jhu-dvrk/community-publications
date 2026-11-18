const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            loading: true,
            publications: [],
            datasetCreatorMap: {},
            searchQuery: '',
            searchInAbstract: false,
            sortBy: 'year_desc',
            startYear: '',
            endYear: '',
            selectedType: '',
            selectedPeerReviewed: '',
            selectedDataset: '',
            selectedAuthor: '',
            isInitializing: true,
            isApplyingUrl: false,
            filterLinkCopied: false
        };
    },
    computed: {
        availableYears() {
            const years = [...new Set(this.publications.map(p => p.year).filter(Boolean))];
            return years.sort((a, b) => b - a);
        },
        minAvailableYear() {
            return this.availableYears.length > 0 ? this.availableYears[this.availableYears.length - 1] : '';
        },
        maxAvailableYear() {
            return this.availableYears.length > 0 ? this.availableYears[0] : '';
        },
        availableStartYears() {
            if (!this.endYear) return this.availableYears;
            return this.availableYears.filter(y => parseInt(y, 10) <= parseInt(this.endYear, 10));
        },
        availableEndYears() {
            if (!this.startYear) return this.availableYears;
            return this.availableYears.filter(y => parseInt(y, 10) >= parseInt(this.startYear, 10));
        },
        isCustomYearRange() {
            if (!this.minAvailableYear || !this.maxAvailableYear) return false;
            const customStart = Boolean(this.startYear && String(this.startYear) !== String(this.minAvailableYear));
            const customEnd = Boolean(this.endYear && String(this.endYear) !== String(this.maxAvailableYear));
            return customStart || customEnd;
        },
        datasetUsageCounts() {
            const counts = {};
            this.publications.forEach(pub => {
                (pub.datasets || []).forEach(dsId => {
                    counts[dsId] = (counts[dsId] || 0) + 1;
                });
            });
            return counts;
        },
        datasetCatalog() {
            return Object.values(this.datasetCreatorMap)
                .map(creator => ({
                    id: creator.id,
                    name: creator.dvrk_dataset,
                    title: creator.title,
                    year: creator.year,
                    count: this.datasetUsageCounts[creator.id] || 0
                }))
                .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
        },
        availableDatasets() {
            return this.datasetCatalog.filter(ds => ds.count > 0 || ds.id === this.selectedDataset);
        },
        selectedDatasetInfo() {
            if (!this.selectedDataset) return null;
            return this.datasetCreatorMap[this.selectedDataset]
                ? {
                    id: this.selectedDataset,
                    name: this.datasetCreatorMap[this.selectedDataset].dvrk_dataset,
                    title: this.datasetCreatorMap[this.selectedDataset].title,
                    year: this.datasetCreatorMap[this.selectedDataset].year
                }
                : null;
        },
        filteredPublications() {
            return CONFIG.filterPublications(this.publications, {
                searchQuery: this.searchQuery,
                searchInAbstract: this.searchInAbstract,
                startYear: this.startYear,
                endYear: this.endYear,
                selectedType: this.selectedType,
                selectedPeerReviewed: this.selectedPeerReviewed,
                selectedDataset: this.selectedDataset,
                selectedAuthor: this.selectedAuthor,
                sortBy: this.sortBy
            });
        },
        totalAuthors() {
            const authors = new Set();
            this.filteredPublications.forEach(pub => {
                if (pub.authorsList) {
                    pub.authorsList.forEach(a => authors.add(a.normalized || a.full));
                }
            });
            return authors.size;
        },
        activeFilterChips() {
            const chips = [];
            if (this.selectedDataset) {
                chips.push({
                    key: 'dataset',
                    kind: 'type',
                    prefix: 'Dataset',
                    value: this.getDatasetName(this.selectedDataset),
                    clear: () => { this.selectedDataset = ''; }
                });
            }
            if (this.selectedAuthor) {
                chips.push({
                    key: 'author',
                    kind: 'author',
                    prefix: 'Author',
                    value: this.selectedAuthor,
                    clear: () => { this.selectedAuthor = ''; }
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
                const from = this.startYear || this.minAvailableYear;
                const to = this.endYear || this.maxAvailableYear;
                chips.push({
                    key: 'year',
                    kind: 'year',
                    prefix: 'Years',
                    value: from === to ? String(from) : `${from}–${to}`,
                    clear: () => {
                        this.startYear = this.minAvailableYear;
                        this.endYear = this.maxAvailableYear;
                    }
                });
            }
            if (this.searchQuery && this.searchQuery.trim()) {
                chips.push({
                    key: 'search',
                    kind: 'search',
                    prefix: this.searchInAbstract ? 'Search (incl. abstract)' : 'Search',
                    value: this.searchQuery.trim(),
                    clear: () => { this.searchQuery = ''; }
                });
            }
            return chips;
        }
    },
    watch: {
        searchQuery() { this.syncUrlWithFilters(); },
        searchInAbstract() { this.syncUrlWithFilters(); },
        sortBy() { this.syncUrlWithFilters(); },
        startYear() { this.syncUrlWithFilters(); },
        endYear() { this.syncUrlWithFilters(); },
        selectedType() { this.syncUrlWithFilters(); },
        selectedPeerReviewed() { this.syncUrlWithFilters(); },
        selectedDataset() { this.syncUrlWithFilters(); },
        selectedAuthor() { this.syncUrlWithFilters(); }
    },
    methods: {
        async loadData() {
            try {
                const [datasetResult, primaryResult] = await Promise.all([
                    CONFIG.loadPublications({
                        bibUrl: 'dataset_publications.bib',
                        withBibtexText: true,
                        withUiState: true,
                        sortBy: 'year_desc'
                    }),
                    CONFIG.loadPublications({
                        bibUrl: 'publications.bib',
                        sortBy: 'year_desc'
                    })
                ]);

                this.publications = datasetResult.publications;
                const creators = {};
                primaryResult.publications.forEach(pub => {
                    if (pub.dvrk_dataset) {
                        creators[pub.id] = pub;
                    }
                });
                this.datasetCreatorMap = creators;

                if (this.availableYears.length > 0) {
                    if (!this.startYear) this.startYear = this.minAvailableYear;
                    if (!this.endYear) this.endYear = this.maxAvailableYear;
                }
            } catch (error) {
                console.error('Error loading dataset publications:', error);
            } finally {
                this.loading = false;
            }
        },
        getDatasetName(datasetId) {
            return this.datasetCreatorMap[datasetId]?.dvrk_dataset || datasetId;
        },
        formatTypeFilter(typeVal) {
            const map = {
                article: 'Journal Articles',
                inproceedings: 'Conference Papers',
                incollection: 'Book Chapters',
                phdthesis: 'Theses',
                misc: 'Other'
            };
            return map[typeVal] || CONFIG.formatPublicationType(typeVal);
        },
        formatPeerReviewedFilter(val) {
            const map = {
                yes: 'Peer-Reviewed Only',
                no: 'Preprints / Unreviewed',
                thesis: 'Theses / Dissertations'
            };
            return map[val] || val;
        },
        toggleDatasetFilter(dsId) {
            this.selectedDataset = this.selectedDataset === dsId ? '' : dsId;
        },
        togglePeerReviewedFilter(status) {
            this.selectedPeerReviewed = this.selectedPeerReviewed === status ? '' : status;
        },
        toggleAuthorFilter(authorName) {
            if (!authorName) return;
            const matches = this.selectedAuthor && CONFIG.authorsMatch(authorName, this.selectedAuthor);
            this.selectedAuthor = matches ? '' : authorName;
        },
        downloadFilteredBibtex() {
            const content = this.filteredPublications
                .map(p => p.bibtexText)
                .filter(Boolean)
                .join('\n\n');
            this.triggerDownload(content, 'dvrk_dataset_publications.bib', 'application/x-bibtex');
        },
        downloadFilteredRis() {
            const content = this.filteredPublications
                .map(p => CONFIG.generateRis(p))
                .join('\n');
            this.triggerDownload(content, 'dvrk_dataset_publications.ris', 'application/x-research-info-systems');
        },
        triggerDownload(content, filename, mimeType) {
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        resetFilters() {
            this.searchQuery = '';
            this.searchInAbstract = false;
            this.sortBy = 'year_desc';
            this.selectedType = '';
            this.selectedPeerReviewed = '';
            this.selectedDataset = '';
            this.selectedAuthor = '';
            if (this.availableYears.length > 0) {
                this.startYear = this.minAvailableYear;
                this.endYear = this.maxAvailableYear;
            } else {
                this.startYear = '';
                this.endYear = '';
            }
        },
        applyFiltersFromUrl() {
            const params = new URLSearchParams(window.location.search);
            this.isApplyingUrl = true;

            this.searchQuery = params.get('search') || '';
            this.searchInAbstract = params.get('abstract') === 'true';
            this.sortBy = params.get('sort') || 'year_desc';
            this.selectedType = params.get('type') || '';
            this.selectedPeerReviewed = params.get('peer_reviewed') || '';
            this.selectedDataset = params.get('dataset') || '';
            this.selectedAuthor = params.get('author') || '';

            const yearParam = params.get('year');
            if (yearParam) {
                this.startYear = yearParam;
                this.endYear = yearParam;
            } else {
                const sy = params.get('startYear');
                const ey = params.get('endYear');
                this.startYear = sy || this.minAvailableYear;
                this.endYear = ey || this.maxAvailableYear;
            }

            this.$nextTick(() => {
                this.isApplyingUrl = false;
            });
        },
        syncUrlWithFilters() {
            if (this.isInitializing || this.isApplyingUrl) return;
            const params = new URLSearchParams();
            if (this.searchQuery) params.set('search', this.searchQuery);
            if (this.searchInAbstract) params.set('abstract', 'true');
            if (this.sortBy && this.sortBy !== 'year_desc') params.set('sort', this.sortBy);
            if (this.selectedType) params.set('type', this.selectedType);
            if (this.selectedPeerReviewed) params.set('peer_reviewed', this.selectedPeerReviewed);
            if (this.selectedDataset) params.set('dataset', this.selectedDataset);
            if (this.selectedAuthor) params.set('author', this.selectedAuthor);

            if (this.startYear && String(this.startYear) !== String(this.minAvailableYear)) {
                params.set('startYear', this.startYear);
            }
            if (this.endYear && String(this.endYear) !== String(this.maxAvailableYear)) {
                params.set('endYear', this.endYear);
            }

            const qs = params.toString();
            const newUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
            window.history.replaceState({}, '', newUrl);
        },
        async copyShareableFilterUrl() {
            try {
                await navigator.clipboard.writeText(window.location.href);
                this.filterLinkCopied = true;
                setTimeout(() => { this.filterLinkCopied = false; }, 2000);
            } catch (err) {
                console.error('Failed to copy filter URL:', err);
            }
        }
    },
    async mounted() {
        CONFIG.initTheme();
        await this.loadData();
        this.applyFiltersFromUrl();
        this.isInitializing = false;
    }
});

CONFIG.registerSharedComponents(app);
app.mount('#app');
