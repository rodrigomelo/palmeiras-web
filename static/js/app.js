/**
 * Palmeiras Agenda v5
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
        CLI: ['CLI', 'LIBERTADORES', 'COPA_LIBERTADORES'],
        COPA: ['COPA', 'COPA_DO_BRASIL'],
        WC: ['WC', 'WORLD_CUP', 'FIFA_WORLD_CUP'],
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
        'ROUND_OF_16': 'Oitavas de Final',
        'ROUND_OF_32': '2ª Fase',
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
    const WORLD_CUP_REFRESH_MS = 15 * 60 * 1000;
    const DEFAULT_TAB = 'classificacao';
    const VALID_TABS = new Set(['classificacao', 'estatisticas', 'prediction', 'worldcup', 'news']);
    const VALID_COMP_FILTERS = new Set(['all', 'BSA', 'CLI', 'COPA', 'WC']);
    const VALID_WC_FILTERS = new Set(['all', 'upcoming', 'finished', 'brazil']);
    let _initialTab = null;
    let _isApplyingUrlState = false;
    let _heroMode = 'palmeiras';
    let _worldCupRefreshInterval = null;

    function formatStage(stage) {
        if (!stage || stage === 'REGULAR_SEASON') return '';
        return STAGE_NAMES[stage] || stage;
    }

    function getCompCode(comp) {
        return comp?.code || '';
    }

    function palmeirasQuery(path) {
        const joiner = path.includes('?') ? '&' : '?';
        return `${path}${joiner}team_id=${TEAM_ID}`;
    }

    function isPalmeirasMatch(match) {
        return match?.homeTeam?.id === TEAM_ID || match?.awayTeam?.id === TEAM_ID;
    }

    function matchDisplaySides(match) {
        const palmeirasMatch = isPalmeirasMatch(match);
        if (!palmeirasMatch) {
            return {
                leftTeam: match.homeTeam,
                rightTeam: match.awayTeam,
                leftScore: match.homeScore,
                rightScore: match.awayScore,
                perspective: 'neutral',
            };
        }

        const isHome = match.homeTeam?.id === TEAM_ID;
        return {
            leftTeam: isHome ? match.homeTeam : match.awayTeam,
            rightTeam: isHome ? match.awayTeam : match.homeTeam,
            leftScore: isHome ? match.homeScore : match.awayScore,
            rightScore: isHome ? match.awayScore : match.homeScore,
            perspective: 'palmeiras',
        };
    }

    // --- Helpers ---
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function formatDate(d) {
        return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ });
    }

    function formatTime(d) {
        return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
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
        return document.querySelector('.tab-btn.active')?.dataset.tab || DEFAULT_TAB;
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

    function updateFullUrlState() {
        updateUrlState({
            tab: currentTabId(),
            year: _calYear,
            month: _calMonth,
            comp: _calCompFilter,
            day: _calSelectedDay,
            wc: worldCupFilter,
        });
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
        if (year) _calYear = year;
        if (month) _calMonth = month;
        if (comp && VALID_COMP_FILTERS.has(comp)) _calCompFilter = comp;
        if (day && isValidDateKey(day)) _calSelectedDay = day;
        if (wc && VALID_WC_FILTERS.has(wc)) worldCupFilter = wc;

        syncYearSelect();
        syncCompLegend();
        _isApplyingUrlState = false;
    }

    // --- Theme ---
    function initTheme() {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(saved || (prefersDark ? 'dark' : 'light'));
    }

    function applyTheme(theme) {
        const toggle = document.getElementById('themeToggle');
        if (theme === 'dark') {
            document.body.classList.add('dark');
            if (toggle) toggle.textContent = '☼';
        } else {
            document.body.classList.remove('dark');
            if (toggle) toggle.textContent = '◐';
        }
        localStorage.setItem('theme', theme);
        if (performanceChart) updateChartColors();
    }

    window.toggleTheme = function () {
        applyTheme(document.body.classList.contains('dark') ? 'light' : 'dark');
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

    // --- API ---
    async function api(path, ttlMs = CACHE_TTL) {
        const cached = _apiCache[path];
        if (cached && Date.now() - cached.time < ttlMs) {
            return cached.data;
        }
        try {
            const res = await fetch(`/api/${path}`, { headers: { 'Accept': 'application/json' } });
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

        function activateTab(btn, focusTab = false) {
            tabs.forEach(tab => {
                const selected = tab === btn;
                tab.classList.toggle('active', selected);
                tab.setAttribute('aria-selected', String(selected));
                tab.tabIndex = selected ? 0 : -1;
            });

            panels.forEach(panel => {
                const selected = panel.id === btn.dataset.tab;
                panel.classList.toggle('active', selected);
                panel.toggleAttribute('hidden', !selected);
                panel.toggleAttribute('inert', !selected);
                panel.setAttribute('aria-hidden', String(!selected));
            });

            if (focusTab) btn.focus();
            if (btn.dataset.tab === 'estatisticas' && !performanceChart) {
                renderPerformanceChart();
            }
            if (btn.dataset.tab === 'prediction') {
                loadPrediction();
            }
            if (btn.dataset.tab === 'worldcup') {
                loadWorldCup();
            }
            updateUrlState({ tab: btn.dataset.tab });
        }

        tabs.forEach((btn, index) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                activateTab(btn);
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

    function refreshWorldCupData() {
        clearWorldCupCaches();
        loadHero();
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

    // --- Hero ---
    async function loadBrazilHero() {
        const path = `matches?competition=WC&from_date=${WORLD_CUP_FROM}&to_date=${WORLD_CUP_TO}&limit=200`;
        const data = await api(path, WORLD_CUP_REFRESH_MS);
        const matches = (data?.matches || []).filter(isBrazilMatch).sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
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
        const data = await api(palmeirasQuery('matches?status=SCHEDULED,TIMED,IN_PLAY,PAUSED&limit=5'));
        return {
            mode: 'palmeiras',
            match: data?.matches?.[0] || null,
            nextMatches: [],
            loaded: Boolean(data),
        };
    }

    async function loadHero() {
        const brazilHero = await loadBrazilHero();
        const heroData = brazilHero?.match ? brazilHero : await loadPalmeirasHero();
        if (!heroData?.match && heroData?.loaded === false) {
            document.getElementById('hero-comp-badge').textContent = 'Erro ao carregar';
            return;
        }

        const match = heroData?.match;
        _heroMode = heroData?.mode || 'palmeiras';

        if (!match) {
            document.getElementById('hero-comp-badge').textContent = 'Nenhum jogo agendado';
            document.getElementById('hero-teams-area').style.display = 'none';
            document.getElementById('hero-date-area').style.display = 'none';
            renderHeroBrazilNext([]);
            return;
        }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = _heroMode === 'brazil' ? 'Copa do Mundo 2026 · Brasil' : CONFIG.formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = LIVE_STATUSES.has(match.status);
        const isPaused = match.status === 'PAUSED';
        const score = match.score?.fullTime || {};
        const ht = match.score?.halfTime || {};
        const venue = CONFIG.getVenue(match);
        const stageLabel = formatStage(match.stage);

        const heroCard = document.getElementById('hero-match');
        heroCard?.classList.toggle('live', isLive);
        document.getElementById('hero-teams-area').style.display = '';
        document.getElementById('hero-date-area').style.display = '';

        // Competition badge
        const liveBadge = isLive
            ? `<span class="live-dot"></span> ${isPaused ? 'INTERVALO' : 'AO VIVO'} · `
            : '';
        document.getElementById('hero-comp-badge').innerHTML = liveBadge + escapeHtml(comp);

        // Home team
        const homeEl = document.getElementById('hero-home');
        homeEl.querySelector('img').src = CONFIG.getCrest(home);
        homeEl.querySelector('img').alt = escapeHtml(CONFIG.teamName(home));
        homeEl.querySelector('.hero-team-name').textContent = CONFIG.teamName(home);

        // Away team
        const awayEl = document.getElementById('hero-away');
        awayEl.querySelector('img').src = CONFIG.getCrest(away);
        awayEl.querySelector('img').alt = escapeHtml(CONFIG.teamName(away));
        awayEl.querySelector('.hero-team-name').textContent = CONFIG.teamName(away);

        // Score / VS
        const scoreArea = document.getElementById('hero-score-area');
        if (isLive) {
            const minute = estimateMinute(match.utcDate);
            const minuteLabel = isPaused ? 'Intervalo' : minute;
            scoreArea.innerHTML = `
                <div class="hero-score live-score">${score.home ?? 0} <span class="score-sep">×</span> ${score.away ?? 0}</div>
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

        if (isLive) startLiveRefresh(); else stopLiveRefresh();

        // Start countdown for upcoming matches
        if (!isLive) {
            startCountdown(match.utcDate);
        } else {
            document.getElementById('hero-countdown').style.display = 'none';
        }

        renderHeroBrazilNext(_heroMode === 'brazil' ? heroData.nextMatches : []);
    }

    function renderHeroBrazilNext(matches) {
        const widget = document.getElementById('hero-brazil-next');
        const list = document.getElementById('hero-brazil-list');
        const formWidget = document.getElementById('form-widget');
        if (!widget || !list) return;

        if (!matches.length) {
            widget.style.display = 'none';
            if (_heroMode !== 'brazil' && formWidget?.querySelector('.form-dot')) formWidget.style.display = '';
            return;
        }

        if (formWidget) formWidget.style.display = 'none';
        list.innerHTML = matches.map(match => {
            const date = new Date(match.utcDate).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', timeZone: BR_TZ });
            const home = CONFIG.teamName(match.homeTeam);
            const away = CONFIG.teamName(match.awayTeam);
            return `<div class="hero-brazil-item">
                <span>${escapeHtml(date)} · ${escapeHtml(formatTime(match.utcDate))}</span>
                <strong>${escapeHtml(home)} x ${escapeHtml(away)}</strong>
            </div>`;
        }).join('');
        widget.style.display = '';
    }

    // --- Countdown Timer ---
    let _countdownInterval = null;

    function startCountdown(utcDate) {
        if (_countdownInterval) clearInterval(_countdownInterval);
        const target = new Date(utcDate).getTime();
        const el = document.getElementById('hero-countdown');

        function tick() {
            const now = Date.now();
            const diff = target - now;
            if (diff <= 0) {
                el.style.display = 'none';
                clearInterval(_countdownInterval);
                _countdownInterval = null;
                // Reload hero — match might be starting
                loadHero();
                return;
            }
            el.style.display = '';
            const d = Math.floor(diff / 86400000);
            const h = Math.floor((diff % 86400000) / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            // Desktop: full labels; Mobile: hidden via CSS, compact separators
            document.getElementById('cd-days').textContent = d;
            document.getElementById('cd-hours').textContent = String(h).padStart(2, '0');
            document.getElementById('cd-mins').textContent = String(m).padStart(2, '0');
            document.getElementById('cd-secs').textContent = String(s).padStart(2, '0');
        }
        tick();
        _countdownInterval = setInterval(tick, 1000);
    }

    // --- Form Widget (last 5 results) ---
    async function loadFormWidget() {
        const data = await api(palmeirasQuery('matches?status=FINISHED&limit=5'));

        const widget = document.getElementById('form-widget');
        const dots = document.getElementById('form-dots');
        if (!widget || !dots) return;
        if (_heroMode === 'brazil') {
            widget.style.display = 'none';
            return;
        }
        if (!data?.matches?.length) return;

        dots.innerHTML = '';
        data.matches.forEach(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
            const opp = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);
            const r = our > opp ? 'W' : our < opp ? 'L' : 'D';
            const label = r === 'W' ? 'V' : r === 'L' ? 'D' : 'E';
            const cls = r === 'W' ? 'win' : r === 'L' ? 'loss' : 'draw';
            const tooltip = `${isHome ? 'Casa' : 'Fora'} ${our}-${opp} vs ${escapeHtml(isHome ? CONFIG.teamName(m.awayTeam) : CONFIG.teamName(m.homeTeam))}`;
            dots.innerHTML += `<span class="form-dot ${cls}" title="${tooltip}">${label}</span>`;
        });
        widget.style.display = '';
    }

    // --- Standings ---
    async function loadStandings() {
        showSkeleton('standings');
        const data = await api('standings?competition=BSA');
        if (!data) { showError('standings', 'Erro ao carregar', 'loadStandings'); return; }
        const rows = data.standings || [];
        const team = rows.find(s => s.teamId === TEAM_ID);
        if (!team) { showEmpty('standings', 'Dados indisponíveis'); return; }

        const gd = team.goalDifference;
        const avg = team.playedGames > 0 ? (team.points / team.playedGames).toFixed(2) : '0';

        const tableHtml = rows.map(s => {
            const isPalmeiras = s.teamId === TEAM_ID;
            return `<div class="standings-row ${isPalmeiras ? 'palmeiras' : ''}">
                <span class="pos">${s.position}</span>
                <span class="team">${escapeHtml(s.teamShort || s.teamName)}</span>
                <span class="stats">
                    <span>J${s.playedGames}</span>
                    <span style="color:var(--win)">V${s.won}</span>
                    <span style="color:var(--draw)">E${s.draw}</span>
                    <span style="color:var(--loss)">D${s.lost}</span>
                    <span>SG${s.goalDifference >= 0 ? '+' : ''}${s.goalDifference}</span>
                </span>
                <span class="pts">${s.points}</span>
            </div>`;
        }).join('');

        document.getElementById('standings').innerHTML = `
            <div style="text-align:center;margin-bottom:1.5rem">
                <div class="position-badge">${team.position}º</div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="stat-value">${team.points}</div><div class="stat-label">Pontos</div></div>
                    <div class="stat-box"><div class="stat-value">${team.playedGames}</div><div class="stat-label">Jogos</div></div>
                    <div class="stat-box"><div class="stat-value">${avg}</div><div class="stat-label">Pts/Jogo</div></div>
                </div>
                <div class="stats-grid" style="margin-top:0.5rem">
                    <div class="stat-box"><div class="stat-value" style="color:var(--win)">${team.won}</div><div class="stat-label">Vitórias</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:var(--draw)">${team.draw}</div><div class="stat-label">Empates</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:var(--loss)">${team.lost}</div><div class="stat-label">Derrotas</div></div>
                </div>
                <div class="stats-grid" style="margin-top:0.5rem">
                    <div class="stat-box"><div class="stat-value">${team.goalsFor}</div><div class="stat-label">Gols Pro</div></div>
                    <div class="stat-box"><div class="stat-value">${team.goalsAgainst}</div><div class="stat-label">Gols Contra</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:${gd >= 0 ? 'var(--win)' : 'var(--loss)'}">${gd >= 0 ? '+' : ''}${gd}</div><div class="stat-label">Saldo</div></div>
                </div>
            </div>
            <div style="border-top:1px solid var(--bg);padding-top:1rem">${tableHtml}</div>`;
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
    async function renderPerformanceChart() {
        const container = document.getElementById('team-stats');
        if (!container) return;

        // Show loading state while Chart.js loads
        if (!chartJsLoaded) {
            container.innerHTML = '<div class="empty" style="padding:2rem">Carregando gráficos...</div>';
            try { await loadChartJs(); } catch {
                container.innerHTML = '<div class="empty" style="padding:2rem">Erro ao carregar gráficos</div>';
                return;
            }
        }

        const data = await api(palmeirasQuery('matches?status=FINISHED&limit=38'));
        if (!data || !data.matches?.length) {
            container.innerHTML = '<div class="empty" style="padding:2rem">Sem dados suficientes</div>';
            return;
        }

        const allMatches = data.matches;
        const bsaMatches = allMatches
            .filter(m => m.competition?.code === 'BSA')
            .sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));

        // Comprehensive stats across ALL competitions
        let wins = 0, draws = 0, losses = 0, goalsFor = 0, goalsAgainst = 0;
        let homeWins = 0, homeDraws = 0, homeLosses = 0, homeGF = 0, homeGA = 0;
        let awayWins = 0, awayDraws = 0, awayLosses = 0, awayGF = 0, awayGA = 0;
        const form = [];

        allMatches.forEach(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
            const opp = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);

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

        // Stats summary
        let html = `
        <div class="stats-summary">
            <div class="stats-grid">
                <div class="stat-box"><div class="stat-value">${total}</div><div class="stat-label">Jogos</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--win)">${wins}</div><div class="stat-label">Vitórias</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--draw)">${draws}</div><div class="stat-label">Empates</div></div>
                <div class="stat-box"><div class="stat-value" style="color:var(--loss)">${losses}</div><div class="stat-label">Derrotas</div></div>
                <div class="stat-box"><div class="stat-value">${goalsFor}</div><div class="stat-label">Gols Pro</div></div>
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
                <div class="stats-col-title">📋 Forma Recente</div>
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
                const our = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
                const opp = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);
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

            const ctx = document.getElementById('performanceCanvas')?.getContext('2d');
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

    // --- News ---
    async function loadNews() {
        showSkeleton('news-list');
        const data = await api('news');
        const items = Array.isArray(data) ? data : (data?.news || []);
        if (!items.length) { showEmpty('news-list', 'Nenhuma notícia'); return; }

        document.getElementById('news-list').innerHTML = items.slice(0, 12).map(n => {
            const source = n.source || 'ge.globo';
            const safeTitle = escapeHtml(n.title);
            const safeSource = escapeHtml(source);
            return `<a class="news-item" href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer">
                <div class="news-title">${safeTitle}</div>
                <div class="news-meta"><span class="news-source">${safeSource}</span></div>
            </a>`;
        }).join('');

        // Delegated click handler is no longer needed — <a> handles natively
    }

    // --- Prediction ---
    async function loadPrediction() {
        showPredictionLoading();
        
        try {
            // Fetch all required data in parallel
            const [upcomingData, recentData, standingsData] = await Promise.all([
                api(palmeirasQuery('matches?status=SCHEDULED,TIMED&limit=5')),
                api(palmeirasQuery('matches?status=FINISHED&limit=8')),
                api('standings?competition=BSA')
            ]);

            // Find next Palmeiras match
            const nextMatch = findNextPalmeirasMatch(upcomingData?.matches || []);
            if (!nextMatch) {
                showPredictionEmpty();
                return;
            }

            // Calculate prediction
            const prediction = calculatePrediction(nextMatch, recentData?.matches || [], standingsData?.standings || []);
            
            // Render prediction UI
            renderPrediction(nextMatch, prediction);
            
        } catch (error) {
            showError('prediction-content', 'Erro ao carregar palpites', 'loadPrediction');
        }
    }

    function findNextPalmeirasMatch(matches) {
        return matches.find(m => m.homeTeam?.id === CONFIG.TEAM_ID || m.awayTeam?.id === CONFIG.TEAM_ID);
    }

    function calculatePrediction(match, recentMatches, standings) {
        const isPalmerasHome = match.homeTeam?.id === CONFIG.TEAM_ID;
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
        const opponentStanding = standings.find(s => s.teamId === opponent?.id);
        
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
        
        return { probs, factors, isPalmerasHome };
    }

    function calculateFormAdjustment(recentMatches) {
        // Get last 5 Palmeiras matches
        const palmeirasMatches = recentMatches
            .filter(m => m.homeTeam?.id === CONFIG.TEAM_ID || m.awayTeam?.id === CONFIG.TEAM_ID)
            .slice(0, 5);

        if (palmeirasMatches.length === 0) return 0;

        let formPoints = 0;
        let matchCount = 0;

        palmeirasMatches.forEach(match => {
            if (match.score?.fullTime) {
                const palmeirasIsHome = match.homeTeam?.id === CONFIG.TEAM_ID;
                const palmeirasScore = palmeirasIsHome ? match.score.fullTime.home : match.score.fullTime.away;
                const opponentScore = palmeirasIsHome ? match.score.fullTime.away : match.score.fullTime.home;

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
            .filter(m => m.homeTeam?.id === CONFIG.TEAM_ID || m.awayTeam?.id === CONFIG.TEAM_ID)
            .slice(0, 5);

        let wins = 0, draws = 0, losses = 0;
        palmeirasMatches.forEach(match => {
            if (match.score?.fullTime) {
                const palmeirasIsHome = match.homeTeam?.id === CONFIG.TEAM_ID;
                const palmeirasScore = palmeirasIsHome ? match.score.fullTime.home : match.score.fullTime.away;
                const opponentScore = palmeirasIsHome ? match.score.fullTime.away : match.score.fullTime.home;

                if (palmeirasScore > opponentScore) wins++;
                else if (palmeirasScore === opponentScore) draws++;
                else losses++;
            }
        });

        if (wins + draws + losses > 0) {
            factors.push(`Forma: ${wins}V ${draws}E ${losses}D`);
        }

        // Home/Away
        factors.push(isPalmerasHome ? 'Casa' : 'Fora');

        // Table positions if available
        if (palmeirasStanding && opponentStanding) {
            factors.push(`Tabela: ${palmeirasStanding.position}º x ${opponentStanding.position}º`);
        }

        return factors.slice(0, 3); // Limit to 3 factors
    }

    function renderPrediction(match, prediction) {
        const { probs, factors, isPalmerasHome } = prediction;
        const opponent = isPalmerasHome ? match.awayTeam : match.homeTeam;
        
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

        // Match title
        const matchTitle = isPalmerasHome 
            ? `Palmeiras x ${escapeHtml(opponent?.shortName || opponent?.name || 'Adversário')}`
            : `${escapeHtml(opponent?.shortName || opponent?.name || 'Adversário')} x Palmeiras`;

        // Format probabilities as percentages
        const winPct = Math.round(probs.win * 100);
        const drawPct = Math.round(probs.draw * 100);
        const lossPct = Math.round(probs.loss * 100);

        const factorsHtml = factors.map(f => `<span class="prediction-factor">${escapeHtml(f)}</span>`).join('');

        document.getElementById('prediction-content').innerHTML = `
            <div class="prediction-card">
                <div class="prediction-match">${matchTitle}</div>
                ${confidenceBadge}
                
                <div class="prediction-probs">
                    <div class="prob-box ${probs.win === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${winPct}%</div>
                        <div class="prob-label">Vitória</div>
                    </div>
                    <div class="prob-box ${probs.draw === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${drawPct}%</div>
                        <div class="prob-label">Empate</div>
                    </div>
                    <div class="prob-box ${probs.loss === maxProb ? 'primary' : ''}">
                        <div class="prob-value">${lossPct}%</div>
                        <div class="prob-label">Derrota</div>
                    </div>
                </div>
                
                ${factors.length > 0 ? `<div class="prediction-factors">${factorsHtml}</div>` : ''}
                
                <div class="prediction-note">
                    Estimativa baseada em forma recente, mando de campo e tabela quando disponível.
                </div>
            </div>
        `;
    }

    function showPredictionLoading() {
        document.getElementById('prediction-content').innerHTML = '<div class="empty">Carregando...</div>';
    }

    function showPredictionEmpty() {
        document.getElementById('prediction-content').innerHTML = '<div class="empty">Nenhum jogo agendado para palpite</div>';
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
        const tla = String(team?.tla || '').toUpperCase();
        const name = String(team?.name || '').toLowerCase();
        const shortName = String(team?.shortName || '').toLowerCase();
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

        return `<article class="worldcup-match${liveClass}">
            <div class="worldcup-match-time">${time}</div>
            <div class="worldcup-match-body">
                <div class="worldcup-teams">
                    <span class="worldcup-team">
                        <img src="${CONFIG.getCrest(match.homeTeam)}" alt="">
                        <span>${escapeHtml(CONFIG.teamName(match.homeTeam))}</span>
                    </span>
                    <strong class="worldcup-score">${escapeHtml(score)}</strong>
                    <span class="worldcup-team away">
                        <span>${escapeHtml(CONFIG.teamName(match.awayTeam))}</span>
                        <img src="${CONFIG.getCrest(match.awayTeam)}" alt="">
                    </span>
                </div>
                <div class="worldcup-match-meta">
                    <span>${escapeHtml(stageLabel)}</span>
                    <span>${escapeHtml(statusText)}</span>
                    <span>${escapeHtml(venue)}</span>
                </div>
            </div>
        </article>`;
    }

    function renderBrazilNextGames() {
        const container = document.getElementById('worldcup-brazil-matches');
        const summary = document.getElementById('worldcup-brazil-summary');
        if (!container) return;

        const allBrazil = worldCupMatches.filter(isBrazilMatch).sort((a, b) => new Date(a.utcDate) - new Date(b.utcDate));
        const upcomingBrazil = nextBrazilMatches(3);

        if (summary) {
            summary.textContent = allBrazil.length
                ? `${upcomingBrazil.length} próximos · ${allBrazil.length} jogos do Brasil na tabela`
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

        return `<article class="worldcup-brazil-card">
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
        </article>`;
    }

    function setWorldCupFilter(filter) {
        worldCupFilter = filter || 'all';
        renderWorldCup();
        updateUrlState({ tab: 'worldcup', wc: worldCupFilter });
    }

    function openWorldCupCalendar() {
        _calYear = 2026;
        _calMonth = 6;
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        window.filterSharedComp('WC');
        updateUrlState({ tab: currentTabId(), year: _calYear, month: _calMonth, comp: 'WC', day: null });
        document.getElementById('calendar-hub')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // --- Calendar ---
    const COMP_DOT_CLASS = {
        BSA: 'bsa',
        CLI: 'cli',
        COPA: 'copa',
        COPA_DO_BRASIL: 'copa',
        WC: 'wc',
    };

    const STATUS_LABEL = {
        SCHEDULED: 'Agendado',
        TIMED: 'Agendado',
        IN_PLAY: 'AO VIVO',
        FINISHED: 'Finalizado',
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

        const data = await api(`calendar_monthly?year=${_calYear}&month=${_calMonth}`);
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
            let matches = data.days[dayStr] || [];

            // Apply competition filter (fuzzy match via COMP_MAP)
            if (_calCompFilter !== 'all') {
                const allowedCodes = COMP_MAP[_calCompFilter] || [_calCompFilter];
                matches = matches.filter(m => allowedCodes.includes(m.competition?.code));
            }

            const comps = [...new Set(matches.map(m => m.competition?.code || 'OTHER'))];
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
                const scoreText = `AO VIVO ${sides.leftScore ?? 0}–${sides.rightScore ?? 0}`;
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
                todayCell?.classList.add('selected');
                todayCell?.setAttribute('aria-pressed', 'true');
                // Show expanded view for today's matches
                renderExpandedDay(todayStr);
            }
        } else {
            document.getElementById('calendar-expanded').innerHTML = '';
        }
    }

    function toggleDay(day) {
        const dayStr = `${_calYear}-${String(_calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        if (_calSelectedDay === dayStr) {
            _calSelectedDay = null;
            document.getElementById('calendar-expanded').innerHTML = '';
        } else {
            _calSelectedDay = dayStr;
            renderExpandedDay(dayStr);
            
            // Auto-scroll to expanded section on mobile after DOM update
            if (window.matchMedia('(max-width: 600px)').matches) {
                requestAnimationFrame(() => {
                    const expandedEl = document.getElementById('calendar-expanded');
                    if (expandedEl && expandedEl.firstElementChild) {
                        expandedEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            }
        }
        
        // Update selected state - only add if day is still selected
        document.querySelectorAll('.cal-day').forEach(d => {
            d.classList.remove('selected');
            d.setAttribute('aria-pressed', 'false');
        });
        if (_calSelectedDay) {
            const selectedCell = document.querySelector(`.cal-day[data-day="${day}"]`);
            selectedCell?.classList.add('selected');
            selectedCell?.setAttribute('aria-pressed', 'true');
        }
        updateUrlState({ year: _calYear, month: _calMonth, day: _calSelectedDay });
    }

    function renderExpandedDay(dayStr) {
        let matches = _calData?.days?.[dayStr] || [];

        // Apply competition filter (fuzzy match via COMP_MAP)
        if (_calCompFilter !== 'all') {
            const allowedCodes = COMP_MAP[_calCompFilter] || [_calCompFilter];
            matches = matches.filter(m => allowedCodes.includes(m.competition?.code));
        }

        const container = document.getElementById('calendar-expanded');

        if (!matches.length) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `<div class="cal-expanded">
            <div class="cal-expanded-header">
                <span class="cal-expanded-date">${dayStr.split('-').reverse().join('/')}</span>
            </div>
            ${matches.filter(m => m?.homeTeam && m?.awayTeam).map(m => {
                const time = new Date(m.utcDate).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: CONFIG.BR_TZ });
                const sides = matchDisplaySides(m);
                const stageLabel = formatStage(m.stage);

                const scoreHtml = FINISHED_STATUSES.has(m.status) && sides.leftScore != null
                    ? `<span class="cal-match-score">${sides.leftScore}–${sides.rightScore}</span>`
                    : '';

                const statusText = STATUS_LABEL[m.status] || m.status;
                const compClass = getCompBadgeClass(m.competition?.code);
                const statusClass = LIVE_STATUSES.has(m.status) ? 'live' : '';

                return `<div class="cal-match ${compClass}">
                    <div class="cal-match-time">${time}</div>
                    <div class="cal-match-comp ${compClass}">${escapeHtml(stageLabel || CONFIG.formatComp(m.competition))}</div>
                    <div class="cal-match-teams">
                        <img class="cal-match-crest" src="${CONFIG.getCrest(sides.leftTeam)}" alt="">
                        <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(sides.leftTeam))}</span>
                        <span class="cal-match-vs">×</span>
                        <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(sides.rightTeam))}</span>
                        <img class="cal-match-crest" src="${CONFIG.getCrest(sides.rightTeam)}" alt="">
                        ${scoreHtml}
                    </div>
                    <div class="cal-match-status ${statusClass}">${statusText}</div>
                </div>`;
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
    document.getElementById('cal-prev')?.addEventListener('click', () => {
        _calMonth--;
        if (_calMonth < 1) { _calMonth = 12; _calYear--; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
        updateUrlState({ year: _calYear, month: _calMonth, day: null });
    });
    document.getElementById('cal-next')?.addEventListener('click', () => {
        _calMonth++;
        if (_calMonth > 12) { _calMonth = 1; _calYear++; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
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

    window.downloadCalendar = async function () {
        try {
            const res = await fetch('/api/calendar.ics');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = new Blob([await res.text()], { type: 'text/calendar' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'palmeiras.ics';
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) { alert('Erro: ' + e.message); }
    };

    window.copyCalendarUrl = async function () {
        const url = window.location.origin + '/api/calendar.ics';
        try {
            await navigator.clipboard.writeText(url);
            alert('Link copiado!');
        } catch {
            prompt('Copie:', url);
        }
    };

    window.copyStateUrl = async function () {
        updateFullUrlState();
        const url = window.location.href;
        try {
            await navigator.clipboard.writeText(url);
            alert('Estado copiado!');
        } catch {
            prompt('Copie:', url);
        }
    };

    function bindStaticControls() {
        document.getElementById('themeToggle')?.addEventListener('click', window.toggleTheme);
        document.getElementById('refreshButton')?.addEventListener('click', () => window.location.reload());
        document.getElementById('cal-year-select')?.addEventListener('change', (event) => {
            window.changeCalYear(event.target.value);
        });
        document.getElementById('downloadCalendarButton')?.addEventListener('click', window.downloadCalendar);
        document.getElementById('copyCalendarUrlButton')?.addEventListener('click', window.copyCalendarUrl);
        document.getElementById('copyStateUrlButton')?.addEventListener('click', window.copyStateUrl);
        document.getElementById('worldcupFilterCalendar')?.addEventListener('click', openWorldCupCalendar);
        document.getElementById('worldcupIcsButton')?.addEventListener('click', window.downloadCalendar);
        document.getElementById('worldcupBrazilFilter')?.addEventListener('click', () => setWorldCupFilter('brazil'));
        document.querySelectorAll('.worldcup-filter').forEach(btn => {
            btn.addEventListener('click', () => setWorldCupFilter(btn.dataset.wcFilter || 'all'));
        });

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

    // --- Public API ---
    window.loadHero = loadHero;
    window.loadStandings = loadStandings;
    window.loadNews = loadNews;
    window.loadPrediction = loadPrediction;
    window.loadWorldCup = loadWorldCup;

    // --- Init ---
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        bindStaticControls();
        hydrateUrlState();
        setLastUpdated();
        initTabs();
        loadHero();
        loadFormWidget();
        loadStandings();
        loadNews();
        loadCalendar();
        startWorldCupRefresh();
    });
})();
