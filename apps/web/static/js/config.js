/**
 * Futebol Agenda — Shared configuration.
 * Club-aware constants and helpers used across JS modules.
 *
 * The selected club is determined by clubs.js (CLUBS.getSelected()) before
 * this file loads. All team-specific values are derived from the club registry.
 */
const CONFIG = {
    /** Selected club ID (e.g. "palmeiras", "corinthians") */
    CLUB_ID: CLUBS.getSelected(),

    /** Football-data.org team ID for the active scope (men or women) */
    TEAM_ID: 0,
    MEN_TEAM_ID: 0,
    WOMEN_TEAM_ID: 0,
    TEAM_SCOPE: 'men',
    BR_TZ: 'America/Sao_Paulo',

    API_BASE_URL: (function () {
        const meta = document.querySelector('meta[name="api-base-url"]');
        return (
            window.PALMEIRAS_API_BASE_URL ||
            (meta ? meta.getAttribute('content') : '') ||
            ''
        ).replace(/\/$/, '');
    })(),

    /** Build an API URL from a path such as "matches?limit=10" */
    apiUrl(path) {
        const cleanPath = String(path || '').replace(/^\/+/, '');
        return `${this.API_BASE_URL}/api/v1/${cleanPath}`;
    },

    /** Known stadium names by opponent team ID (shared across all clubs) */
    STADIUMS: {
        1765: 'Maracanã',
        1766: 'Arena MRV',
        1767: 'Arena do Grêmio',
        1768: 'Ligga Arena',
        1770: 'Estádio Nilton Santos',
        1771: 'Mineirão',
        1772: 'Arena Condá',
        1776: 'MorumBIS',
        1777: 'Arena Fonte Nova',
        1779: 'Neo Química Arena',
        1780: 'São Januário',
        1782: 'Barradão',
        1783: 'Maracanã',
        4241: 'Couto Pereira',
        4286: 'Nabi Abi Chedid',
        4287: 'Baenão',
        4364: 'Maião',
        6684: 'Beira-Rio',
        6685: 'Vila Belmiro',
    },

    /** Restrict dynamic URLs before rendering them into href/src attributes. */
    safeUrl(value, fallback = '#') {
        const raw = String(value || '').trim();
        if (!raw || raw === '#') return fallback;
        try {
            const base = typeof window !== 'undefined' && window.location
                ? window.location.origin
                : 'https://palmeiras.rodrigolanna.com.br';
            const url = new URL(raw, base);
            if (!['http:', 'https:'].includes(url.protocol)) return fallback;
            return url.href;
        } catch {
            return fallback;
        }
    },

    /** Competition code display names */
    COMP_NAMES: {
        BSA: 'Brasileirão',
        COPA: 'Copa do Brasil',
        CBC: 'Copa do Brasil',
        COPA_DO_BRASIL: 'Copa do Brasil',
        CLI: 'Libertadores',
        CL: 'Libertadores',
        LIBERTADORES: 'Libertadores',
        COPA_LIBERTADORES: 'Libertadores',
        CPA: 'Paulistão',
        CAMPEONATO_PAULISTA: 'Paulistão',
        PAULISTA: 'Paulistão',
        WC: 'Copa do Mundo 2026',
        WORLD_CUP: 'Copa do Mundo 2026',
        FIFA_WORLD_CUP: 'Copa do Mundo 2026',
        BFA1: 'Brasileiro Feminino A1',
        PAULISTA_F: 'Paulistão Feminino',
        COPA_F: 'Copa do Brasil Feminina',
        SUPERCOPA_F: 'Supercopa Feminina',
    },

    /** Get venue for a match object */
    getVenue(match) {
        if (match.venue) return match.venue;
        const club = CLUBS.get(CONFIG.CLUB_ID);
        if (match.homeTeam && match.homeTeam.id === this.TEAM_ID) return club.stadium;
        const awayId = match.awayTeam && match.awayTeam.id === this.TEAM_ID
            ? (match.homeTeam && match.homeTeam.id)
            : (match.awayTeam && match.awayTeam.id);
        return this.STADIUMS[awayId] || 'A definir';
    },

    /** Best display name — prefer shortName if it's not a 3-letter code */
    teamName(team) {
        if (team && team.shortName && team.shortName.length > 3) return team.shortName;
        return (team && (team.name || team.shortName)) || 'A definir';
    },

    /** Competition display name */
    formatComp(comp) {
        const code = comp && comp.code;
        return this.COMP_NAMES[code] || (comp && comp.name) || 'Campeonato';
    },

    /** Fallback crest URLs for teams without football-data.org crests */
    TEAM_CRESTS: {
        1769: 'https://crests.football-data.org/1769.png',
        1779: 'https://crests.football-data.org/1779.png',
        20002: '/static/crests/1769.png', // Palmeiras Feminino
        20001: '/static/crests/1779.png', // Corinthians Feminino
    },

    /** CBF Feminino IDs that represent clubs already available in the Masculino feed. */
    SHARED_CLUB_CRESTS: Object.freeze({
        20001: 1779, // Corinthians
        20002: 1769, // Palmeiras
        20005: 1776, // São Paulo
        20007: 4286, // Red Bull Bragantino
        20008: 6685, // Santos
        20011: 6684, // Internacional
        20013: 1767, // Grêmio
        20014: 1765, // Fluminense
        20016: 1783, // Flamengo
        20018: 1782, // Vitória
        59849: 1771, // Cruzeiro
        60175: 1770, // Botafogo
        61377: 1777, // Bahia
        62194: 1766, // Atlético Mineiro
    }),

    /** Women-only clubs with transparent local crests and no Masculino alias. */
    LOCAL_CREST_IDS: new Set([
        20027, // Juventude
        20038, // Ferroviária
        20064, // Mixto
        59897, // América
    ]),

    /** Known broken crest URLs to replace */
    BROKEN_CRESTS: new Set([
        'https://ssl.gstatic.com/lingonautique/paulista_2024/palmeiras.png',
    ]),

    /** Get crest URL with fallback */
    getCrest(team) {
        const crest = team && team.crest;
        const sharedCrestId = team && this.SHARED_CLUB_CRESTS[Number(team.id)];
        if (sharedCrestId) return `/static/crests/${sharedCrestId}.png`;
        if (team && this.LOCAL_CREST_IDS.has(Number(team.id))) {
            return `/static/crests/${Number(team.id)}.png`;
        }
        const sourceCrest = String((team && team.sourceCrest) || crest || '');
        const cbfMatch = sourceCrest.match(/^https:\/\/conteudo\.cbf\.com\.br\/clubes\/(\d+)\/escudo\.jpg(?:\?.*)?$/i);
        if (cbfMatch) return this.apiUrl(`crest?team_id=${encodeURIComponent(cbfMatch[1])}`);
        if (crest && !this.BROKEN_CRESTS.has(crest)) return crest;
        if (team && team.id != null && this.TEAM_CRESTS[team.id]) return this.TEAM_CRESTS[team.id];
        return 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="18" fill="#ccc"/><text x="20" y="25" text-anchor="middle" fill="#666" font-size="14">?</text></svg>');
    },
};

// Initialize team IDs from the selected club.
(function initClubConfig() {
    const ids = CLUBS.teamIds(CONFIG.CLUB_ID);
    CONFIG.MEN_TEAM_ID = ids.men;
    CONFIG.WOMEN_TEAM_ID = ids.women;
    CONFIG.TEAM_ID = ids.men;
})();
