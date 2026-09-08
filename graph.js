const { createApp } = Vue;

createApp({
    data() {
        return {
            publications: [],
            publicationMap: {},
            loading: true,
            searchQuery: '',
            searchResults: [],
            showSearchResults: false,
            minCitations: 5,
            startYear: '',
            endYear: '',
            availableYears: [],
            layoutMode: 'clusters', // 'clusters' or 'timeline'
            colorScheme: 'year',    // 'year' or 'site'
            selectedPub: null,
            visibleNodesCount: 0,
            visibleEdgesCount: 0,
            isPhysicsStabilizing: false,
            network: null,
            nodesDataSet: null,
            edgesDataSet: null,
            activeNodeIds: new Set(),
            defaultNodeColors: {},
            siteColorMap: {
                'JHU': '#2563eb',    // Royal Blue
                'UCB': '#059669',    // Emerald Green
                'ICL': '#7c3aed',    // Purple
                'UV': '#d97706',     // Amber
                'CUHK': '#dc2626',   // Red
                'SSSA': '#db2777',   // Pink
                'WPI': '#0891b2',    // Cyan
                'SU': '#ea580c',     // Orange
                'UBC': '#4f46e5',    // Indigo
                'UA': '#0284c7',     // Sky Blue
                'POLIMI': '#16a34a', // Green
                'Other': '#64748b'   // Slate Gray
            }
        };
    },
    computed: {
        topCitedInView() {
            if (!this.publications || this.publications.length === 0) return [];
            return this.publications
                .filter(p => this.activeNodeIds.has(p.id))
                .sort((a, b) => b.cited_by.length - a.cited_by.length)
                .slice(0, 10);
        }
    },
    methods: {
        createNodeTooltip(pub) {
            const container = document.createElement('div');
            container.className = 'network-tooltip';

            const header = document.createElement('div');
            header.className = 'tooltip-header';
            header.innerHTML = `<strong>${pub.id}</strong> <span class="tooltip-year">(${pub.year})</span>`;
            container.appendChild(header);

            const titleEl = document.createElement('div');
            titleEl.className = 'tooltip-title';
            titleEl.textContent = pub.title;
            container.appendChild(titleEl);

            if (pub.author) {
                const authorEl = document.createElement('div');
                authorEl.className = 'tooltip-author';
                authorEl.textContent = pub.author;
                container.appendChild(authorEl);
            }

            const metaEl = document.createElement('div');
            metaEl.className = 'tooltip-meta';
            const siteStr = pub.dvrk_site ? ` • <span class="tooltip-site">${pub.dvrk_site}</span>` : '';
            metaEl.innerHTML = `<span>Citations: <strong>${pub.cited_by.length}</strong></span> • <span>Refs: <strong>${pub.cites.length}</strong></span>${siteStr}`;
            container.appendChild(metaEl);

            return container;
        },

        async loadPublications() {
            try {
                const response = await fetch('publications.bib');
                const bibtexText = await response.text();

                const cleanedBibtexText = CONFIG.cleanBibtexText(bibtexText);
                const parsed = bibtexParse.toJSON(cleanedBibtexText);

                this.publications = parsed
                    .filter(entry => entry.entryTags && entry.entryTags.title && entry.entryTags.year)
                    .map(entry => {
                        const tags = entry.entryTags;
                        const rawCites = tags.dvrk_cites ? tags.dvrk_cites.replace(/[{}]/g, '') : '';
                        const cites = rawCites ? rawCites.split(' and ').map(s => s.trim()).filter(Boolean) : [];
                        return {
                            id: entry.citationKey,
                            type: entry.entryType,
                            title: CONFIG.convertLatexToUnicode(tags.title || ''),
                            author: CONFIG.convertLatexToUnicode(tags.author || ''),
                            year: tags.year || '',
                            journal: CONFIG.convertLatexToUnicode(tags.journal || ''),
                            booktitle: CONFIG.convertLatexToUnicode(tags.booktitle || ''),
                            doi: tags.doi || '',
                            url: tags.url || '',
                            dvrk_site: tags.dvrk_site ? tags.dvrk_site.replace(/[{}]/g, '') : '',
                            cites: cites,
                            cited_by: []
                        };
                    })
                    .sort((a, b) => parseInt(b.year) - parseInt(a.year));

                // Populate publication map
                this.publicationMap = {};
                this.publications.forEach(p => {
                    this.publicationMap[p.id] = p;
                });

                // Invert graph to compute cited_by dynamically
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

                // Sort cited_by
                this.publications.forEach(p => {
                    if (p.cited_by.length > 1) {
                        p.cited_by.sort();
                    }
                });

                // Extract years
                const years = [...new Set(this.publications.map(p => parseInt(p.year)).filter(y => !isNaN(y)))];
                years.sort((a, b) => a - b);
                this.availableYears = years;
                this.startYear = years[0];
                this.endYear = years[years.length - 1];

                this.loading = false;

                // Initialize network after DOM has updated
                this.$nextTick(() => {
                    this.initNetwork();
                });

            } catch (error) {
                console.error('Error loading publications for citation graph:', error);
                this.loading = false;
            }
        },

        getNodeColor(pub) {
            if (this.colorScheme === 'site') {
                if (!pub.dvrk_site) return this.siteColorMap['Other'];
                const firstSite = pub.dvrk_site.split(' and ')[0].trim();
                return this.siteColorMap[firstSite] || this.siteColorMap['Other'];
            }

            // Color scheme by Year (Linear gradient from 2012 to 2026)
            const minYear = 2012;
            const maxYear = 2026;
            const y = Math.max(minYear, Math.min(maxYear, parseInt(pub.year) || minYear));
            const t = (y - minYear) / (maxYear - minYear);

            // Palette interpolation: Deep Blue (#1e3a8a) -> Cyan (#0284c7) -> Teal (#0d9488) -> Amber (#f59e0b) -> Rose (#e11d48)
            if (t < 0.25) {
                return '#1e40af'; // 2012-2015 Classic
            } else if (t < 0.5) {
                return '#0284c7'; // 2015-2019 Growth
            } else if (t < 0.75) {
                return '#0d9488'; // 2019-2022 Maturation
            } else {
                return '#e11d48'; // 2023-2026 Modern
            }
        },

        computeNodeSize(pub) {
            const count = pub.cited_by.length;
            // Base size 14, scale with square root of citations up to 42
            return Math.max(14, Math.min(42, Math.round(14 + Math.sqrt(count) * 4.2)));
        },

        buildGraphDatasets() {
            const nodes = [];
            const edges = [];
            const filteredMap = new Map();

            // Filter publications
            const startY = parseInt(this.startYear) || 2010;
            const endY = parseInt(this.endYear) || 2030;

            this.publications.forEach(pub => {
                const y = parseInt(pub.year);
                if (y < startY || y > endY) return;

                // Threshold check: cited_by count or if minCitations <= 2, also include active citing papers
                const meetsThreshold = pub.cited_by.length >= this.minCitations ||
                    (this.minCitations <= 2 && pub.cites.length >= this.minCitations);

                if (meetsThreshold) {
                    filteredMap.set(pub.id, pub);
                }
            });

            this.activeNodeIds = new Set(filteredMap.keys());
            this.defaultNodeColors = {};

            filteredMap.forEach(pub => {
                const color = this.getNodeColor(pub);
                this.defaultNodeColors[pub.id] = color;

                const nodeObj = {
                    id: pub.id,
                    label: pub.id,
                    size: this.computeNodeSize(pub),
                    color: {
                        background: color,
                        border: '#ffffff',
                        highlight: {
                            background: '#f97316',
                            border: '#ffffff'
                        },
                        hover: {
                            background: '#fb923c',
                            border: '#ffffff'
                        }
                    },
                    borderWidth: 1.5,
                    title: this.createNodeTooltip(pub),
                    font: {
                        size: 11,
                        face: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
                        color: '#1e293b',
                        strokeWidth: 2,
                        strokeColor: '#ffffff'
                    }
                };

                if (this.layoutMode === 'timeline') {
                    const y = parseInt(pub.year) || 2012;
                    nodeObj.level = y - 2012;
                }

                nodes.push(nodeObj);
            });

            // Build edges between active nodes
            const addedEdges = new Set();
            filteredMap.forEach(pub => {
                if (pub.cites && pub.cites.length > 0) {
                    pub.cites.forEach(targetId => {
                        if (filteredMap.has(targetId)) {
                            const edgeKey = `${pub.id}->${targetId}`;
                            if (!addedEdges.has(edgeKey)) {
                                addedEdges.add(edgeKey);
                                edges.push({
                                    id: edgeKey,
                                    from: pub.id,
                                    to: targetId,
                                    arrows: 'to',
                                    color: {
                                        color: 'rgba(156, 163, 175, 0.45)',
                                        highlight: '#2563eb',
                                        hover: '#3b82f6',
                                        inherit: false
                                    },
                                    width: 1.2
                                });
                            }
                        }
                    });
                }
            });

            this.visibleNodesCount = nodes.length;
            this.visibleEdgesCount = edges.length;

            return { nodes, edges };
        },

        getNetworkOptions() {
            const isTimeline = this.layoutMode === 'timeline';

            const options = {
                nodes: {
                    shape: 'dot',
                    shadow: {
                        enabled: true,
                        size: 3,
                        x: 1,
                        y: 1,
                        color: 'rgba(0, 0, 0, 0.12)'
                    }
                },
                edges: {
                    arrows: {
                        to: {
                            enabled: true,
                            scaleFactor: 0.6
                        }
                    },
                    smooth: {
                        enabled: true,
                        type: isTimeline ? 'cubicBezier' : 'continuous',
                        roundness: isTimeline ? 0.4 : 0.2
                    }
                },
                interaction: {
                    hover: true,
                    tooltipDelay: 80,
                    hideEdgesOnDrag: false,
                    zoomView: true,
                    dragView: true
                }
            };

            if (isTimeline) {
                options.layout = {
                    hierarchical: {
                        enabled: true,
                        direction: 'LR',
                        sortMethod: 'directed',
                        levelSeparation: 170,
                        nodeSpacing: 55,
                        treeSpacing: 100,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: false
                    }
                };
                options.physics = {
                    enabled: false
                };
            } else {
                options.layout = {
                    hierarchical: {
                        enabled: false
                    }
                };
                options.physics = {
                    enabled: true,
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {
                        gravitationalConstant: -60,
                        centralGravity: 0.015,
                        springLength: 120,
                        springConstant: 0.06,
                        damping: 0.4,
                        avoidOverlap: 0.35
                    },
                    stabilization: {
                        enabled: true,
                        iterations: 160,
                        updateInterval: 25
                    }
                };
            }

            return options;
        },

        initNetwork() {
            const container = document.getElementById('citation-network');
            if (!container) return;

            const { nodes, edges } = this.buildGraphDatasets();
            this.nodesDataSet = new vis.DataSet(nodes);
            this.edgesDataSet = new vis.DataSet(edges);

            const data = {
                nodes: this.nodesDataSet,
                edges: this.edgesDataSet
            };

            const options = this.getNetworkOptions();
            this.network = new vis.Network(container, data, options);

            this.isPhysicsStabilizing = true;
            this.network.on('stabilizationIterationsDone', () => {
                this.isPhysicsStabilizing = false;
            });

            // Click event on node
            this.network.on('click', (params) => {
                if (params.nodes && params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    this.selectNode(nodeId);
                } else {
                    this.clearSelection();
                }
            });

            // Close search dropdown on outside click
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.graph-search-wrapper')) {
                    this.showSearchResults = false;
                }
            });
        },

        selectNode(nodeId) {
            const pub = this.publicationMap[nodeId];
            if (!pub) return;

            this.selectedPub = pub;
            this.highlightNeighborhood(nodeId);
        },

        highlightNeighborhood(selectedId) {
            if (!this.network || !this.nodesDataSet || !this.edgesDataSet) return;

            const connectedNodeIds = new Set(this.network.getConnectedNodes(selectedId));
            connectedNodeIds.add(selectedId);

            // Find incoming and outgoing edges
            const outgoingTargetIds = new Set(this.selectedPub.cites);
            const incomingSourceIds = new Set(this.selectedPub.cited_by);

            // Update nodes: dim unrelated nodes
            const nodeUpdates = [];
            this.nodesDataSet.forEach(node => {
                const isSelected = node.id === selectedId;
                const isConnected = connectedNodeIds.has(node.id);

                if (isSelected) {
                    nodeUpdates.push({
                        id: node.id,
                        borderWidth: 3,
                        color: {
                            background: '#ea580c',
                            border: '#ffffff'
                        },
                        font: {
                            color: '#0f172a',
                            size: 13
                        }
                    });
                } else if (isConnected) {
                    const origColor = this.defaultNodeColors[node.id] || '#2563eb';
                    nodeUpdates.push({
                        id: node.id,
                        borderWidth: 2,
                        color: {
                            background: origColor,
                            border: '#ffffff'
                        },
                        font: {
                            color: '#1e293b',
                            size: 11
                        }
                    });
                } else {
                    nodeUpdates.push({
                        id: node.id,
                        borderWidth: 1,
                        color: {
                            background: 'rgba(226, 232, 240, 0.45)',
                            border: 'rgba(203, 213, 225, 0.4)'
                        },
                        font: {
                            color: 'rgba(148, 163, 184, 0.35)',
                            size: 10
                        }
                    });
                }
            });
            this.nodesDataSet.update(nodeUpdates);

            // Update edges: highlight connected edges, dim others
            const edgeUpdates = [];
            this.edgesDataSet.forEach(edge => {
                const isOutgoing = edge.from === selectedId;
                const isIncoming = edge.to === selectedId;

                if (isOutgoing) {
                    // Cites target -> orange arrow
                    edgeUpdates.push({
                        id: edge.id,
                        width: 2.5,
                        color: {
                            color: '#ea580c',
                            highlight: '#ea580c'
                        }
                    });
                } else if (isIncoming) {
                    // Cited by source -> royal blue arrow
                    edgeUpdates.push({
                        id: edge.id,
                        width: 2.5,
                        color: {
                            color: '#2563eb',
                            highlight: '#2563eb'
                        }
                    });
                } else {
                    edgeUpdates.push({
                        id: edge.id,
                        width: 0.7,
                        color: {
                            color: 'rgba(226, 232, 240, 0.25)'
                        }
                    });
                }
            });
            this.edgesDataSet.update(edgeUpdates);
        },

        clearSelection() {
            this.selectedPub = null;
            if (!this.nodesDataSet || !this.edgesDataSet) return;

            // Reset all nodes to original colors
            const nodeUpdates = [];
            this.nodesDataSet.forEach(node => {
                const origColor = this.defaultNodeColors[node.id] || '#2563eb';
                nodeUpdates.push({
                    id: node.id,
                    borderWidth: 1.5,
                    color: {
                        background: origColor,
                        border: '#ffffff',
                        highlight: {
                            background: '#f97316',
                            border: '#ffffff'
                        },
                        hover: {
                            background: '#fb923c',
                            border: '#ffffff'
                        }
                    },
                    font: {
                        color: '#1e293b',
                        size: 11
                    }
                });
            });
            this.nodesDataSet.update(nodeUpdates);

            // Reset edges
            const edgeUpdates = [];
            this.edgesDataSet.forEach(edge => {
                edgeUpdates.push({
                    id: edge.id,
                    width: 1.2,
                    color: {
                        color: 'rgba(156, 163, 175, 0.45)',
                        highlight: '#2563eb',
                        hover: '#3b82f6'
                    }
                });
            });
            this.edgesDataSet.update(edgeUpdates);
        },

        focusNodeById(id) {
            // If the paper is not in the active view, adjust threshold to ensure it appears
            const pub = this.publicationMap[id];
            if (!pub) return;

            if (!this.activeNodeIds.has(id)) {
                if (pub.cited_by.length < this.minCitations) {
                    this.minCitations = Math.max(1, pub.cited_by.length);
                    this.applyFilters();
                }
            }

            this.$nextTick(() => {
                this.selectNode(id);
                if (this.network) {
                    this.network.focus(id, {
                        scale: 1.1,
                        animation: {
                            duration: 600,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                }
            });
        },

        selectAndFocusPaper(pub) {
            this.searchQuery = `${pub.id} (${pub.year})`;
            this.showSearchResults = false;
            this.focusNodeById(pub.id);
        },

        filterSearchResults() {
            if (!this.searchQuery.trim()) {
                this.searchResults = [];
                this.showSearchResults = false;
                return;
            }
            const q = this.searchQuery.toLowerCase();
            this.searchResults = this.publications
                .filter(p => {
                    return p.id.toLowerCase().includes(q) ||
                        p.title.toLowerCase().includes(q) ||
                        p.author.toLowerCase().includes(q);
                })
                .slice(0, 8);
            this.showSearchResults = true;
        },

        clearSearch() {
            this.searchQuery = '';
            this.searchResults = [];
            this.showSearchResults = false;
        },

        setMinCitations(val) {
            if (this.minCitations === val) return;
            this.minCitations = val;
            this.applyFilters();
        },

        setLayoutMode(mode) {
            if (this.layoutMode === mode) return;
            this.layoutMode = mode;
            this.applyFilters();
        },

        setColorScheme(scheme) {
            if (this.colorScheme === scheme) return;
            this.colorScheme = scheme;
            this.applyFilters();
        },

        applyFilters() {
            if (!this.network) return;

            const { nodes, edges } = this.buildGraphDatasets();
            this.nodesDataSet.clear();
            this.nodesDataSet.add(nodes);
            this.edgesDataSet.clear();
            this.edgesDataSet.add(edges);

            const options = this.getNetworkOptions();
            this.network.setOptions(options);

            if (this.layoutMode === 'clusters') {
                this.isPhysicsStabilizing = true;
                this.network.stabilize(140);
            } else {
                this.isPhysicsStabilizing = false;
            }

            if (this.selectedPub && this.activeNodeIds.has(this.selectedPub.id)) {
                this.$nextTick(() => {
                    this.highlightNeighborhood(this.selectedPub.id);
                });
            } else {
                this.selectedPub = null;
            }

            this.fitGraph();
        },

        fitGraph() {
            if (this.network) {
                this.network.fit({
                    animation: {
                        duration: 500,
                        easingFunction: 'easeInOutQuad'
                    }
                });
            }
        },

        zoomIn() {
            if (this.network) {
                const scale = this.network.getScale();
                this.network.moveTo({ scale: scale * 1.3, animation: { duration: 250 } });
            }
        },

        zoomOut() {
            if (this.network) {
                const scale = this.network.getScale();
                this.network.moveTo({ scale: scale * 0.77, animation: { duration: 250 } });
            }
        }
    },
    mounted() {
        this.loadPublications();
    }
}).mount('#app');
