/**
 * Palmeiras Dashboard v3 — With Athena's design system
 *
 * Features:
 * - Live match with estimated minute + auto-refresh
 * - Color-coded results (win/draw/loss)
 * - Animated transitions
 * - Standings with Palmeiras highlighted
 */
(function () {
    'use strict';

    const TEAM_ID = 1769;
    const BR_TZ = 'America/Sao_Paulo';
    let liveInterval = null;

    // --- Helpers ---
    function formatDate(d) {
        return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ });
    }
    function formatTime(d) {
        return new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
    }
    function formatComp(comp) {
        const names = { BSA: 'Brasileirão', COPA_DO_BRASIL: 'Copa do Brasil', LIBERTADORES: 'Libertadores' };
        return names[comp?.code] || comp?.name || 'Campeonato';
    }

    // --- Minute Estimation ---
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

    // --- UI States ---
    function showSkeleton(id, type) {
        const el = document.getElementById(id);
        if (type === 'hero') {
            el.innerHTML = '<div style="padding:2rem"><div class="skeleton-line" style="height:24px;width:50%;margin:0 auto 1rem"></div><div style="display:flex;justify-content:space-around;margin:1rem 0"><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div><div class="skeleton-line" style="width:60px;height:40px"></div><div class="skeleton-line" style="width:80px;height:80px;border-radius:50%"></div></div></div>';
        } else {
            el.innerHTML = '<div class="skeleton-card"><div class="skeleton-line short"></div><div class="skeleton-line medium"></div></div>'.repeat(3);
        }
    }
    function showError(id, msg, fn) {
        document.getElementById(id).innerHTML = `<div class="error-state"><div class="error-icon">⚠️</div><div class="error-message">${msg}</div>${fn ? `<button class="retry-btn" onclick="${fn}()">Tentar novamente</button>` : ''}</div>`;
    }
    function showEmpty(id, msg) {
        document.getElementById(id).innerHTML = `<div class="empty">${msg}</div>`;
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
                const target = document.getElementById(btn.dataset.tab);
                target.classList.add('active');
                target.style.animation = 'none';
                target.offsetHeight;
                target.style.animation = '';
                // Smooth scroll to tab content
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
    }

    // --- Scroll Spy ---
    function initScrollSpy() {
        const tabs = Array.from(document.querySelectorAll('.tab-btn'));
        const tabIds = ['proximos', 'resultados', 'classificacao', 'estatisticas', 'news', 'palpites'];

        // Map tab IDs to their index for ordering
        const tabIndex = {};
        tabIds.forEach((id, i) => tabIndex[id] = i);

        let lastActive = null;

        function setActive(id) {
            if (id === lastActive) return;
            lastActive = id;
            tabs.forEach(btn => {
                const isActive = btn.dataset.tab === id;
                btn.classList.toggle('active', isActive);
                const content = document.getElementById(btn.dataset.tab);
                if (content) content.classList.toggle('active', isActive);
            });
        }

        // Find the first visible (non-collapsed) tab content
        function getVisibleTabId() {
            for (const id of tabIds) {
                const el = document.getElementById(id);
                if (!el) continue;
                const rect = el.getBoundingClientRect();
                if (rect.height > 0) return id;
            }
            return tabIds[0];
        }

        // Scroll-based: detect which tab content block is currently in viewport center
        function onScroll() {
            const scrollY = window.scrollY;
            const vh = window.innerHeight;
            const center = scrollY + vh * 0.35;
            let best = null, bestTop = -Infinity;

            for (const id of tabIds) {
                const el = document.getElementById(id);
                if (!el) continue;
                const rect = el.getBoundingClientRect();
                // Only consider visible (expanded) tabs
                if (rect.height === 0) continue;
                const elTop = rect.top + scrollY;
                if (elTop <= center && elTop > bestTop) {
                    bestTop = elTop;
                    best = id;
                }
            }

            if (best) setActive(best);
        }

        window.addEventListener('scroll', onScroll, { passive: true });
        // Initialize with the visible tab
        setActive(getVisibleTabId());
    }

    // --- Hero ---
    async function loadHero() {
        showSkeleton('hero-front', 'hero');
        const data = await api('matches?status=SCHEDULED,TIMED,IN_PLAY&limit=5');
        if (!data) { showError('hero-front', 'Erro ao carregar', 'loadHero'); return; }
        const match = data.matches?.[0];
        if (!match) { showEmpty('hero-front', 'Nenhum jogo agendado'); return; }

        const home = match.homeTeam, away = match.awayTeam;
        const comp = formatComp(match.competition);
        const dt = new Date(match.utcDate);
        const dayOfWeek = dt.toLocaleDateString('pt-BR', { weekday: 'long', timeZone: BR_TZ });
        const isLive = match.status === 'IN_PLAY';
        const score = match.score?.fullTime || {};
        const ht = match.score?.halfTime || {};

        // Hero card live state
        const heroCard = document.getElementById('hero-match');
        heroCard.classList.toggle('live', isLive);

        // Live badge with pulsing dot
        const liveBadge = isLive ? '<span class="live-dot"></span>AO VIVO' : '';

        // Minute estimation
        const minute = isLive ? estimateMinute(match.utcDate) : null;

        // Venue: use API value, or Allianz Parque for home, or opponent stadium for away
        function getVenue(match) {
            if (match.venue) return match.venue;
            if (match.homeTeam?.id === TEAM_ID) return 'Allianz Parque';
            // Known stadiums
            const stadiums = {
                1776: 'Morumbi',        // São Paulo
                1777: 'Fonte Nova',     // Bahia
                1770: 'Nilton Santos',  // Botafogo
                1779: 'Maracanã',       // Flamengo/Fluminense
                1783: 'Beira-Rio',      // Internacional
                1766: 'Mineirão',       // Cruzeiro
                1780: 'Castelão',       // Fortaleza
                1765: 'Arena MRV',      // Atlético-MG
            };
            const awayId = match.awayTeam?.id === TEAM_ID ? match.homeTeam?.id : match.awayTeam?.id;
            return stadiums[awayId] || 'A definir';
        }

        // Info bar
        document.getElementById('where-watch').textContent = match.broadcast || 'Rodada ' + (match.matchday || '-');
        document.getElementById('stadium-info').textContent = getVenue(match);

        // Score display
        let scoreHtml;
        if (isLive) {
            scoreHtml = `<div class="hero-score">${score.home ?? 0} × ${score.away ?? 0}</div>`;
            if (minute) scoreHtml += `<div class="hero-minute">${minute}</div>`;
        } else {
            scoreHtml = `<div class="hero-vs">×</div>`;
        }

        document.getElementById('hero-front').innerHTML = `
            <div class="hero-comp">${liveBadge ? liveBadge + ' · ' : ''}${comp}</div>
            <div class="hero-teams">
                <div class="hero-team">
                    <img src="${home.crest || ''}" style="width:56px;height:56px" onerror="this.src='https://crests.football-data.org/1769.png'">
                    <div class="hero-team-name">${home.shortName || home.name}</div>
                </div>
                ${scoreHtml}
                <div class="hero-team">
                    <img src="${away.crest || ''}" style="width:56px;height:56px" onerror="this.src='https://crests.football-data.org/4364.png'">
                    <div class="hero-team-name">${away.shortName || away.name}</div>
                </div>
            </div>
            <div class="hero-date">${isLive ? 'JOGANDO AGORA' : formatDate(match.utcDate) + ' · ' + formatTime(match.utcDate)}<span style="display:block;font-size:0.85rem;opacity:0.8;margin-top:0.3rem;font-weight:400">${isLive ? '' : dayOfWeek}</span></div>`;

        // Back card with details
        const venue = getVenue(match);
        const htScore = (ht.home != null && ht.away != null) ? `<p style="margin:0.5rem 0"><strong>1º tempo:</strong> ${ht.home}–${ht.away}</p>` : '';
        document.getElementById('hero-back').innerHTML = `
            <div style="padding-top:1rem"><h3 style="margin-bottom:1rem">Detalhes do Jogo</h3>
            <p style="margin:0.5rem 0"><strong>Rodada:</strong> ${match.matchday || '-'}</p>
            <p style="margin:0.5rem 0"><strong>Estádio:</strong> ${venue}</p>
            <p style="margin:0.5rem 0"><strong>Competição:</strong> ${comp}</p>
            <p style="margin:0.5rem 0"><strong>Transmissão:</strong> ${match.broadcast || 'A confirmar'}</p>
            ${htScore}
            ${match.stage && match.stage !== 'REGULAR_SEASON' ? `<p style="margin:0.5rem 0"><strong>Fase:</strong> ${match.stage}</p>` : ''}</div>`;

        // Auto-refresh during live
        if (isLive && !liveInterval) {
            liveInterval = setInterval(() => loadHero(), 30000);
        } else if (!isLive && liveInterval) {
            clearInterval(liveInterval);
            liveInterval = null;
        }
    }

    // --- Matches ---
    async function loadMatches() {
        showSkeleton('next-matches');
        const data = await api('matches?status=SCHEDULED,TIMED,IN_PLAY&limit=10');
        if (!data) { showError('next-matches', 'Erro ao carregar', 'loadMatches'); return; }
        const matches = data.matches || [];
        if (!matches.length) { showEmpty('next-matches', 'Nenhum jogo agendado'); return; }

        document.getElementById('next-matches').innerHTML = matches.map(m => {
            const isLive = m.status === 'IN_PLAY';
            const venue = m.venue || (m.homeTeam.id === TEAM_ID ? 'Allianz Parque' : (function() {
                const stadiums = { 1776: 'Morumbi', 1777: 'Fonte Nova', 1770: 'Nilton Santos', 1779: 'Maracanã', 1783: 'Beira-Rio', 1766: 'Mineirão', 1780: 'Castelão', 1765: 'Arena MRV' };
                return stadiums[m.homeTeam?.id] || 'A definir';
            })());
            const ht = m.score?.halfTime || {};
            const htInfo = (ht.home != null) ? `<div class="match-extra-row"><span class="icon">⏱️</span> 1º tempo: ${ht.home}–${ht.away}</div>` : '';

            return `<div class="match-item">
                <div class="match-extra">
                    <div class="match-extra-row"><span class="icon">🏟️</span> ${venue}</div>
                    <div class="match-extra-row"><span class="icon">📺</span> ${m.broadcast || 'A confirmar'}</div>
                    <div class="match-extra-row"><span class="icon">🔢</span> Rodada ${m.matchday || '-'}${m.stage && m.stage !== 'REGULAR_SEASON' ? ' · ' + m.stage : ''}</div>
                    ${htInfo}
                </div>
                <div class="match-header"><span>${isLive ? '<span class="live-dot"></span>AO VIVO · ' : ''}${formatDate(m.utcDate)} · ${formatTime(m.utcDate)}</span><span>${formatComp(m.competition)}</span></div>
                <div class="match-teams">
                    <span><img src="${m.homeTeam.crest}" style="width:22px;height:22px;vertical-align:middle;margin-right:4px">${m.homeTeam.shortName || m.homeTeam.name}</span>
                    <span style="color:var(--text-muted)">×</span>
                    <span>${m.awayTeam.shortName || m.awayTeam.name}<img src="${m.awayTeam.crest}" style="width:22px;height:22px;vertical-align:middle;margin-left:4px"></span>
                </div>
            </div>`;
        }).join('');

        document.querySelectorAll('#next-matches .match-item').forEach(el => {
            el.addEventListener('click', () => {
                const extra = el.querySelector('.match-extra');
                extra.classList.toggle('open');
            });
        });
    }

    // --- Results ---
    async function loadResults() {
        showSkeleton('recent-results');
        const data = await api('matches?status=FINISHED&limit=8');
        if (!data) { showError('recent-results', 'Erro ao carregar', 'loadResults'); return; }
        const matches = data.matches || [];
        if (!matches.length) { showEmpty('recent-results', 'Nenhum resultado'); return; }

        document.getElementById('recent-results').innerHTML = matches.map(m => {
            const isHome = m.homeTeam.id === TEAM_ID;
            const our = isHome ? m.score.fullTime.home : m.score.fullTime.away;
            const opp = isHome ? m.score.fullTime.away : m.score.fullTime.home;
            const oppName = isHome ? m.awayTeam.shortName || m.awayTeam.name : m.homeTeam.shortName || m.homeTeam.name;
            const r = our > opp ? 'V' : our < opp ? 'D' : 'E';
            const resultClass = r === 'V' ? 'win' : r === 'D' ? 'loss' : 'draw';

            const ht = m.score?.halfTime || {};
            const htInfo = (ht.home != null) ? `<div class="match-extra-row"><span class="icon">⏱️</span> 1º tempo: ${ht.home}–${ht.away}</div>` : '';

            return `<div class="match-item ${resultClass}">
                <div class="match-extra">
                    <div class="match-extra-row"><span class="icon">🏟️</span> ${m.venue || 'A definir'}</div>
                    <div class="match-extra-row"><span class="icon">📺</span> ${m.broadcast || 'A confirmar'}</div>
                    <div class="match-extra-row"><span class="icon">🔢</span> Rodada ${m.matchday || '-'}</div>
                    ${htInfo}
                </div>
                <div class="match-header"><span>${formatDate(m.utcDate)}</span><span>${formatComp(m.competition)}</span></div>
                <div class="match-teams">
                    <span>${isHome ? '🏠' : '✈️'} ${oppName}</span>
                    <span style="display:flex;align-items:center;gap:0.5rem">
                        <span class="result-badge ${resultClass}">${r === 'V' ? '✅ V' : r === 'D' ? '❌ D' : '➖ E'}</span>
                        <span class="match-score">${our} – ${opp}</span>
                    </span>
                </div>
            </div>`;
        }).join('');

        document.querySelectorAll('#recent-results .match-item').forEach(el => {
            el.addEventListener('click', () => {
                const extra = el.querySelector('.match-extra');
                extra.classList.toggle('open');
            });
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

        // Position badge with stats
        const gd = team.goalDifference;
        const avg = team.playedGames > 0 ? (team.points / team.playedGames).toFixed(2) : '0';

        // Full table
        const tableHtml = rows.map(s => {
            const isPalmeiras = s.teamId === TEAM_ID;
            return `<div class="standings-row ${isPalmeiras ? 'palmeiras' : ''}">
                <span class="pos">${s.position}</span>
                <span class="team">${s.teamShort || s.teamName}</span>
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
            <div style="border-top:1px solid var(--bg);padding-top:1rem">
                ${tableHtml}
            </div>`;
    }

    // --- Stats ---
    async function loadTeamStats() {
        showSkeleton('team-stats');
        const data = await api('matches?status=FINISHED&limit=20');
        if (!data) { showError('team-stats', 'Erro ao carregar', 'loadTeamStats'); return; }
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
        if (!data || !Array.isArray(data) || !data.length) { showEmpty('news-list', 'Nenhuma notícia'); return; }
        document.getElementById('news-list').innerHTML = data.slice(0, 8).map(n => {
            const sourceIcon = n.source === 'lance.com.br' ? '🔵' : '🔴';
            return `<div class="news-item" onclick="window.open('${n.url}','_blank')">
                <div class="news-title">${n.title}</div>
                <div class="news-meta">${sourceIcon} <span class="news-source">${n.source || 'ge.globo'}</span></div>
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
                <div style="font-size:1.1rem;font-weight:600;margin-bottom:0.5rem">${match.homeTeam.shortName || match.homeTeam.name} × ${match.awayTeam.shortName || match.awayTeam.name}</div>
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
            const data = await api('matches?status=FINISHED,TIMED,SCHEDULED,IN_PLAY&limit=100');
            const matches = data?.matches || [];
            const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Palmeiras//EN', 'X-WR-CALNAME:Palmeiras - Jogos', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH'];
            const now = new Date().toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
            matches.forEach(m => {
                const dt = new Date(new Date(m.utcDate).getTime() - 3 * 3600000);
                const s = dt.toISOString().replace(/[-:]/g, '').split('.')[0];
                const e = new Date(dt.getTime() + 7200000).toISOString().replace(/[-:]/g, '').split('.')[0];
                const h = m.homeTeam?.shortName || m.homeTeam?.name || 'Home';
                const a = m.awayTeam?.shortName || m.awayTeam?.name || 'Away';
                let sum = `${h} × ${a}`;
                if (m.status === 'FINISHED') { const sc = m.score?.fullTime || {}; sum = `${h} ${sc.home ?? '-'} × ${sc.away ?? '-'} ${a}`; }
                lines.push('BEGIN:VEVENT', `UID:p-${m.id}@palmeiras`, `DTSTAMP:${now}`, `DTSTART:${s}`, `DTEND:${e}`, `SUMMARY:${sum}`, 'END:VEVENT');
            });
            lines.push('END:VCALENDAR');
            const blob = new Blob([lines.join('\n')], { type: 'text/calendar' });
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'palmeiras.ics'; a.click();
        } catch (e) { alert('Erro: ' + e.message); }
    };
    window.copyCalendarUrl = async function () {
        const url = window.location.origin + '/api/calendar.ics';
        try { await navigator.clipboard.writeText(url); alert('Link copiado!'); } catch { prompt('Copie:', url); }
    };

    // --- Init ---
    window.loadHero = loadHero;
    window.loadMatches = loadMatches;
    window.loadResults = loadResults;
    window.loadStandings = loadStandings;
    window.loadTeamStats = loadTeamStats;
    window.loadNews = loadNews;
    window.loadPrediction = loadPrediction;

    document.addEventListener('DOMContentLoaded', () => {
        const el = document.getElementById('last-updated');
        if (el) el.textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        initTabs();
        initScrollSpy();
        loadHero(); loadMatches(); loadResults(); loadStandings(); loadTeamStats(); loadNews(); loadPrediction();
    });
})();
