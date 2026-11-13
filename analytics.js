const { createApp, markRaw, h } = Vue;

const analyticsApp = createApp({
    data() {
        return {
            publications: [],
            loading: true,
            selectedSite: '',
            sitesChartMode: 'cumulative', // 'cumulative' or 'perYear'
            sitesSelectedYear: null,
            chartReplay: {
                perYear: null,
                cumulative: null,
                fields: null,
                dataTypes: null,
                sites: null
            },
            chartPausedYear: {
                perYear: null,
                cumulative: null,
                fields: null,
                dataTypes: null,
                sites: null
            }
        };
    },
    created() {
        // Keep Chart.js instances and timers outside Vue's reactive Proxy tree.
        this.charts = {};
        this.chartMeta = {};
        this.chartReplayTimers = {};
    },
    computed: {
        yearRange() {
            return CONFIG.calculateYearRange(this.publications);
        },
        totalAuthors() {
            return CONFIG.calculateTotalAuthors(this.publications);
        },
        avgPerYear() {
            if (this.publications.length === 0) return 0;
            const years = this.publications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
            const yearSpan = Math.max(...years) - Math.min(...years) + 1;
            return Math.round(this.publications.length / yearSpan);
        },
        siteTotals() {
            const totals = {};
            Object.keys(CONFIG.SITE_MAP).forEach(siteId => {
                totals[siteId] = 0;
            });
            this.publications.forEach(pub => {
                CONFIG.parseSites(pub.dvrk_site).forEach(s => {
                    totals[s.acronym] = (totals[s.acronym] || 0) + 1;
                });
            });
            return totals;
        },
        allSiteIds() {
            const known = Object.keys(CONFIG.SITE_MAP);
            if (known.length > 0) return known;
            return Object.keys(this.siteTotals);
        },
        siteFilterOptions() {
            return [...this.allSiteIds]
                .map(id => ({
                    id,
                    name: CONFIG.SITE_MAP[id] || id,
                    count: this.siteTotals[id] || 0
                }))
                .sort((a, b) => (b.count - a.count) || a.id.localeCompare(b.id));
        },
        siteFilteredPublications() {
            if (!this.selectedSite) return this.publications;
            return this.publications.filter(pub => {
                if (!pub.dvrk_site) return false;
                return pub.dvrk_site.split(' and ').some(s => s.trim() === this.selectedSite);
            });
        },
        allYearLabels() {
            const yearSet = new Set();
            this.publications.forEach(pub => {
                const y = parseInt(pub.year, 10);
                if (!isNaN(y)) yearSet.add(String(y));
            });
            return Array.from(yearSet).sort();
        },
        allYearLabelsNumbered() {
            return this.allYearLabels.map(y => parseInt(y, 10)).filter(y => !isNaN(y));
        },
        sitesActiveYear() {
            if (this.chartReplay.sites !== null) return this.chartReplay.sites;
            if (this.chartPausedYear.sites !== null) return this.chartPausedYear.sites;
            return this.sitesSelectedYear;
        }
    },
    watch: {
        selectedSite(newSite) {
            this.syncSiteUrlParam(newSite);
            if (!this.loading && this.publications.length > 0) {
                this.$nextTick(() => {
                    this.refreshTopFourCharts();
                });
            }
        }
    },
    methods: {
        async loadPublications() {
            try {
                const { publications } = await CONFIG.loadPublications({ sortBy: 'year_desc' });
                this.publications = publications;

                this.applyUrlSiteFilter();
                this.loading = false;

                // Wait for next tick to ensure DOM is updated
                this.$nextTick(() => {
                    this.createCharts();
                });

            } catch (error) {
                console.error('Error loading publications:', error);
                this.loading = false;
            }
        },
        createCharts() {
            this.createPublicationsPerYearChart();
            this.createCumulativeChart();
            this.createResearchFieldsChart();
            this.createDataTypesChart();
            this.createSitesChart();
            ['perYear', 'cumulative', 'fields', 'dataTypes', 'sites'].forEach(key => {
                this.toggleChartReplay(key);
            });
        },
        refreshTopFourCharts() {
            const topKeys = ['perYear', 'cumulative', 'fields', 'dataTypes'];
            topKeys.forEach(key => {
                this.clearChartTimer(key);
                this.chartReplay[key] = null;
                this.chartPausedYear[key] = null;
                if (this.charts[key]) {
                    this.charts[key].destroy();
                    delete this.charts[key];
                }
            });
            this.createPublicationsPerYearChart();
            this.createCumulativeChart();
            this.createResearchFieldsChart();
            this.createDataTypesChart();
            topKeys.forEach(key => {
                this.toggleChartReplay(key);
            });
        },
        createPublicationsPerYearChart() {
            const yearCounts = {};
            this.siteFilteredPublications.forEach(pub => {
                const year = pub.year;
                yearCounts[year] = (yearCounts[year] || 0) + 1;
            });

            const years = this.allYearLabels.length > 0 ? [...this.allYearLabels] : Object.keys(yearCounts).sort();
            const counts = years.map(year => yearCounts[year] || 0);

            this.chartMeta.perYear = markRaw({
                years: years.map(y => parseInt(y, 10)),
                emptyData: years.map(() => 0),
                dataAtYear: (y) => years.map((yr, idx) => (parseInt(yr, 10) <= y ? counts[idx] : 0)),
                fullData: [...counts]
            });

            const ctx = document.getElementById('publicationsPerYearChart');
            if (!ctx) return;

            this.charts.perYear = markRaw(new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: years,
                    datasets: [{
                        label: 'Publications',
                        data: counts,
                        backgroundColor: 'rgba(54, 162, 235, 0.6)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const year = years[index];
                            const siteParam = this.selectedSite ? `&site=${encodeURIComponent(this.selectedSite)}` : '';
                            window.location.href = `index.html?year=${year}${siteParam}`;
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return `Publications: ${context.parsed.y}`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            }));
        },
        createCumulativeChart() {
            const yearCounts = {};
            this.siteFilteredPublications.forEach(pub => {
                const year = pub.year;
                yearCounts[year] = (yearCounts[year] || 0) + 1;
            });

            const years = this.allYearLabels.length > 0 ? [...this.allYearLabels] : Object.keys(yearCounts).sort();
            const cumulativeCounts = [];
            let total = 0;
            years.forEach(year => {
                total += (yearCounts[year] || 0);
                cumulativeCounts.push(total);
            });

            this.chartMeta.cumulative = markRaw({
                years: years.map(y => parseInt(y, 10)),
                emptyData: years.map(() => null),
                dataAtYear: (y) => years.map((yr, idx) => (parseInt(yr, 10) <= y ? cumulativeCounts[idx] : null)),
                fullData: [...cumulativeCounts]
            });

            const ctx = document.getElementById('cumulativeChart');
            if (!ctx) return;

            this.charts.cumulative = markRaw(new Chart(ctx, {
                type: 'line',
                data: {
                    labels: years,
                    datasets: [{
                        label: 'Cumulative Publications',
                        data: cumulativeCounts,
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const year = years[index];
                            const siteParam = this.selectedSite ? `&site=${encodeURIComponent(this.selectedSite)}` : '';
                            window.location.href = `index.html?year=${year}${siteParam}`;
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return `Total: ${context.parsed.y}`;
                                }
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            }));
        },

        createResearchFieldsChart() {
            const fieldCounts = {};
            this.siteFilteredPublications.forEach(pub => {
                if (pub.research_field) {
                    pub.research_field.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        const fieldName = CONFIG.FIELD_MAP[trimmed] || trimmed;
                        if (fieldName) {
                            fieldCounts[fieldName] = (fieldCounts[fieldName] || 0) + 1;
                        }
                    });
                }
            });

            // Sort by count descending
            const sortedFields = Object.entries(fieldCounts)
                .sort((a, b) => b[1] - a[1]);

            const labels = sortedFields.map(([name]) => name);
            const data = sortedFields.map(([, count]) => count);

            const replayYears = this.allYearLabels.map(y => parseInt(y, 10));
            this.chartMeta.fields = this.buildTagReplayMeta(labels, pub => {
                if (!pub.research_field) return [];
                return pub.research_field.split(' and ').map(code => {
                    const trimmed = code.trim();
                    return CONFIG.FIELD_MAP[trimmed] || trimmed;
                }).filter(Boolean);
            }, this.siteFilteredPublications, replayYears);

            const ctx = document.getElementById('researchFieldsChart');
            if (!ctx) return;

            this.charts.fields = markRaw(new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Publications',
                        data: data,
                        backgroundColor: 'rgba(153, 102, 255, 0.6)',
                        borderColor: 'rgba(153, 102, 255, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    indexAxis: 'y',
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const field = encodeURIComponent(labels[index]);
                            const siteParam = this.selectedSite ? `&site=${encodeURIComponent(this.selectedSite)}` : '';
                            window.location.href = `index.html?field=${field}${siteParam}`;
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return `Publications: ${context.parsed.x}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            }));
        },

        createDataTypesChart() {
            const typeCounts = {};
            this.siteFilteredPublications.forEach(pub => {
                if (pub.data_type) {
                    pub.data_type.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        const typeName = CONFIG.DATA_TYPE_MAP[trimmed] || trimmed;
                        if (typeName) {
                            typeCounts[typeName] = (typeCounts[typeName] || 0) + 1;
                        }
                    });
                }
            });

            // Sort by count descending
            const sortedTypes = Object.entries(typeCounts)
                .sort((a, b) => b[1] - a[1]);

            const labels = sortedTypes.map(([name]) => name);
            const data = sortedTypes.map(([, count]) => count);

            const replayYears = this.allYearLabels.map(y => parseInt(y, 10));
            this.chartMeta.dataTypes = this.buildTagReplayMeta(labels, pub => {
                if (!pub.data_type) return [];
                return pub.data_type.split(' and ').map(code => {
                    const trimmed = code.trim();
                    return CONFIG.DATA_TYPE_MAP[trimmed] || trimmed;
                }).filter(Boolean);
            }, this.siteFilteredPublications, replayYears);

            const ctx = document.getElementById('dataTypesChart');
            if (!ctx) return;

            this.charts.dataTypes = markRaw(new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Publications',
                        data: data,
                        backgroundColor: 'rgba(255, 159, 64, 0.6)',
                        borderColor: 'rgba(255, 159, 64, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    indexAxis: 'y',
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const dataType = encodeURIComponent(labels[index]);
                            const siteParam = this.selectedSite ? `&site=${encodeURIComponent(this.selectedSite)}` : '';
                            window.location.href = `index.html?dataType=${dataType}${siteParam}`;
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    return `Publications: ${context.parsed.x}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            }));
        },
        createSitesChart() {
            const siteCounts = {};
            const byYear = {};
            const yearSet = new Set();
            this.publications.forEach(pub => {
                const y = parseInt(pub.year, 10);
                const hasValidYear = !isNaN(y);
                if (hasValidYear) yearSet.add(y);
                if (pub.dvrk_site) {
                    const uniqueSites = CONFIG.parseSites(pub.dvrk_site).map(s => s.acronym);
                    uniqueSites.forEach(site => {
                        siteCounts[site] = (siteCounts[site] || 0) + 1;
                        if (hasValidYear) {
                            if (!byYear[y]) byYear[y] = {};
                            byYear[y][site] = (byYear[y][site] || 0) + 1;
                        }
                    });
                }
            });

            const allPublishingSites = Object.keys(siteCounts);
            const years = Array.from(yearSet).sort((a, b) => a - b);
            const latestYear = years.length > 0 ? years[years.length - 1] : null;
            if (this.sitesSelectedYear === null || !years.includes(this.sitesSelectedYear)) {
                this.sitesSelectedYear = latestYear;
            }

            let maxAnnualCount = 1;
            years.forEach(y => {
                allPublishingSites.forEach(s => {
                    const c = byYear[y]?.[s] || 0;
                    if (c > maxAnnualCount) maxAnnualCount = c;
                });
            });
            const annualYAxisMax = maxAnnualCount < 5
                ? maxAnnualCount + 1
                : Math.ceil((maxAnnualCount + 1) / 5) * 5;

            const isPerYear = this.sitesChartMode === 'perYear';
            const cumThrough = (site, targetYear) => {
                let sum = 0;
                years.forEach(yr => {
                    if (yr <= targetYear) sum += (byYear[yr]?.[site] || 0);
                });
                return sum;
            };

            const orderSitesAtYear = (targetYear) => {
                const countMap = {};
                const cumMap = {};
                allPublishingSites.forEach(site => {
                    cumMap[site] = targetYear !== null ? cumThrough(site, targetYear) : siteCounts[site];
                    countMap[site] = isPerYear
                        ? (targetYear !== null ? (byYear[targetYear]?.[site] || 0) : 0)
                        : cumMap[site];
                });
                const sorted = [...allPublishingSites].sort((a, b) => {
                    const diff = countMap[b] - countMap[a];
                    if (diff !== 0) return diff;
                    if (isPerYear) {
                        const cumDiff = cumMap[b] - cumMap[a];
                        if (cumDiff !== 0) return cumDiff;
                    }
                    const totalDiff = siteCounts[b] - siteCounts[a];
                    if (totalDiff !== 0) return totalDiff;
                    return a.localeCompare(b);
                });
                return {
                    labels: sorted,
                    data: sorted.map(site => countMap[site])
                };
            };

            const targetInitialYear = isPerYear ? this.sitesSelectedYear : latestYear;
            const initialOrder = orderSitesAtYear(targetInitialYear);

            this.chartMeta.sites = markRaw({
                years,
                emptyData: allPublishingSites.map(() => 0),
                fullLabels: [...initialOrder.labels],
                fullData: [...initialOrder.data],
                labelsAtYear: (y) => orderSitesAtYear(y).labels,
                dataAtYear: (y) => orderSitesAtYear(y).data
            });

            const ctx = document.getElementById('sitesChart');
            if (!ctx) return;

            const yScaleConfig = {
                beginAtZero: true,
                ticks: {
                    stepSize: 1
                }
            };
            if (isPerYear) {
                yScaleConfig.max = annualYAxisMax;
            }

            this.charts.sites = markRaw(new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: [...initialOrder.labels],
                    datasets: [{
                        label: 'Publications',
                        data: [...initialOrder.data],
                        backgroundColor: 'rgba(54, 162, 235, 0.6)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const liveLabels = this.charts.sites?.data?.labels || initialOrder.labels;
                            const site = liveLabels[index];
                            if (!site) return;
                            const year = this.sitesChartMode === 'perYear' && this.sitesActiveYear
                                ? this.sitesActiveYear
                                : '';
                            window.location.href = CONFIG.getSearchUrl({ site, year });
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                title: (context) => {
                                    if (!context || context.length === 0) return '';
                                    const item = context[0];
                                    const site = item.chart?.data?.labels?.[item.dataIndex] || item.label || '';
                                    return CONFIG.getSiteName(site);
                                },
                                label: (context) => {
                                    if (this.sitesChartMode === 'perYear') {
                                        return `Publications in ${this.sitesActiveYear || ''}: ${context.parsed.y}`;
                                    }
                                    const cumulativeYear = this.chartReplay.sites ?? this.chartPausedYear.sites;
                                    if (cumulativeYear !== null) {
                                        return `Publications through ${cumulativeYear}: ${context.parsed.y}`;
                                    }
                                    return `Total Publications: ${context.parsed.y}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            ticks: {
                                autoSkip: false,
                                maxRotation: 45,
                                minRotation: 45
                            }
                        },
                        y: yScaleConfig
                    }
                }
            }));
        },
        setSitesChartMode(mode) {
            if (this.sitesChartMode === mode) return;
            this.sitesChartMode = mode;
            this.clearChartTimer('sites');
            this.chartReplay.sites = null;
            this.chartPausedYear.sites = null;
            if (this.charts.sites) {
                this.charts.sites.destroy();
                delete this.charts.sites;
            }
            if (mode === 'perYear' && this.allYearLabelsNumbered.length > 0) {
                this.sitesSelectedYear = this.allYearLabelsNumbered[this.allYearLabelsNumbered.length - 1];
            }
            this.$nextTick(() => {
                this.createSitesChart();
                this.toggleChartReplay('sites');
            });
        },
        onSitesYearChange() {
            if (this.sitesChartMode !== 'perYear') return;
            this.clearChartTimer('sites');
            this.chartReplay.sites = null;
            this.chartPausedYear.sites = null;
            if (this.sitesSelectedYear !== null) {
                this.applyChartYear('sites', this.sitesSelectedYear);
            }
        },
        applyChartTheme(theme) {
            const isDark = (theme || document.documentElement.getAttribute('data-theme')) === 'dark';
            if (window.Chart) {
                Chart.defaults.color = isDark ? '#94a3b8' : '#64748b';
                Chart.defaults.borderColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)';
            }
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.config && chart.config.options) {
                    const opts = chart.config.options;
                    if (opts.scales) {
                        Object.values(opts.scales).forEach(scale => {
                            if (scale.ticks) scale.ticks.color = isDark ? '#94a3b8' : '#64748b';
                            if (scale.grid) scale.grid.color = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
                        });
                    }
                    if (opts.plugins && opts.plugins.legend) {
                        if (!opts.plugins.legend.labels || typeof opts.plugins.legend.labels !== 'object') {
                            opts.plugins.legend.labels = {};
                        }
                        opts.plugins.legend.labels.color = isDark ? '#cbd5e1' : '#334155';
                    }
                    chart.update('none');
                }
            });
        },
        getSiteFullName(siteId) {
            return CONFIG.getSiteName(siteId);
        },
        applyUrlSiteFilter() {
            const siteParam = new URLSearchParams(window.location.search).get('site');
            if (!siteParam) return;
            const trimmed = siteParam.trim();
            const match = this.allSiteIds.find(id => id.toLowerCase() === trimmed.toLowerCase());
            if (match) {
                this.selectedSite = match;
            }
        },
        syncSiteUrlParam(site) {
            const url = new URL(window.location.href);
            if (site) {
                url.searchParams.set('site', site);
            } else {
                url.searchParams.delete('site');
            }
            window.history.replaceState({}, '', url.toString());
        },
        buildTagReplayMeta(labels, extractTagsFn, pubs = this.publications, overrideYears = null) {
            const yearSet = new Set(overrideYears || []);
            const byYear = {};
            pubs.forEach(pub => {
                const y = parseInt(pub.year, 10);
                if (isNaN(y)) return;
                yearSet.add(y);
                extractTagsFn(pub).forEach(tag => {
                    if (!byYear[y]) byYear[y] = {};
                    byYear[y][tag] = (byYear[y][tag] || 0) + 1;
                });
            });
            const years = Array.from(yearSet).sort((a, b) => a - b);
            const fullData = labels.map(lbl => {
                let total = 0;
                years.forEach(yr => {
                    total += (byYear[yr]?.[lbl] || 0);
                });
                return total;
            });
            return markRaw({
                years,
                emptyData: labels.map(() => 0),
                fullData,
                dataAtYear: (y) => labels.map(lbl => {
                    let sum = 0;
                    years.forEach(yr => {
                        if (yr <= y) sum += (byYear[yr]?.[lbl] || 0);
                    });
                    return sum;
                })
            });
        },
        clearChartTimer(key) {
            if (this.chartReplayTimers[key]) {
                clearInterval(this.chartReplayTimers[key]);
                delete this.chartReplayTimers[key];
            }
        },
        replayBtnTitle(key) {
            if (this.chartReplay[key] !== null) return 'Pause playback';
            if (this.chartPausedYear[key] !== null) return `Resume playback from ${this.chartPausedYear[key]}`;
            return 'Replay by publication year';
        },
        applyChartYear(key, year) {
            const chart = this.charts[key];
            const meta = this.chartMeta[key];
            if (!chart || !meta) return;
            if (typeof meta.labelsAtYear === 'function') {
                chart.data.labels = [...meta.labelsAtYear(year)];
            }
            chart.data.datasets[0].data = [...meta.dataAtYear(year)];
            chart.update();
        },
        canStepChart(key, delta) {
            const pausedYear = this.chartPausedYear[key];
            const meta = this.chartMeta[key];
            if (pausedYear === null || !meta || !meta.years || meta.years.length === 0) return false;
            const idx = meta.years.indexOf(pausedYear);
            if (idx === -1) return false;
            const nextIdx = idx + delta;
            return nextIdx >= 0 && nextIdx < meta.years.length;
        },
        stepChartReplay(key, delta) {
            const pausedYear = this.chartPausedYear[key];
            const meta = this.chartMeta[key];
            if (pausedYear === null || !meta || !meta.years || meta.years.length === 0) return;
            const idx = meta.years.indexOf(pausedYear);
            if (idx === -1) return;
            const nextIdx = Math.max(0, Math.min(meta.years.length - 1, idx + delta));
            if (nextIdx === idx) return;
            const nextYear = meta.years[nextIdx];
            this.chartPausedYear[key] = nextYear;
            if (key === 'sites' && this.sitesChartMode === 'perYear') {
                this.sitesSelectedYear = nextYear;
            }
            this.applyChartYear(key, nextYear);
        },
        pauseChartReplay(key) {
            this.clearChartTimer(key);
            const currentYear = this.chartReplay[key];
            this.chartReplay[key] = null;
            this.chartPausedYear[key] = currentYear;
            if (key === 'sites' && this.sitesChartMode === 'perYear' && currentYear !== null) {
                this.sitesSelectedYear = currentYear;
            }
        },
        toggleChartReplay(key) {
            if (this.chartReplay[key] !== null) {
                this.pauseChartReplay(key);
                return;
            }
            const chart = this.charts[key];
            const meta = this.chartMeta[key];
            if (!chart || !meta || !meta.years.length) return;

            // Lock the value axis to the full-dataset ceiling so bars/lines don't autoresize mid-replay
            const axisKey = chart.options.indexAxis === 'y' ? 'x' : 'y';
            const valueScale = chart.scales && chart.scales[axisKey];
            if (valueScale && typeof valueScale.max === 'number' && chart.options.scales && chart.options.scales[axisKey]) {
                chart.options.scales[axisKey].max = valueScale.max;
            }

            const applyYear = (year) => {
                this.chartPausedYear[key] = null;
                this.chartReplay[key] = year;
                if (key === 'sites' && this.sitesChartMode === 'perYear') {
                    this.sitesSelectedYear = year;
                }
                this.applyChartYear(key, year);
            };

            const pausedYear = this.chartPausedYear[key];
            const pausedIdx = pausedYear !== null ? meta.years.indexOf(pausedYear) : -1;
            let idx = 0;

            if (pausedIdx !== -1 && pausedIdx + 1 < meta.years.length) {
                idx = pausedIdx + 1;
                applyYear(meta.years[idx]);
            } else {
                if (meta.emptyData) {
                    if (typeof meta.labelsAtYear === 'function') {
                        chart.data.labels = [...meta.labelsAtYear(meta.years[0])];
                    }
                    chart.data.datasets[0].data = [...meta.emptyData];
                    chart.update('none');
                }
                applyYear(meta.years[0]);
            }

            if (idx + 1 >= meta.years.length) {
                this.stopChartReplay(key, false);
                return;
            }

            this.clearChartTimer(key);
            this.chartReplayTimers[key] = setInterval(() => {
                idx += 1;
                if (idx < meta.years.length) {
                    applyYear(meta.years[idx]);
                } else {
                    this.stopChartReplay(key, false);
                }
            }, 380);
        },
        stopChartReplay(key, restoreFull) {
            this.clearChartTimer(key);
            this.chartReplay[key] = null;
            this.chartPausedYear[key] = null;
            if (key === 'sites' && this.sitesChartMode === 'perYear' && this.chartMeta.sites) {
                const years = this.chartMeta.sites.years;
                if (restoreFull && this.sitesSelectedYear !== null) {
                    const yrLabels = this.chartMeta.sites.labelsAtYear
                        ? this.chartMeta.sites.labelsAtYear(this.sitesSelectedYear)
                        : this.chartMeta.sites.fullLabels;
                    const yrData = this.chartMeta.sites.dataAtYear(this.sitesSelectedYear);
                    if (yrLabels) this.chartMeta.sites.fullLabels = [...yrLabels];
                    this.chartMeta.sites.fullData = [...yrData];
                    if (this.charts.sites) {
                        if (yrLabels) this.charts.sites.data.labels = [...yrLabels];
                        this.charts.sites.data.datasets[0].data = [...yrData];
                        this.charts.sites.update();
                    }
                } else if (!restoreFull && years.length > 0) {
                    this.sitesSelectedYear = years[years.length - 1];
                }
                return;
            }
            if (restoreFull && this.charts[key] && this.chartMeta[key]) {
                if (this.chartMeta[key].fullLabels) {
                    this.charts[key].data.labels = [...this.chartMeta[key].fullLabels];
                }
                this.charts[key].data.datasets[0].data = [...this.chartMeta[key].fullData];
                this.charts[key].update();
            }
        }
    },
    async mounted() {
        await CONFIG.init();
        this.applyChartTheme();
        window.addEventListener('dvrk-theme-changed', (e) => {
            this.applyChartTheme(e.detail?.theme);
        });
        this.loadPublications();
    },
    beforeUnmount() {
        Object.keys(this.chartReplayTimers).forEach(k => clearInterval(this.chartReplayTimers[k]));
    }
});

analyticsApp.component('chart-replay-controls', {
    props: {
        playingYear: { type: Number, default: null },
        pausedYear: { type: Number, default: null },
        canPrev: { type: Boolean, default: false },
        canNext: { type: Boolean, default: false }
    },
    emits: ['toggle', 'step'],
    render() {
        const isPlaying = this.playingYear !== null;
        const isPaused = this.pausedYear !== null;
        const title = isPlaying
            ? 'Pause playback'
            : (isPaused ? `Resume playback from ${this.pausedYear}` : 'Replay by publication year');
        const label = isPlaying
            ? `⏸ ${this.playingYear}`
            : (isPaused ? `▶ ${this.pausedYear}` : '▶');

        const renderStepIcon = (isNext) => h('svg', {
            viewBox: '0 0 12 12',
            width: 10,
            height: 10,
            fill: 'currentColor',
            'aria-hidden': 'true'
        }, isNext
            ? [
                h('polygon', { points: '1.5,2 7.8,6 1.5,10' }),
                h('rect', { x: 8.7, y: 2, width: 1.8, height: 8, rx: 0.4 })
            ]
            : [
                h('rect', { x: 1.5, y: 2, width: 1.8, height: 8, rx: 0.4 }),
                h('polygon', { points: '10.5,2 4.2,6 10.5,10' })
            ]);

        const children = [];
        if (isPaused) {
            children.push(h('button', {
                type: 'button',
                class: 'chart-step-btn',
                disabled: !this.canPrev,
                title: 'Previous year',
                'aria-label': 'Previous year',
                onClick: () => this.$emit('step', -1)
            }, [renderStepIcon(false)]));
        }
        children.push(h('button', {
            type: 'button',
            class: ['chart-replay-btn', { playing: isPlaying, paused: isPaused }],
            title,
            onClick: () => this.$emit('toggle')
        }, label));
        if (isPaused) {
            children.push(h('button', {
                type: 'button',
                class: 'chart-step-btn',
                disabled: !this.canNext,
                title: 'Next year',
                'aria-label': 'Next year',
                onClick: () => this.$emit('step', 1)
            }, [renderStepIcon(true)]));
        }
        return h('div', { class: 'chart-replay-controls' }, children);
    }
});

CONFIG.registerSharedComponents(analyticsApp);
analyticsApp.mount('#app');
