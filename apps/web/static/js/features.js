/** Palmeiras Agenda — team scopes, match center, history, spoiler mode and Web Push. */
(function () {
    'use strict';

    const KEYS = {
        scope: 'pa-team-scope',
        spoiler: 'pa-spoiler-free',
        followed: 'pa-followed-matches',
        pushPreferences: 'pa-push-preferences',
    };
    const TEAM_IDS = { men: 1769, women: 20002 };
    const DEFAULT_PUSH_PREFERENCES = {
        oneHour: false,
        kickoff: false,
        results: false,
        news: false,
        scheduleChanges: true,
        liveEvents: false,
        spoilerFree: false,
    };

    function readStorage(key, fallback) {
        try {
            const value = localStorage.getItem(key);
            return value == null ? fallback : value;
        } catch (_) {
            return fallback;
        }
    }

    function writeStorage(key, value) {
        try { localStorage.setItem(key, value); } catch (_) { /* Storage can be unavailable. */ }
    }

    function readJson(key, fallback) {
        try { return JSON.parse(readStorage(key, '')) || fallback; } catch (_) { return fallback; }
    }

    const selectedScope = readStorage(KEYS.scope, 'men') === 'women' ? 'women' : 'men';
    const nativeShell = /PalmeirasAgenda(?:iOS|Android)\//.test(navigator.userAgent);
    CONFIG.TEAM_SCOPE = selectedScope;
    CONFIG.TEAM_ID = TEAM_IDS[selectedScope];

    let initialized = false;
    let focusMatch = null;
    let historyPayload = null;
    let historyLoaded = false;
    let spoilerScanQueued = false;
    let heroContextRequest = 0;

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = String(value == null ? '' : value);
        return div.innerHTML;
    }

    function safeUrl(value, fallback = '#') {
        return CONFIG.safeUrl(value, fallback);
    }

    async function api(path, options = {}) {
        const response = await fetch(CONFIG.apiUrl(path), {
            cache: 'no-store',
            credentials: 'same-origin',
            headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
            ...options,
        });
        let body = null;
        try { body = await response.json(); } catch (_) { body = null; }
        if (!response.ok) throw new Error((body && body.error) || `HTTP ${response.status}`);
        return body;
    }

    function teamName(team) {
        return CONFIG.teamName(team || {});
    }

    function matchScore(match) {
        const ready = match && match.homeScore != null && match.awayScore != null;
        return ready ? `${match.homeScore}–${match.awayScore}` : '×';
    }

    function formattedKickoff(value) {
        if (!value) return 'Data a definir';
        return new Intl.DateTimeFormat('pt-BR', {
            weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
            timeZone: CONFIG.BR_TZ,
        }).format(new Date(value));
    }

    function followedMatches() {
        return new Set(readJson(KEYS.followed, []).map(String).filter(Boolean));
    }

    function setFeatureStatus(message) {
        const status = document.getElementById('featureStatus');
        if (status) status.textContent = message || '';
    }

    function googleCalendarUrl(match) {
        const start = new Date(match.utcDate);
        const end = new Date(start.getTime() + 2.5 * 60 * 60 * 1000);
        const stamp = (date) => date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
        const query = new URLSearchParams({
            action: 'TEMPLATE',
            text: `${teamName(match.homeTeam)} x ${teamName(match.awayTeam)}`,
            dates: `${stamp(start)}/${stamp(end)}`,
            details: `Palmeiras Agenda · ${CONFIG.formatComp(match.competition)}`,
            location: match.venue || '',
        });
        return `https://calendar.google.com/calendar/render?${query}`;
    }

    function heroRecordMarkup(h2h) {
        if (h2h === undefined) {
            return `<div class="hero-record is-loading">
                <div class="hero-record-title"><span>Retrospecto recente</span></div>
                <p>Carregando retrospecto...</p>
            </div>`;
        }
        const record = h2h && h2h.record;
        if (!record || !record.played) {
            return `<div class="hero-record is-empty">
                <div class="hero-record-title"><span>Retrospecto recente</span></div>
                <p>Primeiro confronto no arquivo carregado.</p>
            </div>`;
        }
        return `<div class="hero-record">
            <div class="hero-record-title"><span>Retrospecto recente</span><strong>${escapeHtml(record.played)} jogos</strong></div>
            <div class="hero-record-stats">
                <div><strong>${escapeHtml(record.wins)}</strong><span>Vitórias</span></div>
                <div><strong>${escapeHtml(record.draws)}</strong><span>Empates</span></div>
                <div><strong>${escapeHtml(record.losses)}</strong><span>Derrotas</span></div>
                <div><strong>${escapeHtml(record.goalsFor)}–${escapeHtml(record.goalsAgainst)}</strong><span>Gols</span></div>
            </div>
        </div>`;
    }

    function renderHeroContext(match, h2h) {
        const container = document.getElementById('hero-context');
        if (!container) return;
        if (!match) {
            container.innerHTML = '<div class="hero-context-empty">Nenhum jogo disponível.</div>';
            return;
        }
        container.innerHTML = `${heroRecordMarkup(h2h)}
            <div class="hero-icon-actions" aria-label="Ações do jogo">
                <button type="button" class="hero-icon-action" id="heroShareAction" aria-label="Compartilhar jogo" title="Compartilhar jogo">
                    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.5-4.4M8.2 13.2l7.5 4.4"/></svg>
                </button>
                <a class="hero-icon-action" id="heroCalendarAction" href="${escapeHtml(googleCalendarUrl(match))}" target="_blank" rel="noopener" aria-label="Adicionar jogo ao calendário" title="Adicionar ao calendário">
                    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18M12 13v5M9.5 15.5h5"/></svg>
                </a>
            </div>`;
    }

    async function setHeroMatch(match) {
        const requestId = ++heroContextRequest;
        focusMatch = match || null;
        const container = document.getElementById('hero-context');
        if (!container) return;
        if (!focusMatch) {
            renderHeroContext(null, null);
            return;
        }
        renderHeroContext(focusMatch, undefined);
        try {
            const teamId = TEAM_IDS[CONFIG.TEAM_SCOPE];
            const opponent = focusMatch.homeTeam && focusMatch.homeTeam.id === teamId
                ? focusMatch.awayTeam
                : focusMatch.homeTeam;
            if (!opponent || !opponent.id) throw new Error('opponent_unavailable');
            const h2h = await api(
                `h2h?team_scope=${encodeURIComponent(CONFIG.TEAM_SCOPE)}&opponent_id=${encodeURIComponent(opponent.id)}&limit=20`
            );
            if (requestId !== heroContextRequest) return;
            renderHeroContext(focusMatch, h2h);
        } catch (_) {
            if (requestId === heroContextRequest) renderHeroContext(focusMatch, null);
        }
    }

    function computeFilteredRecord(matches) {
        const record = { played: 0, wins: 0, draws: 0, losses: 0, goalsFor: 0, goalsAgainst: 0 };
        matches.forEach((match) => {
            const home = match.homeTeam && match.homeTeam.id === CONFIG.TEAM_ID;
            const goalsFor = home ? match.homeScore : match.awayScore;
            const goalsAgainst = home ? match.awayScore : match.homeScore;
            if (goalsFor == null || goalsAgainst == null) return;
            record.played += 1;
            record.goalsFor += goalsFor;
            record.goalsAgainst += goalsAgainst;
            if (goalsFor > goalsAgainst) record.wins += 1;
            else if (goalsFor < goalsAgainst) record.losses += 1;
            else record.draws += 1;
        });
        return record;
    }

    function populateHistoryFilters(payload) {
        const opponent = document.getElementById('historyOpponent');
        const competition = document.getElementById('historyCompetition');
        const year = document.getElementById('historyYear');
        if (!opponent || !competition || !year) return;
        const opponentValue = opponent.value;
        opponent.innerHTML = '<option value="">Todos</option>' + (payload.opponents || []).map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join('');
        opponent.value = opponentValue;
        const comps = new Map();
        (payload.matches || []).forEach((match) => comps.set(match.competition && match.competition.code, CONFIG.formatComp(match.competition)));
        competition.innerHTML = '<option value="">Todas</option>' + [...comps].filter(([code]) => code).map(([code, label]) => `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`).join('');
        year.innerHTML = '<option value="">Todos</option>' + (payload.seasons || []).map((item) => `<option value="${escapeHtml(item.year)}">${escapeHtml(item.year)}</option>`).join('');
    }

    function renderHistory() {
        const container = document.getElementById('history-content');
        if (!container || !historyPayload) return;
        const opponentId = document.getElementById('historyOpponent')?.value || '';
        const comp = document.getElementById('historyCompetition')?.value || '';
        const year = document.getElementById('historyYear')?.value || '';
        const matches = (historyPayload.matches || []).filter((match) => {
            const homeId = String(match.homeTeam && match.homeTeam.id || '');
            const awayId = String(match.awayTeam && match.awayTeam.id || '');
            const opponentMatches = !opponentId || (homeId === opponentId || awayId === opponentId);
            const competitionMatches = !comp || (match.competition && match.competition.code === comp);
            const yearMatches = !year || String(new Date(match.utcDate).getFullYear()) === year;
            return opponentMatches && competitionMatches && yearMatches;
        });
        const record = computeFilteredRecord(matches);
        const summary = document.getElementById('history-summary');
        if (summary) summary.textContent = `${record.played} jogos · ${record.wins} vitórias · ${record.draws} empates · ${record.losses} derrotas`;
        container.innerHTML = `<div class="history-record">
            <div><strong>${record.played}</strong><span>Jogos</span></div><div><strong>${record.wins}</strong><span>Vitórias</span></div>
            <div><strong>${record.draws}</strong><span>Empates</span></div><div><strong>${record.losses}</strong><span>Derrotas</span></div>
            <div><strong>${record.goalsFor}–${record.goalsAgainst}</strong><span>Gols</span></div>
        </div>
        <div class="history-list">${matches.length ? matches.map((match) => `
            <details class="history-match">
                <summary><time>${escapeHtml(formattedKickoff(match.utcDate))}</time><div><span>${escapeHtml(teamName(match.homeTeam))}</span><strong data-spoiler-score="true">${escapeHtml(matchScore(match))}</strong><span>${escapeHtml(teamName(match.awayTeam))}</span></div><small>${escapeHtml(CONFIG.formatComp(match.competition))}</small></summary>
                <div><span>${escapeHtml(match.venue || 'Local não informado')}</span><a href="/?match=${escapeHtml(match.id)}">Destacar no banner</a></div>
            </details>`).join('') : '<div class="empty">Nenhum jogo corresponde aos filtros.</div>'}</div>`;
        queueSpoilerScan();
    }

    async function loadHistory(force = false) {
        if (historyLoaded && !force) { renderHistory(); return; }
        const container = document.getElementById('history-content');
        try {
            historyPayload = await api(`history?team_scope=${CONFIG.TEAM_SCOPE}&from_year=2000&limit=1000`);
            historyLoaded = true;
            populateHistoryFilters(historyPayload);
            renderHistory();
        } catch (_) {
            if (container) container.innerHTML = '<div class="error-state"><strong>Histórico indisponível</strong><span>Não foi possível carregar o arquivo agora.</span></div>';
        }
    }

    function pushPreferences() {
        return { ...DEFAULT_PUSH_PREFERENCES, ...readJson(KEYS.pushPreferences, {}), spoilerFree: document.body.classList.contains('spoiler-free') };
    }

    function collectPreferenceInputs() {
        const result = pushPreferences();
        document.querySelectorAll('[data-push-pref]').forEach((input) => { result[input.dataset.pushPref] = input.checked; });
        writeStorage(KEYS.pushPreferences, JSON.stringify(result));
        return result;
    }

    function syncPreferenceInputs() {
        const preferences = pushPreferences();
        document.querySelectorAll('[data-push-pref]').forEach((input) => { input.checked = Boolean(preferences[input.dataset.pushPref]); });
    }

    function pushStatus(message) {
        const target = document.getElementById('pushStatus');
        if (target) target.textContent = message;
        setFeatureStatus(message);
    }

    function base64ToUint8Array(value) {
        const padding = '='.repeat((4 - value.length % 4) % 4);
        const raw = atob((value + padding).replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
    }

    async function currentRegistration() {
        if (!('serviceWorker' in navigator)) throw new Error('Service Worker não suportado');
        await navigator.serviceWorker.register('/sw.js');
        return navigator.serviceWorker.ready;
    }

    async function savePushSubscription({ requestPermission = false } = {}) {
        if (!('PushManager' in window) || !('Notification' in window)) throw new Error('Alertas não suportados neste navegador');
        if (requestPermission && Notification.permission !== 'granted') {
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') throw new Error('Permissão de notificações não concedida');
        }
        if (Notification.permission !== 'granted') return null;
        const registration = await currentRegistration();
        let subscription = await registration.pushManager.getSubscription();
        if (!subscription) {
            const key = await api('push/public-key');
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: base64ToUint8Array(key.publicKey),
            });
        }
        const preferences = collectPreferenceInputs();
        await api('push/subscriptions', {
            method: 'POST',
            body: JSON.stringify({
                subscription: subscription.toJSON(),
                preferences,
                followedMatchIds: [...followedMatches()],
                teamScope: CONFIG.TEAM_SCOPE,
            }),
        });
        pushStatus('Alertas ativos e sincronizados.');
        updateNotificationControls({ active: true });
        return subscription;
    }

    async function enablePush() {
        // Enable = activate ALL alert types so the user receives every notification.
        document.querySelectorAll('[data-push-pref]').forEach((input) => { input.checked = true; });
        collectPreferenceInputs();
        updateNotificationControls({ active: false, busy: true });
        pushStatus('Ativando alertas...');
        try { await savePushSubscription({ requestPermission: true }); }
        catch (error) {
            pushStatus(error.message || 'Não foi possível ativar alertas.');
            await refreshPushState({ announce: false });
        }
    }

    async function disablePush() {
        // Disable = silence ALL alert types.
        document.querySelectorAll('[data-push-pref]').forEach((input) => { input.checked = false; });
        collectPreferenceInputs();
        updateNotificationControls({ active: true, busy: true });
        try {
            const registration = await currentRegistration();
            const subscription = await registration.pushManager.getSubscription();
            if (subscription) {
                await api('push/subscriptions', { method: 'DELETE', body: JSON.stringify({ subscription: subscription.toJSON() }) });
                await subscription.unsubscribe();
            }
            pushStatus('Alertas desativados neste navegador.');
            updateNotificationControls({ active: false });
        } catch (error) {
            pushStatus(error.message || 'Não foi possível desativar alertas.');
            await refreshPushState({ announce: false });
        }
    }

    function updateNotificationControls({
        active = false,
        supported = true,
        busy = false,
        blocked = false,
        native = false,
    } = {}) {
        const quick = document.getElementById('quickNotifyButton');
        const enable = document.getElementById('enablePushButton');
        const disable = document.getElementById('disablePushButton');
        const settingsSection = enable?.closest('.settings-section');
        const state = busy
            ? 'pending'
            : (!supported ? 'unsupported' : (blocked ? 'blocked' : (active ? 'active' : 'inactive')));
        document.body.dataset.notificationState = state;

        if (quick) {
            let label = active ? 'Desativar alertas' : 'Ativar alertas';
            if (native) {
                label = active
                    ? 'Notificações ativas — abrir Ajustes'
                    : (blocked
                        ? 'Notificações bloqueadas — abrir Ajustes'
                        : 'Configurar notificações em Ajustes');
            } else if (!supported) {
                label = 'Alertas indisponíveis neste navegador';
            } else if (blocked) {
                label = 'Notificações bloqueadas no navegador';
            } else if (busy) {
                label = 'Atualizando alertas';
            }
            quick.disabled = busy || (!native && (!supported || blocked));
            quick.setAttribute('aria-pressed', String(active));
            quick.setAttribute('aria-busy', String(busy));
            quick.setAttribute('aria-label', label);
            quick.title = label;
        }

        if (enable) {
            enable.disabled = native || busy || !supported || blocked || active;
            enable.textContent = active
                ? 'Alertas ativos'
                : (busy
                    ? 'Salvando alertas…'
                    : (blocked
                        ? 'Permissão bloqueada'
                        : (supported ? 'Ativar e salvar alertas' : 'Alertas indisponíveis')));
        }
        if (disable) disable.disabled = native || busy || !supported || !active;
        if (settingsSection) {
            settingsSection.dataset.notificationState = state;
            settingsSection.setAttribute('aria-busy', String(busy));
        }
    }

    function setNativeNotificationState(payload = {}) {
        if (!nativeShell) return;
        const permission = String(payload.permission || 'notDetermined');
        const active = Boolean(payload.active);
        const blocked = permission === 'denied';
        // Sync individual preference values from native to web checkboxes.
        if (payload.preferences && typeof payload.preferences === 'object') {
            const prefs = payload.preferences;
            document.querySelectorAll('[data-push-pref]').forEach((input) => {
                if (prefs[input.dataset.pushPref] !== undefined) input.checked = Boolean(prefs[input.dataset.pushPref]);
            });
        }
        updateNotificationControls({
            active,
            blocked,
            native: true,
        });
        if (active) pushStatus('Notificações ativas no aplicativo.');
        else if (blocked) pushStatus('Notificações bloqueadas nas permissões do aparelho.');
        else pushStatus('Configure as notificações nos Ajustes do aplicativo.');
    }

    function requestNativeNotificationState() {
        if (!nativeShell) return false;
        try {
            if (window.PalmeirasNative?.getNotificationState) {
                const payload = JSON.parse(window.PalmeirasNative.getNotificationState());
                setNativeNotificationState(payload);
                return true;
            }
            if (window.webkit?.messageHandlers?.palmeirasNative) {
                window.webkit.messageHandlers.palmeirasNative.postMessage({
                    action: 'requestNotificationState',
                });
                updateNotificationControls({ busy: true, native: true });
                return true;
            }
        } catch (_) {
            updateNotificationControls({ active: false, native: true });
        }
        return false;
    }

    function openNativeNotificationSettings() {
        if (!nativeShell) return false;
        if (window.PalmeirasNative?.openNotificationSettings) {
            window.PalmeirasNative.openNotificationSettings();
            return true;
        }
        if (window.webkit?.messageHandlers?.palmeirasNative) {
            window.webkit.messageHandlers.palmeirasNative.postMessage({
                action: 'openNotificationSettings',
            });
            return true;
        }
        return false;
    }

    function toggleNativeNotifications(enable) {
        if (!nativeShell) return false;
        if (window.PalmeirasNative?.toggleNotifications) {
            window.PalmeirasNative.toggleNotifications(enable);
            return true;
        }
        if (window.webkit?.messageHandlers?.palmeirasNative) {
            window.webkit.messageHandlers.palmeirasNative.postMessage({
                action: 'toggleNotifications',
                enable,
            });
            updateNotificationControls({ busy: true, native: true });
            return true;
        }
        return false;
    }

    async function togglePush() {
        const quick = document.getElementById('quickNotifyButton');
        const isOn = quick?.getAttribute('aria-pressed') === 'true';
        // On native shells, toggle all prefs via the bridge instead of opening settings.
        if (nativeShell && toggleNativeNotifications(!isOn)) return;
        if (!isOn) await enablePush();
        else await disablePush();
    }

    async function refreshPushState({ announce = true } = {}) {
        if (nativeShell) {
            requestNativeNotificationState();
            return;
        }
        if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
            pushStatus('Este navegador não oferece Web Push.');
            updateNotificationControls({ supported: false });
            return;
        }
        if (Notification.permission === 'denied') {
            pushStatus('Permissão de notificações bloqueada neste navegador.');
            updateNotificationControls({ blocked: true });
            return;
        }
        try {
            const registration = await currentRegistration();
            const subscription = await registration.pushManager.getSubscription();
            const active = Boolean(subscription);
            updateNotificationControls({ active });
            if (announce) {
                pushStatus(active
                    ? 'Alertas ativos neste navegador.'
                    : 'Alertas desativados neste navegador.');
            }
        } catch (_) {
            updateNotificationControls({ active: false });
        }
    }

    function applySpoilerPreference() {
        const enabled = readStorage(KEYS.spoiler, 'false') === 'true';
        document.body.classList.toggle('spoiler-free', enabled);
        const toggle = document.getElementById('spoilerFreeToggle');
        if (toggle) {
            const label = enabled ? 'Mostrar placares' : 'Ocultar placares';
            toggle.checked = enabled;
            toggle.setAttribute('aria-label', label);
            const control = toggle.closest('.spoiler-toggle');
            control?.classList.toggle('active', enabled);
            if (control) control.title = label;
        }
        queueSpoilerScan();
    }

    function scanSpoilerScores() {
        spoilerScanQueued = false;
        const selectors = [
            '.hero-center-score', '.palmeiras-score', '.cal-score', '.worldcup-score',
            '.worldcup-final-result strong', '.worldcup-brazil-teams strong', '.prediction-score',
            '.competition-match strong em', '.history-match summary strong',
        ];
        document.querySelectorAll(selectors.join(',')).forEach((node) => {
            if (/\d+\s*[–—-]\s*\d+/.test(node.textContent || '')) node.dataset.spoilerScore = 'true';
        });
    }

    function queueSpoilerScan() {
        if (spoilerScanQueued) return;
        spoilerScanQueued = true;
        requestAnimationFrame(scanSpoilerScores);
    }

    function syncScopeUi() {
        document.body.dataset.teamScope = CONFIG.TEAM_SCOPE;
        document.querySelectorAll('[data-team-scope]').forEach((button) => {
            const selected = button.dataset.teamScope === CONFIG.TEAM_SCOPE;
            button.classList.toggle('active', selected);
            button.setAttribute('aria-pressed', String(selected));
        });
        const calendarLink = document.getElementById('scopedCalendarLink');
        if (calendarLink) calendarLink.href = `/api/v1/calendar.ics?team_scope=${CONFIG.TEAM_SCOPE}`;
        const feminine = CONFIG.TEAM_SCOPE === 'women';
        const homeTitle = document.getElementById('palmeiras-home-title');
        if (homeTitle && feminine) homeTitle.textContent = 'Próximos jogos e resultados do Palmeiras Feminino';
        const statsTitle = document.getElementById('stats-title');
        if (statsTitle && feminine) statsTitle.textContent = 'Estatísticas do Palmeiras Feminino';
    }

    async function shareFocusMatch() {
        if (!focusMatch) return;
        const text = `${teamName(focusMatch.homeTeam)} x ${teamName(focusMatch.awayTeam)} · ${formattedKickoff(focusMatch.utcDate)}`;
        const url = `${location.origin}/?match=${encodeURIComponent(focusMatch.id)}`;
        try {
            if (navigator.share) await navigator.share({ title: 'Palmeiras Agenda', text, url });
            else { await navigator.clipboard.writeText(`${text} ${url}`); setFeatureStatus('Link do jogo copiado.'); }
        } catch (_) { /* Share cancellation is not an error state. */ }
    }

    function bindControls() {
        document.querySelectorAll('[data-team-scope]').forEach((button) => button.addEventListener('click', () => {
            const scope = button.dataset.teamScope;
            if (!TEAM_IDS[scope] || scope === CONFIG.TEAM_SCOPE) return;
            writeStorage(KEYS.scope, scope);
            location.reload();
        }));
        document.getElementById('spoilerFreeToggle')?.addEventListener('change', (event) => {
            writeStorage(KEYS.spoiler, String(event.target.checked));
            applySpoilerPreference();
            savePushSubscription().catch(() => {});
        });
        document.getElementById('quickNotifyButton')?.addEventListener('click', togglePush);
        document.getElementById('enablePushButton')?.addEventListener('click', enablePush);
        document.getElementById('disablePushButton')?.addEventListener('click', disablePush);
        document.querySelectorAll('[data-push-pref]').forEach((input) => input.addEventListener('change', () => {
            collectPreferenceInputs();
            savePushSubscription().catch(() => {});
        }));
        ['historyOpponent', 'historyCompetition', 'historyYear'].forEach((id) => document.getElementById(id)?.addEventListener('change', renderHistory));
        document.getElementById('historyClear')?.addEventListener('click', () => {
            ['historyOpponent', 'historyCompetition', 'historyYear'].forEach((id) => { const node = document.getElementById(id); if (node) node.value = ''; });
            renderHistory();
        });
        document.querySelectorAll('[data-open-tab]').forEach((button) => button.addEventListener('click', () => {
            document.querySelector(`.tab-btn[data-tab="${button.dataset.openTab}"]`)?.click();
        }));
        document.getElementById('hero-context')?.addEventListener('click', (event) => {
            if (event.target.closest('#heroShareAction')) shareFocusMatch();
        });
    }

    function onTabActivated(tab) {
        if (tab === 'historico') loadHistory();
        if (tab === 'ajustes') { syncPreferenceInputs(); refreshPushState(); }
    }

    async function loadAll() {
        const work = focusMatch ? [setHeroMatch(focusMatch)] : [];
        if (historyLoaded || document.body.dataset.activeTab === 'historico') work.push(loadHistory(true));
        await Promise.allSettled(work);
    }

    function init() {
        if (initialized) return;
        initialized = true;
        syncScopeUi();
        applySpoilerPreference();
        syncPreferenceInputs();
        bindControls();
        refreshPushState();
        window.addEventListener('pageshow', () => refreshPushState({ announce: false }));
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') refreshPushState({ announce: false });
        });
        const observer = new MutationObserver(queueSpoilerScan);
        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }

    window.PalmeirasFeatures = {
        init,
        loadAll,
        loadHistory,
        setHeroMatch,
        onTabActivated,
        setNativeNotificationState,
    };
    document.addEventListener('DOMContentLoaded', init, { once: true });
})();
