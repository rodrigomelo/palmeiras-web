/**
 * Palmeiras Agenda v5
 */
(function () {
    'use strict';

    const TEAM_ID = CONFIG.TEAM_ID;
    const BR_TZ = CONFIG.BR_TZ;
    let liveInterval = null;
    let performanceChart = null;

    // --- Competition Codes ---
    const COMP_MAP = {
        BSA: ['BSA'],
        CLI: ['CLI', 'LIBERTADORES', 'COPA_LIBERTADORES'],
        COPA: ['COPA', 'COPA_DO_BRASIL'],
    };

    function getCompCode(comp) {
        return comp?.code || '';
    }

    function matchCompetition(match, comp) {
        if (comp === 'all') return true;
        const code = getCompCode(match.competition);
        return (COMP_MAP[comp] || []).includes(code);
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
            if (toggle) toggle.textContent = '☀️';
        } else {
            document.body.classList.remove('dark');
            if (toggle) toggle.textContent = '🌙';
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
        el.innerHTML = `<div class="error-state"><div class="error-icon">⚠️</div><div class="error-message">${escapeHtml(msg)}</div>${fn ? `<button class="retry-btn" onclick="${fn}()">Tentar novamente</button>` : ''}</div>`;
    }

    function showEmpty(id, msg) {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = `<div class="empty">${escapeHtml(msg)}</div>`;
    }

    // --- API ---
    async function api(path) {
        try {
            const res = await fetch(`/api/${path}${path.includes('?') ? '&' : '?'}_t=${Date.now()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`API [${path}]:`, e);
            return null;
        }
    }

    // --- Tabs ---
    function initTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                const tab = document.getElementById(btn.dataset.tab);
                tab?.classList.add('active');
                if (btn.dataset.tab === 'estatisticas' && !performanceChart) {
                    renderPerformanceChart();
                }
                if (btn.dataset.tab === 'calendario' && !_calendarLoaded) {
                    _calendarLoaded = true;
                    loadCalendar();
                }
                // Load mini strip when "Próximos" tab is first shown
                if (btn.dataset.tab === 'proximos') {
                    loadMiniStrip();
                }
            });
        });
    }

    // --- Live Refresh ---
    function startLiveRefresh() {
        if (!liveInterval) liveInterval = setInterval(loadHero, 30000);
    }

    function stopLiveRefresh() {
        if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
    }

    // --- Hero ---
    async function loadHero() {
        showSkeleton('hero-front', 'hero');
        const data = await api('matches?status=SCHEDULED,TIMED,IN_PLAY&limit=5');
        if (!data) { showError('hero-front', 'Erro ao carregar', 'loadHero'); return; }
        const match = data.matches?.[0];
        if (!match) { showEmpty('hero-front', 'Nenhum jogo agendado'); return; }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = CONFIG.formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = match.status === 'IN_PLAY';
        const score = match.score?.fullTime || {};
        const ht = match.score?.halfTime || {};
        const venue = CONFIG.getVenue(match);

        const heroCard = document.getElementById('hero-match');
        heroCard?.classList.toggle('live', isLive);

        const liveBadge = isLive ? '<span class="live-dot"></span>AO VIVO' : '';
        const minute = isLive ? estimateMinute(match.utcDate) : null;

        const infoWatch = document.getElementById('where-watch');
        const infoStadium = document.getElementById('stadium-info');
        if (infoWatch) infoWatch.textContent = match.broadcast || 'Rodada ' + (match.matchday || '-');
        if (infoStadium) infoStadium.textContent = venue;

        let scoreHtml;
        if (isLive) {
            scoreHtml = `<div class="hero-score">${score.home ?? 0} × ${score.away ?? 0}</div>`;
            if (minute) scoreHtml += `<div class="hero-minute">${minute}</div>`;
        } else {
            scoreHtml = `<div class="hero-vs">×</div>`;
        }

        document.getElementById('hero-front').innerHTML = `
            <div class="hero-comp">${liveBadge ? liveBadge + ' · ' : ''}${escapeHtml(comp)}</div>
            <div class="hero-teams">
                <div class="hero-team">
                    <img src="${CONFIG.getCrest(home)}" style="width:56px;height:56px" alt="${escapeHtml(CONFIG.teamName(home))}">
                    <div class="hero-team-name">${escapeHtml(CONFIG.teamName(home))}</div>
                </div>
                ${scoreHtml}
                <div class="hero-team">
                    <img src="${CONFIG.getCrest(away)}" style="width:56px;height:56px" alt="${escapeHtml(CONFIG.teamName(away))}">
                    <div class="hero-team-name">${escapeHtml(CONFIG.teamName(away))}</div>
                </div>
            </div>
            <div class="hero-date">${isLive ? 'JOGANDO AGORA' : formatDate(match.utcDate) + ' · ' + formatTime(match.utcDate)}<span style="display:block;font-size:0.85rem;opacity:0.8;margin-top:0.3rem;font-weight:400">${isLive ? '' : dayOfWeek}</span></div>`;

        const htScore = (ht.home != null && ht.away != null) ? `<p style="margin:0.5rem 0"><strong>1º tempo:</strong> ${ht.home}–${ht.away}</p>` : '';
        document.getElementById('hero-back').innerHTML = `
            <div style="padding-top:1rem"><h3 style="margin-bottom:1rem">Detalhes do Jogo</h3>
            <p style="margin:0.5rem 0"><strong>Rodada:</strong> ${match.matchday || '-'}</p>
            <p style="margin:0.5rem 0"><strong>Estádio:</strong> ${escapeHtml(venue)}</p>
            <p style="margin:0.5rem 0"><strong>Competição:</strong> ${escapeHtml(comp)}</p>
            <p style="margin:0.5rem 0"><strong>Transmissão:</strong> ${escapeHtml(match.broadcast || 'A confirmar')}</p>
            ${htScore}
            ${match.stage && match.stage !== 'REGULAR_SEASON' ? `<p style="margin:0.5rem 0"><strong>Fase:</strong> ${escapeHtml(match.stage)}</p>` : ''}</div>`;

        if (isLive) startLiveRefresh(); else stopLiveRefresh();
    }

    // --- Match HTML Builder ---
    function buildMatchHtml(m, isLive) {
        const venue = CONFIG.getVenue(m);
        const isFinished = m.status === 'FINISHED';
        const isPast = isFinished || m.status === 'PLAYING_TIME_FINISHED';

        // Build match-header (status badge + date/time + competition)
        let statusLabel = '';
        if (isLive) statusLabel = '<span class="live-dot"></span>AO VIVO · ';
        else if (isPast) statusLabel = '✅ FINALIZADO · ';
        const score = m.score?.fullTime;
        const ht = m.score?.halfTime || {};
        const htInfo = (ht.home != null) ? `<div class="match-extra-row"><span class="icon">⏱️</span> 1º tempo: ${ht.home}–${ht.away}</div>` : '';

        // Teams row with optional score for finished/live matches
        let teamsHtml;
        if (isPast && score?.home != null) {
            teamsHtml = `<div class="match-teams">
                <span><img src="${CONFIG.getCrest(m.homeTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-right:4px" alt="">${escapeHtml(CONFIG.teamName(m.homeTeam))}</span>
                <span class="match-score-badge">${score.home} × ${score.away}</span>
                <span>${escapeHtml(CONFIG.teamName(m.awayTeam))}<img src="${CONFIG.getCrest(m.awayTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-left:4px" alt=""></span>
            </div>`;
        } else {
            teamsHtml = `<div class="match-teams">
                <span><img src="${CONFIG.getCrest(m.homeTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-right:4px" alt="">${escapeHtml(CONFIG.teamName(m.homeTeam))}</span>
                <span style="color:var(--text-muted)">×</span>
                <span>${escapeHtml(CONFIG.teamName(m.awayTeam))}<img src="${CONFIG.getCrest(m.awayTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-left:4px" alt=""></span>
            </div>`;
        }

        return `<div class="match-item">
            <div class="match-extra">
                <div class="match-extra-row"><span class="icon">🏟️</span> ${escapeHtml(venue)}</div>
                <div class="match-extra-row"><span class="icon">📺</span> ${escapeHtml(m.broadcast || 'A confirmar')}</div>
                <div class="match-extra-row"><span class="icon">🔢</span> Rodada ${m.matchday || '-'}${m.stage && m.stage !== 'REGULAR_SEASON' ? ' · ' + escapeHtml(m.stage) : ''}</div>
                ${htInfo}
            </div>
            <div class="match-header"><span>${statusLabel}${formatDate(m.utcDate)}${!isPast ? ' · ' + formatTime(m.utcDate) : ''}</span><span>${escapeHtml(CONFIG.formatComp(m.competition))}</span></div>
            ${teamsHtml}
        </div>`;
    }

    // --- Matches ---
    let _allMatches = [];

    async function loadMatches() {
        showSkeleton('next-matches');
        const data = await api('matches?status=SCHEDULED,TIMED,IN_PLAY&limit=20');
        if (!data) { showError('next-matches', 'Erro ao carregar', 'loadMatches'); return; }
        const allMatches = data.matches || [];
        _allMatches = allMatches.slice(1); // Skip first (shown in hero)

        // Pre-load current month calendar data so day-filter works (uses _calData for complete month data)
        if (!_calData) {
            const today = new Date();
            const calData = await api(`calendar_monthly?year=${today.getFullYear()}&month=${today.getMonth() + 1}`);
            if (calData) {
                _calYear = today.getFullYear();
                _calMonth = today.getMonth() + 1;
                _calData = calData;
            }
        }

        // Reset all filters and apply unified filter
        clearListDayFilter();
        applyMatchFilter(_sharedCompFilter);
    }

    window.filterMatches = function (comp, btn) {
        // Support both old .comp-filter buttons and new .comp-legend-item
        const container = document.getElementById('proximos');
        container.querySelectorAll('.comp-filter, .comp-legend-item').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        // Also activate the matching legend item if using old filter
        container.querySelector(`.comp-legend-item[data-comp="${comp}"]`)?.classList.add('active');
        // Update shared comp filter and apply with current day filter
        _sharedCompFilter = comp;
        clearListDayFilter(); // changing competition resets day filter
        applyMatchFilter(comp);
    };

    function applyMatchFilter(comp) {
        const filtered = _allMatches.filter(m => matchCompetition(m, comp));
        if (!filtered.length) {
            showEmpty('next-matches', 'Nenhum jogo para esta competição');
            return;
        }
        document.getElementById('next-matches').innerHTML = filtered.map(m => buildMatchHtml(m, m.status === 'IN_PLAY')).join('');
        attachMatchListeners('next-matches');
    }

    // --- Results ---
    let _allResults = [];

    async function loadResults() {
        showSkeleton('recent-results');
        const data = await api('matches?status=FINISHED&limit=20');
        if (!data) { showError('recent-results', 'Erro ao carregar', 'loadResults'); return; }
        _allResults = data.matches || [];
        applyResultFilter('all');
    }

    window.filterResults = function (comp, btn) {
        document.querySelectorAll('#resultados .comp-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyResultFilter(comp);
    };

    function applyResultFilter(comp) {
        const filtered = _allResults.filter(m => matchCompetition(m, comp));
        if (!filtered.length) {
            showEmpty('recent-results', 'Nenhum resultado para esta competição');
            return;
        }
        document.getElementById('recent-results').innerHTML = filtered.map(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
            const opp = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);
            const oppName = isHome ? CONFIG.teamName(m.awayTeam) : CONFIG.teamName(m.homeTeam);
            const r = our > opp ? 'V' : our < opp ? 'D' : 'E';
            const resultClass = r === 'V' ? 'win' : r === 'D' ? 'loss' : 'draw';
            const ht = m.score?.halfTime || {};
            const htInfo = (ht.home != null) ? `<div class="match-extra-row"><span class="icon">⏱️</span> 1º tempo: ${ht.home}–${ht.away}</div>` : '';

            return `<div class="match-item ${resultClass}">
                <div class="match-extra">
                    <div class="match-extra-row"><span class="icon">🏟️</span> ${escapeHtml(m.venue || 'A definir')}</div>
                    <div class="match-extra-row"><span class="icon">📺</span> ${escapeHtml(m.broadcast || 'A confirmar')}</div>
                    <div class="match-extra-row"><span class="icon">🔢</span> Rodada ${m.matchday || '-'}</div>
                    ${htInfo}
                </div>
                <div class="match-header"><span>${formatDate(m.utcDate)}</span><span>${escapeHtml(CONFIG.formatComp(m.competition))}</span></div>
                <div class="match-teams">
                    <span>${isHome ? '🏠' : '✈️'} ${escapeHtml(oppName)}</span>
                    <span style="display:flex;align-items:center;gap:0.5rem">
                        <span class="result-badge ${resultClass}">${r === 'V' ? '✅ V' : r === 'D' ? '❌ D' : '➖ E'}</span>
                        <span class="match-score">${our} – ${opp}</span>
                    </span>
                </div>
            </div>`;
        }).join('');
        attachMatchListeners('recent-results');
    }

    function attachMatchListeners(containerId) {
        document.querySelectorAll(`#${containerId} .match-item`).forEach(el => {
            el.addEventListener('click', () => el.querySelector('.match-extra')?.classList.toggle('open'));
        });
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

    // --- Performance Chart + Stats ---
    async function renderPerformanceChart() {
        const container = document.getElementById('team-stats');
        if (!container) return;

        const data = await api('matches?status=FINISHED&limit=38');
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
            const our = isHome ? m.score.fullTime.home : m.score.fullTime.away;
            const opp = isHome ? m.score.fullTime.away : m.score.fullTime.home;

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
        const pct = total ? Math.round(wins / total * 100) : 0;
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
                <div class="stats-col-title">🏠 Casa (${homeTotal}J)</div>
                <div class="mini-stats">
                    <span style="color:var(--win)">${homeWins}V</span>
                    <span style="color:var(--draw)">${homeDraws}E</span>
                    <span style="color:var(--loss)">${homeLosses}D</span>
                    <span>${homeGF}/${homeGA}</span>
                    <span style="font-weight:700">${homePts}pts</span>
                </div>
            </div>
            <div class="stats-col">
                <div class="stats-col-title">✈️ Fora (${awayTotal}J)</div>
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
                <div class="stats-col-title">📊 Médias</div>
                <div class="mini-stats">
                    <span>${avgGF} gpj</span>
                    <span>${avgGA} gcj</span>
                    <span>${pct}% apr.</span>
                </div>
            </div>
            <div class="stats-col">
                <div class="stats-col-title">📋 Forma Recente</div>
                <div class="form-guide">
                    ${lastFive.map(f => `<span class="form-badge ${f.result === 'V' ? 'win' : f.result === 'D' ? 'loss' : 'draw'}" title="${f.home ? '🏠' : '✈️'} vs ${escapeHtml(f.opp)} (${f.score})">${f.result}</span>`).join('')}
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
                const our = isHome ? m.score.fullTime.home : m.score.fullTime.away;
                const opp = isHome ? m.score.fullTime.away : m.score.fullTime.home;
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
                                        return p === 3 ? '✅ Vitória' : p === 1 ? '➖ Empate' : '❌ Derrota';
                                    }
                                    return `Total: ${item.raw} pts`;
                                }
                            }
                        }
                    }
                }
            });
        } else {
            html += '<div style="text-align:center;padding:1rem;font-size:0.85rem;color:var(--text-muted)">📈 Gráfico disponível com mínimo 3 jogos do Brasileirão</div>';
            container.innerHTML = html;
        }
    }

    // --- Stats (legacy fallback) ---
    async function loadTeamStats() {
        // Don't overwrite if chart is already rendered
        if (document.getElementById('performanceCanvas')) return;
        
        showSkeleton('team-stats');
        const data = await api('matches?status=FINISHED&limit=20');
        if (!data) { showError('team-stats', 'Erro ao carregar', 'loadTeamStats'); return; }
        // Don't overwrite if chart was rendered while waiting for API
        if (document.getElementById('performanceCanvas')) return;
        
        const matches = data.matches || [];
        if (!matches.length) { showEmpty('team-stats', 'Nenhum dado'); return; }

        let w = 0, d = 0, l = 0, gf = 0, ga = 0;
        matches.forEach(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const f = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
            const a = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);
            gf += f; ga += a;
            if (f > a) w++; else if (f < a) l++; else d++;
        });
        const total = w + d + l;
        const pct = total ? Math.round(w / total * 100) : 0;

        document.getElementById('team-stats').innerHTML = [
            ['⚽ Jogos', total], ['✅ Vitórias', w], ['➖ Empates', d], ['❌ Derrotas', l],
            ['🥅 Gols Pro', gf], ['🛡️ Gols Contra', ga], ['📊 Saldo', gf - ga], ['📈 Aproveitamento', pct + '%']
        ].map(([n, v]) => `<div class="stat-row"><span class="stat-name">${n}</span><span class="stat-number">${v}</span></div>`).join('');
    }

    // --- News ---
    async function loadNews() {
        showSkeleton('news-list');
        const data = await api('news');
        const items = Array.isArray(data) ? data : (data?.news || []);
        if (!items.length) { showEmpty('news-list', 'Nenhuma notícia'); return; }

        const sourceIcons = {
            'ge.globo': '🔴',
            'lance.com.br': '🔵',
            'gazetaesportiva.com': '🟡',
            'uol.com.br': '🟠',
        };

        document.getElementById('news-list').innerHTML = items.slice(0, 12).map(n => {
            const source = n.source || 'ge.globo';
            const icon = sourceIcons[source] || '📰';
            const safeTitle = escapeHtml(n.title);
            const safeSource = escapeHtml(source);
            return `<div class="news-item" data-href="${escapeHtml(n.url || '#')}" role="link" tabindex="0">
                <div class="news-title">${safeTitle}</div>
                <div class="news-meta">${icon} <span class="news-source">${safeSource}</span></div>
            </div>`;
        }).join('');

        // Delegated click handler for news items
        document.getElementById('news-list').addEventListener('click', function (e) {
            const item = e.target.closest('.news-item[data-href]');
            if (item) window.open(item.dataset.href, '_blank');
        });
    }

    // --- Prediction ---
    async function loadPrediction() {
        showSkeleton('prediction');
        const data = await api('matches?status=SCHEDULED,TIMED&limit=1');
        if (!data) { showError('prediction', 'Erro ao carregar', 'loadPrediction'); return; }
        const match = data.matches?.[0];
        if (!match) { showEmpty('prediction', 'Nenhum jogo para palpitar'); return; }
        const isHome = match.homeTeam.id === TEAM_ID;
        const hw = isHome ? 45 : 30, dr = 28, aw = 100 - hw - dr;

        document.getElementById('prediction').innerHTML = `
            <div class="prediction-card">
                <div style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">${escapeHtml(CONFIG.teamName(match.homeTeam))} × ${escapeHtml(CONFIG.teamName(match.awayTeam))}</div>
                <div class="prediction-probs">
                    <div class="prob-box"><div class="prob-value">${hw}%</div><div class="prob-label">${isHome ? 'Vitória' : 'Derrota'}</div></div>
                    <div class="prob-box"><div class="prob-value">${dr}%</div><div class="prob-label">Empate</div></div>
                    <div class="prob-box"><div class="prob-value">${aw}%</div><div class="prob-label">${isHome ? 'Derrota' : 'Vitória'}</div></div>
                </div>
                <div style="margin-top:1rem;font-size:0.8rem;color:var(--text-muted)">* Palpite simples baseado em mando de campo</div>
            </div>`;
    }

    // --- Calendar ---
    const COMP_DOT_CLASS = {
        BSA: 'bsa',
        CLI: 'cli',
        COPA: 'copa',
        COPADO_BRASIL: 'copa',
    };

    const STATUS_LABEL = {
        SCHEDULED: 'Agendado',
        TIMED: 'Agendado',
        IN_PLAY: '🔴 AO VIVO',
        FINISHED: 'Finalizado',
        PAUSED: 'Intervalo',
        POSTPONED: 'Adiado',
        SUSPENDED: 'Suspenso',
        CANCELLED: 'Cancelado',
    };

    function getDotClass(code) {
        return getCompBadgeClass(code);
    }

    function getCompBadgeClass(code) {
        return COMP_DOT_CLASS[code] || 'other';
    }

    const MONTHS_PT = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                       'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

    let _calYear = null;
    let _calMonth = null;
    let _calData = null;
    let _calSelectedDay = null;
    let _calendarLoaded = false;

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
            html += `<div class="cal-head">${d}</div>`;
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

            // Apply competition filter
            if (_calCompFilter !== 'all') {
                matches = matches.filter(m => m.competition?.code === _calCompFilter);
            }

            const comps = [...new Set(matches.map(m => m.competition?.code || 'OTHER'))];
            const visibleComps = comps.slice(0, 3);
            const overflow = comps.length > 3 ? comps.length - 3 : 0;

            const dotsHtml = visibleComps.map(c =>
                `<div class="cal-dot ${getDotClass(c)}"></div>`
            ).join('');
            const overflowHtml = overflow > 0 ? `<span class="cal-overflow">+${overflow}</span>` : '';

            const classes = ['cal-day'];
            if (isToday) classes.push('today');
            if (_calSelectedDay === dayStr) classes.push('selected');

            html += `<div class="${classes.join(' ')}" data-day="${day}">
                <div class="cal-day-num">${day}</div>
                ${matches.length ? `<div class="cal-dots">${dotsHtml}${overflowHtml}</div>` : ''}
            </div>`;
        }

        grid.innerHTML = html;

        // Attach click listeners
        grid.querySelectorAll('.cal-day:not(.other-month)').forEach(cell => {
            cell.addEventListener('click', () => {
                const day = parseInt(cell.dataset.day);
                toggleDay(day);
            });
        });
    }

    function toggleDay(day) {
        const dayStr = `${_calYear}-${String(_calMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        if (_calSelectedDay === dayStr) {
            _calSelectedDay = null;
            document.getElementById('calendar-expanded').innerHTML = '';
        } else {
            _calSelectedDay = dayStr;
            renderExpandedDay(dayStr);
            // Also switch to "Próximos" tab and filter the list to this day
            switchToTab('proximos');
            filterMatchesToDay(dayStr);
        }
        // Update selected state
        document.querySelectorAll('.cal-day').forEach(d => d.classList.remove('selected'));
        document.querySelector(`.cal-day[data-day="${day}"]`)?.classList.add('selected');
    }

    // Helper: switch to a tab by ID without triggering its load logic
    window.switchToTab = function (tabId) {
        const tabBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
        if (!tabBtn || tabBtn.classList.contains('active')) return;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tabBtn.classList.add('active');
        document.getElementById(tabId)?.classList.add('active');
    };

    function renderExpandedDay(dayStr) {
        let matches = _calData?.days?.[dayStr] || [];

        // Apply competition filter
        if (_calCompFilter !== 'all') {
            matches = matches.filter(m => m.competition?.code === _calCompFilter);
        }

        const container = document.getElementById('calendar-expanded');

        if (!matches.length) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `<div class="cal-expanded">
            <div class="cal-expanded-header">
                <span class="cal-expanded-date">${dayStr.split('-').reverse().join('/')}</span>
                <button class="cal-expanded-btn" onclick="filterMatchesToDay('${dayStr}'); switchToTab('proximos')">
                    📋 Ver em Próximos
                </button>
            </div>
            ${matches.map(m => {
                const time = new Date(m.utcDate).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: CONFIG.BR_TZ });
                const isHome = m.homeTeam.id === CONFIG.TEAM_ID;
                const ourTeam = isHome ? m.homeTeam : m.awayTeam;
                const oppTeam = isHome ? m.awayTeam : m.homeTeam;
                const ourScore = isHome ? m.homeScore : m.awayScore;
                const oppScore = isHome ? m.awayScore : m.homeScore;

                const scoreHtml = (m.status === 'FINISHED' || m.status === 'PLAYING_TIME_FINISHED') && ourScore != null
                    ? `<span style="margin-left:0.5rem;font-weight:700;font-size:0.9rem">${ourScore}–${oppScore}</span>`
                    : '';

                const statusText = STATUS_LABEL[m.status] || m.status;
                const compClass = getCompBadgeClass(m.competition?.code);

                return `<div class="cal-match">
                    <div class="cal-match-time">${time}</div>
                    <div class="cal-match-comp ${compClass}">${escapeHtml(CONFIG.formatComp(m.competition))}</div>
                    <div class="cal-match-teams">
                        <img src="${CONFIG.getCrest(ourTeam)}" alt="">
                        <span>${escapeHtml(CONFIG.teamName(ourTeam))}</span>
                        <span class="cal-match-vs">×</span>
                        <span>${escapeHtml(CONFIG.teamName(oppTeam))}</span>
                        <img src="${CONFIG.getCrest(oppTeam)}" alt="">
                        ${scoreHtml}
                    </div>
                    <div class="cal-match-status">${statusText}</div>
                </div>`;
            }).join('')}
        </div>`;
    }

    window.loadCalendar = loadCalendar;

    // --- Mini Calendar Strip ---
    const WEEKDAYS_PT = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S'];
    let _miniStripYear = null;
    let _miniStripMonth = null;
    let _miniStripData = null;
    let _miniStripSelectedDay = null;
    let _miniStripLoading = false;

    function getTodayStr() {
        return new Date().toLocaleDateString('en-CA', { timeZone: CONFIG.BR_TZ });
    }

    async function loadMiniStrip() {
        if (_miniStripLoading) return;
        _miniStripLoading = true;
        try {
        const todayStr = getTodayStr();
        const todayYear = parseInt(todayStr.split('-')[0]);
        const todayMonth = parseInt(todayStr.split('-')[1]);

        if (_miniStripYear === null) {
            _miniStripYear = todayYear;
            _miniStripMonth = todayMonth;
        }

        const data = await api(`calendar_monthly?year=${_miniStripYear}&month=${_miniStripMonth}`);
        _miniStripData = data;

        const monthLabel = document.getElementById('mini-strip-month-label');
        if (monthLabel) monthLabel.textContent = `${MONTHS_PT[_miniStripMonth - 1]} ${_miniStripYear}`;

        const grid = document.getElementById('mini-strip-grid');
        if (!grid) return;

        const daysInMonth = new Date(_miniStripYear, _miniStripMonth, 0).getDate();
        const firstDow = new Date(_miniStripYear, _miniStripMonth - 1, 1).getDay();

        let html = '';
        // Weekday headers
        WEEKDAYS_PT.forEach(d => {
            html += `<div style="text-align:center;font-size:0.6rem;font-weight:700;color:rgba(255,255,255,0.6);padding:0.2rem 0;text-transform:uppercase;letter-spacing:0.05em">${d}</div>`;
        });

        // Leading empty cells
        for (let i = 0; i < firstDow; i++) {
            html += `<div class="mini-strip-day empty"></div>`;
        }

        // Day cells
        for (let day = 1; day <= daysInMonth; day++) {
            const dayStr = `${_miniStripYear}-${String(_miniStripMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const isToday = dayStr === todayStr;
            const matches = (data?.days || {})[dayStr] || [];
            const comps = [...new Set(matches.map(m => {
                const c = m.competition?.code;
                if (c === 'BSA') return 'bsa';
                if (c === 'CLI' || c === 'LIBERTADORES') return 'cli';
                if (c === 'COPA' || c === 'COPA_DO_BRASIL') return 'copa';
                return 'other';
            }))];

            const classes = ['mini-strip-day'];
            if (isToday) classes.push('today');
            if (matches.length > 0) classes.push('has-match');
            if (_miniStripSelectedDay === dayStr) classes.push('selected');

            const dotsHtml = comps.slice(0, 3).map(c =>
                `<div class="mini-strip-dot ${c}"></div>`
            ).join('');

            html += `<div class="${classes.join(' ')}" data-day="${day}">
                <div class="mini-strip-day-num">${day}</div>
                ${matches.length > 0 ? `<div class="mini-strip-day-dots">${dotsHtml}</div>` : ''}
            </div>`;
        }

        grid.innerHTML = html;

        // Attach click listeners
        grid.querySelectorAll('.mini-strip-day:not(.empty)').forEach(cell => {
            cell.addEventListener('click', () => {
                const day = parseInt(cell.dataset.day);
                const dayStr = `${_miniStripYear}-${String(_miniStripMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                selectMiniStripDay(dayStr);
            });
        });
        } finally { _miniStripLoading = false; }
    }

    function selectMiniStripDay(dayStr) {
        _miniStripSelectedDay = dayStr;
        // Update selected visual
        document.querySelectorAll('.mini-strip-day').forEach(d => d.classList.remove('selected'));
        const dayNum = parseInt(dayStr.split('-')[2]);
        document.querySelector(`.mini-strip-day[data-day="${dayNum}"]`)?.classList.add('selected');
        // Filter next matches to this day (unified filter respects competition too)
        filterMatchesToDay(dayStr);
    }

    // --- Unified List Filter (competition + day) ---
    // _sharedCompFilter: 'all' | 'BSA' | 'CLI' | 'COPA'
    // _listDayFilter: null (all days) | 'YYYY-MM-DD' (specific day)
    let _listDayFilter = null;

    window.clearListDayFilter = function () {
        _listDayFilter = null;
        _miniStripSelectedDay = null;
        document.querySelectorAll('.mini-strip-day').forEach(d => d.classList.remove('selected'));
        const chip = document.getElementById('day-filter-chip');
        if (chip) chip.style.display = 'none';
        applyUnifiedListFilter();
    };

    window.filterMatchesToDay = function filterMatchesToDay(dayStr) {
        _listDayFilter = dayStr;
        _miniStripSelectedDay = dayStr; // sync mini strip visual (uses YYYY-MM-DD now)
        document.querySelectorAll('.mini-strip-day').forEach(d => d.classList.remove('selected'));
        const dayNum = parseInt(dayStr.split('-')[2]);
        document.querySelector(`.mini-strip-day[data-day="${dayNum}"]`)?.classList.add('selected');
        applyUnifiedListFilter();
    };

    function applyUnifiedListFilter() {
        let filtered;
        const container = document.getElementById('next-matches');

        // --- Day Filter Chip management ---
        const chip = document.getElementById('day-filter-chip');
        const chipText = document.getElementById('day-filter-text');
        if (_listDayFilter && chip && chipText) {
            const [y, m, d] = _listDayFilter.split('-');
            const dateStr = new Date(`${y}-${m}-${d}T12:00:00`).toLocaleDateString('pt-BR', { weekday: 'short', timeZone: BR_TZ });
            const dayName = dateStr.charAt(0).toUpperCase() + dateStr.slice(1);
            const compLabels = { BSA: '🇧🇷 Brasileirão', CLI: '🏆 Libertadores', COPA: '🥇 Copa do Brasil' };
            const compPart = _sharedCompFilter !== 'all' ? ` · ${compLabels[_sharedCompFilter] || _sharedCompFilter}` : '';
            chipText.textContent = `${dayName}, ${d}/${m}${compPart}`;
            chip.style.display = 'flex';
        } else if (chip) {
            chip.style.display = 'none';
        }

        if (_listDayFilter) {
            // Use _miniStripData (same month as the strip) if available,
            // otherwise fall back to _calData, then _allMatches
            let sourceMatches = [];
            if (_miniStripData && _miniStripData.days?.[_listDayFilter]) {
                sourceMatches = _miniStripData.days[_listDayFilter];
            } else if (_calData && _calData.days?.[_listDayFilter]) {
                sourceMatches = _calData.days[_listDayFilter];
            } else {
                sourceMatches = _allMatches.filter(m => {
                    const d = new Date(m.utcDate).toLocaleDateString('en-CA', { timeZone: CONFIG.BR_TZ });
                    return d === _listDayFilter;
                });
            }

            filtered = sourceMatches.filter(m => matchCompetition(m, _sharedCompFilter));
        } else {
            filtered = _allMatches.filter(m => matchCompetition(m, _sharedCompFilter));
        }

        if (!filtered.length) {
            const dayDesc = _listDayFilter ? `em ${_listDayFilter.split('-').reverse().join('/')}` : '';
            const compDesc = _sharedCompFilter !== 'all' ? ` para ${_sharedCompFilter}` : '';
            container.innerHTML = `<div class="empty">Nenhum jogo encontrado ${dayDesc}${compDesc}</div>`;
        } else {
            container.innerHTML = filtered.map(m => buildMatchHtml(m, m.status === 'IN_PLAY')).join('');
            attachMatchListeners('next-matches');
        }
    }

    // Mini strip navigation
    document.getElementById('mini-strip-prev')?.addEventListener('click', () => {
        _miniStripMonth--;
        if (_miniStripMonth < 1) { _miniStripMonth = 12; _miniStripYear--; }
        _miniStripSelectedDay = null;
        clearListDayFilter(); // reset day filter so all matches show
        loadMiniStrip();
    });
    document.getElementById('mini-strip-next')?.addEventListener('click', () => {
        _miniStripMonth++;
        if (_miniStripMonth > 12) { _miniStripMonth = 1; _miniStripYear++; }
        _miniStripSelectedDay = null;
        clearListDayFilter(); // reset day filter so all matches show
        loadMiniStrip();
    });

    // --- Calendar View Switcher (Grid | List) ---
    let _calView = 'grid';

    window.switchCalView = function (view, btn) {
        _calView = view;
        document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.cal-view-content').forEach(el => el.classList.remove('active'));
        if (view === 'grid') {
            document.getElementById('calendar-grid')?.classList.add('active');
        } else {
            document.getElementById('calendar-list')?.classList.add('active');
            renderCalendarListView();
        }
    };

    // --- Calendar Competition Filter ---
    let _calCompFilter = 'all';

    window.filterCalendarComp = function (comp, btn) {
        _calCompFilter = comp;
        _sharedCompFilter = comp;
        document.querySelectorAll('.cal-comp-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Also sync the "Próximos" tab filter so switching tabs shows consistent data
        document.querySelectorAll('.comp-legend-item').forEach(b => b.classList.remove('active'));
        document.querySelector(`.comp-legend-item[data-comp="${comp}"]`)?.classList.add('active');

        // Clear day filter so all days of the competition show in list
        clearListDayFilter();
        applyUnifiedListFilter(); // update "Próximos" tab state too

        // Re-render calendar view with filter
        if (_calView === 'grid') {
            loadCalendar();
        } else {
            renderCalendarListView();
        }
    };

    // --- Shared Competition Filter (syncs calendar + list views) ---
    let _sharedCompFilter = 'all';

    window.filterSharedComp = function (comp, btn) {
        _sharedCompFilter = comp;
        _calCompFilter = comp; // Keep calendar in sync

        // Sync calendar tab filter buttons
        document.querySelectorAll('.cal-comp-btn').forEach(b => b.classList.remove('active'));
        document.querySelector(`.cal-comp-btn[data-comp="${comp}"]`)?.classList.add('active');

        // Sync "Próximos" tab filter buttons
        document.querySelectorAll('.comp-legend-item').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        document.querySelector(`.comp-legend-item[data-comp="${comp}"]`)?.classList.add('active');

        // Apply unified filter to list (clears day filter so all days of new comp show)
        clearListDayFilter();
        applyUnifiedListFilter();
        if (_calView === 'grid') {
            loadCalendar();
        } else {
            renderCalendarListView();
        }
    };

    async function renderCalendarListView() {
        const container = document.getElementById('calendar-list');
        if (!container) return;
        if (!_calData) {
            container.innerHTML = '<div class="empty">Carregue o calendário primeiro</div>';
            return;
        }
        const todayStr = getTodayStr();
        const todayYear = parseInt(todayStr.split('-')[0]);
        const todayMonth = parseInt(todayStr.split('-')[1]);

        // Fetch 12 months centered on current month for full year view
        const months = [];
        const d = new Date(_calYear, _calMonth - 1, 1);
        for (let i = -5; i <= 6; i++) {
            const dt = new Date(d.getFullYear(), d.getMonth() + i, 1);
            months.push({ year: dt.getFullYear(), month: dt.getMonth() + 1 });
        }

        let allDays = {};
        const results = await Promise.all(months.map(m =>
            api(`calendar_monthly?year=${m.year}&month=${m.month}`)
        ));
        results.forEach(data => {
            if (data?.days) Object.assign(allDays, data.days);
        });

        // Sort dates
        const sortedDates = Object.keys(allDays).sort();

        let html = '';
        let currentMonthKey = null;

        sortedDates.forEach(dateStr => {
            const [y, m, d] = dateStr.split('-');
            const monthKey = `${y}-${m}`;
            const matches = allDays[dateStr] || [];

            // Month header
            if (monthKey !== currentMonthKey) {
                currentMonthKey = monthKey;
                const mi = parseInt(m);
                html += `<div class="cal-list-month-header">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="opacity:0.8"><path d="M4 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2H4zm0 1h8a1 1 0 0 1 1 1v1H3V2a1 1 0 0 1 1-1z"/></svg>
                    ${MONTHS_PT[mi - 1]} ${y}
                </div>`;
            }

            const dt = new Date(dateStr);
            const weekday = WEEKDAYS_PT[dt.getDay()];
            const dayNum = parseInt(d);

            // Filter by competition
            const filteredMatches = matches.filter(m => {
                if (_calCompFilter === 'all') return true;
                return m.competition?.code === _calCompFilter;
            });

            filteredMatches.forEach(m => {
                const time = new Date(m.utcDate).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: CONFIG.BR_TZ });
                const isHome = m.homeTeam.id === CONFIG.TEAM_ID;
                const ourTeam = isHome ? m.homeTeam : m.awayTeam;
                const oppTeam = isHome ? m.awayTeam : m.homeTeam;
                const ourScore = isHome ? m.homeScore : m.awayScore;
                const oppScore = isHome ? m.awayScore : m.homeScore;
                const compClass = getCompBadgeClass(m.competition?.code);
                const scoreHtml = (m.status === 'FINISHED' || m.status === 'PLAYING_TIME_FINISHED') && ourScore != null
                    ? `<span class="cal-match-score">${ourScore}–${oppScore}</span>` : '';
                const statusText = STATUS_LABEL[m.status] || m.status;
                const isLive = m.status === 'IN_PLAY';

                html += `<div class="cal-list-match">
                    <div class="cal-list-date">
                        <div class="cal-list-date-day">${dayNum}</div>
                        <div class="cal-list-date-weekday">${weekday}</div>
                    </div>
                    <div class="cal-list-comp ${compClass}">${escapeHtml(CONFIG.formatComp(m.competition))}</div>
                    <div class="cal-list-info">
                        <div class="cal-list-teams">
                            <img src="${CONFIG.getCrest(ourTeam)}" alt="">${escapeHtml(CONFIG.teamName(ourTeam))}
                            <span style="color:var(--text-muted)">×</span>
                            ${escapeHtml(CONFIG.teamName(oppTeam))}<img src="${CONFIG.getCrest(oppTeam)}" alt="">
                            ${scoreHtml}
                        </div>
                    </div>
                    <div class="cal-list-time">${time}</div>
                    <div class="cal-match-status ${isLive ? 'live' : ''}">${statusText}</div>
                </div>`;
            });
        });

        if (!html) {
            html = '<div class="empty">Nenhum jogo encontrado</div>';
        }
        container.innerHTML = html;
    }

    // Nav buttons
    document.getElementById('cal-prev')?.addEventListener('click', () => {
        _calMonth--;
        if (_calMonth < 1) { _calMonth = 12; _calYear--; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
    });
    document.getElementById('cal-next')?.addEventListener('click', () => {
        _calMonth++;
        if (_calMonth > 12) { _calMonth = 1; _calYear++; }
        _calSelectedDay = null;
        document.getElementById('calendar-expanded').innerHTML = '';
        syncYearSelect();
        loadCalendar();
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
    };

    // Populate year select (current year -1 to +2)
    (function populateYearSelect() {
        const sel = document.getElementById('cal-year-select');
        if (!sel) return;
        const currentYear = new Date().getFullYear();
        const years = [currentYear - 1, currentYear, currentYear + 1, currentYear + 2];
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

    // --- Public API ---
    window.loadHero = loadHero;
    window.loadMatches = loadMatches;
    window.loadResults = loadResults;
    window.loadStandings = loadStandings;
    window.loadTeamStats = loadTeamStats;
    window.loadNews = loadNews;
    window.loadPrediction = loadPrediction;

    // --- Init ---
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        const el = document.getElementById('last-updated');
        if (el) el.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        initTabs();
        loadHero();
        loadMatches();
        loadResults();
        loadStandings();
        loadTeamStats();
        loadNews();
        loadPrediction();
        loadMiniStrip(); // Load mini calendar strip for default "Próximos" tab
    });
})();
