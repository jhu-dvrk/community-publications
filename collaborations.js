const { createApp } = Vue;

const collaborationsApp = createApp({
    data() {
        return {
            publications: [],
            loading: true,
            matrixFilter: 'collaborating', // 'collaborating' or 'all'
            matrixSort: 'collaborations',   // 'collaborations', 'total', 'alphabetical'
            hoveredCell: null,
            selectedCollab: null
        };
    },
    computed: {
        totalAuthors() {
            return CONFIG.calculateTotalAuthors(this.publications);
        },
        collaborationData() {
            const siteTotals = {};
            const jointPairs = {};
            const siteJointCounts = {};
            let uniqueJointPubs = 0;

            Object.keys(CONFIG.SITE_MAP).forEach(siteId => {
                siteTotals[siteId] = [];
                siteJointCounts[siteId] = 0;
            });

            this.publications.forEach(pub => {
                const uniqueSites = CONFIG.parseSites(pub.dvrk_site).map(s => s.acronym);
                if (uniqueSites.length === 0) return;

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
                sites.sort((a, b) => a.localeCompare(b));
            }

            return sites;
        },
        collabKPIs() {
            const { jointPairs, siteJointCounts, uniqueJointPubs } = this.collaborationData;
            const totalPubs = this.publications.length;
            const percent = totalPubs > 0 ? ((uniqueJointPubs / totalPubs) * 100).toFixed(1) : '0.0';

            let topPair = { name: 'None', count: 0 };
            Object.entries(jointPairs).forEach(([key, papers]) => {
                if (papers.length > topPair.count) {
                    const [s1, s2] = key.split(':::');
                    topPair = { name: `${s1} & ${s2}`, count: papers.length };
                }
            });

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
                const { publications } = await CONFIG.loadPublications({ sortBy: 'year_desc' });
                this.publications = publications;
                this.loading = false;
            } catch (error) {
                console.error('Error loading publications for collaborations:', error);
                this.loading = false;
            }
        },
        getSiteFullName(siteId) {
            return CONFIG.getSiteName(siteId);
        },
        getSiteCountry(siteId) {
            return CONFIG.getSiteCountry(siteId);
        },
        getSiteUrl(siteId) {
            return CONFIG.getSiteUrl(siteId);
        },
        getSiteAnalyticsUrl(siteId) {
            return CONFIG.getSiteAnalyticsUrl(siteId);
        },
        getSearchUrl(siteId) {
            return CONFIG.getSearchUrl({ site: siteId });
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
                        papers
                    };
                }
            } else {
                const papers = this.getPairPapers(rowSite, colSite);
                if (papers.length > 0) {
                    this.selectedCollab = {
                        siteA: rowSite,
                        siteB: colSite,
                        isDiagonal: false,
                        papers
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
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.selectedCollab) {
                this.closeModal();
            }
        });
        this.loadPublications();
    }
});

CONFIG.registerSharedComponents(collaborationsApp);
collaborationsApp.mount('#app');
