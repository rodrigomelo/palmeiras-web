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
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
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
                document.getElementById(btn.dataset.tab)?.classList.add('active');
                if (btn.dataset.tab === 'estatisticas' && !performanceChart) {
                    renderPerformanceChart();
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
        const ht = m.score?.halfTime || {};
        const htInfo = (ht.home != null) ? `<div class="match-extra-row"><span class="icon">⏱️</span> 1º tempo: ${ht.home}–${ht.away}</div>` : '';
        return `<div class="match-item">
            <div class="match-extra">
                <div class="match-extra-row"><span class="icon">🏟️</span> ${escapeHtml(venue)}</div>
                <div class="match-extra-row"><span class="icon">📺</span> ${escapeHtml(m.broadcast || 'A confirmar')}</div>
                <div class="match-extra-row"><span class="icon">🔢</span> Rodada ${m.matchday || '-'}${m.stage && m.stage !== 'REGULAR_SEASON' ? ' · ' + escapeHtml(m.stage) : ''}</div>
                ${htInfo}
            </div>
            <div class="match-header"><span>${isLive ? '<span class="live-dot"></span>AO VIVO · ' : ''}${formatDate(m.utcDate)} · ${formatTime(m.utcDate)}</span><span>${escapeHtml(CONFIG.formatComp(m.competition))}</span></div>
            <div class="match-teams">
                <span><img src="${CONFIG.getCrest(m.homeTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-right:4px" alt="">${escapeHtml(CONFIG.teamName(m.homeTeam))}</span>
                <span style="color:var(--text-muted)">×</span>
                <span>${escapeHtml(CONFIG.teamName(m.awayTeam))}<img src="${CONFIG.getCrest(m.awayTeam)}" style="width:22px;height:22px;vertical-align:middle;margin-left:4px" alt=""></span>
            </div>
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
        applyMatchFilter('all');
    }

    window.filterMatches = function (comp, btn) {
        document.querySelectorAll('#proximos .comp-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
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
            const our = isHome ? m.score.fullTime.home : m.score.fullTime.away;
            const opp = isHome ? m.score.fullTime.away : m.score.fullTime.home;
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
            const f = isHome ? m.score.fullTime.home : m.score.fullTime.away;
            const a = isHome ? m.score.fullTime.away : m.score.fullTime.home;
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
            const safeUrl = escapeHtml(n.url || '#');
            const safeTitle = escapeHtml(n.title);
            const safeSource = escapeHtml(source);
            return `<div class="news-item" onclick="window.open('${safeUrl}','_blank')" role="link" tabindex="0">
                <div class="news-title">${safeTitle}</div>
                <div class="news-meta">${icon} <span class="news-source">${safeSource}</span></div>
            </div>`;
        }).join('');
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
    });
})();
