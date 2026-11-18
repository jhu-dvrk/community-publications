const { createApp } = Vue;

const OSM_TILES_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const mapApp = createApp({
    data() {
        return {
            publications: [],
            loading: true,
            minYear: 2013,
            maxYear: new Date().getFullYear(),
            selectedYear: 2013,
            mode: 'cumulative', // 'cumulative' or 'annual'
            isPlaying: true,
            playSpeedMs: 1400,
            playTimer: null,
            siteFilter: '',
            selectedModal: null,
            map: null,
            tileLayer: null,
            markerLayerGroup: null,
            pulseLayerGroup: null,
            siteMarkers: {},
            siteCurrentRadius: {},
            animRafId: null,
            lastRenderedYear: null
        };
    },
    computed: {
        totalAuthors() {
            return CONFIG.calculateTotalAuthors(this.publications);
        },
        knownSiteIds() {
            return Object.keys(CONFIG.SITE_COORDS_MAP);
        },
        frameStats() {
            const year = this.selectedYear;
            const cumulativeCounts = {};
            const annualCounts = {};
            const cumulativePubsBySite = {};
            const annualPubsBySite = {};

            this.knownSiteIds.forEach(id => {
                cumulativeCounts[id] = 0;
                annualCounts[id] = 0;
                cumulativePubsBySite[id] = [];
                annualPubsBySite[id] = [];
            });

            let matchedPubs = 0;
            this.publications.forEach(pub => {
                const pubYear = parseInt(pub.year, 10);
                if (isNaN(pubYear)) return;
                const inScope = this.mode === 'cumulative' ? pubYear <= year : pubYear === year;
                if (inScope) matchedPubs++;

                if (!pub.dvrk_site) return;
                const sites = Array.from(new Set(
                    pub.dvrk_site.split(' and ').map(s => s.trim()).filter(Boolean)
                ));

                sites.forEach(sid => {
                    if (pubYear <= year) {
                        cumulativeCounts[sid] = (cumulativeCounts[sid] || 0) + 1;
                        if (!cumulativePubsBySite[sid]) cumulativePubsBySite[sid] = [];
                        cumulativePubsBySite[sid].push(pub);
                    }
                    if (pubYear === year) {
                        annualCounts[sid] = (annualCounts[sid] || 0) + 1;
                        if (!annualPubsBySite[sid]) annualPubsBySite[sid] = [];
                        annualPubsBySite[sid].push(pub);
                    }
                });
            });

            return {
                matchedPubs,
                cumulativeCounts,
                annualCounts,
                cumulativePubsBySite,
                annualPubsBySite
            };
        },
        globalSiteMaxes() {
            const cumTotals = {};
            const annualBySiteYear = {};
            this.publications.forEach(pub => {
                if (!pub.dvrk_site) return;
                const y = parseInt(pub.year, 10);
                const sites = Array.from(new Set(
                    pub.dvrk_site.split(' and ').map(s => s.trim()).filter(Boolean)
                ));
                sites.forEach(sid => {
                    if (!CONFIG.SITE_COORDS_MAP[sid]) return;
                    cumTotals[sid] = (cumTotals[sid] || 0) + 1;
                    if (!isNaN(y)) {
                        const key = `${sid}:::${y}`;
                        annualBySiteYear[key] = (annualBySiteYear[key] || 0) + 1;
                    }
                });
            });
            const maxCumulative = Math.max(1, ...Object.values(cumTotals), 0);
            const maxAnnual = Math.max(1, ...Object.values(annualBySiteYear), 0);
            return { maxCumulative, maxAnnual };
        },
        colorScaleMax() {
            return this.mode === 'cumulative'
                ? this.globalSiteMaxes.maxCumulative
                : this.globalSiteMaxes.maxAnnual;
        },
        frameKPIs() {
            const { matchedPubs, cumulativeCounts, annualCounts } = this.frameStats;
            const counts = this.mode === 'cumulative' ? cumulativeCounts : annualCounts;
            let activeSites = 0;
            let joinedSites = 0;

            this.knownSiteIds.forEach(id => {
                if ((counts[id] || 0) > 0) activeSites++;
                const yAdded = CONFIG.SITE_YEAR_ADDED_MAP[id];
                if (!yAdded || yAdded <= this.selectedYear) {
                    joinedSites++;
                }
            });

            return {
                publications: matchedPubs,
                activeSites,
                joinedSites
            };
        },
        rankedSites() {
            const { cumulativeCounts, annualCounts } = this.frameStats;
            const query = this.siteFilter.trim().toLowerCase();

            const list = [];
            this.knownSiteIds.forEach(id => {
                const cum = cumulativeCounts[id] || 0;
                const ann = annualCounts[id] || 0;
                const displayCount = this.mode === 'cumulative' ? cum : ann;
                const yearAdded = CONFIG.SITE_YEAR_ADDED_MAP[id] || null;
                const isJoined = !yearAdded || yearAdded <= this.selectedYear;

                if (displayCount === 0 && !isJoined) {
                    return;
                }

                const name = CONFIG.SITE_MAP[id] || id;
                const country = CONFIG.SITE_COUNTRY_MAP[id] || '';
                if (query) {
                    const hay = `${id} ${name} ${country}`.toLowerCase();
                    if (!hay.includes(query)) return;
                }

                list.push({
                    id,
                    name,
                    country,
                    yearAdded,
                    cumCount: cum,
                    annualCount: ann,
                    displayCount
                });
            });

            list.sort((a, b) => {
                if (b.displayCount !== a.displayCount) return b.displayCount - a.displayCount;
                if (b.annualCount !== a.annualCount) return b.annualCount - a.annualCount;
                return a.id.localeCompare(b.id);
            });
            return list;
        }
    },
    watch: {
        selectedYear() {
            this.renderMap();
        },
        mode() {
            this.renderMap();
        },
        playSpeedMs() {
            if (this.isPlaying) {
                this.startTimer();
            }
        }
    },
    methods: {
        async loadPublications() {
            try {
                const { publications } = await CONFIG.loadPublications({ sortBy: 'year_desc' });
                this.publications = publications;

                const years = this.publications
                    .map(p => parseInt(p.year, 10))
                    .filter(y => !isNaN(y) && y > 1990);
                if (years.length > 0) {
                    this.minYear = Math.min(...years);
                    this.maxYear = Math.max(...years);
                    this.selectedYear = this.minYear;
                }

                this.loading = false;
                this.$nextTick(() => {
                    this.initMap();
                    this.renderMap();
                    if (this.isPlaying) {
                        this.startTimer();
                    }
                });
            } catch (err) {
                console.error('Error loading publications for map:', err);
                this.loading = false;
            }
        },
        isDarkTheme() {
            return document.documentElement.getAttribute('data-theme') === 'dark';
        },
        initMap() {
            if (this.map || !document.getElementById('dvrk-map')) return;

            this.map = L.map('dvrk-map', {
                center: [24, 12],
                zoom: 2,
                minZoom: 2,
                maxZoom: 14,
                zoomSnap: 0.25,
                worldCopyJump: true
            });

            this.tileLayer = L.tileLayer(OSM_TILES_URL, {
                attribution: TILE_ATTRIBUTION,
                maxZoom: 19
            }).addTo(this.map);

            this.pulseLayerGroup = L.layerGroup().addTo(this.map);
            this.markerLayerGroup = L.layerGroup().addTo(this.map);

            setTimeout(() => {
                if (this.map) {
                    this.map.invalidateSize();
                    this.fitToSites(false);
                }
            }, 50);
        },
        getSiteBounds() {
            const latLngs = this.knownSiteIds
                .map(sid => CONFIG.SITE_COORDS_MAP[sid])
                .filter(Boolean);
            return latLngs.length > 0 ? L.latLngBounds(latLngs) : null;
        },
        fitToSites(animate = true) {
            if (!this.map) return;
            const bounds = this.getSiteBounds();
            if (bounds) {
                this.map.fitBounds(bounds, { padding: [24, 24], animate });
            } else {
                this.map.setView([24, 12], 2, { animate });
            }
        },
        updateTileTheme() {
            if (!this.map) return;
            this.renderMap();
        },
        resetMapView() {
            this.fitToSites(true);
        },
        computeRadius(count) {
            if (count <= 0) return 5;
            return Math.min(34, 5.5 + 3.1 * Math.sqrt(count));
        },
        siteColor(count, dark) {
            if (count <= 0) {
                return {
                    fill: dark ? '#f87171' : '#dc2626',
                    stroke: dark ? '#fca5a5' : '#991b1b'
                };
            }
            const maxVal = Math.max(1, this.colorScaleMax);
            const t = maxVal > 1 ? Math.max(0, Math.min(1, (count - 1) / (maxVal - 1))) : 1;
            // Smooth HSL gradient from Blue (1) -> Teal -> Full Green (max cumulated)
            const hue = Math.round(220 - 80 * t);
            const sat = Math.round(84 - 8 * t);
            const fillLight = Math.round((dark ? 58 : 52) - 10 * t);
            const strokeLight = Math.round((dark ? 76 : 30) - 6 * t);
            return {
                fill: `hsl(${hue}, ${sat}%, ${fillLight}%)`,
                stroke: `hsl(${hue}, ${Math.min(92, sat + 5)}%, ${strokeLight}%)`
            };
        },
        renderMap() {
            if (!this.map || !this.markerLayerGroup) return;

            const dark = this.isDarkTheme();
            const year = this.selectedYear;
            const yearChanged = year !== this.lastRenderedYear;
            this.lastRenderedYear = year;
            const { cumulativeCounts, annualCounts } = this.frameStats;

            // Pulse rings play once when entering a year
            if (yearChanged) {
                this.pulseLayerGroup.clearLayers();
            }

            // 3. Site markers with smooth animated radius interpolation
            const targetRadii = {};
            const joinedNowSet = new Set();
            const sortedSites = [...this.knownSiteIds].sort((a, b) => {
                const ca = this.mode === 'cumulative' ? (cumulativeCounts[a] || 0) : (annualCounts[a] || 0);
                const cb = this.mode === 'cumulative' ? (cumulativeCounts[b] || 0) : (annualCounts[b] || 0);
                return cb - ca; // Draw largest first so smaller overlapping bubbles sit on top
            });

            sortedSites.forEach(sid => {
                const coords = CONFIG.SITE_COORDS_MAP[sid];
                if (!coords) return;

                const cum = cumulativeCounts[sid] || 0;
                const ann = annualCounts[sid] || 0;
                const count = this.mode === 'cumulative' ? cum : ann;
                const yearAdded = CONFIG.SITE_YEAR_ADDED_MAP[sid];
                const isJoined = !yearAdded || yearAdded <= year;
                const visible = isJoined || count > 0;

                let marker = this.siteMarkers[sid];
                if (!visible) {
                    if (marker && this.markerLayerGroup.hasLayer(marker)) {
                        this.markerLayerGroup.removeLayer(marker);
                    }
                    this.siteCurrentRadius[sid] = 0;
                    return;
                }

                const hasNewInYear = ann > 0;
                const isJoinedThisYear = yearAdded === year;
                if (isJoinedThisYear && yearChanged) {
                    joinedNowSet.add(sid);
                }

                const { fill: fillColor, stroke: strokeColor } = this.siteColor(count, dark);

                const style = {
                    color: strokeColor,
                    weight: isJoinedThisYear ? 2.6 : (hasNewInYear ? 2.0 : 1.5),
                    fillColor: fillColor,
                    fillOpacity: count === 0 ? (isJoinedThisYear ? 0.85 : 0.68) : 0.78
                };

                const targetR = this.computeRadius(count);
                targetRadii[sid] = targetR;

                const name = this.getSiteFullName(sid);
                const country = this.getSiteCountry(sid);
                const joinedLine = yearAdded ? ` • Joined dVRK: ${yearAdded}` : '';
                const deltaLine = this.mode === 'cumulative' && ann > 0 ? `<br><span class="tooltip-delta">+${ann} in ${year}</span>` : '';
                const tooltipHtml = `
                    <div class="map-tooltip-box">
                        <strong>${sid}</strong> — ${name}<br>
                        <span>${country}${joinedLine}</span><br>
                        <strong>${count}</strong> publication${count === 1 ? '' : 's'} ${this.mode === 'cumulative' ? 'through ' + year : 'in ' + year}${deltaLine}
                    </div>
                `;

                if (!marker) {
                    const startR = isJoinedThisYear ? 0.5 : (this.siteCurrentRadius[sid] || targetR);
                    marker = L.circleMarker(coords, { ...style, radius: startR });
                    marker.bindTooltip(tooltipHtml, { direction: 'top', offset: [0, -6] });
                    marker.on('click', () => this.openSiteModal(sid));
                    this.siteMarkers[sid] = marker;
                    marker.addTo(this.markerLayerGroup);
                    this.siteCurrentRadius[sid] = startR;
                } else {
                    marker.setStyle(style);
                    marker.setTooltipContent(tooltipHtml);
                    if (!this.markerLayerGroup.hasLayer(marker)) {
                        const entryR = isJoinedThisYear ? 0.5 : targetR;
                        marker.setRadius(entryR);
                        this.siteCurrentRadius[sid] = entryR;
                        marker.addTo(this.markerLayerGroup);
                    }
                    marker.bringToFront();
                }

                // Single one-shot pop/pulse ring when entering this year
                if (yearChanged && (isJoinedThisYear || hasNewInYear)) {
                    const pulseSize = Math.max(isJoinedThisYear ? 28 : 18, targetR * 2 + (isJoinedThisYear ? 16 : 10));
                    const ringClass = isJoinedThisYear ? 'pulse-joined-pop' : (count === 0 ? 'pulse-joined' : 'pulse-paper');
                    const pulseIcon = L.divIcon({
                        className: 'map-pulse-wrapper',
                        iconSize: [pulseSize, pulseSize],
                        iconAnchor: [pulseSize / 2, pulseSize / 2],
                        html: `<div class="map-pulse-ring ${ringClass}"></div>`
                    });
                    L.marker(coords, { icon: pulseIcon, interactive: false }).addTo(this.pulseLayerGroup);
                }
            });

            this.animateMarkerRadii(targetRadii, joinedNowSet);
        },
        animateMarkerRadii(targetRadii, joinedNowSet = new Set()) {
            if (this.animRafId) {
                cancelAnimationFrame(this.animRafId);
                this.animRafId = null;
            }
            const startRadii = {};
            const ids = Object.keys(targetRadii);
            let needsAnim = false;

            ids.forEach(sid => {
                const isPop = joinedNowSet.has(sid);
                const start = isPop ? 0.5 : (this.siteCurrentRadius[sid] ?? targetRadii[sid]);
                startRadii[sid] = start;
                if (isPop || Math.abs(start - targetRadii[sid]) > 0.25) {
                    needsAnim = true;
                }
            });

            if (!needsAnim) {
                ids.forEach(sid => {
                    this.siteCurrentRadius[sid] = targetRadii[sid];
                    if (this.siteMarkers[sid]) this.siteMarkers[sid].setRadius(targetRadii[sid]);
                });
                return;
            }

            const duration = 380;
            const t0 = performance.now();
            const easeOutBack = (t) => {
                const c1 = 2.4;
                const c3 = c1 + 1;
                return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
            };
            const step = (now) => {
                const progress = Math.min(1, (now - t0) / duration);
                const easedLinear = 1 - Math.pow(1 - progress, 3);
                const easedPop = easeOutBack(progress);
                ids.forEach(sid => {
                    const e = joinedNowSet.has(sid) ? easedPop : easedLinear;
                    const r = Math.max(0.5, startRadii[sid] + (targetRadii[sid] - startRadii[sid]) * e);
                    this.siteCurrentRadius[sid] = r;
                    if (this.siteMarkers[sid]) this.siteMarkers[sid].setRadius(r);
                });
                if (progress < 1) {
                    this.animRafId = requestAnimationFrame(step);
                } else {
                    ids.forEach(sid => {
                        this.siteCurrentRadius[sid] = targetRadii[sid];
                        if (this.siteMarkers[sid]) this.siteMarkers[sid].setRadius(targetRadii[sid]);
                    });
                    this.animRafId = null;
                }
            };
            this.animRafId = requestAnimationFrame(step);
        },
        togglePlay() {
            if (this.isPlaying) {
                this.pausePlay();
            } else {
                if (this.selectedYear >= this.maxYear) {
                    this.selectedYear = this.minYear;
                }
                this.isPlaying = true;
                this.startTimer();
            }
        },
        startTimer() {
            if (this.playTimer) clearInterval(this.playTimer);
            this.playTimer = setInterval(() => {
                if (this.selectedYear < this.maxYear) {
                    this.selectedYear += 1;
                } else {
                    this.pausePlay();
                }
            }, this.playSpeedMs);
        },
        pausePlay() {
            this.isPlaying = false;
            if (this.playTimer) {
                clearInterval(this.playTimer);
                this.playTimer = null;
            }
        },
        stepYear(delta) {
            this.pausePlay();
            const next = Math.max(this.minYear, Math.min(this.maxYear, this.selectedYear + delta));
            this.selectedYear = next;
        },
        resetToStart() {
            this.pausePlay();
            this.selectedYear = this.minYear;
        },
        openSiteModal(siteId) {
            const pubs = this.mode === 'cumulative'
                ? (this.frameStats.cumulativePubsBySite[siteId] || [])
                : (this.frameStats.annualPubsBySite[siteId] || []);
            this.selectedModal = {
                siteId,
                papers: pubs
            };
        },
        closeModal() {
            this.selectedModal = null;
        },
        getSiteFullName(siteId) {
            return CONFIG.getSiteName(siteId);
        },
        getSiteCountry(siteId) {
            return CONFIG.getSiteCountry(siteId);
        },
        getSiteYearAdded(siteId) {
            return CONFIG.getSiteYearAdded(siteId);
        },
        getSiteUrl(siteId) {
            return CONFIG.getSiteUrl(siteId);
        }
    },
    async mounted() {
        CONFIG.updateThemeToggleButtons(CONFIG.getStoredTheme());
        await CONFIG.init();
        window.addEventListener('dvrk-theme-changed', (e) => {
            this.updateTileTheme(e.detail?.theme);
        });
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.selectedModal) {
                this.closeModal();
            }
        });
        this.loadPublications();
    },
    beforeUnmount() {
        this.pausePlay();
        if (this.animRafId) cancelAnimationFrame(this.animRafId);
    }
});

CONFIG.registerSharedComponents(mapApp);
mapApp.mount('#app');

