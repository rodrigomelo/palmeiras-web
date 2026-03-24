/**
 * Shared configuration for Palmeiras Dashboard.
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

    /** Get venue for a match object */
    getVenue(match) {
        if (match.venue) return match.venue;
        if (match.homeTeam?.id === this.TEAM_ID) return 'Allianz Parque';
        const awayId = match.awayTeam?.id === this.TEAM_ID ? match.homeTeam?.id : match.awayTeam?.id;
        return this.STADIUMS[awayId] || 'A definir';
    },
};
