/**
 * Futebol Agenda — Club Registry
 * Single source of truth for all club definitions.
 * Used by config.js, features.js, and the theming system.
 *
 * To add a new club: add one entry to CLUBS below. No other code changes needed.
 */
const CLUB_REGISTRY = {
    palmeiras: {
        id: 'palmeiras',
        name: 'Palmeiras',
        fullName: 'Sociedade Esportiva Palmeiras',
        footballDataId: 1769,
        womenFootballDataId: 20002,
        cbfWomenId: 20002,
        shortCode: 'PAL',
        stadium: 'Allianz Parque',
        theme: {
            brand: '#075c3b',
            brandStrong: '#043522',
            brandBright: '#0a7a4a',
            brandSoft: '#e7f1e9',
            gold: '#c99a3d',
            ink: '#10231a',
            text: '#17251d',
            bg: '#f3f5ef',
            bgCard: '#ffffff',
            bgSoft: '#e9efe8',
            line: '#d9e2d8',
            lineStrong: '#bdcabb',
        },
        darkTheme: {
            brand: '#48b57a',
            brandStrong: '#06140f',
            brandBright: '#65d996',
            brandSoft: '#10251a',
            gold: '#d8b560',
            ink: '#eff6f1',
            text: '#eaf2ed',
            bg: '#07110c',
            bgCard: '#0f1e16',
            bgSoft: '#13261b',
            line: 'rgba(222, 236, 226, 0.13)',
            lineStrong: 'rgba(222, 236, 226, 0.24)',
        },
    },
    corinthians: {
        id: 'corinthians',
        name: 'Corinthians',
        fullName: 'Sport Club Corinthians Paulista',
        footballDataId: 1779,
        womenFootballDataId: 20001,
        cbfWomenId: 20001,
        shortCode: 'COR',
        stadium: 'Neo Química Arena',
        theme: {
            brand: '#1a1a1a',
            brandStrong: '#000000',
            brandBright: '#404040',
            brandSoft: '#e8e8e8',
            gold: '#c99a3d',
            ink: '#0a0a0a',
            text: '#1a1a1a',
            bg: '#f5f5f5',
            bgCard: '#ffffff',
            bgSoft: '#eaeaea',
            line: '#d5d5d5',
            lineStrong: '#b8b8b8',
        },
        darkTheme: {
            brand: '#e0e0e0',
            brandStrong: '#0a0a0a',
            brandBright: '#f0f0f0',
            brandSoft: '#1a1a1a',
            gold: '#d8b560',
            ink: '#f5f5f5',
            text: '#eaeaea',
            bg: '#0a0a0a',
            bgCard: '#141414',
            bgSoft: '#1e1e1e',
            line: 'rgba(255, 255, 255, 0.10)',
            lineStrong: 'rgba(255, 255, 255, 0.20)',
        },
    },
};

const DEFAULT_CLUB_ID = 'palmeiras';
const CLUB_STORAGE_KEY = 'fa-selected-club';
const CLUB_LEGACY_KEY = 'pa-team-scope'; // old Palmeiras-only key

const CLUBS = {
    /**
     * Get a club definition by ID.
     * Falls back to Palmeiras if not found (backward compatibility).
     */
    get(clubId) {
        return CLUB_REGISTRY[clubId] || CLUB_REGISTRY[DEFAULT_CLUB_ID];
    },

    /** Get all registered club IDs. */
    ids() {
        return Object.keys(CLUB_REGISTRY);
    },

    /** Get all club definitions as an array. */
    all() {
        return Object.values(CLUB_REGISTRY);
    },

    /** Default club ID (Palmeiras for backward compat). */
    defaultId: DEFAULT_CLUB_ID,

    /** Get the currently selected club from localStorage or URL param. */
    getSelected() {
        // URL param takes priority (?club=corinthians)
        const params = new URLSearchParams(window.location.search);
        const urlClub = params.get('club');
        if (urlClub && CLUB_REGISTRY[urlClub]) return urlClub;

        // Then localStorage
        try {
            const stored = localStorage.getItem(CLUB_STORAGE_KEY);
            if (stored && CLUB_REGISTRY[stored]) return stored;
        } catch (_) { /* localStorage unavailable */ }

        // Legacy: if old app had Palmeiras data, keep Palmeiras
        return DEFAULT_CLUB_ID;
    },

    /** Persist club selection to localStorage. */
    setSelected(clubId) {
        try { localStorage.setItem(CLUB_STORAGE_KEY, clubId); } catch (_) { /* */ }
    },

    /** Get team IDs for a club (men + women). */
    teamIds(clubId) {
        const club = this.get(clubId);
        return {
            men: club.footballDataId,
            women: club.womenFootballDataId,
        };
    },

    /**
     * Inject CSS custom properties for a club's theme.
     * Call this as early as possible (before first paint) to avoid FOUC.
     */
    applyTheme(clubId) {
        const club = this.get(clubId);
        const root = document.documentElement;
        const theme = club.theme;
        Object.entries(theme).forEach(([key, value]) => {
            const cssKey = '--' + key.replace(/([A-Z])/g, '-$1').toLowerCase();
            root.style.setProperty(cssKey, value);
        });
        // Update shadow colors based on brand
        const brandStrong = theme.brandStrong;
        root.style.setProperty('--shadow', `0 18px 50px ${brandStrong}1a`);
        root.style.setProperty('--shadow-tight', `0 10px 28px ${brandStrong}16`);
        root.style.setProperty('--data-club', clubId);
    },

    /**
     * Apply dark mode theme for a club.
     */
    applyDarkTheme(clubId) {
        const club = this.get(clubId);
        const root = document.documentElement;
        const dark = club.darkTheme;
        Object.entries(dark).forEach(([key, value]) => {
            const cssKey = '--' + key.replace(/([A-Z])/g, '-$1').toLowerCase();
            root.style.setProperty(cssKey, value);
        });
        root.style.setProperty('--shadow', `0 18px 48px rgba(0, 0, 0, 0.32)`);
        root.style.setProperty('--shadow-tight', `0 10px 24px rgba(0, 0, 0, 0.26)`);
    },
};
