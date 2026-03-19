/**
 * Palmeiras Dashboard - Client Application
 *
 * Environment detection:
 * - Local: uses relative /api (proxied by Flask to localhost:5002)
 * - Production: calls palmeiras-data.vercel.app directly
 */
(function () {
    'use strict';

    // --- Configuration ---
    const isLocal = ['localhost', '127.0.0.1'].includes(window.location.hostname) ||
        window.location.hostname.startsWith('192.168.') ||
        window.location.hostname.startsWith('10.');
    const DATA_API = isLocal ? '/api' : 'https://palmeiras-data.vercel.app/api';
    const TEAM_ID = 1769;
    const BR_TZ = 'America/Sao_Paulo';

    // --- Helpers ---
    function formatDate(d) {
        return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ });
    }

    function formatTime(d) {
        return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
    }

    function formatComp(comp) {
        const names = { BSA: 'Brasileirao', COPA_DO_BRASIL: 'Copa do Brasil', LIBERTADORES: 'Libertadores' };
        return names[comp?.code] || comp?.name || 'Campeonato';
    }

    // --- UI States ---
    function showSkeleton(containerId, type) {
        const el = document.getElementById(containerId);
        if (type === 'hero') {
            el.innerHTML = '<div style="padding:2rem"><div class="skeleton-line" style="height:24px;width:50%;margin:0 auto 1rem"></div><div style="display:flex;justify-content:space-around;margin:1rem 0"><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div><div class="skeleton-line" style="width:60px;height:40px"></div><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div></div></div>';
        } else {
            el.innerHTML = '<div class="skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line medium"></div></div>'.repeat(3);
        }
    }

    function showError(containerId, msg, retryFn) {
        const el = document.getElementById(containerId);
        el.innerHTML = `<div class="error-state"><div class="error-icon">⚠️</div><div class="error-message">${msg}</div>${retryFn ? `<button class="retry-btn" onclick="${retryFn}()">🔄 Tentar novamente</button>` : ''}</div>`;
    }

    function showEmpty(containerId, msg) {
        document.getElementById(containerId).innerHTML = `<div class="empty">${msg}</div>`;
    }

    // --- API ---
    async function api(path) {
        try {
            const res = await fetch(`${DATA_API}${path}&_t=${Date.now()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`API error [${path}]:`, e);
            return null;
        }
    }

    // --- Tabs ---
    function initTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(btn.dataset.tab).classList.add('active');
            });
        });
    }

    // --- Hero ---
    async function loadHero() {
        showSkeleton('hero-front', 'hero');
        const data = await api('/matches?status=SCHEDULED,TIMED,IN_PLAY&limit=5');
        if (!data) { showError('hero-front', 'Erro ao carregar próximo jogo', 'loadHero'); return; }

        const match = data.matches?.[0];
        if (!match) { showEmpty('hero-front', 'Nenhum jogo agendado'); return; }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = match.status === 'IN_PLAY';
        const score = match.score?.fullTime || {};
        const liveBadge = isLive ? '<span style="background:#ff4444;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-right:8px">🔴 AO VIVO</span>' : '';

        document.getElementById('where-watch').textContent = 'Rodada ' + (match.matchday || '-');
        document.getElementById('stadium-info').textContent = home.id === TEAM_ID ? 'Allianz Parque' : (match.venue || 'A definir');

        document.getElementById('hero-front').innerHTML = `
            <div class="hero-comp">${liveBadge}${comp}</div>
            <div class="hero-teams">
                <div class="hero-team">
                    <img src="${home.crest || ''}" style="width:50px;height:50px" onerror="this.src='https://crests.football-data.org/1769.png'">
                    <div class="hero-team-name">${home.name}</div>
                </div>
                <div class="hero-vs" style="font-size:${isLive ? '2rem' : '1.5rem'};color:${isLive ? '#ff4444' : 'inherit'}">${isLive ? score.home + ' x ' + score.away : 'X'}</div>
                <div class="hero-team">
                    <img src="${away.crest || ''}" style="width:50px;height:50px" onerror="this.src='https://crests.football-data.org/4364.png'">
                    <div class="hero-team-name">${away.name}</div>
                </div>
            </div>
            <div class="hero-date">${isLive ? 'JOGANDO AGORA' : formatDate(match.utcDate) + ' - ' + formatTime(match.utcDate)}<span style="display:block;font-size:0.85rem;opacity:0.8;margin-top:0.3rem;font-weight:400">${isLive ? '' : dayOfWeek}</span></div>`;

        document.getElementById('hero-back').innerHTML = `
            <div style="padding-top:1rem">
                <h3 style="margin-bottom:1rem">Detalhes do Jogo</h3>
                <p style="margin:0.5rem 0"><strong>Rodada:</strong> ${match.matchday || '-'}</p>
                <p style="margin:0.5rem 0"><strong>Estadio:</strong> ${home.id === TEAM_ID ? 'Allianz Parque' : (match.venue || 'A definir')}</p>
                <p style="margin:0.5rem 0"><strong>Competicao:</strong> ${comp}</p>
            </div>`;
    }

    // --- Upcoming Matches ---
    async function loadMatches() {
        showSkeleton('next-matches');
        const data = await api('/matches?status=SCHEDULED,TIMED,IN_PLAY&limit=10');
        if (!data) { showError('next-matches', 'Erro ao carregar jogos', 'loadMatches'); return; }

        const matches = data.matches || [];
        if (!matches.length) { showEmpty('next-matches', 'Nenhum jogo agendado'); return; }

        document.getElementById('next-matches').innerHTML = matches.map(m => `
            <div class="match-item">
                <div class="match-extra">
                    <p style="margin:0.2rem 0;font-size:0.8rem">🏟️ ${m.venue || 'TBD'}</p>
                    <p style="margin:0.2rem 0;font-size:0.8rem">⚽ Rodada ${m.matchday || '-'}</p>
                </div>
                <div class="match-header"><span>${formatDate(m.utcDate)} - ${formatTime(m.utcDate)}</span><span>${formatComp(m.competition)}</span></div>
                <div class="match-teams">
                    <span><img src="${m.homeTeam.crest}" style="width:20px;height:20px;vertical-align:middle;margin-right:4px">${m.homeTeam.name}</span>
                    <span style="color:var(--text-muted)">X</span>
                    <span>${m.awayTeam.name}<img src="${m.awayTeam.crest}" style="width:20px;height:20px;vertical-align:middle;margin-left:4px"></span>
                </div>
            </div>`).join('');

        // Toggle detail on click
        document.querySelectorAll('#next-matches .match-item').forEach(el => {
            el.addEventListener('click', () => {
                const extra = el.querySelector('.match-extra');
                extra.style.display = extra.style.display === 'none' ? 'block' : 'none';
            });
        });
    }

    // --- Results ---
    async function loadResults() {
        showSkeleton('recent-results');
        const data = await api('/matches?status=FINISHED&limit=5');
        if (!data) { showError('recent-results', 'Erro ao carregar resultados', 'loadResults'); return; }

        const matches = data.matches || [];
        if (!matches.length) { showEmpty('recent-results', 'Nenhum resultado encontrado'); return; }

        document.getElementById('recent-results').innerHTML = matches.map(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? m.score.fullTime.home : m.score.fullTime.away;
            const opp = isHome ? m.score.fullTime.away : m.score.fullTime.home;
            const oppName = isHome ? m.awayTeam.name : m.homeTeam.name;
            const result = our > opp ? 'V' : our < opp ? 'D' : 'E';
            const colors = { V: ['#d4edda', '#155724'], D: ['#f8d7da', '#721c24'], E: ['#fff3cd', '#856404'] };
            const [bg, fg] = colors[result];

            return `<div class="match-item">
                <div class="match-extra">
                    <p style="margin:0.2rem 0;font-size:0.8rem">🏟️ ${m.venue || 'TBD'}</p>
                    <p style="margin:0.2rem 0;font-size:0.8rem">⚽ Rodada ${m.matchday || '-'}</p>
                </div>
                <div class="match-header"><span>${formatDate(m.utcDate)}</span><span>${formatComp(m.competition)}</span></div>
                <div class="match-teams">
                    <span>${isHome ? '🟢' : '⚪'} ${oppName}</span>
                    <span style="display:flex;align-items:center;gap:0.5rem">
                        <span style="padding:0.2rem 0.5rem;border-radius:4px;font-size:0.75rem;font-weight:600;background:${bg};color:${fg}">${result}</span>
                        <span style="font-weight:700">${our} - ${opp}</span>
                    </span>
                </div>
            </div>`;
        }).join('');

        document.querySelectorAll('#recent-results .match-item').forEach(el => {
            el.addEventListener('click', () => {
                const extra = el.querySelector('.match-extra');
                extra.style.display = extra.style.display === 'none' ? 'block' : 'none';
            });
        });
    }

    // --- Standings ---
    async function loadStandings() {
        showSkeleton('standings');
        const data = await api('/standings?competition=BSA');
        if (!data) { showError('standings', 'Erro ao carregar classificacao', 'loadStandings'); return; }

        const rows = data.standings || [];
        const team = rows.find(s => {
            const t = typeof s.team === 'string' ? JSON.parse(s.team) : s.team;
            return t.id === TEAM_ID;
        });

        if (!team) { showEmpty('standings', 'Dados indisponiveis'); return; }

        const gd = team.goals_for - team.goals_against;
        const avg = team.played_games > 0 ? (team.points / team.played_games).toFixed(2) : '0';

        document.getElementById('standings').innerHTML = `
            <div style="text-align:center">
                <div class="position-badge">${team.position}º</div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="stat-value">${team.points}</div><div class="stat-label">Pontos</div></div>
                    <div class="stat-box"><div class="stat-value">${team.played_games}</div><div class="stat-label">Jogos</div></div>
                    <div class="stat-box"><div class="stat-value">${avg}</div><div class="stat-label">Pts/Jogo</div></div>
                </div>
                <div class="stats-grid" style="margin-top:0.5rem">
                    <div class="stat-box"><div class="stat-value" style="color:#27ae60">${team.won}</div><div class="stat-label">Vitorias</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:#f39c12">${team.drawn}</div><div class="stat-label">Empates</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:#e74c3c">${team.lost}</div><div class="stat-label">Derrotas</div></div>
                </div>
                <div class="stats-grid" style="margin-top:0.5rem">
                    <div class="stat-box"><div class="stat-value">${team.goals_for}</div><div class="stat-label">Gols Pro</div></div>
                    <div class="stat-box"><div class="stat-value">${team.goals_against}</div><div class="stat-label">Gols Contra</div></div>
                    <div class="stat-box"><div class="stat-value" style="color:${gd >= 0 ? '#27ae60' : '#e74c3c'}">${gd >= 0 ? '+' : ''}${gd}</div><div class="stat-label">Saldo</div></div>
                </div>
            </div>`;
    }

    // --- Team Stats ---
    async function loadTeamStats() {
        showSkeleton('team-stats');
        const data = await api('/matches?status=FINISHED&limit=20');
        if (!data) { showError('team-stats', 'Erro ao carregar estatisticas', 'loadTeamStats'); return; }

        const matches = data.matches || [];
        if (!matches.length) { showEmpty('team-stats', 'Nenhum dado disponivel'); return; }

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
            ['Jogos', total], ['Vitorias', w], ['Empates', d], ['Derrotas', l],
            ['Gols Pro', gf], ['Gols Contra', ga], ['Saldo', gf - ga], ['Aproveitamento', pct + '%']
        ].map(([name, val]) => `<div class="stat-row"><span class="stat-name">${name}</span><span class="stat-number">${val}</span></div>`).join('');
    }

    // --- News ---
    async function loadNews() {
        showSkeleton('news-list');
        const data = await api('/news');
        if (!data || !Array.isArray(data) || !data.length) { showEmpty('news-list', 'Nenhuma noticia disponivel'); return; }

        document.getElementById('news-list').innerHTML = data.slice(0, 8).map(n => `
            <div class="news-item" onclick="window.open('${n.url}', '_blank')">
                <div class="news-title">${n.title}</div>
                <div class="news-meta"><span class="news-source">${n.source || 'ge.globo'}</span></div>
            </div>`).join('');
    }

    // --- Prediction ---
    async function loadPrediction() {
        showSkeleton('prediction');
        const data = await api('/matches?status=SCHEDULED,TIMED&limit=1');
        if (!data) { showError('prediction', 'Erro ao carregar palpite', 'loadPrediction'); return; }

        const match = data.matches?.[0];
        if (!match) { showEmpty('prediction', 'Nenhum jogo para palpitar'); return; }

        const isHome = match.homeTeam.id === TEAM_ID;
        const homeWin = isHome ? 45 : 30;
        const draw = 28;
        const awayWin = 100 - homeWin - draw;

        document.getElementById('prediction').innerHTML = `
            <div class="prediction-card">
                <div style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">${match.homeTeam.name} X ${match.awayTeam.name}</div>
                <div class="prediction-probs">
                    <div class="prob-box"><div class="prob-value">${homeWin}%</div><div class="prob-label">${isHome ? 'V' : 'D'}</div></div>
                    <div class="prob-box"><div class="prob-value">${draw}%</div><div class="prob-label">Empate</div></div>
                    <div class="prob-box"><div class="prob-value">${awayWin}%</div><div class="prob-label">${isHome ? 'D' : 'V'}</div></div>
                </div>
                <div style="margin-top:1rem;font-size:0.8rem;color:var(--text-muted)">* Palpite simples baseado em mando de campo</div>
            </div>`;
    }

    // --- Calendar ---
    window.downloadCalendar = async function () {
        try {
            const data = await api('/matches?status=FINISHED,TIMED,SCHEDULED,IN_PLAY&limit=100');
            const matches = data?.matches || [];

            const lines = [
                'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Palmeiras//Dashboard//EN',
                'X-WR-CALNAME:Palmeiras - Jogos', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'
            ];

            const now = new Date().toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
            matches.forEach(m => {
                const dt = new Date(new Date(m.utcDate).getTime() - 3 * 60 * 60 * 1000);
                const start = dt.toISOString().replace(/[-:]/g, '').split('.')[0];
                const end = new Date(dt.getTime() + 2 * 60 * 60 * 1000).toISOString().replace(/[-:]/g, '').split('.')[0];
                const home = m.homeTeam?.name || 'Home';
                const away = m.awayTeam?.name || 'Away';
                let summary = `🏆 ${home} x ${away}`;
                if (m.status === 'FINISHED') {
                    const s = m.score?.fullTime || {};
                    summary = `🏆 ${home} ${s.home ?? '-'} x ${s.away ?? '-'} ${away}`;
                }
                lines.push('BEGIN:VEVENT', `UID:palmeiras-${m.id}@dashboard`, `DTSTAMP:${now}`,
                    `DTSTART:${start}`, `DTEND:${end}`, `SUMMARY:${summary}`, 'END:VEVENT');
            });
            lines.push('END:VCALENDAR');

            const blob = new Blob([lines.join('\n')], { type: 'text/calendar' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'palmeiras-calendar.ics';
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            alert('Erro ao gerar calendario: ' + e.message);
        }
    };

    window.copyCalendarUrl = async function () {
        const url = window.location.origin + '/api/calendar.ics';
        try {
            await navigator.clipboard.writeText(url);
            alert('Link copiado! ✅\n\nCole no Google Calendar, Apple Calendar ou outro app.');
        } catch {
            prompt('Copie este link:', url);
        }
    };

    // --- Version ---
    fetch('/version').then(r => r.text()).then(v => {
        const el = document.getElementById('portal-version');
        if (el) el.textContent = v;
    });

    // --- Init ---
    document.addEventListener('DOMContentLoaded', () => {
        const now = new Date();
        const el = document.getElementById('last-updated');
        if (el) el.textContent = 'Atualizado: ' + now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

        initTabs();
        loadHero();
        loadMatches();
        loadResults();
        loadStandings();
        loadTeamStats();
        loadNews();
        loadPrediction();
    });

    // Make reload functions globally accessible
    window.loadHero = loadHero;
    window.loadMatches = loadMatches;
    window.loadResults = loadResults;
    window.loadStandings = loadStandings;
    window.loadTeamStats = loadTeamStats;
    window.loadNews = loadNews;
    window.loadPrediction = loadPrediction;
})();
