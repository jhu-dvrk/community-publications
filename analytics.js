const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            loading: true,
            charts: {},
            matrixFilter: 'collaborating', // 'collaborating' or 'all'
            matrixSort: 'collaborations',   // 'collaborations', 'total', 'alphabetical'
            hoveredCell: null,
            selectedCollab: null
        };
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
        collaborationData() {
            const siteTotals = {};         // site -> [pub, ...]
            const jointPairs = {};          // 'siteA:::siteB' -> [pub, ...]
            const siteJointCounts = {};     // site -> number of joint papers
            let uniqueJointPubs = 0;

            // Initialize all known sites from CONFIG.SITE_MAP
            Object.keys(CONFIG.SITE_MAP).forEach(siteId => {
                siteTotals[siteId] = [];
                siteJointCounts[siteId] = 0;
            });

            this.publications.forEach(pub => {
                if (!pub.dvrk_site) return;
                const rawSites = pub.dvrk_site.split(' and ').map(s => s.trim()).filter(Boolean);
                const uniqueSites = Array.from(new Set(rawSites));

                uniqueSites.forEach(s => {
                    if (!siteTotals[s]) siteTotals[s] = [];
                    siteTotals[s].push(pub);
                });

                if (uniqueSites.length > 1) {
                    uniqueJointPubs++;
                    uniqueSites.forEach(s => {
                        siteJointCounts[s] = (siteJointCounts[s] || 0) + 1;
                    });

                    for (let i = 0; i < uniqueSites.length; i++) {
                        for (let j = i + 1; j < uniqueSites.length; j++) {
                            const s1 = uniqueSites[i];
                            const s2 = uniqueSites[j];
                            const pairKey = s1 < s2 ? `${s1}:::${s2}` : `${s2}:::${s1}`;
                            if (!jointPairs[pairKey]) jointPairs[pairKey] = [];
                            jointPairs[pairKey].push(pub);
                        }
                    }
                }
            });

            return {
                siteTotals,
                jointPairs,
                siteJointCounts,
                uniqueJointPubs
            };
        },
        allSiteIds() {
            const known = Object.keys(CONFIG.SITE_MAP);
            if (known.length > 0) return known;
            return Object.keys(this.collaborationData.siteTotals);
        },
        collaboratingSiteIds() {
            const counts = this.collaborationData.siteJointCounts;
            return this.allSiteIds.filter(s => (counts[s] || 0) > 0);
        },
        displayedSites() {
            const sites = this.matrixFilter === 'all'
                ? [...this.allSiteIds]
                : [...this.collaboratingSiteIds];

            const { siteJointCounts, siteTotals } = this.collaborationData;

            if (this.matrixSort === 'collaborations') {
                sites.sort((a, b) => {
                    const cDiff = (siteJointCounts[b] || 0) - (siteJointCounts[a] || 0);
                    if (cDiff !== 0) return cDiff;
                    const tDiff = (siteTotals[b]?.length || 0) - (siteTotals[a]?.length || 0);
                    if (tDiff !== 0) return tDiff;
                    return a.localeCompare(b);
                });
            } else if (this.matrixSort === 'total') {
                sites.sort((a, b) => {
                    const tDiff = (siteTotals[b]?.length || 0) - (siteTotals[a]?.length || 0);
                    if (tDiff !== 0) return tDiff;
                    return (siteJointCounts[b] || 0) - (siteJointCounts[a] || 0);
                });
            } else {
                // alphabetical
                sites.sort((a, b) => a.localeCompare(b));
            }

            return sites;
        },
        collabKPIs() {
            const { jointPairs, siteJointCounts, uniqueJointPubs } = this.collaborationData;
            const totalPubs = this.publications.length;
            const percent = totalPubs > 0 ? ((uniqueJointPubs / totalPubs) * 100).toFixed(1) : '0.0';

            // Top pair
            let topPair = { name: 'None', count: 0 };
            Object.entries(jointPairs).forEach(([key, papers]) => {
                if (papers.length > topPair.count) {
                    const [s1, s2] = key.split(':::');
                    topPair = { name: `${s1} & ${s2}`, count: papers.length };
                }
            });

            // Top hub
            let topHub = { name: 'None', count: 0 };
            Object.entries(siteJointCounts).forEach(([site, count]) => {
                if (count > topHub.count) {
                    topHub = { name: site, count };
                }
            });

            return {
                jointPapersCount: uniqueJointPubs,
                jointPapersPercent: percent,
                collaboratingCount: this.collaboratingSiteIds.length,
                allSitesCount: this.allSiteIds.length,
                topPair,
                topHub
            };
        }
    },
    methods: {
        async loadPublications() {
            try {
                // Fetch the BibTeX file
                const response = await fetch('publications.bib');
                const bibtexText = await response.text();

                // Parse BibTeX using bibtex-parse-js
                const cleanedBibtexText = CONFIG.cleanBibtexText(bibtexText);
                const parsed = bibtexParse.toJSON(cleanedBibtexText);

                // Convert to our format
                this.publications = parsed
                    .filter(entry => entry.entryTags && entry.entryTags.title && entry.entryTags.year)
                    .map(entry => {
                        const tags = entry.entryTags;
                        return {
                            id: entry.citationKey,
                            type: entry.entryType,
                            title: CONFIG.convertLatexToUnicode(tags.title ? tags.title.replace(/[{}]/g, '') : ''),
                            author: CONFIG.convertLatexToUnicode(tags.author || ''),
                            year: tags.year || '',
                            journal: CONFIG.convertLatexToUnicode(tags.journal || tags.booktitle || ''),
                            doi: tags.doi ? tags.doi.replace(/[{}]/g, '') : '',
                            url: tags.url ? tags.url.replace(/[{}]/g, '') : '',
                            research_field: tags.research_field ? tags.research_field.replace(/[{}]/g, '') : '',
                            data_type: tags.data_type ? tags.data_type.replace(/[{}]/g, '') : '',
                            dvrk_site: tags.dvrk_site ? tags.dvrk_site.replace(/[{}]/g, '') : '',
                            date_added: tags.date_added ? tags.date_added.replace(/[{}]/g, '') : ''
                        };
                    })
                    .sort((a, b) => parseInt(a.year) - parseInt(b.year));

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
        },
        createPublicationsPerYearChart() {
            const yearCounts = {};
            this.publications.forEach(pub => {
                const year = pub.year;
                yearCounts[year] = (yearCounts[year] || 0) + 1;
            });

            const years = Object.keys(yearCounts).sort();
            const counts = years.map(year => yearCounts[year]);

            const ctx = document.getElementById('publicationsPerYearChart');
            if (!ctx) return;

            this.charts.perYear = new Chart(ctx, {
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
                            window.location.href = `index.html?year=${year}`;
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
            });
        },
        createCumulativeChart() {
            const yearCounts = {};
            this.publications.forEach(pub => {
                const year = pub.year;
                yearCounts[year] = (yearCounts[year] || 0) + 1;
            });

            const years = Object.keys(yearCounts).sort();
            const cumulativeCounts = [];
            let total = 0;
            years.forEach(year => {
                total += yearCounts[year];
                cumulativeCounts.push(total);
            });

            const ctx = document.getElementById('cumulativeChart');
            if (!ctx) return;

            this.charts.cumulative = new Chart(ctx, {
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
                            window.location.href = `index.html?year=${year}`;
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
            });
        },

        createResearchFieldsChart() {
            const fieldCounts = {};
            this.publications.forEach(pub => {
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

            const ctx = document.getElementById('researchFieldsChart');
            if (!ctx) return;

            this.charts.fields = new Chart(ctx, {
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
                            window.location.href = `index.html?field=${field}`;
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
            });
        },

        createDataTypesChart() {
            const typeCounts = {};
            this.publications.forEach(pub => {
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

            const ctx = document.getElementById('dataTypesChart');
            if (!ctx) return;

            this.charts.dataTypes = new Chart(ctx, {
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
                            window.location.href = `index.html?dataType=${dataType}`;
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
            });
        },
        createSitesChart() {
            const siteCounts = {};
            this.publications.forEach(pub => {
                if (pub.dvrk_site) {
                    pub.dvrk_site.split(' and ').forEach(site => {
                        const trimmed = site.trim();
                        if (trimmed) {
                            siteCounts[trimmed] = (siteCounts[trimmed] || 0) + 1;
                        }
                    });
                }
            });

            // Sort by count
            const sites = Object.keys(siteCounts).sort((a, b) => siteCounts[b] - siteCounts[a]);
            const counts = sites.map(site => siteCounts[site]);
            
            // Map acronyms to full names for tooltips but use acronyms for X-axis labels to fit better "by column"
            const labels = sites;
            const fullNames = sites.map(acronym => CONFIG.SITE_MAP[acronym] || acronym);

            const ctx = document.getElementById('sitesChart');
            if (!ctx) return;

            this.charts.sites = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
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
                    maintainAspectRatio: false,
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const index = elements[0].index;
                            const site = sites[index]; 
                            window.location.href = `index.html?site=${site}`;
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                title: (context) => {
                                    const index = context[0].dataIndex;
                                    return fullNames[index];
                                },
                                label: function (context) {
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
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            });
        },
        applyChartTheme(theme) {
            const isDark = (theme || document.documentElement.getAttribute('data-theme')) === 'dark';
            if (window.Chart) {
                Chart.defaults.color = isDark ? '#94a3b8' : '#64748b';
                Chart.defaults.borderColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)';
            }
            Object.values(this.charts).forEach(chart => {
                if (chart) {
                    if (chart.options && chart.options.scales) {
                        Object.values(chart.options.scales).forEach(scale => {
                            if (scale.ticks) scale.ticks.color = isDark ? '#94a3b8' : '#64748b';
                            if (scale.grid) scale.grid.color = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
                        });
                    }
                    if (chart.options && chart.options.plugins && chart.options.plugins.legend) {
                        chart.options.plugins.legend.labels = chart.options.plugins.legend.labels || {};
                        chart.options.plugins.legend.labels.color = isDark ? '#cbd5e1' : '#334155';
                    }
                    chart.update();
                }
            });
        },
        getSiteFullName(siteId) {
            return CONFIG.SITE_MAP[siteId] || siteId;
        },
        getSiteCountry(siteId) {
            return CONFIG.SITE_COUNTRY_MAP[siteId] || '';
        },
        getPairPapers(s1, s2) {
            const key = s1 < s2 ? `${s1}:::${s2}` : `${s2}:::${s1}`;
            return this.collaborationData.jointPairs[key] || [];
        },
        getCellCount(s1, s2) {
            if (s1 === s2) {
                return this.collaborationData.siteTotals[s1]?.length || 0;
            }
            return this.getPairPapers(s1, s2).length;
        },
        getCellDisplay(rowSite, colSite) {
            const count = this.getCellCount(rowSite, colSite);
            if (rowSite === colSite) {
                return count > 0 ? count : '0';
            }
            return count > 0 ? count : '';
        },
        getCellTitle(rowSite, colSite) {
            const count = this.getCellCount(rowSite, colSite);
            const rowName = this.getSiteFullName(rowSite);
            const colName = this.getSiteFullName(colSite);
            const rowCountry = this.getSiteCountry(rowSite) ? ` (${this.getSiteCountry(rowSite)})` : '';
            const colCountry = this.getSiteCountry(colSite) ? ` (${this.getSiteCountry(colSite)})` : '';

            if (rowSite === colSite) {
                const jointCount = this.collaborationData.siteJointCounts[rowSite] || 0;
                return `${rowName}${rowCountry}: ${count} total publications, ${jointCount} joint co-authorships. Click to view publications.`;
            }
            if (count > 0) {
                return `${rowName} × ${colName}: ${count} joint co-authored publications. Click to view papers.`;
            }
            return `${rowName} × ${colName}: No joint publications.`;
        },
        getCellClasses(rowSite, colSite) {
            const isDiagonal = rowSite === colSite;
            const count = this.getCellCount(rowSite, colSite);
            const isHovered = this.hoveredCell && (
                (this.hoveredCell.row === rowSite && this.hoveredCell.col === colSite) ||
                (this.hoveredCell.row === colSite && this.hoveredCell.col === rowSite)
            );
            const isCrosshair = this.hoveredCell && (this.hoveredCell.row === rowSite || this.hoveredCell.col === colSite);

            let levelClass = 'level-0';
            if (isDiagonal) {
                levelClass = 'diagonal-cell';
            } else if (count >= 9) {
                levelClass = 'level-4';
            } else if (count >= 6) {
                levelClass = 'level-3';
            } else if (count >= 3) {
                levelClass = 'level-2';
            } else if (count >= 1) {
                levelClass = 'level-1';
            }

            return {
                [levelClass]: true,
                'has-papers': count > 0,
                'cell-hovered': isHovered,
                'cell-crosshair': isCrosshair && !isHovered
            };
        },
        onCellHover(rowSite, colSite) {
            this.hoveredCell = { row: rowSite, col: colSite };
        },
        onCellLeave() {
            this.hoveredCell = null;
        },
        onCellClick(rowSite, colSite) {
            if (rowSite === colSite) {
                const papers = this.collaborationData.siteTotals[rowSite] || [];
                if (papers.length > 0) {
                    this.selectedCollab = {
                        siteA: rowSite,
                        siteB: rowSite,
                        isDiagonal: true,
                        papers: papers
                    };
                }
            } else {
                const papers = this.getPairPapers(rowSite, colSite);
                if (papers.length > 0) {
                    this.selectedCollab = {
                        siteA: rowSite,
                        siteB: colSite,
                        isDiagonal: false,
                        papers: papers
                    };
                }
            }
        },
        closeModal() {
            this.selectedCollab = null;
        }
    },
    async mounted() {
        await CONFIG.init();
        this.applyChartTheme();
        window.addEventListener('dvrk-theme-changed', (e) => {
            this.applyChartTheme(e.detail?.theme);
        });
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.selectedCollab) {
                this.closeModal();
            }
        });
        this.loadPublications();
    }
}).mount('#app');
