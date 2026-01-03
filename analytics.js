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
            if (this.publications.length === 0) return 'N/A';
            const years = this.publications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
            return `${Math.min(...years)} - ${Math.max(...years)}`;
        },
        totalAuthors() {
            const authors = new Set();
            this.publications.forEach(pub => {
                if (pub.author) {
                    pub.author.split(' and ').forEach(author => {
                        authors.add(author.trim());
                    });
                }
            });
            return authors.size;
        },
        avgPerYear() {
            if (this.publications.length === 0) return 0;
            const years = this.publications.map(p => parseInt(p.year)).filter(y => !isNaN(y));
            const yearSpan = Math.max(...years) - Math.min(...years) + 1;
            return Math.round(this.publications.length / yearSpan);
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
            result = result.replace(/\\{\\\\(['`^"~])(\\{([a-zA-Z])\\}|([a-zA-Z]))\\}/g, (match, accent, group, letter1, letter2) => {
                const letter = letter1 || letter2;
                const key = accent + letter;
                return latexMap[key] || match;
            });

            // Handle patterns like \\'{a} or \\'a
            result = result.replace(/\\\\(['`^"~])\\{?([a-zA-Z])\\}?/g, (match, accent, letter) => {
                const key = accent + letter;
                return latexMap[key] || match;
            });

            // Handle special commands like \\c{c}, \\aa, \\o, etc.
            result = result.replace(/\\\\(c|aa|AA|o|O|ae|AE|oe|OE|ss|l|L)(\\{([a-zA-Z])\\}|\\s([a-zA-Z])|(?![a-zA-Z]))/g, (match, cmd, group, letter1, letter2) => {
                if (letter1 || letter2) {
                    const key = cmd + '{' + (letter1 || letter2) + '}';
                    return latexMap[key] || latexMap[cmd + ' ' + (letter1 || letter2)] || match;
                }
                return latexMap[cmd] || match;
            });

            // Remove any remaining curly braces (used for capitalization preservation in BibTeX)
            result = result.replace(/\\{([^\\\\}]+)\\}/g, '$1');

            return result;
        },
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
                            title: this.convertLatexToUnicode(tags.title ? tags.title.replace(/[{}]/g, '') : ''),
                            author: this.convertLatexToUnicode(tags.author || ''),
                            year: tags.year || '',
                            research_field: tags.research_field || ''
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
            this.createPublicationTypesChart();
            this.createResearchFieldsChart();
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
        createPublicationTypesChart() {
            const typeMap = {
                'article': 'Journal Articles',
                'inproceedings': 'Conference Papers',
                'incollection': 'Book Chapters',
                'misc': 'Other'
            };

            const typeCounts = {};
            this.publications.forEach(pub => {
                const typeName = typeMap[pub.type] || pub.type || 'Unknown';
                typeCounts[typeName] = (typeCounts[typeName] || 0) + 1;
            });

            const labels = Object.keys(typeCounts);
            const data = Object.values(typeCounts);

            const ctx = document.getElementById('publicationTypesChart');
            if (!ctx) return;

            this.charts.types = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: [
                            'rgba(255, 99, 132, 0.6)',
                            'rgba(54, 162, 235, 0.6)',
                            'rgba(255, 206, 86, 0.6)',
                            'rgba(75, 192, 192, 0.6)',
                            'rgba(153, 102, 255, 0.6)'
                        ],
                        borderColor: [
                            'rgba(255, 99, 132, 1)',
                            'rgba(54, 162, 235, 1)',
                            'rgba(255, 206, 86, 1)',
                            'rgba(75, 192, 192, 1)',
                            'rgba(153, 102, 255, 1)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        },
                        tooltip: {
                            callbacks: {
                                label: function (context) {
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    return `${label}: ${value} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        },
        createResearchFieldsChart() {
            const fieldMap = {
                'AU': 'Automation',
                'TR': 'Training & Skill Assessment',
                'HW': 'Hardware & Integration',
                'SS': 'System Simulation',
                'IM': 'Imaging & Vision',
                'RE': 'Reviews'
            };

            const fieldCounts = {};
            this.publications.forEach(pub => {
                if (pub.research_field) {
                    pub.research_field.split(' and ').forEach(code => {
                        const trimmed = code.trim();
                        const fieldName = fieldMap[trimmed] || trimmed;
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
