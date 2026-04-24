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
        'PLAYOFF_ROUND': 'Repescagem',
        'QUALIFYING_ROUND': 'Eliminatória',
        'PRELIMINARY_ROUND': 'Fase Preliminar',
        'REGULAR_SEASON': '',
        'LEAGUE_PHASE': 'Fase de Liga',
    };

    function formatStage(stage) {
        if (!stage || stage === 'REGULAR_SEASON') return '';
        return STAGE_NAMES[stage] || stage;
    }

    function getCompCode(comp) {
        return comp?.code || '';
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
    async function api(path, ttlMs = CACHE_TTL) {
        const cached = _apiCache[path];
        if (cached && Date.now() - cached.time < ttlMs) {
            return cached.data;
        }
        try {
            const res = await fetch(`/api/${path}${path.includes('?') ? '&' : '?'}_t=${Date.now()}`);
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
            console.error(`API [${path}]:`, e);
            // Return stale cache on failure
            if (cached) return cached.data;
            return null;
        }
    }

    // --- Tabs ---
    function initTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.tab-btn').forEach(b => {
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                });
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                btn.setAttribute('aria-selected', 'true');
                const tab = document.getElementById(btn.dataset.tab);
                tab?.classList.add('active');
                if (btn.dataset.tab === 'estatisticas' && !performanceChart) {
                    renderPerformanceChart();
                }
                if (btn.dataset.tab === 'prediction') {
                    loadPrediction();
                }
            });
        });
    }

    // --- Live Refresh ---
    function startLiveRefresh() {
        if (!liveInterval) liveInterval = setInterval(loadHero, 15000);
    }

    function stopLiveRefresh() {
        if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
    }

    // --- Hero ---
    async function loadHero() {
        const data = await api('matches?status=SCHEDULED,TIMED,IN_PLAY,PAUSED&limit=5');
        if (!data) {
            document.getElementById('hero-comp-badge').textContent = 'Erro ao carregar';
            return;
        }
        const match = data.matches?.[0];
        if (!match) {
            document.getElementById('hero-comp-badge').textContent = 'Nenhum jogo agendado';
            document.getElementById('hero-teams-area').style.display = 'none';
            document.getElementById('hero-date-area').style.display = 'none';
            return;
        }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = CONFIG.formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = match.status === 'IN_PLAY' || match.status === 'PAUSED';
        const isPaused = match.status === 'PAUSED';
        const score = match.score?.fullTime || {};
        const ht = match.score?.halfTime || {};
        const venue = CONFIG.getVenue(match);
        const stageLabel = formatStage(match.stage);

        const heroCard = document.getElementById('hero-match');
        heroCard?.classList.toggle('live', isLive);

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
            isLive ? (isPaused ? '⏸️ INTERVALO' : '🔴 JOGANDO AGORA') :
            `${formatDate(match.utcDate)} · ${formatTime(match.utcDate)} <span class="hero-day">${dayOfWeek}</span>`;

        // Detail pills
        const pillStadium = document.getElementById('pill-stadium');
        const pillBroadcast = document.getElementById('pill-broadcast');
        const pillRound = document.getElementById('pill-round');
        const pillStage = document.getElementById('pill-stage');

        pillStadium.textContent = '🏟️ ' + (venue || 'A definir');
        pillBroadcast.textContent = '📺 ' + (match.broadcast || 'A confirmar');
        pillRound.textContent = '🔢 Rodada ' + (match.matchday || '-');

        if (stageLabel) {
            pillStage.textContent = '🏷️ ' + stageLabel;
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
        const data = await api('matches?status=FINISHED&limit=5');
        if (!data?.matches?.length) return;

        const widget = document.getElementById('form-widget');
        const dots = document.getElementById('form-dots');
        if (!widget || !dots) return;

        dots.innerHTML = '';
        data.matches.forEach(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? (m.score?.fullTime?.home ?? 0) : (m.score?.fullTime?.away ?? 0);
            const opp = isHome ? (m.score?.fullTime?.away ?? 0) : (m.score?.fullTime?.home ?? 0);
            const r = our > opp ? 'W' : our < opp ? 'L' : 'D';
            const label = r === 'W' ? 'V' : r === 'L' ? 'D' : 'E';
            const cls = r === 'W' ? 'win' : r === 'L' ? 'loss' : 'draw';
            const tooltip = `${isHome ? '🏠' : '✈️'} ${our}-${opp} vs ${escapeHtml(isHome ? CONFIG.teamName(m.awayTeam) : CONFIG.teamName(m.homeTeam))}`;
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
                container.innerHTML = '<div class="empty" style="padding:2rem">⚠️ Erro ao carregar gráficos</div>';
                return;
            }
        }

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
            return `<a class="news-item" href="${escapeHtml(n.url || '#')}" target="_blank" rel="noopener noreferrer">
                <div class="news-title">${safeTitle}</div>
                <div class="news-meta">${icon} <span class="news-source">${safeSource}</span></div>
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
                api('matches?status=SCHEDULED,TIMED&limit=5'),
                api('matches?status=FINISHED&limit=8'),
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
            confidenceBadge = '<div class="prediction-badge likely">🟢 Provável</div>';
        } else if (maxProb >= 0.45) {
            confidenceBadge = '<div class="prediction-badge maybe">🟡 Possível</div>';
        } else {
            confidenceBadge = '<div class="prediction-badge risky">🔴 Arriscado</div>';
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
            if (live.length > 0) {
                const m = live[0];
                const isHome = m.homeTeam?.id === TEAM_ID;
                const ourScore = isHome ? m.homeScore : m.awayScore;
                const oppScore = isHome ? m.awayScore : m.homeScore;
                scoreHtml = `<div class="cal-score live">🔴 ${ourScore ?? 0}–${oppScore ?? 0}</div>`;
            } else if (finished.length > 0) {
                // Show result badge for each finished game
                scoreHtml = finished.map(m => {
                    const isHome = m.homeTeam?.id === TEAM_ID;
                    const ourScore = isHome ? m.homeScore : m.awayScore;
                    const oppScore = isHome ? m.awayScore : m.homeScore;
                    const result = ourScore > oppScore ? 'V' : ourScore < oppScore ? 'D' : 'E';
                    const cls = result === 'V' ? 'win' : result === 'D' ? 'loss' : 'draw';
                    return `<div class="cal-score ${cls}">${ourScore}–${oppScore}</div>`;
                }).join('');
            }

            const classes = ['cal-day'];
            if (isToday) classes.push('today');
            if (matches.length > 0) classes.push('has-match');
            if (live.length > 0) classes.push('is-live');
            if (_calSelectedDay === dayStr) classes.push('selected');

            html += `<div class="${classes.join(' ')}" data-day="${day}">
                <div class="cal-day-num">${day}</div>
                ${matches.length ? `<div class="cal-dots">${dotsHtml}${overflowHtml}</div>` : ''}
                ${scoreHtml}
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

        // Auto-select today's date if no day is selected and today is in current month
        if (!_calSelectedDay && _calYear === todayYear && _calMonth === todayMonth) {
            const todayDay = parseInt(todayStr.split('-')[2]);
            if (todayDay >= 1 && todayDay <= daysInMonth) {
                _calSelectedDay = todayStr;
                // Update the visual selected state
                document.querySelector(`.cal-day[data-day="${todayDay}"]`)?.classList.add('selected');
                // Show expanded view for today's matches
                renderExpandedDay(todayStr);
            }
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
        document.querySelectorAll('.cal-day').forEach(d => d.classList.remove('selected'));
        if (_calSelectedDay) {
            document.querySelector(`.cal-day[data-day="${day}"]`)?.classList.add('selected');
        }
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
                const isHome = m.homeTeam.id === CONFIG.TEAM_ID;
                const ourTeam = isHome ? m.homeTeam : m.awayTeam;
                const oppTeam = isHome ? m.awayTeam : m.homeTeam;
                const ourScore = isHome ? m.homeScore : m.awayScore;
                const oppScore = isHome ? m.awayScore : m.homeScore;

                const scoreHtml = (m.status === 'FINISHED' || m.status === 'PLAYING_TIME_FINISHED') && ourScore != null
                    ? `<span class="cal-match-score">${ourScore}–${oppScore}</span>`
                    : '';

                const statusText = STATUS_LABEL[m.status] || m.status;
                const compClass = getCompBadgeClass(m.competition?.code);
                const statusClass = (m.status === 'IN_PLAY' || m.status === 'PAUSED') ? 'live' : '';

                return `<div class="cal-match ${compClass}">
                    <div class="cal-match-time">${time}</div>
                    <div class="cal-match-comp ${compClass}">${escapeHtml(CONFIG.formatComp(m.competition))}</div>
                    <div class="cal-match-teams">
                        <img class="cal-match-crest" src="${CONFIG.getCrest(ourTeam)}" alt="">
                        <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(ourTeam))}</span>
                        <span class="cal-match-vs">×</span>
                        <span class="cal-match-team-name">${escapeHtml(CONFIG.teamName(oppTeam))}</span>
                        <img class="cal-match-crest" src="${CONFIG.getCrest(oppTeam)}" alt="">
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
    window.filterSharedComp = function (comp, btn) {
        _calCompFilter = comp;

        // Update legend items
        document.querySelectorAll('.comp-legend-item').forEach(b => b.classList.remove('active'));
        document.querySelector(`.comp-legend-item[data-comp="${comp}"]`)?.classList.add('active');

        // Re-render calendar view with filter
        loadCalendar();
    };

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
        const years = [currentYear, currentYear + 1];
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
    window.loadStandings = loadStandings;
    window.loadNews = loadNews;

    // --- Init ---
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        const el = document.getElementById('last-updated');
        if (el) el.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        initTabs();
        loadHero();
        loadFormWidget();
        loadStandings();
        loadNews();
        loadCalendar();
    });
})();
