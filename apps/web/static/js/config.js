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
        1765: 'Arena MRV',
        1766: 'Mineirão',
        1770: 'Nilton Santos',
        1776: 'Morumbi',
        1777: 'Fonte Nova',
        1779: 'Maracanã',
        1780: 'Castelão',
        1783: 'Beira-Rio',
        1784: 'Arena da Baixada',
        1785: 'Arena Condá',
        1786: 'Allianz Parque',
        1787: 'Arena Pantanal',
        1788: 'Barradão',
        1789: 'Perpetuão',
        1790: 'Arena Amazônia',
        1791: 'Castelão (CE)',
        1792: 'Arena Pernambuco',
        1793: 'Ilha do Retiro',
        1794: 'Almeidão',
        1795: 'Mangueirão',
        1796: 'Lumberman Arena',
        1797: 'Arena das Dunas',
        1798: 'Estádio Kleber Andrade',
        1799: 'Brinco de Ouro',
        1800: 'Santa Cruz',
        1801: 'Arruda',
        1802: 'Centenário',
        1803: 'Moisés Lucarelli',
        1804: 'Vila Belmiro',
        1805: 'São Januário',
        1806: 'Nabi Abi Chedid',
        1807: 'Aníbal Torres',
        1808: 'Monumental (Lima)',
        1809: 'El Teniente',
        1810: 'La Portada',
        1811: 'Defensores del Chaco',
        1812: 'Monumental (Buenos Aires)',
        1813: 'Mario Alberto Kempes',
        1814: 'Libertadores de América',
        1815: 'Más Monumental',
    },

    /** Fallback crest URLs for teams without football-data.org crests */
    TEAM_CRESTS: {
        1769: 'https://crests.football-data.org/1769.png', // Palmeiras
    },

    /** Known broken crest URLs to replace */
    BROKEN_CRESTS: new Set([
        'https://ssl.gstatic.com/lingonautique/paulista_2024/palmeiras.png',
    ]),

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
        if (match.homeTeam && match.homeTeam.id === this.TEAM_ID) return 'Allianz Parque';
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

    /** Get crest URL with fallback */
    getCrest(team) {
        const crest = team && team.crest;
        if (crest && !this.BROKEN_CRESTS.has(crest)) return crest;
        if (team && team.id != null && this.TEAM_CRESTS[team.id]) return this.TEAM_CRESTS[team.id];
        return 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="18" fill="#ccc"/><text x="20" y="25" text-anchor="middle" fill="#666" font-size="14">?</text></svg>');
    },
};
