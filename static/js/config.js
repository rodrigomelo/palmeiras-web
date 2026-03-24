/**
 * Shared configuration for Palmeiras Agenda.
 * Single source of truth for constants used across JS.
 */
const CONFIG = {
    TEAM_ID: 1769,
    BR_TZ: 'America/Sao_Paulo',

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
        COPA_DO_BRASIL: 'Copa do Brasil',
        CLI: 'Libertadores',
        LIBERTADORES: 'Libertadores',
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
        return team?.name || team?.shortName || '?';
    },

    /** Competition display name */
    formatComp(comp) {
        return this.COMP_NAMES[comp?.code] || comp?.name || 'Campeonato';
    },

    /** Get crest URL with fallback */
    getCrest(team) {
        const crest = team?.crest;
        if (crest && !this.BROKEN_CRESTS.has(crest)) return crest;
        if (team?.id && this.TEAM_CRESTS[team.id]) return this.TEAM_CRESTS[team.id];
        return 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><circle cx="20" cy="20" r="18" fill="#ccc"/><text x="20" y="25" text-anchor="middle" fill="#666" font-size="14">?</text></svg>');
    },
};
