/**
 * Shared configuration for Palmeiras Agenda.
 * Single source of truth for constants used across JS.
 */
const CONFIG = {
    TEAM_ID: 1769,
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

    /** Known stadium names by opponent team ID */
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

    /** Fallback crest URLs for teams without football-data.org crests */
    TEAM_CRESTS: {
        1769: 'https://crests.football-data.org/1769.png', // Palmeiras
    },

    /** Known broken crest URLs to replace */
    BROKEN_CRESTS: new Set([
        'https://ssl.gstatic.com/lingonautique/paulista_2024/palmeiras.png',
    ]),

    PLACEHOLDER_CREST: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="18" fill="#ccc"/><text x="20" y="25" text-anchor="middle" fill="#666" font-size="14">?</text></svg>'),

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
    },

    /** Get venue for a match object */
    getVenue(match) {
        if (match.venue) return match.venue;
        if (match.homeTeam?.id === this.TEAM_ID) return 'Allianz Parque';
        const awayId = match.awayTeam?.id === this.TEAM_ID ? match.homeTeam?.id : match.awayTeam?.id;
        return this.STADIUMS[awayId] || 'A definir';
    },

    /** Best display name — prefer shortName if it's not a 3-letter code */
    teamName(team) {
        if (team?.shortName && team.shortName.length > 3) return team.shortName;
        return team?.name || team?.shortName || 'A definir';
    },

    /** Competition display name */
    formatComp(comp) {
        return this.COMP_NAMES[comp?.code] || comp?.name || 'Campeonato';
    },

    /** Get crest URL with fallback */
    getCrest(team) {
        const crest = this.safeUrl(team?.crest, '');
        if (crest && !this.BROKEN_CRESTS.has(crest)) return crest;
        if (team?.id != null && this.TEAM_CRESTS[team.id]) return this.TEAM_CRESTS[team.id];
        return this.PLACEHOLDER_CREST;
    },
};
