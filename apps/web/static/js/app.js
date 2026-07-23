/**
 * Palmeiras Agenda v6
 */
(function () {
    'use strict';

    const TEAM_ID = CONFIG.TEAM_ID;
    const BR_TZ = CONFIG.BR_TZ;
    let liveInterval = null;
    let performanceChart = null;
    let chartJsLoaded = false;

    // --- API Cache (5 min TTL) ---
    const _apiCache = {};
    const CACHE_TTL = 5 * 60 * 1000;

    // --- Competition Codes ---
    const COMP_MAP = {
        BSA: ['BSA'],
        CLI: ['CLI', 'CL', 'LIBERTADORES', 'COPA_LIBERTADORES'],
        COPA: ['COPA', 'CBC', 'COPA_DO_BRASIL'],
        CPA: ['CPA', 'CAMPEONATO_PAULISTA', 'PAULISTA'],
        WC: ['WC', 'WORLD_CUP', 'FIFA_WORLD_CUP'],
        BFA1: ['BFA1', 'BRASILEIRO_FEMININO', 'BRASILEIRO_FEMININO_A1'],
    };

    // --- Stage Name Translation (API enums → Portuguese) ---
    const STAGE_NAMES = {
        'GROUP_STAGE': 'Fase de Grupos',
        '5TH_PHASE': '5ª Fase',
        '4TH_PHASE': '4ª Fase',
        '3RD_PHASE': '3ª Fase',
        '2ND_PHASE': '2ª Fase',
        '1ST_PHASE': '1ª Fase',
        'QUARTER_FINALS': 'Quartas de Final',
        'SEMI_FINALS': 'Semifinal',
        'FINAL': 'Final',
        'LAST_16': 'Oitavas de Final',
        'LAST_8': 'Quartas de Final',
        'LAST_4': 'Semifinal',
        'LAST_32': '16 avos de Final',
        'ROUND_OF_16': 'Oitavas de Final',
        'ROUND_OF_8': 'Quartas de Final',
        'ROUND_OF_4': 'Semifinal',
        'ROUND_OF_32': '2ª Fase',
        'PLAY_OFFS': 'Playoffs',
        'PLAYOFFS': 'Playoffs',
        'KNOCKOUT_STAGE': 'Mata-mata',
        'THIRD_PLACE': 'Disputa de 3º lugar',
        'THIRD_PLACE_PLAY_OFF': 'Disputa de 3º lugar',
        'PLAYOFF_ROUND': 'Repescagem',
        'QUALIFYING_ROUND': 'Eliminatória',
        'PRELIMINARY_ROUND': 'Fase Preliminar',
        'REGULAR_SEASON': '',
        'LEAGUE_PHASE': 'Fase de Liga',
    };

    const FINISHED_STATUSES = new Set(['FINISHED', 'PLAYING_TIME_FINISHED']);
    const LIVE_STATUSES = new Set(['IN_PLAY', 'PAUSED']);
    const UPCOMING_STATUSES = new Set(['SCHEDULED', 'TIMED']);
    const WORLD_CUP_FROM = '2026-06-11';
    const WORLD_CUP_TO = '2026-07-19';
    const WORLD_CUP_CODES = new Set(['WC', 'WORLD_CUP', 'FIFA_WORLD_CUP']);
    const WORLD_CUP_REFRESH_MS = 15 * 60 * 1000;
    const WORLD_CUP_TEAM_NAMES_PT = {
        ESP: 'Espanha',
        ARG: 'Argentina',
        BRA: 'Brasil',
    };
    const NEWS_REFRESH_MS = 5 * 60 * 1000;
    const DEFAULT_TAB = 'home';
    const VALID_TABS = new Set(['home', 'classificacao', 'estatisticas', 'historico', 'worldcup', 'news', 'ajustes']);
    const VALID_COMP_FILTERS = new Set(['all', 'BSA', 'CLI', 'COPA', 'CPA', 'BFA1', 'PAULISTA_F', 'COPA_F', 'SUPERCOPA_F', 'WC']);
    const VALID_WC_FILTERS = new Set(['all', 'upcoming', 'finished', 'brazil']);
    const VALID_PALMEIRAS_FILTERS = new Set(['all', 'next', 'results']);
    let _initialTab = null;
    let _isApplyingUrlState = false;
    let _heroMode = 'palmeiras';
    let _countdownInterval = null;
    let _worldCupRefreshInterval = null;
    let _newsRefreshInterval = null;
    let _newsVisibilityBound = false;
    let palmeirasHomeLoaded = false;
    let palmeirasHomeError = false;
    let palmeirasUpcomingMatches = [];
    let palmeirasFinishedMatches = [];
    let palmeirasHomeFilter = 'all';
    let standingsCompetition = 'all';
    const expandedMatchKeys = new Set();

    function initNativeShell() {
        const isNativeShell = /PalmeirasAgenda(?:iOS|Android)\//.test(navigator.userAgent);
        document.body.classList.toggle('native-shell', isNativeShell);
        if (isNativeShell) document.body.dataset.nativeTab = 'home';
    }

    function formatStage(stage) {
        const code = String(stage || '').trim().toUpperCase();
        if (!code || code === 'REGULAR_SEASON') return '';
        if (STAGE_NAMES[code]) return STAGE_NAMES[code];

        // Never expose API enum formatting (for example LAST_16) in the UI.
        return code
            .toLocaleLowerCase('pt-BR')
            .split('_')
            .filter(Boolean)
            .map(word => word.charAt(0).toLocaleUpperCase('pt-BR') + word.slice(1))
            .join(' ');
    }

    function getCompCode(comp) {
        return (comp && comp.code) || '';
    }

    function palmeirasQuery(path) {
        const joiner = path.includes('?') ? '&' : '?';
        return `${path}${joiner}team_id=${TEAM_ID}&team_scope=${encodeURIComponent(CONFIG.TEAM_SCOPE || 'men')}`;
    }

    function isSafeCompFilter(value) {
        return value === 'all' || /^[A-Z0-9_]{2,36}$/.test(String(value || ''));
    }

    function isWorldCupCode(value) {
        return WORLD_CUP_CODES.has(String(value || '').toUpperCase());
    }

    function isSharedCalendarCompFilter(value) {
        return isSafeCompFilter(value);
    }

    function isSharedCalendarMatch(match) {
        return Boolean(match);
    }

    function isPalmeirasMatch(match) {
        return Boolean(
            match &&
            ((match.homeTeam && match.homeTeam.id === TEAM_ID) ||
             (match.awayTeam && match.awayTeam.id === TEAM_ID))
        );
    }

    function matchDomKey(match) {
        if (!match) return '';
        const homeId = (match.homeTeam && (match.homeTeam.id || match.homeTeam.name || match.homeTeam.shortName)) || 'home';
        const awayId = (match.awayTeam && (match.awayTeam.id || match.awayTeam.name || match.awayTeam.shortName)) || 'away';
        const comp = getCompCode(match.competition) || 'OTHER';
        return String(match.id || match.matchId || `${match.utcDate || 'date'}-${comp}-${homeId}-${awayId}`);
    }

    function matchOpenAttr(match) {
        const key = matchDomKey(match);
        return key && expandedMatchKeys.has(key) ? ' open' : '';
    }

    function matchDataAttr(match) {
        const key = matchDomKey(match);
        return key ? ` data-match-key="${escapeHtml(key)}"` : '';
    }

    function matchSideScore(match, side) {
        if (!match) return null;
        const direct = side === 'home' ? match.homeScore : match.awayScore;
        if (hasValue(direct)) return direct;
        const nested = match.score && match.score.fullTime;
        return nested && hasValue(nested[side]) ? nested[side] : null;
    }

    function matchDisplaySides(match) {
        const homeScore = matchSideScore(match, 'home');
        const awayScore = matchSideScore(match, 'away');
        const palmeirasMatch = isPalmeirasMatch(match);
        if (!palmeirasMatch) {
            return {
                leftTeam: match.homeTeam,
                rightTeam: match.awayTeam,
                leftScore: homeScore,
                rightScore: awayScore,
                perspective: 'neutral',
            };
        }

        const isHome = match.homeTeam && match.homeTeam.id === TEAM_ID;
        return {
            leftTeam: isHome ? match.homeTeam : match.awayTeam,
            rightTeam: isHome ? match.awayTeam : match.homeTeam,
            leftScore: isHome ? homeScore : awayScore,
            rightScore: isHome ? awayScore : homeScore,
            perspective: 'palmeiras',
        };
    }

    function isPastMatchAwaitingResult(match) {
        if (!match || !['SCHEDULED', 'TIMED'].includes(match.status)) return false;
        const kickoff = Date.parse(match.utcDate || '');
        return Number.isFinite(kickoff) && kickoff < Date.now() - (2 * 60 * 60 * 1000);
    }

    // --- Helpers ---
    function hasValue(value) {
        return value !== null && value !== undefined;
    }

    function setBooleanAttribute(el, attr, enabled) {
        if (!el) return;
        if (enabled) {
            el.setAttribute(attr, '');
        } else {
            el.removeAttribute(attr);
        }
    }

    function addClickListener(id, handler) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', handler);
    }

    function scoreValue(score, side) {
        return score && hasValue(score[side]) ? score[side] : 0;
    }

    function fullTimeScore(match) {
        return (match && match.score && match.score.fullTime) || {};
    }

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function safeExternalUrl(url, fallback = '#') {
        try {
            const parsed = new URL(String(url || ''), window.location.href);
            return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : fallback;
        } catch (error) {
            return fallback;
        }
    }

    function safeImageUrl(url) {
        try {
            const parsed = new URL(String(url || ''), window.location.href);
            return ['http:', 'https:', 'data:'].includes(parsed.protocol) ? String(url) : CONFIG.getCrest(null);
        } catch (error) {
            return CONFIG.getCrest(null);
        }
    }

    function formatDate(d) {
        return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ });
    }

    function formatTime(d) {
        return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
    }

    function formatShortDate(d) {
        const dt = new Date(d);
        const day = dt.toLocaleDateString('pt-BR', { day: '2-digit', timeZone: BR_TZ });
        const month = dt.toLocaleDateString('pt-BR', { month: 'short', timeZone: BR_TZ }).replace('.', '');
        return `${day} ${month}`;
    }

    function setLastUpdated() {
        const el = document.getElementById('last-updated');
        if (el) {
            el.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        }
    }

    function estimateMinute(utcDate) {
        const kickoff = new Date(utcDate);
        const now = new Date();
        const elapsedMin = Math.floor((now - kickoff) / 60000);

        if (elapsedMin < 0) return null;
        if (elapsedMin <= 45) return `~${elapsedMin}'`;
        if (elapsedMin <= 60) return '~Intervalo';
        if (elapsedMin <= 105) return `~${elapsedMin - 15}'`;
        return '~Encerrando';
    }

    function isValidDateKey(value) {
        return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
    }

    function normalizeMonthParam(value) {
        const month = parseInt(value, 10);
        return month >= 1 && month <= 12 ? month : null;
    }

    function normalizeYearParam(value) {
        const year = parseInt(value, 10);
        return year >= 2020 && year <= 2035 ? year : null;
    }

    function currentTabId() {
        const activeTab = document.querySelector('.tab-btn.active');
        return (activeTab && activeTab.dataset.tab) || DEFAULT_TAB;
    }

    function updateUrlState(patch = {}) {
        if (_isApplyingUrlState) return;
        const url = new URL(window.location.href);
        const params = url.searchParams;

        Object.entries(patch).forEach(([key, value]) => {
            if (value == null || value === '') {
                params.delete(key);
                return;
            }
            if (key === 'tab' && value === DEFAULT_TAB) {
                params.delete(key);
                return;
            }
            if ((key === 'comp' || key === 'wc') && value === 'all') {
                params.delete(key);
                return;
            }
            if (key === 'month') {
                params.set(key, String(value).padStart(2, '0'));
                return;
            }
            params.set(key, String(value));
        });

        const nextUrl = `${url.pathname}${params.toString() ? `?${params.toString()}` : ''}${url.hash}`;
        const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        if (nextUrl !== currentUrl) {
            window.history.replaceState(null, '', nextUrl);
        }
    }

    function hydrateUrlState() {
        _isApplyingUrlState = true;
        const params = new URL(window.location.href).searchParams;
        const tab = params.get('tab');
        const year = normalizeYearParam(params.get('year'));
        const month = normalizeMonthParam(params.get('month'));
        const comp = String(params.get('comp') || '').toUpperCase();
        const day = params.get('day');
        const wc = String(params.get('wc') || '').toLowerCase();

        if (tab && VALID_TABS.has(tab)) _initialTab = tab;

        // Default to current year/month before applying URL overrides
        const todayParts = getTodayStr().split('-');
        const todayYr = parseInt(todayParts[0]);
        const todayMo = parseInt(todayParts[1]);
        if (_calYear === null) _calYear = todayYr;
        if (_calMonth === null) _calMonth = todayMo;

        if (year) _calYear = year;
        if (month) _calMonth = month;
        if (comp && isSharedCalendarCompFilter(comp)) _calCompFilter = comp;
        if (day && isValidDateKey(day)) _calSelectedDay = day;
        if (wc && VALID_WC_FILTERS.has(wc)) worldCupFilter = wc;

        syncYearSelect();
        syncCompLegend();
        _isApplyingUrlState = false;
    }

    // --- Theme ---
    function getStoredTheme() {
        try {
            return localStorage.getItem('theme');
        } catch (error) {
            return null;
        }
    }

    function setStoredTheme(theme) {
        try {
            localStorage.setItem('theme', theme);
        } catch (error) {
            // Theme still applies for this session when storage is unavailable.
        }
    }

    function initTheme() {
        const saved = getStoredTheme();
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(saved || (prefersDark ? 'dark' : 'light'));
    }

    function applyTheme(theme) {
        const toggle = document.getElementById('themeToggle');
        const isDark = theme === 'dark';
        if (theme === 'dark') {
            document.body.classList.add('dark');
        } else {
            document.body.classList.remove('dark');
        }
        if (toggle) {
            toggle.innerHTML = isDark
                ? '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"></path></svg>'
                : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5 8.5 8.5 0 1 0 20.5 14.2Z"></path></svg>';
            toggle.setAttribute('aria-label', isDark ? 'Alternar para tema claro' : 'Alternar para tema escuro');
            toggle.setAttribute('aria-pressed', String(isDark));
            toggle.title = isDark ? 'Alternar para tema claro' : 'Alternar para tema escuro';
        }
        setStoredTheme(theme);
        if (performanceChart) updateChartColors();
    }

    window.toggleTheme = function () {
        applyTheme(document.body.classList.contains('dark') ? 'light' : 'dark');
    };

    window.nativeSetTheme = function (theme) {
        applyTheme(theme === 'dark' ? 'dark' : 'light');
    };

    function updateChartColors() {
        if (!performanceChart) return;
        const isDark = document.body.classList.contains('dark');
        const textColor = isDark ? '#B0B0B0' : '#666666';
        const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)';
        ['x', 'y'].forEach(axis => {
            performanceChart.options.scales[axis].ticks.color = textColor;
            performanceChart.options.scales[axis].grid.color = gridColor;
        });
        performanceChart.options.plugins.legend.labels.color = textColor;
        performanceChart.update('none');
    }

    // --- UI States ---
    function showSkeleton(id, type) {
        const el = document.getElementById(id);
        if (!el) return;
        if (type === 'hero') {
            el.innerHTML = '<div style="padding:2rem"><div class="skeleton-line" style="height:24px;width:50%;margin:0 auto 1rem"></div><div style="display:flex;justify-content:space-around;margin:1rem 0"><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div><div class="skeleton-line" style="width:60px;height:40px"></div><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div></div></div>';
        } else {
            el.innerHTML = '<div class="skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line medium"></div></div>'.repeat(3);
        }
    }

    function showError(id, msg, fn) {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = `<div class="error-state"><div class="error-icon" aria-hidden="true">!</div><div class="error-message">${escapeHtml(msg)}</div>${fn ? `<button type="button" class="retry-btn" data-retry-fn="${escapeHtml(fn)}">Tentar novamente</button>` : ''}</div>`;
        const retry = el.querySelector('[data-retry-fn]');
        if (retry) {
            retry.addEventListener('click', () => {
                const retryFn = window[retry.dataset.retryFn];
                if (typeof retryFn === 'function') retryFn();
            });
        }
    }

    function showEmpty(id, msg) {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = `<div class="empty">${escapeHtml(msg)}</div>`;
    }

    let toastTimer = null;

    function ensureToastRegion() {
        let region = document.getElementById('toast-region');
        if (region) return region;
        region = document.createElement('div');
        region.id = 'toast-region';
        region.className = 'toast-region';
        region.setAttribute('aria-live', 'polite');
        region.setAttribute('aria-atomic', 'true');
        document.body.appendChild(region);
        return region;
    }

    function showToast(message, variant = 'success') {
        const region = ensureToastRegion();
        region.innerHTML = `<div class="toast ${escapeHtml(variant)}">${escapeHtml(message)}</div>`;
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            region.innerHTML = '';
            toastTimer = null;
        }, 3200);
    }

    // --- API ---
    async function api(path, ttlMs = CACHE_TTL) {
        const cached = _apiCache[path];
        if (cached && Date.now() - cached.time < ttlMs) {
            return cached.data;
        }
        try {
            const res = await fetch(CONFIG.apiUrl(path), { headers: { 'Accept': 'application/json' } });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            _apiCache[path] = { data, time: Date.now() };
            // Evict stale entries to prevent memory leak
            const now = Date.now();
            for (const key of Object.keys(_apiCache)) {
                if (now - _apiCache[key].time > CACHE_TTL * 3) delete _apiCache[key];
            }
            return data;
        } catch (e) {
            console.warn(`API [${path}] failed; using fallback when available`);
            // Return stale cache on failure
            if (cached) return cached.data;
            return null;
        }
    }

    // --- Tabs ---
    function initTabs() {
        const tabs = Array.from(document.querySelectorAll('.tab-btn'));
        const panels = Array.from(document.querySelectorAll('.tab-content'));

        function resetPageScrollAfterLayout() {
            const root = document.documentElement;
            const previousScrollBehavior = root.style.scrollBehavior;
            root.style.scrollBehavior = 'auto';

            const reset = () => {
                window.scrollTo(0, 0);
                if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
                document.body.scrollTop = 0;
            };

            // Reset immediately as well as after the panel visibility changes.
            // The delayed reset covers late API-driven layout changes on slower
            // production connections without leaving smooth scrolling disabled.
            reset();
            requestAnimationFrame(() => {
                reset();
                requestAnimationFrame(() => {
                    reset();
                });
            });
            window.setTimeout(() => {
                reset();
                root.style.scrollBehavior = previousScrollBehavior;
            }, 150);
        }

        function activateTab(btn, focusTab = false) {
            document.body.dataset.activeTab = btn.dataset.tab;

            tabs.forEach(tab => {
                const selected = tab === btn;
                tab.classList.toggle('active', selected);
                tab.setAttribute('aria-selected', String(selected));
                tab.tabIndex = selected ? 0 : -1;
            });

            panels.forEach(panel => {
                const selected = panel.id === btn.dataset.tab;
                panel.classList.toggle('active', selected);
                setBooleanAttribute(panel, 'hidden', !selected);
                setBooleanAttribute(panel, 'inert', !selected);
                panel.setAttribute('aria-hidden', String(!selected));
            });

            if (focusTab) btn.focus();
            if (btn.dataset.tab === 'estatisticas' && !performanceChart) {
                renderPerformanceChart();
            }
            if (btn.dataset.tab === 'worldcup') {
                loadWorldCup();
            }
            if (btn.dataset.tab === 'news') {
                startNewsRefresh();
            }
            if (window.PalmeirasFeatures) {
                window.PalmeirasFeatures.onTabActivated(btn.dataset.tab);
            }
            updateUrlState({ tab: btn.dataset.tab });
        }

        window.nativeSelectTab = function (tabId) {
            const target = tabs.find(tab => tab.dataset.tab === tabId);
            if (!target) return false;
            activateTab(target);
            document.body.dataset.nativeTab = tabId;
            // Reset after the active native panel has settled.
            resetPageScrollAfterLayout();
            return true;
        };

        tabs.forEach((btn, index) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                activateTab(btn);
                if (window.matchMedia('(max-width: 720px)').matches) {
                    resetPageScrollAfterLayout();
                }
            });
            btn.addEventListener('keydown', (event) => {
                const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
                if (!keys.includes(event.key)) return;
                event.preventDefault();
                let nextIndex = index;
                if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
                if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = tabs.length - 1;
                activateTab(tabs[nextIndex], true);
            });
        });

        activateTab(tabs.find(tab => tab.dataset.tab === _initialTab) || tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0]);
    }

    function initStickyDesktopTabs() {
        const tabs = document.querySelector('.tabs');
        const header = document.querySelector('.header');
        if (!tabs || !header) return;

        const desktopPointer = window.matchMedia('(hover: hover) and (pointer: fine)');
        let animationFrame = 0;

        const syncFloatingState = () => {
            animationFrame = 0;
            const shouldFloat = desktopPointer.matches
                && !document.body.classList.contains('native-shell')
                && header.getBoundingClientRect().bottom <= 12;
            tabs.classList.toggle('is-floating', shouldFloat);
        };

        const scheduleFloatingState = () => {
            if (animationFrame) return;
            animationFrame = window.requestAnimationFrame(syncFloatingState);
        };

        window.addEventListener('scroll', scheduleFloatingState, { passive: true });
        window.addEventListener('resize', scheduleFloatingState, { passive: true });
        if (typeof desktopPointer.addEventListener === 'function') {
            desktopPointer.addEventListener('change', scheduleFloatingState);
        } else {
            desktopPointer.addListener(scheduleFloatingState);
        }

        syncFloatingState();
    }

    // --- Live Refresh ---
    function startLiveRefresh() {
        if (!liveInterval) liveInterval = setInterval(loadHero, WORLD_CUP_REFRESH_MS);
    }

    function stopLiveRefresh() {
        if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
    }

    function clearWorldCupCaches() {
        Object.keys(_apiCache).forEach(key => {
            if (key.includes('competition=WC') || key.startsWith('calendar_monthly?')) {
                delete _apiCache[key];
            }
        });
    }

    function clearApiCache() {
        Object.keys(_apiCache).forEach(key => delete _apiCache[key]);
    }

    function refreshWorldCupData() {
        clearWorldCupCaches();
        loadHero();
        loadPalmeirasHome(true);
        loadCalendar();
        if (currentTabId() === 'worldcup' || worldCupLoaded) {
            worldCupLoaded = false;
            loadWorldCup();
        }
        setLastUpdated();
    }

    function startWorldCupRefresh() {
        if (!_worldCupRefreshInterval) {
            _worldCupRefreshInterval = setInterval(refreshWorldCupData, WORLD_CUP_REFRESH_MS);
        }
    }

    function setRefreshBusy(isBusy) {
        const button = document.getElementById('refreshButton');
        if (!button) return;
        button.disabled = isBusy;
        button.classList.toggle('is-refreshing', isBusy);
        button.setAttribute('aria-busy', String(isBusy));
        button.setAttribute('aria-label', isBusy ? 'Atualizando dados' : 'Atualizar dados agora');
    }

    async function refreshAllData() {
        setRefreshBusy(true);
        clearApiCache();
        worldCupLoaded = false;
        predictionContext = null;
        predictionContextPromise = null;

        try {
            await loadHero();
            const results = await Promise.allSettled([
                loadPalmeirasHome(true),
                loadStandings(),
                loadNews(),
                loadCalendar(),
                loadCompetitionOverview(true),
                currentTabId() === 'estatisticas' ? renderPerformanceChart() : Promise.resolve(),
                currentTabId() === 'worldcup' ? loadWorldCup() : Promise.resolve(),
                window.PalmeirasFeatures ? window.PalmeirasFeatures.loadAll() : Promise.resolve(),
            ]);
            setLastUpdated();
            const hasRejected = results.some(result => result.status === 'rejected');
            const hasVisibleErrors = document.querySelectorAll('.error-state').length > 0;
            showToast(
                hasRejected || hasVisibleErrors ? 'Atualização concluída com avisos.' : 'Dados atualizados.',
                hasRejected || hasVisibleErrors ? 'warning' : 'success'
            );
        } catch (error) {
            showToast('Não foi possível atualizar tudo agora.', 'error');
        } finally {
            setRefreshBusy(false);
        }
    }

    // --- Hero ---
    async function loadBrazilHero() {
        const path = `matches?competition=WC&from_date=${WORLD_CUP_FROM}&to_date=${WORLD_CUP_TO}&limit=200`;
        const data = await api(path, WORLD_CUP_REFRESH_MS);
        const matches = ((data && data.matches) || []).filter(isBrazilMatch).sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
        if (!matches.length) return null;

        const now = Date.now();
        const live = matches.find(m => LIVE_STATUSES.has(m.status));
        const upcoming = matches.find(m => isNextCandidate(m, now));
        const nextMatches = matches
            .filter(m => isNextCandidate(m, now))
            .slice(0, 3);

        return {
            mode: 'brazil',
            match: live || upcoming || matches[matches.length - 1],
            nextMatches,
        };
    }

    async function loadPalmeirasHero() {
        const requestedId = new URL(window.location.href).searchParams.get('match');
        if (requestedId && /^[A-Za-z0-9_-]{1,80}$/.test(requestedId)) {
            const detail = await api(`match?id=${encodeURIComponent(requestedId)}`);
            if (detail && detail.match) {
                return { mode: 'palmeiras', match: detail.match, nextMatches: [], loaded: true };
            }
        }
        const data = await api(palmeirasQuery('matches?status=SCHEDULED,TIMED,IN_PLAY,PAUSED&limit=5'));
        const matches = (data && data.matches) || [];
        return {
            mode: 'palmeiras',
            match: matches[0] || null,
            nextMatches: [],
            loaded: Boolean(data),
        };
    }

    function setHeroUnavailable(badge, title, detail) {
        const heroCard = document.getElementById('hero-match');
        const compBadge = document.getElementById('hero-comp-badge');
        const teamsArea = document.getElementById('hero-teams-area');
        const metaArea = document.getElementById('hero-meta-area');
        const emptyState = document.getElementById('hero-empty-state');

        if (heroCard) heroCard.classList.remove('live');
        if (compBadge) compBadge.textContent = badge;
        if (teamsArea) teamsArea.style.display = 'none';
        if (metaArea) metaArea.style.display = 'none';
        if (emptyState) {
            const strong = emptyState.querySelector('strong');
            const span = emptyState.querySelector('span');
            if (strong) strong.textContent = title;
            if (span) span.textContent = detail;
            emptyState.hidden = false;
        }
        const countdown = document.getElementById('hero-countdown');
        if (countdown) countdown.style.display = 'none';
        if (_countdownInterval) {
            clearInterval(_countdownInterval);
            _countdownInterval = null;
        }
        if (window.PalmeirasFeatures) window.PalmeirasFeatures.setHeroMatch(null);
    }

    function setHeroMatchVisible() {
        const emptyState = document.getElementById('hero-empty-state');
        const teamsArea = document.getElementById('hero-teams-area');
        const metaArea = document.getElementById('hero-meta-area');
        if (emptyState) emptyState.hidden = true;
        if (teamsArea) teamsArea.style.display = '';
        if (metaArea) metaArea.style.display = '';
    }

    async function loadHero() {
        const palmeirasHero = await loadPalmeirasHero();
        const brazilHero = palmeirasHero && palmeirasHero.match ? null : await loadBrazilHero();
        const heroData = palmeirasHero && palmeirasHero.match
            ? palmeirasHero
            : (brazilHero && brazilHero.match ? brazilHero : palmeirasHero);
        if (!(heroData && heroData.match) && heroData && heroData.loaded === false) {
            setHeroUnavailable('Erro ao carregar', 'Dados temporariamente indisponíveis', 'Tente atualizar em instantes.');
            return;
        }

        const match = heroData && heroData.match;
        _heroMode = (heroData && heroData.mode) || 'palmeiras';

        if (!match) {
            setHeroUnavailable('Nenhum jogo agendado', 'Nenhum jogo agendado', 'Assim que o calendário trouxer o próximo jogo, ele aparece aqui.');
            return;
        }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = _heroMode === 'brazil' ? 'Copa do Mundo 2026 · Brasil' : CONFIG.formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = LIVE_STATUSES.has(match.status);
        const isPaused = match.status === 'PAUSED';
        const score = fullTimeScore(match);
        const ht = (match.score && match.score.halfTime) || {};
        const venue = CONFIG.getVenue(match);
        const stageLabel = formatStage(match.stage);

        const heroCard = document.getElementById('hero-match');
        if (heroCard) heroCard.classList.toggle('live', isLive);
        setHeroMatchVisible();

        // Competition badge
        const liveBadge = isLive
            ? `<span class="live-dot"></span> ${isPaused ? 'INTERVALO' : 'AO VIVO'} · `
            : '';
        document.getElementById('hero-comp-badge').innerHTML = liveBadge + escapeHtml(comp);

        // Home team
        const homeEl = document.getElementById('hero-home');
        const homeCrest = homeEl.querySelector('img');
        homeCrest.src = safeImageUrl(CONFIG.getCrest(home));
        homeCrest.alt = CONFIG.teamName(home);
        homeEl.querySelector('.hero-team-name').textContent = CONFIG.teamName(home);

        // Away team
        const awayEl = document.getElementById('hero-away');
        const awayCrest = awayEl.querySelector('img');
        awayCrest.src = safeImageUrl(CONFIG.getCrest(away));
        awayCrest.alt = CONFIG.teamName(away);
        awayEl.querySelector('.hero-team-name').textContent = CONFIG.teamName(away);

        // Score / VS
        const scoreArea = document.getElementById('hero-score-area');
        if (isLive) {
            const minute = estimateMinute(match.utcDate);
            const minuteLabel = isPaused ? 'Intervalo' : minute;
            scoreArea.innerHTML = `
                <div class="hero-score live-score">${scoreValue(score, 'home')} <span class="score-sep">×</span> ${scoreValue(score, 'away')}</div>
                ${minuteLabel ? `<div class="hero-minute">${minuteLabel}</div>` : ''}
                ${(ht.home != null && ht.away != null) ? `<div class="hero-ht">1º tempo: ${ht.home}–${ht.away}</div>` : ''}`;
        } else {
            scoreArea.innerHTML = '<div class="hero-vs">×</div>';
        }

        // Date
        document.getElementById('hero-date-area').innerHTML =
            isLive ? (isPaused ? 'INTERVALO' : 'AO VIVO') :
            `${formatDate(match.utcDate)} · ${formatTime(match.utcDate)} <span class="hero-day">${dayOfWeek}</span>`;

        // Detail pills
        const pillStadium = document.getElementById('pill-stadium');
        const pillBroadcast = document.getElementById('pill-broadcast');
        const pillRound = document.getElementById('pill-round');
        const pillStage = document.getElementById('pill-stage');

        pillStadium.textContent = 'Estádio ' + (venue || 'A definir');
        pillBroadcast.textContent = 'TV ' + (match.broadcast || 'A confirmar');
        pillRound.textContent = 'Rodada ' + (match.matchday || '-');

        if (stageLabel) {
            pillStage.textContent = stageLabel;
            pillStage.style.display = '';
        } else {
            pillStage.style.display = 'none';
        }

        if (isLive) {
            startLiveRefresh();
            const countdown = document.getElementById('hero-countdown');
            if (countdown) countdown.style.display = 'none';
            if (_countdownInterval) {
                clearInterval(_countdownInterval);
                _countdownInterval = null;
            }
        } else {
            stopLiveRefresh();
            startCountdown(match.utcDate);
        }

        if (window.PalmeirasFeatures) window.PalmeirasFeatures.setHeroMatch(match);
    }

    function startCountdown(utcDate) {
        if (_countdownInterval) clearInterval(_countdownInterval);
        const countdown = document.getElementById('hero-countdown');
        if (!countdown) return;
        const target = new Date(utcDate).getTime();

        function tick() {
            const diff = target - Date.now();
            if (diff <= 0) {
                countdown.style.display = 'none';
                if (_countdownInterval) {
                    clearInterval(_countdownInterval);
                    _countdownInterval = null;
                }
                loadHero();
                return;
            }

            countdown.style.display = '';
            const days = Math.floor(diff / 86_400_000);
            const hours = Math.floor((diff % 86_400_000) / 3_600_000);
            const minutes = Math.floor((diff % 3_600_000) / 60_000);
            const seconds = Math.floor((diff % 60_000) / 1_000);
            document.getElementById('cd-days').textContent = String(days);
            document.getElementById('cd-hours').textContent = String(hours).padStart(2, '0');
            document.getElementById('cd-mins').textContent = String(minutes).padStart(2, '0');
            document.getElementById('cd-secs').textContent = String(seconds).padStart(2, '0');
        }

        tick();
        _countdownInterval = setInterval(tick, 1_000);
    }

    // --- Palmeiras Home Board ---
    async function loadPalmeirasHome(force = false) {
        const upcomingPath = palmeirasQuery('matches?status=SCHEDULED,TIMED,IN_PLAY,PAUSED&limit=8');
        const finishedPath = palmeirasQuery('matches?status=FINISHED,PLAYING_TIME_FINISHED&limit=8');

        if (force) {
            delete _apiCache[upcomingPath];
            delete _apiCache[finishedPath];
        }

        if (!palmeirasHomeLoaded) {
            showSkeleton('palmeiras-next-matches');
            showSkeleton('palmeiras-latest-results');
            showSkeleton('palmeiras-matches');
        }

        const [upcomingData, finishedData] = await Promise.all([
            api(upcomingPath, WORLD_CUP_REFRESH_MS),
            api(finishedPath, WORLD_CUP_REFRESH_MS),
        ]);

        if (!upcomingData && !finishedData) {
            palmeirasHomeError = true;
            const homeSummary = document.getElementById('palmeiras-home-summary');
            const nextSummary = document.getElementById('palmeiras-next-summary');
            const resultsSummary = document.getElementById('palmeiras-results-summary');
            const boardSummary = document.getElementById('palmeiras-board-summary');
            if (homeSummary) homeSummary.textContent = 'Não foi possível carregar os jogos do Palmeiras.';
            if (nextSummary) nextSummary.textContent = 'Agenda indisponível no momento.';
            if (resultsSummary) resultsSummary.textContent = 'Resultados indisponíveis no momento.';
            if (boardSummary) boardSummary.textContent = 'Jogos indisponíveis no momento.';
            showError('palmeiras-next-matches', 'Erro ao carregar próximos jogos', 'loadPalmeirasHome');
            showError('palmeiras-latest-results', 'Erro ao carregar resultados', 'loadPalmeirasHome');
            showError('palmeiras-matches', 'Erro ao carregar jogos do Palmeiras', 'loadPalmeirasHome');
            return;
        }

        palmeirasUpcomingMatches = ((upcomingData && upcomingData.matches) || [])
            .filter(isPalmeirasMatch)
            .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
        palmeirasFinishedMatches = ((finishedData && finishedData.matches) || [])
            .filter(isPalmeirasMatch)
            .sort((a, b) => new Date(b.utcDate) - new Date(a.utcDate));
        palmeirasHomeLoaded = true;
        palmeirasHomeError = false;
        renderPalmeirasHome();
    }

    function palmeirasResult(match) {
        const sides = matchDisplaySides(match);
        if (!hasValue(sides.leftScore) || !hasValue(sides.rightScore)) {
            return { label: STATUS_LABEL[match.status] || match.status || 'Agendado', className: 'scheduled' };
        }
        if (LIVE_STATUSES.has(match.status)) {
            return { label: match.status === 'PAUSED' ? 'Intervalo' : 'Ao vivo', className: 'live' };
        }
        if (!FINISHED_STATUSES.has(match.status)) {
            return { label: STATUS_LABEL[match.status] || 'Agendado', className: 'scheduled' };
        }
        if (sides.leftScore > sides.rightScore) return { label: 'Vitória', className: 'win' };
        if (sides.leftScore < sides.rightScore) return { label: 'Derrota', className: 'loss' };
        return { label: 'Empate', className: 'draw' };
    }

    function palmeirasScoreText(match) {
        const sides = matchDisplaySides(match);
        const scoreReady = (FINISHED_STATUSES.has(match.status) || LIVE_STATUSES.has(match.status))
            && hasValue(sides.leftScore)
            && hasValue(sides.rightScore);
        return scoreReady ? `${sides.leftScore}–${sides.rightScore}` : '×';
    }

    function palmeirasMatchMeta(match) {
        const parts = [];
        const comp = CONFIG.formatComp(match.competition);
        const stage = formatStage(match.stage);
        if (comp) parts.push(comp);
        if (stage) parts.push(stage);
        else if (match.matchday) parts.push(`Rodada ${match.matchday}`);
        const venue = CONFIG.getVenue(match);
        if (venue) parts.push(venue);
        if (match.broadcast) parts.push(match.broadcast);
        return parts;
    }

    function renderPalmeirasHome() {
        const live = palmeirasUpcomingMatches.filter(m => LIVE_STATUSES.has(m.status)).length;
        const upcoming = palmeirasUpcomingMatches.filter(m => UPCOMING_STATUSES.has(m.status)).length;
        const finished = palmeirasFinishedMatches.length;
        const liveText = live ? ` · ${live} ao vivo` : '';

        const homeSummary = document.getElementById('palmeiras-home-summary');
        if (homeSummary) {
            homeSummary.textContent = upcoming || finished || live
                ? `${upcoming} próximos · ${finished} resultados carregados${liveText}`
                : 'Nenhum jogo do Palmeiras encontrado no banco ainda.';
        }

        const nextSummary = document.getElementById('palmeiras-next-summary');
        if (nextSummary) {
            nextSummary.textContent = palmeirasUpcomingMatches.length
                ? `${palmeirasUpcomingMatches.length} jogos na agenda`
                : 'Sem próximos jogos carregados.';
        }

        const resultsSummary = document.getElementById('palmeiras-results-summary');
        if (resultsSummary) {
            resultsSummary.textContent = palmeirasFinishedMatches.length
                ? `${palmeirasFinishedMatches.length} placares recentes`
                : 'Sem resultados carregados.';
        }

        renderPalmeirasSnapshot('palmeiras-next-matches', palmeirasUpcomingMatches.slice(0, 3), 'next');
        renderPalmeirasSnapshot('palmeiras-latest-results', palmeirasFinishedMatches.slice(0, 3), 'results');
        renderPalmeirasMatchBoard();
        ensurePredictionContextForMatches(palmeirasUpcomingMatches, renderPalmeirasHome);
    }

    function renderPalmeirasSnapshot(id, matches, mode) {
        const container = document.getElementById(id);
        if (!container) return;
        if (!matches.length) {
            container.innerHTML = `<div class="empty">${mode === 'next' ? 'Nenhum próximo jogo carregado' : 'Nenhum resultado carregado'}</div>`;
            return;
        }
        container.innerHTML = `<div class="palmeiras-quick-list">
            ${matches.map(match => renderPalmeirasQuickCard(match, mode)).join('')}
        </div>`;
    }

    function renderPalmeirasQuickCard(match, mode) {
        const sides = matchDisplaySides(match);
        const outcome = palmeirasResult(match);
        const date = formatShortDate(match.utcDate);
        const time = formatTime(match.utcDate);
        const opponent = CONFIG.teamName(sides.rightTeam);
        const meta = palmeirasMatchMeta(match).slice(0, 3);

        return `<details class="palmeiras-quick-match match-card ${escapeHtml(outcome.className)}"${matchDataAttr(match)}${matchOpenAttr(match)}>
            <summary class="palmeiras-quick-summary match-card-summary">
                <div class="palmeiras-quick-date">
                    <strong>${escapeHtml(date)}</strong>
                    <span>${escapeHtml(time)}</span>
                </div>
                <div class="palmeiras-quick-main">
                    <div class="palmeiras-quick-teams">
                        <span>
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.leftTeam)))}" alt="">
                            ${escapeHtml(CONFIG.teamName(sides.leftTeam))}
                        </span>
                        <strong>${escapeHtml(palmeirasScoreText(match))}</strong>
                        <span>
                            ${escapeHtml(opponent)}
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.rightTeam)))}" alt="">
                        </span>
                    </div>
                    <div class="palmeiras-match-meta">
                        <span class="palmeiras-result ${escapeHtml(outcome.className)}">${escapeHtml(mode === 'next' ? (LIVE_STATUSES.has(match.status) ? outcome.label : 'Próximo') : outcome.label)}</span>
                        ${meta.map(item => `<span>${escapeHtml(item)}</span>`).join('')}
                    </div>
                </div>
            </summary>
            ${renderMatchInsight(match)}
        </details>`;
    }

    function filteredPalmeirasSections() {
        if (palmeirasHomeFilter === 'next') {
            return [{ title: 'Próximos jogos', matches: palmeirasUpcomingMatches }];
        }
        if (palmeirasHomeFilter === 'results') {
            return [{ title: 'Últimos resultados', matches: palmeirasFinishedMatches }];
        }
        return [
            { title: 'Próximos jogos', matches: palmeirasUpcomingMatches },
            { title: 'Últimos resultados', matches: palmeirasFinishedMatches },
        ];
    }

    function renderPalmeirasMatchBoard() {
        const container = document.getElementById('palmeiras-matches');
        if (!container) return;

        document.querySelectorAll('.palmeiras-filter').forEach(btn => {
            const selected = btn.dataset.palmeirasFilter === palmeirasHomeFilter;
            btn.classList.toggle('active', selected);
            btn.setAttribute('aria-pressed', String(selected));
        });

        const sections = filteredPalmeirasSections().filter(section => section.matches.length);
        const count = sections.reduce((total, section) => total + section.matches.length, 0);
        const summary = document.getElementById('palmeiras-board-summary');
        if (palmeirasHomeError) {
            if (summary) summary.textContent = 'Jogos indisponíveis no momento.';
            showError('palmeiras-matches', 'Erro ao carregar jogos do Palmeiras', 'loadPalmeirasHome');
            return;
        }

        if (summary) {
            summary.textContent = count
                ? `${count} ${count === 1 ? 'jogo exibido' : 'jogos exibidos'}`
                : 'Nenhum jogo neste filtro.';
        }

        if (!sections.length) {
            container.innerHTML = '<div class="empty">Nenhum jogo neste filtro</div>';
            return;
        }

        container.innerHTML = sections.map(section => `<section class="palmeiras-game-group" aria-label="${escapeHtml(section.title)}">
            <div class="palmeiras-game-heading">
                <span>${escapeHtml(section.title)}</span>
                <strong>${section.matches.length} ${section.matches.length === 1 ? 'jogo' : 'jogos'}</strong>
            </div>
            <div class="palmeiras-match-list">
                ${section.matches.map(renderPalmeirasMatchRow).join('')}
            </div>
        </section>`).join('');
    }

    function renderPalmeirasMatchRow(match) {
        const sides = matchDisplaySides(match);
        const outcome = palmeirasResult(match);
        const date = formatShortDate(match.utcDate);
        const time = formatTime(match.utcDate);
        const liveClass = LIVE_STATUSES.has(match.status) ? ' live' : '';
        const meta = palmeirasMatchMeta(match);

        return `<details class="palmeiras-match match-card${liveClass}"${matchDataAttr(match)}${matchOpenAttr(match)}>
            <summary class="palmeiras-match-summary match-card-summary">
                <div class="palmeiras-match-date">
                    <strong>${escapeHtml(date)}</strong>
                    <span>${escapeHtml(time)}</span>
                </div>
                <div class="palmeiras-match-body">
                    <div class="palmeiras-teams">
                        <span class="palmeiras-team">
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.leftTeam)))}" alt="">
                            <span>${escapeHtml(CONFIG.teamName(sides.leftTeam))}</span>
                        </span>
                        <strong class="palmeiras-score">${escapeHtml(palmeirasScoreText(match))}</strong>
                        <span class="palmeiras-team away">
                            <span>${escapeHtml(CONFIG.teamName(sides.rightTeam))}</span>
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.rightTeam)))}" alt="">
                        </span>
                    </div>
                    <div class="palmeiras-match-meta">
                        <span class="palmeiras-result ${escapeHtml(outcome.className)}">${escapeHtml(outcome.label)}</span>
                        ${meta.map(item => `<span>${escapeHtml(item)}</span>`).join('')}
                    </div>
                </div>
            </summary>
            ${renderMatchInsight(match)}
        </details>`;
    }

    function setPalmeirasHomeFilter(filter) {
        palmeirasHomeFilter = VALID_PALMEIRAS_FILTERS.has(filter) ? filter : 'all';
        renderPalmeirasMatchBoard();
    }

    // --- Palmeiras Competition Hub / Standings ---
    function standingsYearWindow(year) {
        return {
            from: `${year}-01-01`,
            to: `${year}-12-31`,
        };
    }

    function currentStandingsYear() {
        return currentCompetitionYear();
    }

    function updateStandingsSummary(message) {
        const summary = document.getElementById('standings-summary');
        if (summary) summary.textContent = message;
    }

    function syncStandingsControls() {
        document.querySelectorAll('.standings-filter').forEach(btn => {
            const selected = btn.dataset.standingsComp === standingsCompetition;
            btn.classList.toggle('active', selected);
            btn.setAttribute('aria-pressed', String(selected));
        });

        const title = document.getElementById('standings-title');
        if (title) {
            title.textContent = standingsCompetition === 'all'
                ? 'Tabelas do Palmeiras'
                : `Tabelas — ${CONFIG.formatComp({ code: standingsCompetition })}`;
        }
    }

    function renderStandingsFilters(competitions = []) {
        const group = document.getElementById('standings-filter-group');
        if (!group) return;

        const known = new Map();
        competitions.forEach(summary => {
            if (summary && summary.code) known.set(summary.code, CONFIG.formatComp({ code: summary.code, name: summary.name }));
        });
        if (!known.size) {
            ['BSA', 'CLI', 'COPA', 'CPA'].forEach(code => known.set(code, CONFIG.formatComp({ code })));
        }

        const buttons = [{ code: 'all', label: 'Todas' }].concat(
            [...known.entries()].map(([code, label]) => ({ code, label }))
        );

        group.innerHTML = buttons.map(item => {
            const selected = item.code === standingsCompetition;
            return `<button type="button" class="standings-filter ${selected ? 'active' : ''}" data-standings-comp="${escapeHtml(item.code)}" aria-pressed="${selected}">
                ${escapeHtml(item.label)}
            </button>`;
        }).join('');
    }

    function matchYearPath(comp = null) {
        const year = currentStandingsYear();
        const { from, to } = standingsYearWindow(year);
        const compPart = comp && comp !== 'all' ? `&competition=${encodeURIComponent(comp)}` : '';
        return palmeirasQuery(`matches?from_date=${from}&to_date=${to}&limit=250${compPart}`);
    }

    function aggregateCompetitionRecords(competitions) {
        return competitions.reduce((record, summary) => {
            const item = summary.record || {};
            record.played += item.played || 0;
            record.wins += item.wins || 0;
            record.draws += item.draws || 0;
            record.losses += item.losses || 0;
            record.goalsFor += item.goalsFor || 0;
            record.goalsAgainst += item.goalsAgainst || 0;
            record.points += item.points || 0;
            record.goalDifference = record.goalsFor - record.goalsAgainst;
            return record;
        }, { played: 0, wins: 0, draws: 0, losses: 0, goalsFor: 0, goalsAgainst: 0, goalDifference: 0, points: 0 });
    }

    function renderStandingsSummaryCards(record, totalMatches) {
        const played = record.played || 0;
        const points = record.points || 0;
        const pct = played ? Math.round(points / (played * 3) * 100) : 0;
        const gd = record.goalDifference || ((record.goalsFor || 0) - (record.goalsAgainst || 0));
        return `<div class="standings-campaign-stats stats-grid">
            <div class="stat-box"><div class="stat-value">${totalMatches || played}</div><div class="stat-label">Jogos</div></div>
            <div class="stat-box"><div class="stat-value" style="color:var(--win)">${record.wins || 0}</div><div class="stat-label">Vitórias</div></div>
            <div class="stat-box"><div class="stat-value" style="color:var(--draw)">${record.draws || 0}</div><div class="stat-label">Empates</div></div>
            <div class="stat-box"><div class="stat-value" style="color:var(--loss)">${record.losses || 0}</div><div class="stat-label">Derrotas</div></div>
            <div class="stat-box"><div class="stat-value">${record.goalsFor || 0}</div><div class="stat-label">Gols Pró</div></div>
            <div class="stat-box"><div class="stat-value">${record.goalsAgainst || 0}</div><div class="stat-label">Gols Contra</div></div>
            <div class="stat-box"><div class="stat-value" style="color:${gd >= 0 ? 'var(--win)' : 'var(--loss)'}">${gd >= 0 ? '+' : ''}${gd}</div><div class="stat-label">Saldo</div></div>
            <div class="stat-box"><div class="stat-value">${points}</div><div class="stat-label">Pontos</div></div>
            <div class="stat-box"><div class="stat-value">${pct}%</div><div class="stat-label">Aproveit.</div></div>
        </div>`;
    }

    function renderStandingsMatchGroups(matches) {
        if (!matches.length) return '<div class="empty">Nenhum jogo do Palmeiras encontrado neste recorte.</div>';
        const groups = new Map();
        matches.forEach(match => {
            const code = (match.competition && match.competition.code) || 'OTHER';
            if (!groups.has(code)) groups.set(code, []);
            groups.get(code).push(match);
        });

        return [...groups.entries()].map(([code, groupMatches]) => `<section class="standings-match-group" aria-label="${escapeHtml(CONFIG.formatComp({ code }))}">
            <div class="palmeiras-game-heading">
                <span>${escapeHtml(CONFIG.formatComp({ code }))}</span>
                <strong>${groupMatches.length} ${groupMatches.length === 1 ? 'jogo' : 'jogos'}</strong>
            </div>
            <div class="palmeiras-match-list">
                ${groupMatches.map(renderPalmeirasMatchRow).join('')}
            </div>
        </section>`).join('');
    }

    function standingsZone(position, rowCount, competitionCode) {
        const code = String(competitionCode || '').toUpperCase();
        if (code === 'BSA' && rowCount >= 18) {
            if (position <= 6) return 'libertadores';
            if (position <= 12) return 'sudamericana';
            if (position > rowCount - 4) return 'relegation';
        }
        if (code === 'BFA1' && rowCount >= 12) {
            if (position <= 8) return 'knockout';
            if (position > rowCount - 4) return 'relegation';
        }
        return '';
    }

    function renderStandingsZoneLegend(competitionCode, rowCount) {
        const code = String(competitionCode || '').toUpperCase();
        if (code === 'BSA' && rowCount >= 18) {
            return `<div class="standings-zone-legend" aria-label="Faixas da classificação">
                <span class="standings-zone-title">Faixas</span>
                <span><i class="standings-zone-dot libertadores" aria-hidden="true"></i>Libertadores</span>
                <span><i class="standings-zone-dot sudamericana" aria-hidden="true"></i>Sul-Americana</span>
                <span><i class="standings-zone-dot relegation" aria-hidden="true"></i>Rebaixamento</span>
            </div>`;
        }
        if (code === 'BFA1' && rowCount >= 12) {
            return `<div class="standings-zone-legend" aria-label="Faixas da classificação">
                <span class="standings-zone-title">Faixas</span>
                <span><i class="standings-zone-dot knockout" aria-hidden="true"></i>Mata-mata</span>
                <span><i class="standings-zone-dot relegation" aria-hidden="true"></i>Rebaixamento</span>
            </div>`;
        }
        return '';
    }

    const LOCAL_STANDINGS_CREST_IDS = new Set([
        1765, 1766, 1767, 1768, 1769, 1770, 1771, 1772, 1776, 1777,
        1779, 1780, 1782, 1783, 4241, 4286, 4287, 4364, 4439, 5347,
        6684, 6685, 9373,
    ]);

    function standingsCrestUrl(team) {
        const teamId = Number(team && team.teamId);
        if (LOCAL_STANDINGS_CREST_IDS.has(teamId)) {
            return `/static/crests/${teamId}.png`;
        }
        return safeImageUrl(CONFIG.getCrest({
            id: team && team.teamId,
            crest: team && team.crest,
        }));
    }

    function renderOfficialStandings(rows, team, competitionCode) {
        const gd = team.goalDifference;
        const pct = team.playedGames > 0
            ? Math.round(team.points / (team.playedGames * 3) * 100)
            : 0;
        const teamCrest = standingsCrestUrl(team);
        const tableHtml = rows.map(s => {
            const isPalmeiras = s.teamId === TEAM_ID;
            const zone = standingsZone(s.position, rows.length, competitionCode);
            const crest = standingsCrestUrl(s);
            const teamName = s.teamShort || s.teamName;
            const fullName = s.teamName || teamName;
            return `<tr class="${isPalmeiras ? 'palmeiras ' : ''}${zone ? `zone-${zone}` : ''}"${isPalmeiras ? ' aria-current="true"' : ''}>
                <td class="standing-position-cell">${s.position}</td>
                <th class="standing-club-cell" scope="row">
                    <img src="${escapeHtml(crest)}" alt="" width="28" height="28" decoding="async">
                    <span title="${escapeHtml(fullName)}">${escapeHtml(teamName)}</span>
                </th>
                <td class="standing-points-cell">${s.points}</td>
                <td>${s.playedGames}</td>
                <td>${s.won}</td>
                <td>${s.draw}</td>
                <td>${s.lost}</td>
                <td>${s.goalsFor}</td>
                <td>${s.goalsAgainst}</td>
                <td class="${s.goalDifference > 0 ? 'positive' : s.goalDifference < 0 ? 'negative' : ''}">${s.goalDifference > 0 ? '+' : ''}${s.goalDifference}</td>
            </tr>`;
        }).join('');

        return `<section class="standings-section" aria-label="Classificação oficial">
            <div class="standings-section-head">
                <div>
                    <h3>Classificação</h3>
                    <p>Campanha completa e critérios principais da tabela.</p>
                </div>
                <span>${rows.length} equipes</span>
            </div>
            <div class="standings-team-snapshot" aria-label="Resumo do Palmeiras na classificação">
                <div class="standings-team-identity">
                    <img src="${escapeHtml(teamCrest)}" alt="" width="42" height="42" decoding="async">
                    <div>
                        <span>Palmeiras</span>
                        <strong>${team.position}º lugar</strong>
                    </div>
                </div>
                <dl class="standings-key-stats">
                    <div><dt>Pontos</dt><dd>${team.points}</dd></div>
                    <div><dt>Jogos</dt><dd>${team.playedGames}</dd></div>
                    <div><dt>Aproveit.</dt><dd>${pct}%</dd></div>
                    <div><dt>Saldo</dt><dd class="${gd >= 0 ? 'positive' : 'negative'}">${gd >= 0 ? '+' : ''}${gd}</dd></div>
                </dl>
            </div>
            ${renderStandingsZoneLegend(competitionCode, rows.length)}
            <p class="standings-scroll-hint" id="standings-scroll-help">Deslize para ver todos os números.</p>
            <div class="standings-table-shell" tabindex="0" role="region" aria-label="Classificação completa" aria-describedby="standings-scroll-help">
                <table class="standings-data-table">
                    <caption class="sr-only">Classificação completa com pontos, jogos, vitórias, empates, derrotas, gols e saldo.</caption>
                    <thead>
                        <tr>
                            <th class="standing-position-cell" scope="col"><abbr title="Posição">Pos.</abbr></th>
                            <th class="standing-club-cell" scope="col">Clube</th>
                            <th class="standing-points-cell" scope="col"><abbr title="Pontos">Pts</abbr></th>
                            <th scope="col"><abbr title="Jogos">J</abbr></th>
                            <th scope="col"><abbr title="Vitórias">V</abbr></th>
                            <th scope="col"><abbr title="Empates">E</abbr></th>
                            <th scope="col"><abbr title="Derrotas">D</abbr></th>
                            <th scope="col"><abbr title="Gols pró">GP</abbr></th>
                            <th scope="col"><abbr title="Gols contra">GC</abbr></th>
                            <th scope="col"><abbr title="Saldo de gols">SG</abbr></th>
                        </tr>
                    </thead>
                    <tbody>${tableHtml}</tbody>
                </table>
            </div>
        </section>`;
    }

    function renderCompetitionCampaign(summary, matches, rows = []) {
        const comp = summary ? summary.code : standingsCompetition;
        const compName = CONFIG.formatComp({ code: comp, name: summary && summary.name });
        const record = (summary && summary.record) || aggregateCompetitionRecords([]);
        const officialTeam = rows.find(s => s.teamId === TEAM_ID);
        const officialHtml = officialTeam
            ? renderOfficialStandings(rows, officialTeam, comp)
            : `<div class="standings-data-note">Tabela oficial de ${escapeHtml(compName)} ainda não está carregada. Abaixo estão campanha e jogos do Palmeiras disponíveis no banco.</div>`;
        const status = summary ? competitionStatus(summary) : { label: 'Sem agenda', className: 'idle' };
        const stage = summary && formatStage(summary.currentStage);

        return `<div class="standings-campaign">
            <div class="standings-section-head">
                <div>
                    <h3>${escapeHtml(compName)}</h3>
                    <p>${summary ? `${summary.totalMatches || matches.length} jogos no ano${stage ? ` · ${stage}` : ''}` : `${matches.length} jogos no ano`}</p>
                </div>
                <span class="competition-status ${escapeHtml(status.className)}">${escapeHtml(status.label)}</span>
            </div>
            <section class="standings-section" aria-label="Campanha do Palmeiras">
                <div class="standings-section-head">
                    <h3>Campanha</h3>
                    <span>${record.played} ${record.played === 1 ? 'jogo' : 'jogos'}</span>
                </div>
                ${renderStandingsSummaryCards(record, summary ? summary.totalMatches : matches.length)}
            </section>
            <div class="standings-focus-grid">
                ${renderCompetitionMatch('Próximo', summary && summary.nextMatch)}
                ${renderCompetitionMatch('Último', summary && summary.lastMatch)}
            </div>
            ${officialHtml}
            <section class="standings-section" aria-label="Jogos do Palmeiras">
                <div class="standings-section-head">
                    <h3>Jogos do Palmeiras</h3>
                    <span>${matches.length} ${matches.length === 1 ? 'jogo' : 'jogos'}</span>
                </div>
                ${renderStandingsMatchGroups(matches)}
            </section>
        </div>`;
    }

    function renderAllPalmeirasData(competitions, matches) {
        if (!competitions.length && !matches.length) {
            showEmpty('standings', 'Nenhuma tabela ou campanha do Palmeiras encontrada para o ano selecionado.');
            return;
        }

        const record = aggregateCompetitionRecords(competitions);
        const totalMatches = competitions.reduce((sum, item) => sum + (item.totalMatches || 0), 0) || matches.length;
        updateStandingsSummary(`${competitions.length} competições · ${totalMatches} jogos do Palmeiras em ${currentStandingsYear()}.`);
        document.getElementById('standings').innerHTML = `
            <section class="standings-section" aria-label="Resumo geral do Palmeiras">
                <div class="standings-section-head">
                    <div>
                        <h3>Resumo geral</h3>
                        <p>Campanhas, tabelas e jogos disponíveis no banco para ${currentStandingsYear()}.</p>
                    </div>
                    <span>${competitions.length} ${competitions.length === 1 ? 'competição' : 'competições'}</span>
                </div>
                ${renderStandingsSummaryCards(record, totalMatches)}
            </section>
            <section class="standings-section" aria-label="Competições do Palmeiras">
                <div class="standings-section-head">
                    <h3>Competições</h3>
                    <span>${competitions.length}</span>
                </div>
                <div class="competition-grid">${competitions.map(summary => renderCompetitionCard(summary, { actionMode: 'standings' })).join('')}</div>
            </section>
            <section class="standings-section" aria-label="Todos os jogos do Palmeiras">
                <div class="standings-section-head">
                    <h3>Todos os jogos</h3>
                    <span>${matches.length} ${matches.length === 1 ? 'jogo' : 'jogos'}</span>
                </div>
                ${renderStandingsMatchGroups(matches)}
            </section>`;
    }

    async function loadCompetitionStandingsView(competitions) {
        const summary = competitions.find(item => item.code === standingsCompetition);
        const [standingsData, matchesData] = await Promise.all([
            api(`standings?competition=${encodeURIComponent(standingsCompetition)}`),
            api(matchYearPath(standingsCompetition), WORLD_CUP_REFRESH_MS),
        ]);
        const rows = (standingsData && standingsData.standings) || [];
        const matches = ((matchesData && matchesData.matches) || [])
            .filter(isPalmeirasMatch)
            .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));

        const compName = CONFIG.formatComp({ code: standingsCompetition, name: summary && summary.name });
        if (!summary && !rows.length && !matches.length) {
            updateStandingsSummary(`${compName} ainda não tem tabelas ou campanhas do Palmeiras carregadas no banco.`);
            showEmpty('standings', `Nenhuma tabela ou campanha do Palmeiras encontrada para ${compName}.`);
            return;
        }

        const tableText = rows.length ? ` · tabela oficial com ${rows.length} equipes` : ' · tabela oficial indisponível';
        updateStandingsSummary(`${compName}: ${(summary && summary.totalMatches) || matches.length} jogos do Palmeiras${tableText}.`);
        document.getElementById('standings').innerHTML = renderCompetitionCampaign(summary, matches, rows);
        ensurePredictionContextForMatches(matches, () => {
            document.getElementById('standings').innerHTML = renderCompetitionCampaign(summary, matches, rows);
        });
    }

    async function loadStandings() {
        syncStandingsControls();
        showSkeleton('standings');
        const year = currentStandingsYear();
        updateStandingsSummary(`Carregando tabelas e campanhas do Palmeiras em ${year}...`);

        const competitionsData = await api(palmeirasQuery(`competitions?year=${year}`));
        if (!competitionsData) { showError('standings', 'Erro ao carregar tabelas do Palmeiras', 'loadStandings'); return; }
        const competitions = competitionsData.competitions || [];
        renderStandingsFilters(competitions);
        syncStandingsControls();

        if (standingsCompetition !== 'all' && !competitions.some(item => item.code === standingsCompetition)) {
            standingsCompetition = 'all';
            renderStandingsFilters(competitions);
            syncStandingsControls();
        }

        if (standingsCompetition === 'all') {
            const matchesData = await api(matchYearPath('all'), WORLD_CUP_REFRESH_MS);
            const matches = ((matchesData && matchesData.matches) || [])
                .filter(isPalmeirasMatch)
                .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
            renderAllPalmeirasData(competitions, matches);
            ensurePredictionContextForMatches(matches, () => renderAllPalmeirasData(competitions, matches));
            return;
        }

        await loadCompetitionStandingsView(competitions);
    }

    function setStandingsCompetition(comp) {
        if (!(comp === 'all' || isSafeCompFilter(comp))) return;
        if (standingsCompetition === comp) return;
        standingsCompetition = comp;
        loadStandings();
    }

    // --- Competitions Overview ---
    function currentCompetitionYear() {
        if (_calYear) return _calYear;
        return parseInt(getTodayStr().split('-')[0], 10);
    }

    function competitionStatus(summary) {
        if (summary.live) return { label: 'Ao vivo', className: 'live' };
        if (summary.nextMatch) return { label: 'Em disputa', className: 'active' };
        if (summary.finished && summary.finished === summary.totalMatches) return { label: 'Encerrada', className: 'finished' };
        return { label: 'Sem agenda', className: 'idle' };
    }

    function matchDateKey(match) {
        if (!(match && match.utcDate)) return '';
        return new Date(match.utcDate).toLocaleDateString('en-CA', { timeZone: BR_TZ });
    }

    function matchLine(match) {
        if (!(match && match.homeTeam && match.awayTeam)) return 'Jogo a definir';
        return `${CONFIG.teamName(match.homeTeam)} x ${CONFIG.teamName(match.awayTeam)}`;
    }

    function matchScoreText(match) {
        if (!match) return '';
        const scoreReady = (FINISHED_STATUSES.has(match.status) || LIVE_STATUSES.has(match.status))
            && match.homeScore != null
            && match.awayScore != null;
        return scoreReady ? `${match.homeScore}–${match.awayScore}` : '';
    }

    function renderCompetitionMatch(label, match) {
        const cardLabel = `${label} jogo`;
        if (!match) {
            return `<div class="competition-match empty-line" aria-label="${escapeHtml(cardLabel)}: sem jogo carregado">
                <span>${escapeHtml(cardLabel)}</span>
                <strong>Sem jogo carregado</strong>
                <small>Aguardando atualização da agenda</small>
            </div>`;
        }
        const date = new Date(match.utcDate).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', timeZone: BR_TZ });
        const time = formatTime(match.utcDate);
        const score = matchScoreText(match);
        const status = STATUS_LABEL[match.status] || match.status || 'Agendado';
        return `<details class="competition-match match-card"${matchDataAttr(match)}${matchOpenAttr(match)}>
            <summary class="competition-match-summary match-card-summary">
                <span>${escapeHtml(cardLabel)} · ${escapeHtml(date)} ${escapeHtml(time)}</span>
                <strong>${escapeHtml(matchLine(match))}${score ? ` <em>${escapeHtml(score)}</em>` : ''}</strong>
                <small>${escapeHtml(status)}</small>
            </summary>
            ${renderMatchInsight(match)}
        </details>`;
    }

    function renderCompetitionCard(summary, options = {}) {
        const record = summary.record || {};
        const played = record.played || 0;
        const points = record.points || 0;
        const performance = played ? Math.round(points / (played * 3) * 100) : 0;
        const status = competitionStatus(summary);
        const compClass = getCompBadgeClass(summary.code);
        const stageLabel = formatStage(summary.currentStage);
        const standing = summary.standing
            ? `<span>${summary.standing.position}º · ${summary.standing.points} pts na tabela</span>`
            : '';
        const focusMatch = summary.nextMatch || summary.lastMatch;
        const focusDate = matchDateKey(focusMatch);
        const actionMode = options.actionMode || 'calendar';
        const actionAttrs = actionMode === 'standings'
            ? `data-standings-comp="${escapeHtml(summary.code)}"`
            : `data-comp-filter="${escapeHtml(summary.code)}" data-comp-date="${escapeHtml(focusDate)}"`;
        const actionLabel = actionMode === 'standings' ? 'Ver detalhes' : 'Ver no calendário';

        return `<article class="competition-card ${compClass}">
            <div class="competition-card-top">
                <div>
                    <span class="competition-code">${escapeHtml(summary.code)}</span>
                    <h3>${escapeHtml(CONFIG.formatComp({ code: summary.code, name: summary.name }))}</h3>
                </div>
                <span class="competition-status ${status.className}">${escapeHtml(status.label)}</span>
            </div>

            <div class="competition-meta">
                <span>${summary.totalMatches || 0} jogos no ano</span>
                ${stageLabel ? `<span>${escapeHtml(stageLabel)}</span>` : ''}
                ${standing}
            </div>

            <div class="competition-record" aria-label="Resumo de desempenho">
                <div><strong>${played}</strong><span>J</span></div>
                <div><strong>${record.wins || 0}</strong><span>V</span></div>
                <div><strong>${record.draws || 0}</strong><span>E</span></div>
                <div><strong>${record.losses || 0}</strong><span>D</span></div>
                <div><strong>${performance}%</strong><span>Apr.</span></div>
            </div>

            ${summary.nextMatch
                ? renderCompetitionMatch('Próximo', summary.nextMatch)
                : renderCompetitionMatch('Último', summary.lastMatch)}

            <button type="button" class="competition-card-action" ${actionAttrs}>
                ${actionLabel}
            </button>
        </article>`;
    }

    async function loadCompetitionOverview(force = false) {
        const container = document.getElementById('competitions-overview');
        const summaryEl = document.getElementById('competitions-summary');
        if (!container) return;

        const year = currentCompetitionYear();
        const path = palmeirasQuery(`competitions?year=${year}`);
        if (force) delete _apiCache[path];

        showSkeleton('competitions-overview');
        if (summaryEl) summaryEl.textContent = `Carregando disputas de ${year}...`;

        const data = await api(path);
        if (!data) {
            if (summaryEl) summaryEl.textContent = `Não foi possível consolidar as disputas de ${year}.`;
            showError('competitions-overview', 'Erro ao carregar disputas', 'loadCompetitionOverview');
            return;
        }

        const competitions = data.competitions || [];
        if (summaryEl) {
            const live = competitions.reduce((sum, item) => sum + (item.live || 0), 0);
            const upcoming = competitions.reduce((sum, item) => sum + (item.upcoming || 0), 0);
            const finished = competitions.reduce((sum, item) => sum + (item.finished || 0), 0);
            const liveText = live ? ` · ${live} ao vivo` : '';
            summaryEl.textContent = competitions.length
                ? `${competitions.length} disputas em ${year} · ${finished} resultados · ${upcoming} próximos${liveText}`
                : `Nenhuma disputa do Palmeiras encontrada em ${year}.`;
        }

        if (!competitions.length) {
            container.innerHTML = '<div class="empty">Nenhuma competição do Palmeiras encontrada no banco para este ano.</div>';
            return;
        }

        container.innerHTML = `<div class="competition-grid">${competitions.map(renderCompetitionCard).join('')}</div>`;
        ensurePredictionContextForMatches(
            competitions.flatMap(item => [item.nextMatch, item.lastMatch].filter(Boolean)),
            () => {
                container.innerHTML = `<div class="competition-grid">${competitions.map(renderCompetitionCard).join('')}</div>`;
            }
        );
    }

    function focusCompetitionCalendar(comp, dateKey) {
        if (!isSafeCompFilter(comp)) return;
        if (dateKey && isValidDateKey(dateKey)) {
            const parts = dateKey.split('-');
            _calYear = parseInt(parts[0], 10);
            _calMonth = parseInt(parts[1], 10);
            _calSelectedDay = dateKey;
            syncYearSelect();
        }

        window.filterSharedComp(comp);
        updateUrlState({ year: _calYear, month: _calMonth, comp, day: _calSelectedDay });
        const calendarHub = document.getElementById('calendar-hub');
        if (calendarHub) calendarHub.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // --- Chart.js Lazy Loader ---
    function loadChartJs() {
        return new Promise((resolve, reject) => {
            if (window.Chart) { chartJsLoaded = true; resolve(); return; }
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
            script.async = true;
            script.crossOrigin = 'anonymous';
            script.onload = () => { chartJsLoaded = true; resolve(); };
            script.onerror = () => reject(new Error('Chart.js CDN failed'));
            document.head.appendChild(script);
        });
    }

    // --- Performance Chart + Stats ---
    function updateStatsSummary(message) {
        const summary = document.getElementById('stats-summary');
        if (summary) summary.textContent = message;
    }

    async function renderPerformanceChart() {
        const container = document.getElementById('team-stats');
        if (!container) return;

        // Show loading state while Chart.js loads
        if (!chartJsLoaded) {
            updateStatsSummary('Carregando estatísticas do Palmeiras...');
            container.innerHTML = '<div class="empty" style="padding:2rem">Carregando estatísticas...</div>';
            try { await loadChartJs(); } catch (error) {
                updateStatsSummary('Não foi possível carregar os gráficos de estatísticas.');
                container.innerHTML = '<div class="empty" style="padding:2rem">Erro ao carregar estatísticas</div>';
                return;
            }
        }

        const data = await api(palmeirasQuery('matches?status=FINISHED&limit=38'));
        if (!data || !data.matches || !data.matches.length) {
            updateStatsSummary('Ainda não há jogos finalizados suficientes para calcular estatísticas.');
            container.innerHTML = '<div class="empty" style="padding:2rem">Sem dados suficientes</div>';
            return;
        }

        const allMatches = data.matches;
        const bsaMatches = allMatches
            .filter(m => m.competition && m.competition.code === 'BSA')
            .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));

        // Comprehensive stats across ALL competitions
        let wins = 0, draws = 0, losses = 0, goalsFor = 0, goalsAgainst = 0;
        let homeWins = 0, homeDraws = 0, homeLosses = 0, homeGF = 0, homeGA = 0;
        let awayWins = 0, awayDraws = 0, awayLosses = 0, awayGF = 0, awayGA = 0;
        const form = [];

        allMatches.forEach(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const score = fullTimeScore(m);
            const our = isHome ? scoreValue(score, 'home') : scoreValue(score, 'away');
            const opp = isHome ? scoreValue(score, 'away') : scoreValue(score, 'home');

            goalsFor += our;
            goalsAgainst += opp;

            let result;
            if (our > opp) { wins++; result = 'V'; }
            else if (our < opp) { losses++; result = 'D'; }
            else { draws++; result = 'E'; }

            if (isHome) {
                homeGF += our; homeGA += opp;
                if (our > opp) homeWins++; else if (our < opp) homeLosses++; else homeDraws++;
            } else {
                awayGF += our; awayGA += opp;
                if (our > opp) awayWins++; else if (our < opp) awayLosses++; else awayDraws++;
            }

            form.push({
                result,
                opp: isHome ? CONFIG.teamName(m.awayTeam) : CONFIG.teamName(m.homeTeam),
                score: `${our}-${opp}`,
                home: isHome,
            });
        });

        const total = wins + draws + losses;
        const avgGF = total ? (goalsFor / total).toFixed(1) : '0';
        const avgGA = total ? (goalsAgainst / total).toFixed(1) : '0';
        const points = wins * 3 + draws;
        const pct = total ? Math.round(points / (total * 3) * 100) : 0;
        const homeTotal = homeWins + homeDraws + homeLosses;
        const awayTotal = awayWins + awayDraws + awayLosses;
        const homePts = homeWins * 3 + homeDraws;
        const awayPts = awayWins * 3 + awayDraws;
        const lastFive = form.slice(-5).reverse();
        updateStatsSummary(`${total} jogos finalizados · ${wins} vitórias · ${goalsFor} gols marcados · ${pct}% aproveitamento.`);

        // Stats summary
        let html = `
        <div class="stats-summary">
            <div class="stats-grid">
                <div class="stat-box"><div class="stat-value">${total}</div><div class="stat-label">Jogos</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--win)">${wins}</div><div class="stat-label">Vitórias</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--draw)">${draws}</div><div class="stat-label">Empates</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--loss)">${losses}</div><div class="stat-label">Derrotas</div></div>
                <div class="stat-box"><div class="stat-value">${goalsFor}</div><div class="stat-label">Gols Pró</div></div>
                <div class="stat-box"><div class="stat-value">${goalsAgainst}</div><div class="stat-label">Gols Contra</div></div>
            </div>
        </div>
        <div class="stats-row">
            <div class="stats-col">
                <div class="stats-col-title">Casa (${homeTotal}J)</div>
                <div class="mini-stats">
                    <span style="color:var(--win)">${homeWins}V</span>
                    <span style="color:var(--draw)">${homeDraws}E</span>
                    <span style="color:var(--loss)">${homeLosses}D</span>
                    <span>${homeGF}/${homeGA}</span>
                    <span style="font-weight:700">${homePts}pts</span>
                </div>
            </div>
            <div class="stats-col">
                <div class="stats-col-title">Fora (${awayTotal}J)</div>
                <div class="mini-stats">
                    <span style="color:var(--win)">${awayWins}V</span>
                    <span style="color:var(--draw)">${awayDraws}E</span>
                    <span style="color:var(--loss)">${awayLosses}D</span>
                    <span>${awayGF}/${awayGA}</span>
                    <span style="font-weight:700">${awayPts}pts</span>
                </div>
            </div>
        </div>
        <div class="stats-row">
            <div class="stats-col">
                <div class="stats-col-title">Médias</div>
                <div class="mini-stats">
                    <span>${avgGF} gpj</span>
                    <span>${avgGA} gcj</span>
                    <span>${pct}% apr.</span>
                </div>
            </div>
            <div class="stats-col">
                <div class="stats-col-title">Desempenho recente</div>
                <div class="form-guide">
                    ${lastFive.map(f => `<span class="form-badge ${f.result === 'V' ? 'win' : f.result === 'D' ? 'loss' : 'draw'}" title="${f.home ? 'Casa' : 'Fora'} vs ${escapeHtml(f.opp)} (${f.score})">${f.result}</span>`).join('')}
                </div>
            </div>
        </div>`;

        // Chart section (Brasileirão only)
        if (bsaMatches.length >= 3) {
            const labels = [];
            const pontos = [];
            const acumulada = [];
            let pts = 0;

            bsaMatches.forEach((m, i) => {
                const isHome = m.homeTeam.id === TEAM_ID;
                const score = fullTimeScore(m);
                const our = isHome ? scoreValue(score, 'home') : scoreValue(score, 'away');
                const opp = isHome ? scoreValue(score, 'away') : scoreValue(score, 'home');
                const r = our > opp ? 3 : our < opp ? 0 : 1;
                pts += r;
                pontos.push(r);
                acumulada.push(pts);
                labels.push(`R${m.matchday || i + 1}`);
            });

            html += `
            <div class="chart-container">
                <canvas id="performanceCanvas"></canvas>
            </div>
            <div style="text-align:center;margin-top:0.5rem;font-size:0.75rem;color:var(--text-muted)">Evolução de pontos por rodada — Brasileirão</div>`;

            container.innerHTML = html;

            const isDark = document.body.classList.contains('dark');
            const textColor = isDark ? '#B0B0B0' : '#666666';
            const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)';

            const canvas = document.getElementById('performanceCanvas');
            const ctx = canvas && canvas.getContext('2d');
            if (!ctx) return;

            if (performanceChart) { performanceChart.destroy(); performanceChart = null; }
            performanceChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'Pontos por jogo',
                            data: pontos,
                            borderColor: 'rgba(0,107,63,0.5)',
                            backgroundColor: 'rgba(0,107,63,0.1)',
                            borderWidth: 1,
                            pointRadius: 4,
                            pointBackgroundColor: pontos.map(p => p === 3 ? '#006B3F' : p === 1 ? '#757575' : '#D32F2F'),
                            tension: 0.3,
                            yAxisID: 'y',
                        },
                        {
                            label: 'Pontos acumulados',
                            data: acumulada,
                            borderColor: '#006B3F',
                            backgroundColor: 'rgba(0,107,63,0.05)',
                            borderWidth: 2,
                            pointRadius: 3,
                            pointBackgroundColor: '#006B3F',
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'y1',
                        }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        x: {
                            ticks: { color: textColor, maxRotation: 0, font: { size: 10 } },
                            grid: { color: gridColor },
                        },
                        y: {
                            position: 'left',
                            ticks: { color: textColor, stepSize: 1 },
                            grid: { color: gridColor },
                            title: { display: true, text: 'Pts/jogo', color: textColor, font: { size: 10 } },
                            min: 0, max: 3,
                        },
                        y1: {
                            position: 'right',
                            ticks: { color: textColor },
                            grid: { drawOnChartArea: false },
                            title: { display: true, text: 'Acumulado', color: textColor, font: { size: 10 } },
                        }
                    },
                    plugins: {
                        legend: { labels: { color: textColor, font: { size: 11 } } },
                        tooltip: {
                            callbacks: {
                                afterLabel: (item) => {
                                    if (item.datasetIndex === 0) {
                                        const p = item.raw;
                                        return p === 3 ? 'Vitória' : p === 1 ? 'Empate' : 'Derrota';
                                    }
                                    return `Total: ${item.raw} pts`;
                                }
                            }
                        }
                    }
                }
            });
        } else {
            html += '<div style="text-align:center;padding:1rem;font-size:0.85rem;color:var(--text-muted)">Gráfico disponível com mínimo 3 jogos do Brasileirão</div>';
            container.innerHTML = html;
        }
    }

    function setNewsStatus(text, options = {}) {
        const status = document.getElementById('news-status');
        if (!status) return;
        status.setAttribute('aria-live', options.announce ? 'polite' : 'off');
        if (status.textContent !== text) status.textContent = text;
    }

    // --- News ---
    async function loadNews(options = {}) {
        if (!options.silent) {
            showSkeleton('news-list');
            setNewsStatus('', { announce: false });
        }
        const data = await api('news', options.force ? 0 : CACHE_TTL);
        const items = Array.isArray(data) ? data : ((data && data.news) || []);
        if (!items.length) {
            showEmpty('news-list', 'Nenhuma notícia');
            if (options.auto) setNewsStatus('Atualizado automaticamente. Sem novas notícias.', { announce: false });
            return;
        }

        document.getElementById('news-list').innerHTML = items.slice(0, 12).map(n => {
            const source = n.source || 'ge.globo';
            const safeTitle = escapeHtml(n.title);
            const safeSource = escapeHtml(source);
            const safeHref = escapeHtml(safeExternalUrl(n.url));
            return `<a class="news-item" href="${safeHref}" target="_blank" rel="noopener noreferrer">
                <div class="news-title">${safeTitle}</div>
                <div class="news-meta"><span class="news-source">${safeSource}</span></div>
            </a>`;
        }).join('');

        setNewsStatus(options.auto ? 'Atualizado automaticamente.' : '', { announce: false });

        // Delegated click handler is no longer needed — <a> handles natively
    }

    function refreshNewsData(options = {}) {
        if (document.hidden || currentTabId() !== 'news') return;
        return loadNews({ silent: options.silent !== false, auto: true, force: true });
    }

    function startNewsRefresh() {
        if (!_newsRefreshInterval) {
            _newsRefreshInterval = setInterval(() => refreshNewsData({ silent: true }), NEWS_REFRESH_MS);
        }
        if (!_newsVisibilityBound) {
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden && currentTabId() === 'news') {
                    refreshNewsData({ silent: true });
                }
            });
            _newsVisibilityBound = true;
        }
    }

    // --- Match predictions ---
    let predictionContext = null;
    let predictionContextPromise = null;

    function ensurePredictionContext() {
        if (predictionContext) return Promise.resolve(predictionContext);
        if (!predictionContextPromise) {
            predictionContextPromise = Promise.all([
                api(palmeirasQuery('matches?status=FINISHED&limit=12')),
                api('standings?competition=BSA')
            ]).then(([recentData, standingsData]) => {
                predictionContext = {
                    recentMatches: (recentData && recentData.matches) || [],
                    standings: (standingsData && standingsData.standings) || [],
                };
                return predictionContext;
            }).catch(() => {
                predictionContext = { recentMatches: [], standings: [] };
                return predictionContext;
            });
        }
        return predictionContextPromise;
    }

    function ensurePredictionContextForMatches(matches, rerender) {
        const list = (matches || []).filter(Boolean);
        const needsContext = list.some(match => (
            isPalmeirasMatch(match) &&
            UPCOMING_STATUSES.has(match.status) &&
            !predictionContext
        ));
        if (!needsContext) return;

        ensurePredictionContext().then(() => {
            if (typeof rerender === 'function') rerender();
        });
    }

    function findNextPalmeirasMatch(matches) {
        return matches.find(m => (m.homeTeam && m.homeTeam.id === CONFIG.TEAM_ID) || (m.awayTeam && m.awayTeam.id === CONFIG.TEAM_ID));
    }

    function calculatePrediction(match, recentMatches, standings) {
        const isPalmerasHome = match.homeTeam && match.homeTeam.id === CONFIG.TEAM_ID;
        const opponent = isPalmerasHome ? match.awayTeam : match.homeTeam;
        
        // Base probabilities based on home/away
        let probs = isPalmerasHome 
            ? { win: 0.50, draw: 0.27, loss: 0.23 }
            : { win: 0.38, draw: 0.29, loss: 0.33 };

        // Recent form adjustment
        const formAdjustment = calculateFormAdjustment(recentMatches);
        probs.win += formAdjustment;
        probs.loss -= formAdjustment;

        // Position adjustment if both teams are in standings
        const palmeirasStanding = standings.find(s => s.teamId === CONFIG.TEAM_ID);
        const opponentStanding = standings.find(s => opponent && s.teamId === opponent.id);
        
        if (palmeirasStanding && opponentStanding) {
            const positionAdjustment = calculatePositionAdjustment(palmeirasStanding, opponentStanding);
            probs.win += positionAdjustment;
            probs.loss -= positionAdjustment;
        }

        // Normalize and apply floor
        const total = probs.win + probs.draw + probs.loss;
        probs.win = Math.max(0.12, probs.win / total);
        probs.draw = Math.max(0.12, probs.draw / total);
        probs.loss = Math.max(0.12, probs.loss / total);

        // Final normalization
        const newTotal = probs.win + probs.draw + probs.loss;
        probs.win /= newTotal;
        probs.draw /= newTotal;
        probs.loss /= newTotal;

        // Generate factors
        const factors = generateFactors(match, recentMatches, palmeirasStanding, opponentStanding, isPalmerasHome);
        
        return {
            probs,
            factors,
            isPalmerasHome,
            labels: { win: 'Vitória', draw: 'Empate', loss: 'Derrota' },
            note: 'Estimativa baseada em desempenho recente, mando de campo e tabela quando disponível.',
        };
    }

    function calculateFormAdjustment(recentMatches) {
        // Get last 5 Palmeiras matches
        const palmeirasMatches = recentMatches
            .filter(m => (m.homeTeam && m.homeTeam.id === CONFIG.TEAM_ID) || (m.awayTeam && m.awayTeam.id === CONFIG.TEAM_ID))
            .slice(0, 5);

        if (palmeirasMatches.length === 0) return 0;

        let formPoints = 0;
        let matchCount = 0;

        palmeirasMatches.forEach(match => {
            const score = fullTimeScore(match);
            if (Object.keys(score).length) {
                const palmeirasIsHome = match.homeTeam && match.homeTeam.id === CONFIG.TEAM_ID;
                const palmeirasScore = palmeirasIsHome ? score.home : score.away;
                const opponentScore = palmeirasIsHome ? score.away : score.home;

                if (palmeirasScore > opponentScore) formPoints += 3;
                else if (palmeirasScore === opponentScore) formPoints += 1;
                
                matchCount++;
            }
        });

        if (matchCount === 0) return 0;

        // Average points per game, adjusted to influence range
        const avgPoints = formPoints / matchCount;
        // Scale: 0 points/game = -0.09, 1.5 points/game = 0, 3 points/game = +0.09
        return Math.max(
            -PREDICTION_CONSTANTS.MAX_FORM_ADJUSTMENT, 
            Math.min(
                PREDICTION_CONSTANTS.MAX_FORM_ADJUSTMENT, 
                (avgPoints - 1.5) * PREDICTION_CONSTANTS.FORM_WEIGHT_PER_POINT
            )
        );
    }

    // Prediction model constants
    const PREDICTION_CONSTANTS = {
        POSITION_WEIGHT_PER_PLACE: 0.004,  // 0.02 per 5 places = 0.004 per place
        MAX_POSITION_ADJUSTMENT: 0.10,
        FORM_WEIGHT_PER_POINT: 0.06,
        MAX_FORM_ADJUSTMENT: 0.09
    };

    function calculatePositionAdjustment(palmeirasStanding, opponentStanding) {
        const positionDiff = opponentStanding.position - palmeirasStanding.position;
        // Better position = positive adjustment, worse = negative
        // Scale: 0.004 per position difference, max ±0.10
        return Math.max(
            -PREDICTION_CONSTANTS.MAX_POSITION_ADJUSTMENT, 
            Math.min(
                PREDICTION_CONSTANTS.MAX_POSITION_ADJUSTMENT, 
                positionDiff * PREDICTION_CONSTANTS.POSITION_WEIGHT_PER_PLACE
            )
        );
    }

    function generateFactors(match, recentMatches, palmeirasStanding, opponentStanding, isPalmerasHome) {
        const factors = [];

        // Recent form
        const palmeirasMatches = recentMatches
            .filter(m => (m.homeTeam && m.homeTeam.id === CONFIG.TEAM_ID) || (m.awayTeam && m.awayTeam.id === CONFIG.TEAM_ID))
            .slice(0, 5);

        let wins = 0, draws = 0, losses = 0;
        palmeirasMatches.forEach(match => {
            const score = fullTimeScore(match);
            if (Object.keys(score).length) {
                const palmeirasIsHome = match.homeTeam && match.homeTeam.id === CONFIG.TEAM_ID;
                const palmeirasScore = palmeirasIsHome ? score.home : score.away;
                const opponentScore = palmeirasIsHome ? score.away : score.home;

                if (palmeirasScore > opponentScore) wins++;
                else if (palmeirasScore === opponentScore) draws++;
                else losses++;
            }
        });

        if (wins + draws + losses > 0) {
            factors.push(`Desempenho: ${wins}V ${draws}E ${losses}D`);
        }

        // Home/Away
        factors.push(isPalmerasHome ? 'Casa' : 'Fora');

        // Table positions if available
        if (palmeirasStanding && opponentStanding) {
            factors.push(`Tabela: ${palmeirasStanding.position}º x ${opponentStanding.position}º`);
        }

        return factors.slice(0, 3); // Limit to 3 factors
    }

    function calculateNeutralPrediction(match) {
        const probs = { win: 0.39, draw: 0.29, loss: 0.32 };
        const factors = [];
        const stageLabel = formatStage(match.stage);
        if (stageLabel) factors.push(stageLabel);
        if (match.venue) factors.push(match.venue);
        factors.push('Campo neutro');

        return {
            probs,
            factors: factors.slice(0, 3),
            labels: { win: 'Mandante', draw: 'Empate', loss: 'Visitante' },
            note: 'Estimativa simples para jogo neutro, baseada em mando nominal e contexto da partida.',
        };
    }

    function predictionTitle(match, prediction) {
        if (prediction.isPalmerasHome === true) {
            const opponent = match.awayTeam;
            return `Palmeiras x ${escapeHtml((opponent && (opponent.shortName || opponent.name)) || 'Adversário')}`;
        }
        if (prediction.isPalmerasHome === false) {
            const opponent = match.homeTeam;
            return `${escapeHtml((opponent && (opponent.shortName || opponent.name)) || 'Adversário')} x Palmeiras`;
        }
        return `${escapeHtml(CONFIG.teamName(match.homeTeam))} x ${escapeHtml(CONFIG.teamName(match.awayTeam))}`;
    }

    function renderPredictionHtml(match, prediction, options = {}) {
        const { probs, factors } = prediction;
        const labels = prediction.labels || { win: 'Vitória', draw: 'Empate', loss: 'Derrota' };

        // Determine confidence based on highest probability
        const maxProb = Math.max(probs.win, probs.draw, probs.loss);
        let confidenceBadge;
        if (maxProb >= 0.60) {
            confidenceBadge = '<div class="prediction-badge likely">Provável</div>';
        } else if (maxProb >= 0.45) {
            confidenceBadge = '<div class="prediction-badge maybe">Possível</div>';
        } else {
            confidenceBadge = '<div class="prediction-badge risky">Arriscado</div>';
        }

        // Format probabilities as percentages
        const winPct = Math.round(probs.win * 100);
        const drawPct = Math.round(probs.draw * 100);
        const lossPct = Math.round(probs.loss * 100);

        const factorsHtml = factors.map(f => `<span class="prediction-factor">${escapeHtml(f)}</span>`).join('');
        const compactClass = options.compact ? ' compact' : '';

        return `
            <div class="prediction-card${compactClass}">
                <div class="prediction-match">${predictionTitle(match, prediction)}</div>
                ${confidenceBadge}
                
                <div class="prediction-probs">
                    <div class="prob-box ${probs.win === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${winPct}%</div>
                        <div class="prob-label">${escapeHtml(labels.win)}</div>
                    </div>
                    <div class="prob-box ${probs.draw === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${drawPct}%</div>
                        <div class="prob-label">${escapeHtml(labels.draw)}</div>
                    </div>
                    <div class="prob-box ${probs.loss === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${lossPct}%</div>
                        <div class="prob-label">${escapeHtml(labels.loss)}</div>
                    </div>
                </div>
                
                ${factors.length > 0 ? `<div class="prediction-factors">${factorsHtml}</div>` : ''}
                
                <div class="prediction-note">
                    ${escapeHtml(prediction.note || 'Estimativa baseada em contexto disponível.')}
                </div>
            </div>
        `;
    }

    function matchScoreValues(match) {
        const fullTime = (match && match.score && match.score.fullTime) || {};
        const home = hasValue(match.homeScore) ? match.homeScore : fullTime.home;
        const away = hasValue(match.awayScore) ? match.awayScore : fullTime.away;
        return { home, away };
    }

    function scorePairText(score) {
        return score && hasValue(score.home) && hasValue(score.away)
            ? `${score.home} x ${score.away}`
            : '';
    }

    function halfTimeScoreText(match) {
        return scorePairText((match && match.score && match.score.halfTime) || {});
    }

    function matchStageRound(match) {
        const parts = [];
        const stage = formatStage(match && match.stage);
        if (stage) parts.push(stage);
        if (match && match.matchday) parts.push(`Rodada ${match.matchday}`);
        return parts.join(' · ');
    }

    function matchDateTimeText(match) {
        if (!(match && match.utcDate)) return '';
        const date = new Date(match.utcDate).toLocaleDateString('pt-BR', {
            weekday: 'short',
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            timeZone: BR_TZ,
        });
        return `${date} · ${formatTime(match.utcDate)}`;
    }

    function matchFinishedResult(match, score) {
        if (!scorePairText(score)) return 'Resultado indisponível';
        if (isPalmeirasMatch(match)) {
            const sides = matchDisplaySides(match);
            if (sides.leftScore > sides.rightScore) return 'Vitória do Palmeiras';
            if (sides.leftScore < sides.rightScore) return 'Derrota do Palmeiras';
            return 'Empate do Palmeiras';
        }
        if (score.home > score.away) return `Vitória de ${CONFIG.teamName(match.homeTeam)}`;
        if (score.home < score.away) return `Vitória de ${CONFIG.teamName(match.awayTeam)}`;
        return 'Empate';
    }

    function teamPerspectiveStats(match, score) {
        if (!scorePairText(score)) return [];
        if (isPalmeirasMatch(match)) {
            const sides = matchDisplaySides(match);
            const points = sides.leftScore > sides.rightScore ? 3 : sides.leftScore === sides.rightScore ? 1 : 0;
            const homeId = match.homeTeam && match.homeTeam.id;
            return [
                { label: 'Gols pró', value: sides.leftScore },
                { label: 'Gols contra', value: sides.rightScore },
                { label: 'Pontos', value: points },
                { label: 'Mando', value: sides.leftTeam && sides.leftTeam.id === homeId ? 'Casa' : 'Fora' },
            ];
        }
        return [
            { label: 'Mandante', value: score.home },
            { label: 'Visitante', value: score.away },
        ];
    }

    function renderFinishedMatchDetails(match) {
        const score = matchScoreValues(match);
        const finalScore = scorePairText(score) || matchScoreText(match) || 'Placar indisponível';
        const halfTime = halfTimeScoreText(match);
        const result = matchFinishedResult(match, score);
        const detailItems = [
            { label: 'Competição', value: CONFIG.formatComp(match.competition) },
            { label: 'Fase/Rodada', value: matchStageRound(match) },
            { label: 'Data', value: matchDateTimeText(match) },
            { label: 'Estádio', value: CONFIG.getVenue(match) || match.venue },
            { label: 'Transmissão', value: match.broadcast },
            { label: 'Status', value: STATUS_LABEL[match.status] || match.status },
            {
                label: 'Arbitragem',
                value: Array.isArray(match.referees)
                    ? match.referees.map(ref => ref.name).filter(Boolean).join(', ')
                    : '',
            },
        ].filter(item => item.value);

        const statItems = [
            { label: 'Resultado', value: result },
            { label: 'Placar final', value: finalScore },
            ...(halfTime ? [{ label: '1º tempo', value: halfTime }] : []),
            ...teamPerspectiveStats(match, score),
        ];

        return `<div class="cal-match-prediction">
            <div class="match-details-card">
                <div class="match-detail-head">
                    <div>
                        <div class="match-detail-title">Resultado e estatísticas</div>
                        <div class="match-detail-subtitle">${escapeHtml(matchLine(match))}</div>
                    </div>
                    <div class="match-detail-score">${escapeHtml(finalScore)}</div>
                </div>
                <div class="match-detail-stats">
                    ${statItems.map(item => `<div class="match-detail-stat">
                        <span>${escapeHtml(item.label)}</span>
                        <strong>${escapeHtml(item.value)}</strong>
                    </div>`).join('')}
                </div>
                ${detailItems.length ? `<div class="match-detail-meta">
                    ${detailItems.map(item => `<div>
                        <span>${escapeHtml(item.label)}</span>
                        <strong>${escapeHtml(item.value)}</strong>
                    </div>`).join('')}
                </div>` : ''}
            </div>
        </div>`;
    }

    function renderMatchInsight(match) {
        if (FINISHED_STATUSES.has(match.status)) {
            return renderFinishedMatchDetails(match);
        }

        if (LIVE_STATUSES.has(match.status)) {
            return `<div class="cal-match-prediction">
                <div class="prediction-card compact result">
                    <div class="prediction-match">Jogo em andamento</div>
                    <div class="prediction-note">O palpite fica em segundo plano enquanto o placar ao vivo está ativo.</div>
                </div>
            </div>`;
        }

        if (!UPCOMING_STATUSES.has(match.status)) {
            const statusText = STATUS_LABEL[match.status] || match.status || 'Status indisponível';
            return `<div class="cal-match-prediction">
                <div class="prediction-card compact result">
                    <div class="prediction-match">Detalhes do jogo</div>
                    <div class="prediction-note">${escapeHtml(statusText)}</div>
                </div>
            </div>`;
        }

        if (isPalmeirasMatch(match) && !predictionContext) {
            return `<div class="cal-match-prediction">
                <div class="prediction-card compact">
                    <div class="prediction-match">Palpite do jogo</div>
                    <div class="prediction-note">Carregando desempenho recente para estimar o cenário.</div>
                </div>
            </div>`;
        }

        const context = predictionContext || { recentMatches: [], standings: [] };
        const prediction = isPalmeirasMatch(match)
            ? calculatePrediction(match, context.recentMatches, context.standings)
            : calculateNeutralPrediction(match);
        return `<div class="cal-match-prediction">${renderPredictionHtml(match, prediction, { compact: true })}</div>`;
    }

    // --- World Cup 2026 ---
    let worldCupLoaded = false;
    let worldCupMatches = [];
    let worldCupFilter = 'all';

    async function loadWorldCup() {
        if (worldCupLoaded) {
            renderWorldCup();
            return;
        }

        showSkeleton('worldcup-matches');
        const path = `matches?competition=WC&from_date=${WORLD_CUP_FROM}&to_date=${WORLD_CUP_TO}&limit=200`;
        const data = await api(path, WORLD_CUP_REFRESH_MS);
        if (!data) {
            showError('worldcup-matches', 'Erro ao carregar a Copa 2026', 'loadWorldCup');
            return;
        }

        worldCupMatches = (data.matches || []).sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
        worldCupLoaded = true;
        renderWorldCup();
    }

    function isBrazilMatch(match) {
        return isBrazilTeam(match.homeTeam) || isBrazilTeam(match.awayTeam);
    }

    function isBrazilTeam(team) {
        const tla = String((team && team.tla) || '').toUpperCase();
        const name = String((team && team.name) || '').toLowerCase();
        const shortName = String((team && team.shortName) || '').toLowerCase();
        return tla === 'BRA' || name === 'brazil' || name === 'brasil' || shortName === 'brazil' || shortName === 'brasil';
    }

    function isNextCandidate(match, now = Date.now()) {
        if (LIVE_STATUSES.has(match.status)) return true;
        return UPCOMING_STATUSES.has(match.status) && new Date(match.utcDate).getTime() >= now - 3 * 60 * 60 * 1000;
    }

    function nextBrazilMatches(limit = 3) {
        return worldCupMatches
            .filter(isBrazilMatch)
            .filter(m => isNextCandidate(m))
            .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate))
            .slice(0, limit);
    }

    function filteredWorldCupMatches() {
        if (worldCupFilter === 'finished') {
            return worldCupMatches.filter(m => FINISHED_STATUSES.has(m.status));
        }
        if (worldCupFilter === 'upcoming') {
            return worldCupMatches.filter(m => UPCOMING_STATUSES.has(m.status) || LIVE_STATUSES.has(m.status));
        }
        if (worldCupFilter === 'brazil') {
            return worldCupMatches.filter(isBrazilMatch);
        }
        return worldCupMatches;
    }

    function worldCupFinal() {
        return worldCupMatches.find(match =>
            String(match.stage || '').toUpperCase() === 'FINAL' && FINISHED_STATUSES.has(match.status)
        ) || null;
    }

    function worldCupTeamName(team) {
        const tla = String((team && team.tla) || '').toUpperCase();
        return WORLD_CUP_TEAM_NAMES_PT[tla] || CONFIG.teamName(team);
    }

    function renderWorldCupChampion() {
        const final = worldCupFinal();
        if (!final || final.homeScore == null || final.awayScore == null || final.homeScore === final.awayScore) return;

        const homeWon = final.homeScore > final.awayScore;
        const champion = homeWon ? final.homeTeam : final.awayTeam;
        const runnerUp = homeWon ? final.awayTeam : final.homeTeam;
        const championScore = homeWon ? final.homeScore : final.awayScore;
        const runnerUpScore = homeWon ? final.awayScore : final.homeScore;
        const championName = worldCupTeamName(champion);
        const runnerUpName = worldCupTeamName(runnerUp);
        const date = new Date(final.utcDate).toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            timeZone: BR_TZ,
        }).replace(/\./g, '');

        const title = document.getElementById('worldcup-title');
        const copy = document.getElementById('worldcup-champion-copy');
        const crest = document.getElementById('worldcup-champion-crest');
        const result = document.getElementById('worldcup-final-result');

        if (title) title.textContent = `${championName} campeã do mundo`;
        if (copy) copy.textContent = `${championName} venceu ${runnerUpName} por ${championScore} a ${runnerUpScore} e conquistou a Copa do Mundo de 2026.`;
        if (crest) {
            crest.src = safeImageUrl(CONFIG.getCrest(champion));
            crest.alt = `Escudo da seleção ${championName}`;
        }
        if (result) {
            result.setAttribute('aria-label', `Final: ${championName} ${championScore} a ${runnerUpScore} ${runnerUpName}`);
            result.innerHTML = `<span>Final</span><strong>${escapeHtml(championName)} <b>${championScore}–${runnerUpScore}</b> ${escapeHtml(runnerUpName)}</strong><span>${escapeHtml(date)}</span>`;
        }
    }

    function renderWorldCup() {
        const total = worldCupMatches.length;
        const finished = worldCupMatches.filter(m => FINISHED_STATUSES.has(m.status)).length;
        const live = worldCupMatches.filter(m => LIVE_STATUSES.has(m.status)).length;
        const upcoming = worldCupMatches.filter(m => UPCOMING_STATUSES.has(m.status)).length;
        const totalEl = document.getElementById('worldcup-total');
        if (totalEl) totalEl.textContent = total ? String(total) : '104';

        const summary = document.getElementById('worldcup-summary');
        if (summary) {
            const liveText = live ? ` · ${live} ao vivo` : '';
            summary.textContent = total
                ? `${total} jogos carregados · ${finished} resultados · ${upcoming} próximos${liveText}`
                : 'Nenhum jogo da Copa 2026 encontrado no banco ainda.';
        }

        renderWorldCupChampion();
        renderBrazilNextGames();

        document.querySelectorAll('.worldcup-filter').forEach(btn => {
            const selected = btn.dataset.wcFilter === worldCupFilter;
            btn.classList.toggle('active', selected);
            btn.setAttribute('aria-pressed', String(selected));
        });

        const container = document.getElementById('worldcup-matches');
        if (!container) return;

        const matches = filteredWorldCupMatches();
        if (!matches.length) {
            container.innerHTML = '<div class="empty">Nenhum jogo neste filtro</div>';
            return;
        }

        const groups = new Map();
        matches.forEach(match => {
            const key = new Date(match.utcDate).toLocaleDateString('en-CA', { timeZone: BR_TZ });
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(match);
        });

        container.innerHTML = [...groups.entries()].map(([dateKey, dayMatches]) => {
            const dayLabel = new Date(`${dateKey}T12:00:00`).toLocaleDateString('pt-BR', {
                weekday: 'long',
                day: '2-digit',
                month: 'short',
                timeZone: BR_TZ,
            });

            return `<section class="worldcup-day-group" aria-label="${escapeHtml(dayLabel)}">
                <div class="worldcup-day-heading">
                    <span>${escapeHtml(dayLabel)}</span>
                    <strong>${dayMatches.length} ${dayMatches.length === 1 ? 'jogo' : 'jogos'}</strong>
                </div>
                <div class="worldcup-match-list">
                    ${dayMatches.map(renderWorldCupMatch).join('')}
                </div>
            </section>`;
        }).join('');
    }

    function renderWorldCupMatch(match) {
        const time = formatTime(match.utcDate);
        const statusText = STATUS_LABEL[match.status] || match.status || 'Agendado';
        const stageLabel = formatStage(match.stage) || `Rodada ${match.matchday || '-'}`;
        const scoreReady = (FINISHED_STATUSES.has(match.status) || LIVE_STATUSES.has(match.status)) && match.homeScore != null && match.awayScore != null;
        const score = scoreReady ? `${match.homeScore}–${match.awayScore}` : '×';
        const liveClass = LIVE_STATUSES.has(match.status) ? ' live' : '';
        const venue = match.venue || 'A definir';

        return `<details class="worldcup-match match-card${liveClass}"${matchDataAttr(match)}${matchOpenAttr(match)}>
            <summary class="worldcup-match-summary match-card-summary">
                <div class="worldcup-match-time">${time}</div>
                <div class="worldcup-match-body">
                    <div class="worldcup-teams">
                        <span class="worldcup-team">
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(match.homeTeam)))}" alt="">
                            <span>${escapeHtml(CONFIG.teamName(match.homeTeam))}</span>
                        </span>
                        <strong class="worldcup-score">${escapeHtml(score)}</strong>
                        <span class="worldcup-team away">
                            <span>${escapeHtml(CONFIG.teamName(match.awayTeam))}</span>
                            <img src="${escapeHtml(safeImageUrl(CONFIG.getCrest(match.awayTeam)))}" alt="">
                        </span>
                    </div>
                    <div class="worldcup-match-meta">
                        <span>${escapeHtml(stageLabel)}</span>
                        <span>${escapeHtml(statusText)}</span>
                        <span>${escapeHtml(venue)}</span>
                    </div>
                </div>
            </summary>
            ${renderMatchInsight(match)}
        </details>`;
    }

    function renderBrazilNextGames() {
        const container = document.getElementById('worldcup-brazil-matches');
        const summary = document.getElementById('worldcup-brazil-summary');
        const title = document.getElementById('worldcup-brazil-title');
        if (!container) return;

        const allBrazil = worldCupMatches.filter(isBrazilMatch).sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
        const upcomingBrazil = nextBrazilMatches(3);

        if (title) title.textContent = upcomingBrazil.length ? 'Próximos jogos do Brasil' : 'Campanha do Brasil';
        if (summary) {
            summary.textContent = allBrazil.length
                ? (upcomingBrazil.length
                    ? `${upcomingBrazil.length} próximos · ${allBrazil.length} jogos do Brasil na tabela`
                    : `${allBrazil.length} jogos disputados pela Seleção na Copa 2026`)
                : 'A tabela atual ainda não trouxe jogos do Brasil.';
        }

        if (!allBrazil.length) {
            container.innerHTML = '<div class="empty">Brasil ainda não aparece na tabela carregada</div>';
            return;
        }

        const matches = upcomingBrazil.length ? upcomingBrazil : allBrazil.slice(-3);
        container.innerHTML = `<div class="worldcup-brazil-list">
            ${matches.map(renderBrazilMatchCard).join('')}
        </div>`;
    }

    function renderBrazilMatchCard(match) {
        const dt = new Date(match.utcDate);
        const date = dt.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', timeZone: BR_TZ });
        const time = formatTime(match.utcDate);
        const stageLabel = formatStage(match.stage) || `Rodada ${match.matchday || '-'}`;
        const home = CONFIG.teamName(match.homeTeam);
        const away = CONFIG.teamName(match.awayTeam);
        const scoreReady = (FINISHED_STATUSES.has(match.status) || LIVE_STATUSES.has(match.status)) && match.homeScore != null && match.awayScore != null;
        const score = scoreReady ? `${match.homeScore}–${match.awayScore}` : '×';

        return `<details class="worldcup-brazil-card match-card"${matchDataAttr(match)}${matchOpenAttr(match)}>
            <summary class="worldcup-brazil-summary match-card-summary">
                <div class="worldcup-brazil-date">
                    <strong>${escapeHtml(date)}</strong>
                    <span>${escapeHtml(time)}</span>
                </div>
                <div class="worldcup-brazil-main">
                    <div class="worldcup-brazil-teams">
                        <span>${escapeHtml(home)}</span>
                        <strong>${escapeHtml(score)}</strong>
                        <span>${escapeHtml(away)}</span>
                    </div>
                    <div class="worldcup-match-meta">
                        <span>${escapeHtml(stageLabel)}</span>
                        <span>${escapeHtml(STATUS_LABEL[match.status] || match.status || 'Agendado')}</span>
                    </div>
                </div>
            </summary>
            ${renderMatchInsight(match)}
        </details>`;
    }

    function setWorldCupFilter(filter) {
        worldCupFilter = VALID_WC_FILTERS.has(filter) ? filter : 'all';
        renderWorldCup();
        updateUrlState({ tab: 'worldcup', wc: worldCupFilter });
    }

    // --- Calendar ---
    const COMP_DOT_CLASS = {
        BSA: 'bsa',
        CLI: 'cli',
        CL: 'cli',
        COPA: 'copa',
        CBC: 'copa',
        COPA_DO_BRASIL: 'copa',
        CPA: 'paulista',
        CAMPEONATO_PAULISTA: 'paulista',
        PAULISTA: 'paulista',
        WC: 'wc',
    };

    const STATUS_LABEL = {
        SCHEDULED: 'Agendado',
        TIMED: 'Agendado',
        IN_PLAY: 'AO VIVO',
        FINISHED: 'Finalizado',
        PLAYING_TIME_FINISHED: 'Finalizado',
        PAUSED: 'Intervalo',
        POSTPONED: 'Adiado',
        SUSPENDED: 'Suspenso',
        CANCELLED: 'Cancelado',
    };

    function getCompBadgeClass(code) {
        return COMP_DOT_CLASS[code] || 'other';
    }

    const MONTHS_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                       'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

    let _calYear = null;
    let _calMonth = null;
    let _calData = null;
    let _calSelectedDay = null;

    async function loadCalendar() {
        if (!document.getElementById('calendar-grid')) return;

        const todayStr = getTodayStr();
        const todayYear = parseInt(todayStr.split('-')[0]);
        const todayMonth = parseInt(todayStr.split('-')[1]);

        if (_calYear === null) {
            _calYear = todayYear;
            _calMonth = todayMonth;
        }

        // Revisioned query invalidates stale browser/PWA HTTP caches when the
        // compact calendar contract or historical results are corrected.
        const data = await api(`calendar_monthly?year=${_calYear}&month=${_calMonth}&team_scope=${encodeURIComponent(CONFIG.TEAM_SCOPE || 'men')}&rev=3`);
        if (!data) {
            document.getElementById('calendar-grid').innerHTML = '<div class="empty">Erro ao carregar</div>';
            return;
        }
        _calData = data;

        document.getElementById('cal-month-label').textContent = `${MONTHS_PT[_calMonth - 1]} ${_calYear}`;

        const daysInMonth = new Date(_calYear, _calMonth, 0).getDate();
        const firstDow = new Date(_calYear, _calMonth - 1, 1).getDay(); // 0=Sun

        const grid = document.getElementById('calendar-grid');
        let html = '';

        // Day headers
        ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'].forEach(d => {
            html += `<div class="cal-head" aria-hidden="true">${d}</div>`;
        });

        // Leading empty cells
        for (let i = 0; i < firstDow; i++) {
            html += `<div class="cal-day other-month"></div>`;
        }

        // Day cells
        for (let day = 1; day <= daysInMonth; day++) {
            const dayStr = `${_calYear}-${String(_calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const isToday = dayStr === todayStr;
            let matches = (data.days[dayStr] || []).filter(isSharedCalendarMatch);

            // Apply competition filter (fuzzy match via COMP_MAP)
            if (_calCompFilter !== 'all') {
                const allowedCodes = COMP_MAP[_calCompFilter] || [_calCompFilter];
                matches = matches.filter(m => m.competition && allowedCodes.includes(m.competition.code));
            }

            const comps = [...new Set(matches.map(m => (m.competition && m.competition.code) || 'OTHER'))];
            const visibleComps = comps.slice(0, 3);
            const overflow = comps.length > 3 ? comps.length - 3 : 0;

            const dotsHtml = visibleComps.map(c =>
                `<div class="cal-dot ${getCompBadgeClass(c)}"></div>`
            ).join('');
            const overflowHtml = overflow > 0 ? `<span class="cal-overflow">+${overflow}</span>` : '';

            // Score summary for finished games
            const finished = matches.filter(m => m.status === 'FINISHED' || m.status === 'PLAYING_TIME_FINISHED');
            const live = matches.filter(m => m.status === 'IN_PLAY' || m.status === 'PAUSED');
            let scoreHtml = '';
            const scoreLabels = [];
            if (live.length > 0) {
                const m = live[0];
                const sides = matchDisplaySides(m);
                const scoreText = `AO VIVO ${hasValue(sides.leftScore) ? sides.leftScore : 0}–${hasValue(sides.rightScore) ? sides.rightScore : 0}`;
                scoreLabels.push(scoreText);
                scoreHtml = `<div class="cal-score live">${escapeHtml(scoreText)}</div>`;
            } else if (finished.length > 0) {
                // Show result badge for each finished game
                scoreHtml = finished.map(m => {
                    const sides = matchDisplaySides(m);
                    const result = sides.leftScore > sides.rightScore ? 'V' : sides.leftScore < sides.rightScore ? 'D' : 'E';
                    const cls = sides.perspective === 'palmeiras'
                        ? (result === 'V' ? 'win' : result === 'D' ? 'loss' : 'draw')
                        : 'neutral';
                    const scoreText = `${sides.leftScore}–${sides.rightScore}`;
                    scoreLabels.push(scoreText);
                    return `<div class="cal-score ${cls}">${escapeHtml(scoreText)}</div>`;
                }).join('');
            }

            const classes = ['cal-day'];
            if (isToday) classes.push('today');
            if (matches.length > 0) classes.push('has-match');
            if (live.length > 0) classes.push('is-live');
            if (_calSelectedDay === dayStr) classes.push('selected');

            const selected = _calSelectedDay === dayStr;
            const matchLabel = matches.length === 1 ? '1 jogo' : `${matches.length} jogos`;
            const visibleScoreLabel = scoreLabels.length ? `, ${scoreLabels.join(', ')}` : '';
            const ariaLabel = `${day}${visibleScoreLabel}, ${day}/${_calMonth}/${_calYear}${matches.length ? `, ${matchLabel}` : ', sem jogos'}`;

            html += `<button type="button" class="${classes.join(' ')}" data-day="${day}" aria-pressed="${selected}" aria-label="${escapeHtml(ariaLabel)}">
                <div class="cal-day-num">${day}</div>
                ${matches.length ? `<div class="cal-dots">${dotsHtml}${overflowHtml}</div>` : ''}
                ${scoreHtml}
            </button>`;
        }

        grid.innerHTML = html;

        const selectedInMonth = _calSelectedDay && _calSelectedDay.startsWith(`${_calYear}-${String(_calMonth).padStart(2, '0')}-`);
        if (selectedInMonth) {
            renderExpandedDay(_calSelectedDay);
        } else if (!_calSelectedDay && _calYear === todayYear && _calMonth === todayMonth) {
            // Auto-select today's date if no day is selected and today is in current month
            const todayDay = parseInt(todayStr.split('-')[2]);
            if (todayDay >= 1 && todayDay <= daysInMonth) {
                _calSelectedDay = todayStr;
                // Update the visual selected state
                const todayCell = document.querySelector(`.cal-day[data-day="${todayDay}"]`);
                if (todayCell) {
                    todayCell.classList.add('selected');
                    todayCell.setAttribute('aria-pressed', 'true');
                }
                // Show expanded view for today's matches
                renderExpandedDay(todayStr);
            }
        } else {
            document.getElementById('calendar-expanded').innerHTML = '';
        }
    }

    function toggleDay(day) {
        const dayStr = `${_calYear}-${String(_calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        // A calendar day is a selector, not a disclosure toggle. Re-selecting
        // an already highlighted date must keep its games visible (especially
        // after arriving via a "Ver no calendário" deep link).
        _calSelectedDay = dayStr;
        renderExpandedDay(dayStr);

        // Keep the selected result in view above the persistent native bar.
        if (window.matchMedia('(max-width: 600px)').matches) {
            requestAnimationFrame(() => {
                const expandedEl = document.getElementById('calendar-expanded');
                if (expandedEl && expandedEl.firstElementChild) {
                    expandedEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        }
        
        // Update selected state - only add if day is still selected
        document.querySelectorAll('.cal-day').forEach(d => {
            d.classList.remove('selected');
            d.setAttribute('aria-pressed', 'false');
        });
        if (_calSelectedDay) {
            const selectedCell = document.querySelector(`.cal-day[data-day="${day}"]`);
            if (selectedCell) {
                selectedCell.classList.add('selected');
                selectedCell.setAttribute('aria-pressed', 'true');
            }
        }
        updateUrlState({ year: _calYear, month: _calMonth, day: _calSelectedDay });
    }

    function renderExpandedDay(dayStr) {
        let matches = ((_calData && _calData.days && _calData.days[dayStr]) || []).filter(isSharedCalendarMatch);

        // Apply competition filter (fuzzy match via COMP_MAP)
        if (_calCompFilter !== 'all') {
            const allowedCodes = COMP_MAP[_calCompFilter] || [_calCompFilter];
            matches = matches.filter(m => m.competition && allowedCodes.includes(m.competition.code));
        }

        const container = document.getElementById('calendar-expanded');

        if (!matches.length) {
            container.innerHTML = `<div class="cal-expanded cal-expanded-empty">
                <div class="cal-expanded-header">
                    <span class="cal-expanded-date">${dayStr.split('-').reverse().join('/')}</span>
                </div>
                <p>Nenhum jogo nesta data.</p>
            </div>`;
            return;
        }

        ensurePredictionContextForMatches(matches, () => {
            if (_calSelectedDay === dayStr) renderExpandedDay(dayStr);
        });

        container.innerHTML = `<div class="cal-expanded">
            <div class="cal-expanded-header">
                <span class="cal-expanded-date">${dayStr.split('-').reverse().join('/')}</span>
            </div>
            ${matches.filter(m => m && m.homeTeam && m.awayTeam).map(m => {
                const time = new Date(m.utcDate).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: CONFIG.BR_TZ });
                const sides = matchDisplaySides(m);
                const stageLabel = formatStage(m.stage);

                const hasFinalScore = FINISHED_STATUSES.has(m.status)
                    && hasValue(sides.leftScore)
                    && hasValue(sides.rightScore);
                const scoreHtml = hasFinalScore
                    ? `<span class="cal-match-score" aria-label="Placar final ${sides.leftScore} a ${sides.rightScore}">${sides.leftScore}–${sides.rightScore}</span>`
                    : '<span class="cal-match-vs" aria-hidden="true">×</span>';

                const awaitingResult = isPastMatchAwaitingResult(m);
                const statusText = awaitingResult ? 'Resultado pendente' : (STATUS_LABEL[m.status] || m.status);
                const compClass = getCompBadgeClass(m.competition && m.competition.code);
                const statusClass = FINISHED_STATUSES.has(m.status)
                    ? 'finished'
                    : (LIVE_STATUSES.has(m.status) ? 'live' : (awaitingResult ? 'pending' : ''));

                return `<details class="cal-match match-card ${compClass}"${matchDataAttr(m)}${matchOpenAttr(m)}>
                    <summary class="cal-match-main match-card-summary">
                        <div class="cal-match-time">${time}</div>
                        <div class="cal-match-comp ${compClass}">${escapeHtml(stageLabel || CONFIG.formatComp(m.competition))}</div>
                        <div class="cal-match-teams${hasFinalScore ? ' has-result' : ''}">
                            <span class="cal-match-team cal-match-team-left">
                                <img class="cal-match-crest" src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.leftTeam)))}" alt="">
                                <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(sides.leftTeam))}</span>
                            </span>
                            ${scoreHtml}
                            <span class="cal-match-team cal-match-team-right">
                                <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(sides.rightTeam))}</span>
                                <img class="cal-match-crest" src="${escapeHtml(safeImageUrl(CONFIG.getCrest(sides.rightTeam)))}" alt="">
                            </span>
                        </div>
                        <div class="cal-match-status ${statusClass}">${statusText}</div>
                    </summary>
                    ${renderMatchInsight(m)}
                </details>`;
            }).join('')}
        </div>`;
    }

    window.loadCalendar = loadCalendar;

    function getTodayStr() {
        return new Date().toLocaleDateString('en-CA', { timeZone: CONFIG.BR_TZ });
    }

    // --- Calendar Competition Filter ---
    let _calCompFilter = 'all';

    // --- Shared Competition Filter (syncs calendar + list views) ---
    function syncCompLegend() {
        document.querySelectorAll('.comp-legend-item').forEach(b => {
            const selected = b.dataset.comp === _calCompFilter;
            b.classList.toggle('active', selected);
            b.setAttribute('aria-pressed', String(selected));
        });
    }

    window.filterSharedComp = function (comp, btn) {
        comp = comp || 'all';
        if (!isSharedCalendarCompFilter(comp)) return;
        _calCompFilter = comp;

        // Update legend items
        syncCompLegend();

        // Re-render calendar view with filter
        loadCalendar();
        updateUrlState({ year: _calYear, month: _calMonth, comp: _calCompFilter, day: _calSelectedDay });
    };

    document.querySelectorAll('.comp-legend-item').forEach(btn => {
        btn.addEventListener('click', () => window.filterSharedComp(btn.dataset.comp || 'all', btn));
    });

    // Nav buttons
    addClickListener('cal-prev', () => {
        _calMonth--;
        if (_calMonth < 1) { _calMonth = 12; _calYear--; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
        loadCompetitionOverview();
        updateUrlState({ year: _calYear, month: _calMonth, day: null });
    });
    addClickListener('cal-next', () => {
        _calMonth++;
        if (_calMonth > 12) { _calMonth = 1; _calYear++; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
        loadCompetitionOverview();
        updateUrlState({ year: _calYear, month: _calMonth, day: null });
    });

    function syncYearSelect() {
        const sel = document.getElementById('cal-year-select');
        if (sel && sel.value != _calYear) sel.value = _calYear;
    }

    window.changeCalYear = function (year) {
        _calYear = parseInt(year);
        _calMonth = 1;
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        loadCalendar();
        loadCompetitionOverview();
        updateUrlState({ year: _calYear, month: _calMonth, day: null });
    };

    // Populate year select and keep the World Cup year available.
    (function populateYearSelect() {
        const sel = document.getElementById('cal-year-select');
        if (!sel) return;
        const currentYear = new Date().getFullYear();
        const years = [...new Set([currentYear - 1, currentYear, currentYear + 1, 2026])].sort();
        sel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
        sel.value = currentYear;
    })();

    function calendarFeedUrl() {
        return new URL(CONFIG.apiUrl('calendar.ics'), window.location.href).href;
    }

    function fallbackCopyText(text) {
        const input = document.createElement('textarea');
        input.value = text;
        input.setAttribute('readonly', '');
        input.style.position = 'fixed';
        input.style.opacity = '0';
        document.body.appendChild(input);
        input.select();
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (error) {
            copied = false;
        }
        input.remove();
        return copied;
    }

    async function writeClipboardText(text) {
        if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }
        return fallbackCopyText(text);
    }

    window.downloadCalendar = async function () {
        try {
            const res = await fetch(CONFIG.apiUrl('calendar.ics'));
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = new Blob([await res.text()], { type: 'text/calendar' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'palmeiras.ics';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 1000);
            showToast('Calendário ICS baixado.');
        } catch (e) {
            showToast('Não foi possível baixar o calendário.', 'error');
        }
    };

    window.copyCalendarUrl = async function () {
        const url = calendarFeedUrl();
        try {
            const copied = await writeClipboardText(url);
            if (!copied) throw new Error('copy_failed');
            showToast('Link do calendário copiado.');
        } catch (error) {
            window.prompt('Copie o link do calendário:', url);
        }
    };

    function bindStaticControls() {
        if (!bindStaticControls._matchDetailsDelegated) {
            document.addEventListener('toggle', (event) => {
                const details = event.target;
                if (!details || !details.matches || !details.matches('.match-card[data-match-key]')) return;
                const key = details.dataset.matchKey;
                if (!key) return;
                if (details.open) expandedMatchKeys.add(key);
                else expandedMatchKeys.delete(key);
            }, true);
            bindStaticControls._matchDetailsDelegated = true;
        }

        addClickListener('themeToggle', window.toggleTheme);
        addClickListener('refreshButton', refreshAllData);
        const yearSelect = document.getElementById('cal-year-select');
        if (yearSelect) yearSelect.addEventListener('change', (event) => {
            window.changeCalYear(event.target.value);
        });
        addClickListener('downloadCalendarButton', window.downloadCalendar);
        addClickListener('copyCalendarUrlButton', window.copyCalendarUrl);
        addClickListener('worldcupBrazilFilter', () => setWorldCupFilter('brazil'));
        document.querySelectorAll('.palmeiras-filter').forEach(btn => {
            btn.addEventListener('click', () => setPalmeirasHomeFilter(btn.dataset.palmeirasFilter || 'all'));
        });
        document.querySelectorAll('.worldcup-filter').forEach(btn => {
            btn.addEventListener('click', () => setWorldCupFilter(btn.dataset.wcFilter || 'all'));
        });
        const standingsFilters = document.getElementById('standings-filter-group');
        if (standingsFilters && !standingsFilters._delegated) {
            standingsFilters.addEventListener('click', (event) => {
                const btn = event.target.closest('[data-standings-comp]');
                if (!btn) return;
                setStandingsCompetition(btn.dataset.standingsComp || 'all');
            });
            standingsFilters._delegated = true;
        }

        const competitions = document.getElementById('competitions-overview');
        if (competitions && !competitions._delegated) {
            competitions.addEventListener('click', (event) => {
                const action = event.target.closest('[data-comp-filter]');
                if (!action) return;
                focusCompetitionCalendar(action.dataset.compFilter, action.dataset.compDate);
            });
            competitions._delegated = true;
        }

        const standings = document.getElementById('standings');
        if (standings && !standings._delegated) {
            standings.addEventListener('click', (event) => {
                const standingsAction = event.target.closest('[data-standings-comp]');
                if (standingsAction) {
                    setStandingsCompetition(standingsAction.dataset.standingsComp || 'all');
                    return;
                }

                const action = event.target.closest('[data-comp-filter]');
                if (!action) return;
                focusCompetitionCalendar(action.dataset.compFilter, action.dataset.compDate);
            });
            standings._delegated = true;
        }

        // Calendar day click — event delegation (set up once, not per render)
        const grid = document.getElementById('calendar-grid');
        if (grid && !grid._delegated) {
            grid.addEventListener('click', (e) => {
                const day = e.target.closest('.cal-day:not(.other-month)');
                if (day) {
                    toggleDay(parseInt(day.dataset.day));
                }
            });
            grid._delegated = true;
        }
    }

    function registerServiceWorker() {
        if (!('serviceWorker' in navigator)) return;

        window.addEventListener('load', () => {
            let refreshing = false;
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                if (refreshing) return;
                refreshing = true;
                window.location.reload();
            });

            navigator.serviceWorker.register('/sw.js').then((registration) => {
                if (registration.waiting) {
                    registration.waiting.postMessage({ type: 'SKIP_WAITING' });
                }
                registration.addEventListener('updatefound', () => {
                    const worker = registration.installing;
                    if (!worker) return;
                    worker.addEventListener('statechange', () => {
                        if (worker.state === 'installed' && navigator.serviceWorker.controller) {
                            worker.postMessage({ type: 'SKIP_WAITING' });
                        }
                    });
                });
            }).catch(() => {
                // The app remains usable when service-worker installation fails.
            });
        }, { once: true });
    }

    // --- Public API ---
    window.loadHero = loadHero;
    window.loadPalmeirasHome = loadPalmeirasHome;
    window.loadStandings = loadStandings;
    window.loadNews = loadNews;
    window.loadWorldCup = loadWorldCup;
    window.loadCompetitionOverview = loadCompetitionOverview;
    window.refreshAllData = refreshAllData;

    // --- Init ---
    document.addEventListener('DOMContentLoaded', () => {
        initNativeShell();
        initTheme();
        bindStaticControls();
        hydrateUrlState();
        setLastUpdated();
        initTabs();
        initStickyDesktopTabs();
        loadHero();
        loadPalmeirasHome();
        loadStandings();
        loadNews();
        loadCalendar();
        loadCompetitionOverview();
        startWorldCupRefresh();
        registerServiceWorker();
    });
})();
