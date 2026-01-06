const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            loading: true,
            charts: {}
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
                            research_field: tags.research_field || '',
                            data_type: tags.data_type || ''
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
        }
    },
    mounted() {
        this.loadPublications();
    }
}).mount('#app');
