#!/usr/bin/env python3
"""Executable browser smoke test for the local Palmeiras Agenda web app."""

import os
import sys
from pathlib import Path


def run_smoke_test() -> int:
    from playwright.sync_api import sync_playwright

    base_url = os.getenv("SMOKE_BASE_URL", "http://localhost:5001")
    screenshot_dir = os.getenv("SMOKE_SCREENSHOT_DIR")
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            service_workers="block",
        )
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        try:
            response = page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
            assert response is not None and response.ok, "home page did not load"
            assert page.title(), "page title is empty"

            tabs = page.locator('.tab-btn[role="tab"]')
            tabs.first.wait_for(state="visible", timeout=10_000)
            page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(state="visible", timeout=10_000)
            utility_actions = page.locator(".quick-preference-actions .utility-icon-action")
            assert utility_actions.count() == 2
            assert page.locator(".header .experience-toolbar").count() == 0, (
                "retired nested preferences toolbar is still present"
            )
            assert page.locator(".header-content > .team-scope-control").count() == 1, (
                "team preferences are not integrated into the open header"
            )
            assert page.locator(".quick-preference-actions").inner_text().strip() == "", (
                "quick preferences are not icon-only"
            )
            assert page.locator('#spoilerFreeToggle[aria-label="Ocultar placares"]').count() == 1
            assert page.locator("#quickNotifyButton").count() == 1
            assert page.locator("#quickNotifyButton").get_attribute("aria-pressed") in {
                "true",
                "false",
            }
            assert page.locator(".icon-scores-visible").is_visible()
            assert not page.locator(".icon-scores-hidden").is_visible()
            page.locator(".spoiler-toggle").click()
            assert page.locator("#spoilerFreeToggle").is_checked()
            assert page.locator("#spoilerFreeToggle").get_attribute("aria-label") == "Mostrar placares"
            assert "spoiler-free" in (page.locator("body").get_attribute("class") or "").split()
            assert page.locator(".icon-scores-hidden").is_visible()
            page.locator(".spoiler-toggle").click()
            assert not page.locator("#spoilerFreeToggle").is_checked()
            assert page.locator("#spoilerFreeToggle").get_attribute("aria-label") == "Ocultar placares"
            header_control_layout = page.evaluate(
                """() => {
                    const header = document.querySelector('.header-content').getBoundingClientRect();
                    const brand = document.querySelector('.header-brand').getBoundingClientRect();
                    const scope = document.querySelector('.team-scope-control').getBoundingClientRect();
                    const actions = document.querySelector('.quick-preference-actions').getBoundingClientRect();
                    const globalActions = document.querySelector('.header-actions').getBoundingClientRect();
                    const selected = document.querySelector('button[data-team-scope="men"]');
                    const persistentControls = Array.from(document.querySelectorAll(
                        '.header .utility-icon-action, .header .theme-toggle, .header .refresh-btn'
                    ));
                    return {
                        scopeBelowBrand: scope.top >= brand.bottom,
                        utilitiesSameRow:
                            Math.abs((actions.top + actions.height / 2) -
                                (globalActions.top + globalActions.height / 2)) < 2,
                        utilitiesOrdered: actions.right <= globalActions.left,
                        contained: scope.left >= header.left && globalActions.right <= header.right,
                        scopeBackground: getComputedStyle(
                            document.querySelector('.team-scope-control')
                        ).backgroundColor,
                        scopeBorder: getComputedStyle(
                            document.querySelector('.team-scope-control')
                        ).borderTopWidth,
                        selectedBackground: getComputedStyle(selected).backgroundColor,
                        selectedUnderline: getComputedStyle(selected, '::after').transform,
                        controlBackgrounds: persistentControls.map(
                            control => getComputedStyle(control).backgroundColor
                        ),
                    };
                }"""
            )
            assert header_control_layout["scopeBelowBrand"], header_control_layout
            assert header_control_layout["utilitiesSameRow"], header_control_layout
            assert header_control_layout["utilitiesOrdered"], header_control_layout
            assert header_control_layout["contained"], header_control_layout
            assert header_control_layout["scopeBackground"] == "rgba(0, 0, 0, 0)"
            assert header_control_layout["scopeBorder"] == "0px"
            assert header_control_layout["selectedBackground"] == "rgba(0, 0, 0, 0)"
            assert header_control_layout["selectedUnderline"] != "matrix(0, 0, 0, 1, 0, 0)"
            assert all(
                background == "rgba(0, 0, 0, 0)"
                for background in header_control_layout["controlBackgrounds"]
            ), header_control_layout
            assert page.locator("#matchday-center").count() == 0, "retired match center is still present"
            assert page.locator("#form-widget").count() == 0, "retired sequence widget is still present"
            assert page.locator("#hero-countdown").is_visible(), "game countdown is hidden"
            page.wait_for_function(
                "document.querySelectorAll('#hero-context .hero-icon-action').length === 2",
                timeout=10_000,
            )
            assert page.locator("#hero-context .hero-icon-action").count() == 2
            assert "retrospecto recente" in page.locator("#hero-context").inner_text().lower()
            assert page.locator('#heroShareAction[aria-label="Compartilhar jogo"]').count() == 1
            assert page.locator('#heroCalendarAction[aria-label="Adicionar jogo ao calendário"]').count() == 1
            assert page.locator("#heroCalendarAction").get_attribute("href").startswith(
                "https://calendar.google.com/calendar/render?"
            )
            assert page.locator("#hero-context .hero-icon-action").evaluate_all(
                "actions => actions.every(action => action.textContent.trim() === '')"
            ), "banner actions are not icon-only"
            hierarchy = page.evaluate(
                """() => {
                    const home = document.querySelector('#home');
                    const tabs = document.querySelector('.tabs');
                    const hero = document.querySelector('#hero-hub');
                    const calendar = document.querySelector('#calendar-hub');
                    const heroBox = hero.getBoundingClientRect();
                    const calendarBox = calendar.getBoundingClientRect();
                    return {
                        heroOwnedByAgenda: home.contains(hero),
                        calendarOwnedByAgenda: home.contains(calendar),
                        menuBeforeAgenda: Boolean(tabs.compareDocumentPosition(home) & Node.DOCUMENT_POSITION_FOLLOWING),
                        menuAboveHero: tabs.getBoundingClientRect().bottom <= heroBox.top,
                        calendarBelowHero: calendarBox.top >= heroBox.bottom,
                    };
                }"""
            )
            assert all(hierarchy.values()), f"desktop Agenda hierarchy is inconsistent: {hierarchy}"
            if screenshot_dir:
                target = Path(screenshot_dir)
                target.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(target / "implemented-desktop.png"), full_page=False)
            desktop_tabs = page.locator(".tabs")
            attached_tabs = desktop_tabs.evaluate(
                """node => {
                    const box = node.getBoundingClientRect();
                    const style = getComputedStyle(node);
                    return {
                        position: style.position,
                        floating: node.classList.contains('is-floating'),
                        height: box.height,
                        top: box.top,
                    };
                }"""
            )
            assert attached_tabs["position"] == "sticky", attached_tabs
            assert not attached_tabs["floating"], attached_tabs
            assert attached_tabs["top"] > 12, attached_tabs
            page.evaluate(
                """() => window.scrollTo(
                    0,
                    document.querySelector('.header').getBoundingClientRect().height + 120
                )"""
            )
            page.locator(".tabs.is-floating").wait_for(state="visible", timeout=5_000)
            floating_tabs = desktop_tabs.evaluate(
                """node => {
                    const box = node.getBoundingClientRect();
                    const style = getComputedStyle(node);
                    return {
                        position: style.position,
                        floating: node.classList.contains('is-floating'),
                        height: box.height,
                        top: box.top,
                        right: box.right,
                        viewportWidth: innerWidth,
                        shadow: style.boxShadow,
                    };
                }"""
            )
            assert floating_tabs["position"] == "sticky", floating_tabs
            assert floating_tabs["floating"], floating_tabs
            assert 10 <= floating_tabs["top"] <= 14, floating_tabs
            assert floating_tabs["height"] < attached_tabs["height"], (
                attached_tabs,
                floating_tabs,
            )
            assert floating_tabs["right"] <= floating_tabs["viewportWidth"], floating_tabs
            assert floating_tabs["shadow"] != "none", floating_tabs
            if screenshot_dir:
                page.wait_for_timeout(200)
                page.screenshot(
                    path=str(target / "implemented-desktop-floating.png"),
                    full_page=False,
                )
            page.evaluate("window.scrollTo(0, 0)")
            page.locator(".tabs.is-floating").wait_for(state="detached", timeout=5_000)
            assert tabs.count() == 7, f"expected 7 desktop tabs, found {tabs.count()}"
            hero = page.locator("#hero-hub")
            calendar = page.locator("#calendar-hub")
            for index in range(tabs.count()):
                tab = tabs.nth(index)
                panel_id = tab.get_attribute("aria-controls")
                assert panel_id, "tab is missing aria-controls"
                tab.click()
                panel = page.locator(f"#{panel_id}")
                assert tab.get_attribute("aria-selected") == "true"
                assert panel.get_attribute("hidden") is None
                assert "active" in (panel.get_attribute("class") or "").split()
                assert hero.is_visible() == (panel_id == "home"), (
                    f"next-game banner visibility is wrong for {panel_id}"
                )
                assert calendar.is_visible() == (panel_id == "home"), (
                    f"calendar visibility is wrong for {panel_id}"
                )

            page.locator("#tab-estatisticas").click()
            stats_summary = page.locator("#team-stats .stats-summary")
            stats_summary.wait_for(state="visible", timeout=10_000)
            stats_inset = stats_summary.evaluate(
                """surface => {
                    const content = surface.querySelector('.stats-grid');
                    const outer = surface.getBoundingClientRect();
                    const inner = content.getBoundingClientRect();
                    return {
                        paddingLeft: parseFloat(getComputedStyle(surface).paddingLeft),
                        leftInset: inner.left - outer.left,
                        rightInset: outer.right - inner.right,
                    };
                }"""
            )
            assert stats_inset["paddingLeft"] >= 16, stats_inset
            assert stats_inset["leftInset"] >= 16, stats_inset
            assert stats_inset["rightInset"] >= 16, stats_inset

            page.locator("#tab-classificacao").click()
            standings_section = page.locator("#standings > .standings-section").first
            standings_section.wait_for(state="visible", timeout=10_000)
            standings_inset = standings_section.evaluate(
                """surface => {
                    const content = surface.querySelector('.standings-campaign-stats');
                    const outer = surface.getBoundingClientRect();
                    const inner = content.getBoundingClientRect();
                    return {
                        paddingLeft: parseFloat(getComputedStyle(surface).paddingLeft),
                        leftInset: inner.left - outer.left,
                        rightInset: outer.right - inner.right,
                    };
                }"""
            )
            assert standings_inset["paddingLeft"] >= 16, standings_inset
            assert standings_inset["leftInset"] >= 16, standings_inset
            assert standings_inset["rightInset"] >= 16, standings_inset

            page.get_by_role("button", name="Brasileirão", exact=True).click()
            classification_table = page.locator(".standings-data-table")
            classification_table.wait_for(state="visible", timeout=10_000)
            assert classification_table.evaluate("table => table.tagName") == "TABLE"
            assert classification_table.locator("thead th").all_inner_texts() == [
                "POS.",
                "CLUBE",
                "PTS",
                "J",
                "V",
                "E",
                "D",
                "GP",
                "GC",
                "SG",
            ]
            assert classification_table.locator("tbody tr").count() == 20
            palmeiras_classification = classification_table.locator(
                'tbody tr[aria-current="true"]'
            )
            assert palmeiras_classification.count() == 1
            assert "Palmeiras" in palmeiras_classification.inner_text()
            assert palmeiras_classification.locator("img").count() == 1
            page.wait_for_function(
                """() => {
                    const image = document.querySelector(
                        '.standings-data-table tbody tr[aria-current="true"] img'
                    );
                    return image && image.complete && image.naturalWidth > 0;
                }""",
                timeout=10_000,
            )
            assert classification_table.locator("tbody tr").nth(0).evaluate(
                "row => row.classList.contains('zone-libertadores')"
            )
            assert classification_table.locator("tbody tr").nth(6).evaluate(
                "row => row.classList.contains('zone-sudamericana')"
            )
            assert classification_table.locator("tbody tr").nth(16).evaluate(
                "row => row.classList.contains('zone-relegation')"
            )
            standings_snapshot_layout = page.locator(
                ".standings-team-snapshot"
            ).evaluate(
                """snapshot => {
                    const identity = snapshot.querySelector('.standings-team-identity');
                    const stats = Array.from(
                        snapshot.querySelectorAll('.standings-key-stats > div')
                    );
                    const identityStyle = getComputedStyle(identity);
                    return {
                        snapshotBorder: getComputedStyle(snapshot).borderTopWidth,
                        identityBorder: identityStyle.borderTopWidth,
                        identityBackground: identityStyle.backgroundColor,
                        statCount: stats.length,
                        statBorders: stats.map(
                            stat => getComputedStyle(stat).borderTopWidth
                        ),
                        statBackgrounds: stats.map(
                            stat => getComputedStyle(stat).backgroundColor
                        ),
                        statRadii: stats.map(
                            stat => getComputedStyle(stat).borderTopLeftRadius
                        ),
                        statHeights: stats.map(
                            stat => stat.getBoundingClientRect().height
                        ),
                    };
                }"""
            )
            assert standings_snapshot_layout["snapshotBorder"] == "0px", (
                standings_snapshot_layout
            )
            assert standings_snapshot_layout["identityBorder"] == "1px", (
                standings_snapshot_layout
            )
            assert standings_snapshot_layout["identityBackground"] != (
                "rgba(0, 0, 0, 0)"
            ), standings_snapshot_layout
            assert standings_snapshot_layout["statCount"] == 4
            assert all(
                border == "1px"
                for border in standings_snapshot_layout["statBorders"]
            ), standings_snapshot_layout
            assert all(
                background == standings_snapshot_layout["identityBackground"]
                for background in standings_snapshot_layout["statBackgrounds"]
            ), standings_snapshot_layout
            assert all(
                radius != "0px"
                for radius in standings_snapshot_layout["statRadii"]
            ), standings_snapshot_layout
            assert (
                max(standings_snapshot_layout["statHeights"])
                - min(standings_snapshot_layout["statHeights"])
                < 1
            ), standings_snapshot_layout
            desktop_table_overflow = page.locator(".standings-table-shell").evaluate(
                """shell => ({
                    clientWidth: shell.clientWidth,
                    scrollWidth: shell.scrollWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    viewportWidth: document.documentElement.clientWidth,
                })"""
            )
            assert desktop_table_overflow["scrollWidth"] <= desktop_table_overflow["clientWidth"]
            assert (
                desktop_table_overflow["documentWidth"]
                <= desktop_table_overflow["viewportWidth"]
            ), desktop_table_overflow
            if screenshot_dir:
                page.locator(
                    '.standings-section[aria-label="Classificação oficial"]'
                ).scroll_into_view_if_needed()
                page.wait_for_timeout(100)
                page.screenshot(
                    path=str(target / "implemented-standings-desktop.png"),
                    full_page=False,
                )

            page.get_by_role("button", name="Copa do Brasil", exact=True).click()
            standings_focus = page.locator(".standings-focus-grid")
            standings_focus.wait_for(state="visible", timeout=10_000)
            empty_competition_match = standings_focus.locator(
                ".competition-match.empty-line"
            )
            assert empty_competition_match.count() == 1
            assert (
                empty_competition_match.locator("span").text_content().strip()
                == "Próximo jogo"
            )
            assert (
                empty_competition_match.locator("strong").inner_text()
                == "Sem jogo carregado"
            )
            assert (
                empty_competition_match.locator("small").inner_text()
                == "Aguardando atualização da agenda"
            )
            assert (
                empty_competition_match.get_attribute("aria-label")
                == "Próximo jogo: sem jogo carregado"
            )
            loaded_competition_match = standings_focus.locator(
                ".competition-match:not(.empty-line)"
            )
            assert loaded_competition_match.count() == 1
            assert "Último jogo" in (
                loaded_competition_match.locator("summary span").text_content() or ""
            )

            page.goto(base_url, wait_until="load")
            page.wait_for_function("typeof window.nativeSelectTab === 'function'")
            page.evaluate(
                """() => {
                    document.body.classList.add('native-shell');
                    document.body.dataset.nativeTab = 'home';
                    window.scrollTo(0, 500);
                    window.nativeSelectTab('classificacao');
                }"""
            )
            page.locator("#hero-hub").wait_for(state="hidden", timeout=5_000)
            page.locator("#calendar-hub").wait_for(state="hidden", timeout=5_000)
            assert not page.locator("#hero-hub").is_visible()
            assert not page.locator("#calendar-hub").is_visible()
            assert page.evaluate("window.scrollY") == 0, "native section did not reset to the top"
            page.evaluate("window.nativeSelectTab('home')")
            page.wait_for_timeout(50)
            assert page.locator("#hero-hub").is_visible()
            assert page.locator("#calendar-hub").is_visible()

            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(base_url, wait_until="domcontentloaded")
            page.evaluate(
                """() => {
                    document.body.classList.add('native-shell');
                    document.body.dataset.nativeTab = 'home';
                    window.nativeSelectTab('home');
                }"""
            )
            page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(state="visible", timeout=10_000)
            assert page.locator("#hero-hub").is_visible(), "banner is hidden in the native phone shell"
            assert page.locator("#hero-countdown").is_visible(), "countdown is hidden in the native phone shell"
            assert page.locator("#matchday-center").count() == 0
            assert page.locator("#hero-context .hero-icon-action").count() == 2
            native_order = page.evaluate(
                """() => {
                    const hero = document.querySelector('#hero-hub').getBoundingClientRect();
                    const calendar = document.querySelector('#calendar-hub').getBoundingClientRect();
                    return calendar.top >= hero.bottom;
                }"""
            )
            assert native_order, "native calendar is not directly below the hero"
            if screenshot_dir:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(100)
                page.screenshot(
                    path=str(Path(screenshot_dir) / "implemented-native.png"),
                    full_page=False,
                )
                native_calendar_y = page.locator("#calendar-hub").bounding_box()["y"]
                page.evaluate("y => window.scrollTo(0, Math.max(0, y - 120))", native_calendar_y)
                page.wait_for_timeout(100)
                page.screenshot(
                    path=str(Path(screenshot_dir) / "implemented-native-agenda-order.png"),
                    full_page=False,
                )

            page.set_viewport_size({"width": 690, "height": 844})
            page.goto(base_url, wait_until="domcontentloaded")
            narrow_desktop_tabs = page.locator(".tabs")
            narrow_desktop_box = narrow_desktop_tabs.bounding_box()
            assert narrow_desktop_box is not None
            assert page.locator('.tab-btn[role="tab"]:visible').count() == 7
            assert narrow_desktop_box["y"] < 844 / 2, (
                "narrow pointer-based desktop incorrectly uses bottom navigation"
            )
            assert narrow_desktop_tabs.evaluate(
                "node => getComputedStyle(node).position"
            ) == "sticky"

            desktop_page = page
            page = browser.new_page(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                service_workers="block",
            )
            page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: page_errors.append(str(error)))

            for width, height in ((320, 700), (360, 780), (390, 844), (430, 932)):
                page.set_viewport_size({"width": width, "height": height})
                page.goto(base_url, wait_until="domcontentloaded")
                page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(state="visible", timeout=10_000)
                assert page.locator(".hero-hub").is_visible(), (
                    f"next-game banner is hidden on phone at {width}px"
                )
                assert page.locator("#hero-countdown").is_visible(), (
                    f"game countdown is hidden on phone at {width}px"
                )
                assert page.locator("#hero-context .hero-icon-action").count() == 2
                phone_header_controls = page.evaluate(
                    """() => {
                        const header = document.querySelector('.header-content').getBoundingClientRect();
                        const scope = document.querySelector('.team-scope-control').getBoundingClientRect();
                        const actions = document.querySelector('.quick-preference-actions').getBoundingClientRect();
                        return {
                            sameRow: Math.abs((scope.top + scope.height / 2) - (actions.top + actions.height / 2)) < 2,
                            ordered: scope.right <= actions.left,
                            contained: actions.right <= header.right && scope.left >= header.left,
                            scopeBackground: getComputedStyle(
                                document.querySelector('.team-scope-control')
                            ).backgroundColor,
                            actionsBackgrounds: Array.from(
                                document.querySelectorAll('.quick-preference-actions .utility-icon-action')
                            ).map(action => getComputedStyle(action).backgroundColor),
                        };
                    }"""
                )
                assert phone_header_controls["sameRow"], phone_header_controls
                assert phone_header_controls["ordered"], phone_header_controls
                assert phone_header_controls["contained"], phone_header_controls
                assert phone_header_controls["scopeBackground"] == "rgba(0, 0, 0, 0)"
                assert all(
                    background == "rgba(0, 0, 0, 0)"
                    for background in phone_header_controls["actionsBackgrounds"]
                ), phone_header_controls
                phone_order = page.evaluate(
                    """() => {
                        const hero = document.querySelector('#hero-hub').getBoundingClientRect();
                        const calendar = document.querySelector('#calendar-hub').getBoundingClientRect();
                        return calendar.top >= hero.bottom;
                    }"""
                )
                assert phone_order, f"calendar is not below the hero at {width}px"
                if screenshot_dir and width == 390:
                    page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(state="visible", timeout=10_000)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(100)
                    page.screenshot(path=str(Path(screenshot_dir) / "implemented-mobile.png"), full_page=False)
                    calendar_y = page.locator("#calendar-hub").bounding_box()["y"]
                    page.evaluate("y => window.scrollTo(0, Math.max(0, y - 120))", calendar_y)
                    page.wait_for_timeout(100)
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "implemented-mobile-agenda-order.png"),
                        full_page=False,
                    )
                mobile_tabs_box = page.locator(".tabs").bounding_box()
                assert mobile_tabs_box is not None
                assert page.locator('.tab-btn[role="tab"]:visible').count() == 5, (
                    f"expected 5 primary mobile tabs at {width}px"
                )
                assert mobile_tabs_box["y"] > height / 2, (
                    f"mobile navigation is not anchored near the bottom at {width}px"
                )
                assert mobile_tabs_box["y"] + mobile_tabs_box["height"] <= height, (
                    f"mobile navigation is clipped at {width}px"
                )
                assert "is-floating" not in (
                    page.locator(".tabs").get_attribute("class") or ""
                ).split(), f"desktop floating state leaked into phone navigation at {width}px"
                page.evaluate("window.scrollTo(0, 500)")
                page.locator('#tab-classificacao').click()
                page.wait_for_timeout(100)
                assert not page.locator("#hero-hub").is_visible(), (
                    f"next-game banner remained visible outside Agenda at {width}px"
                )
                assert not page.locator("#calendar-hub").is_visible(), (
                    f"calendar remained visible outside Agenda at {width}px"
                )
                assert page.evaluate("window.scrollY") == 0, (
                    f"mobile Web section did not reset to the top at {width}px"
                )
                page.get_by_role("button", name="Brasileirão", exact=True).click()
                mobile_classification = page.locator(".standings-data-table")
                mobile_classification.wait_for(state="visible", timeout=10_000)
                mobile_snapshot_layout = page.locator(
                    ".standings-team-snapshot"
                ).evaluate(
                    """snapshot => {
                        const grid = snapshot.querySelector('.standings-key-stats');
                        const stats = Array.from(
                            grid.querySelectorAll(':scope > div')
                        );
                        return {
                            columns: getComputedStyle(grid)
                                .gridTemplateColumns.split(' ').length,
                            statCount: stats.length,
                            contained: stats.every(stat => {
                                const style = getComputedStyle(stat);
                                return (
                                    style.borderTopWidth === '1px' &&
                                    style.backgroundColor !== 'rgba(0, 0, 0, 0)'
                                );
                            }),
                            labelsFit: stats.every(
                                stat => stat.scrollWidth <= stat.clientWidth
                            ),
                        };
                    }"""
                )
                assert mobile_snapshot_layout["columns"] == 2, (
                    f"championship summary is not a two-column grid at {width}px"
                )
                assert mobile_snapshot_layout["statCount"] == 4
                assert mobile_snapshot_layout["contained"], mobile_snapshot_layout
                assert mobile_snapshot_layout["labelsFit"], mobile_snapshot_layout
                mobile_table_layout = page.locator(".standings-table-shell").evaluate(
                    """shell => {
                        const position = shell.querySelector(
                            'tbody .standing-position-cell'
                        );
                        const club = shell.querySelector(
                            'tbody .standing-club-cell'
                        );
                        const points = shell.querySelector(
                            'tbody .standing-points-cell'
                        );
                        const shellBox = shell.getBoundingClientRect();
                        return {
                            clientWidth: shell.clientWidth,
                            scrollWidth: shell.scrollWidth,
                            positionMode: getComputedStyle(position).position,
                            clubMode: getComputedStyle(club).position,
                            positionLeft: position.getBoundingClientRect().left,
                            clubLeft: club.getBoundingClientRect().left,
                            pointsVisible:
                                points.getBoundingClientRect().left >= shellBox.left &&
                                points.getBoundingClientRect().right <= shellBox.right,
                            documentWidth: document.documentElement.scrollWidth,
                            viewportWidth: document.documentElement.clientWidth,
                        };
                    }"""
                )
                assert (
                    mobile_table_layout["scrollWidth"]
                    > mobile_table_layout["clientWidth"]
                ), mobile_table_layout
                assert mobile_table_layout["positionMode"] == "sticky", mobile_table_layout
                assert mobile_table_layout["clubMode"] == "sticky", mobile_table_layout
                assert mobile_table_layout["pointsVisible"], mobile_table_layout
                assert (
                    mobile_table_layout["documentWidth"]
                    <= mobile_table_layout["viewportWidth"]
                ), mobile_table_layout
                sticky_after_scroll = page.locator(".standings-table-shell").evaluate(
                    """shell => {
                        const position = shell.querySelector(
                            'tbody .standing-position-cell'
                        );
                        const club = shell.querySelector(
                            'tbody .standing-club-cell'
                        );
                        shell.scrollLeft = shell.scrollWidth;
                        return {
                            scrollLeft: shell.scrollLeft,
                            positionLeft: position.getBoundingClientRect().left,
                            clubLeft: club.getBoundingClientRect().left,
                        };
                    }"""
                )
                assert sticky_after_scroll["scrollLeft"] > 0, sticky_after_scroll
                assert abs(
                    sticky_after_scroll["positionLeft"]
                    - mobile_table_layout["positionLeft"]
                ) < 1, (mobile_table_layout, sticky_after_scroll)
                assert abs(
                    sticky_after_scroll["clubLeft"] - mobile_table_layout["clubLeft"]
                ) < 1, (mobile_table_layout, sticky_after_scroll)
                page.locator(".standings-table-shell").evaluate(
                    "shell => { shell.scrollLeft = 0; }"
                )
                if screenshot_dir and width == 390:
                    page.locator(
                        '.standings-section[aria-label="Classificação oficial"]'
                    ).scroll_into_view_if_needed()
                    page.wait_for_timeout(100)
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "implemented-standings-mobile.png"),
                        full_page=False,
                    )
                page.locator('#tab-home').click()
                page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(state="visible", timeout=5_000)
                page.locator("#calendar-hub").wait_for(state="visible", timeout=5_000)
                assert page.locator("#hero-hub").is_visible(), (
                    f"next-game banner did not return to Agenda at {width}px"
                )
                assert page.locator("#calendar-hub").is_visible(), (
                    f"calendar did not return to Agenda at {width}px"
                )
                page.locator("#tab-estatisticas").click()
                stats_grid = page.locator("#team-stats .stats-summary .stats-grid")
                stats_grid.wait_for(state="visible", timeout=10_000)
                stats_layout = stats_grid.evaluate(
                    """grid => {
                        const surface = grid.parentElement;
                        const outer = surface.getBoundingClientRect();
                        const inner = grid.getBoundingClientRect();
                        return {
                            columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
                            boxCount: grid.children.length,
                            boxHeights: Array.from(grid.children).map(box => box.getBoundingClientRect().height),
                            labelsFit: Array.from(grid.querySelectorAll('.stat-label')).every(
                                label => label.scrollWidth <= label.clientWidth
                            ),
                            surfacePadding: parseFloat(getComputedStyle(surface).paddingLeft),
                            leftInset: inner.left - outer.left,
                            rightInset: outer.right - inner.right,
                        };
                    }"""
                )
                assert stats_layout["columns"] == 2, (
                    f"statistics summary is not a two-column phone grid at {width}px"
                )
                assert stats_layout["boxCount"] == 6
                assert len(set(stats_layout["boxHeights"])) == 1, (
                    f"statistics summary boxes have uneven heights at {width}px"
                )
                assert stats_layout["labelsFit"], (
                    f"statistics summary labels overflow at {width}px"
                )
                expected_stats_inset = 14 if width <= 360 else 16
                assert stats_layout["surfacePadding"] >= expected_stats_inset, (
                    f"statistics summary has no mobile surface padding at {width}px"
                )
                assert stats_layout["leftInset"] >= expected_stats_inset, stats_layout
                assert stats_layout["rightInset"] >= expected_stats_inset, stats_layout
                viewport_fits = page.evaluate(
                    """() => ({
                        documentWidth: document.documentElement.scrollWidth,
                        viewportWidth: document.documentElement.clientWidth,
                        bodyWidth: document.body.scrollWidth,
                    })"""
                )
                assert viewport_fits["documentWidth"] <= viewport_fits["viewportWidth"], (
                    f"horizontal document overflow at {width}px: {viewport_fits}"
                )
                assert viewport_fits["bodyWidth"] <= viewport_fits["viewportWidth"], (
                    f"horizontal body overflow at {width}px: {viewport_fits}"
                )

            page.close()
            page = desktop_page
            page.set_viewport_size({"width": 1280, "height": 900})
            page.goto(base_url, wait_until="domcontentloaded")
            page.evaluate("localStorage.setItem('pa-team-scope', 'women')")
            page.reload(wait_until="domcontentloaded")
            page.locator("#hero-context .hero-record:not(.is-loading)").wait_for(
                state="visible", timeout=10_000
            )
            assert "retrospecto recente" in page.locator("#hero-context").inner_text().lower()
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('.hero-team img'))
                    .every(image => image.complete && image.naturalWidth > 0)""",
                timeout=10_000,
            )
            assert page.locator('button[data-team-scope="women"]').get_attribute(
                "aria-pressed"
            ) == "true"
            shared_club_crests = {
                "20001": 1779,
                "20002": 1769,
                "20005": 1776,
                "20007": 4286,
                "20008": 6685,
                "20011": 6684,
                "20013": 1767,
                "20014": 1765,
                "20016": 1783,
                "20018": 1782,
                "59849": 1771,
                "60175": 1770,
                "61377": 1777,
                "62194": 1766,
            }
            shared_resolutions = page.evaluate(
                """aliases => Object.entries(aliases).map(([womenId, menId]) => ({
                    womenId,
                    expected: `/static/crests/${menId}.png`,
                    actual: CONFIG.getCrest({
                        id: Number(womenId),
                        crest: `https://conteudo.cbf.com.br/clubes/${womenId}/escudo.jpg`,
                    }),
                }))""",
                shared_club_crests,
            )
            assert all(item["actual"] == item["expected"] for item in shared_resolutions), (
                shared_resolutions
            )
            fallback_resolution = page.evaluate(
                """() => CONFIG.getCrest({
                    id: 20064,
                    crest: 'https://conteudo.cbf.com.br/clubes/20064/escudo.jpg',
                })"""
            )
            assert fallback_resolution.endswith("/static/crests/20064.png"), (
                fallback_resolution
            )
            crest_rendering = page.locator(".hero-team img").evaluate_all(
                """images => images.map(image => {
                    const canvas = document.createElement('canvas');
                    canvas.width = image.naturalWidth;
                    canvas.height = image.naturalHeight;
                    const context = canvas.getContext('2d', { willReadFrequently: true });
                    context.drawImage(image, 0, 0);
                    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
                    const alphaAt = (x, y) => data[(y * canvas.width + x) * 4 + 3];
                    const corners = [
                        alphaAt(0, 0),
                        alphaAt(canvas.width - 1, 0),
                        alphaAt(0, canvas.height - 1),
                        alphaAt(canvas.width - 1, canvas.height - 1),
                    ];
                    let opaquePixels = 0;
                    for (let index = 3; index < data.length; index += 4) {
                        if (data[index] > 240) opaquePixels += 1;
                    }
                    const box = image.getBoundingClientRect();
                    return {
                        source: image.src,
                        corners,
                        opaquePixels,
                        width: box.width,
                        height: box.height,
                        background: getComputedStyle(image).backgroundColor,
                    };
                })"""
            )
            assert len(crest_rendering) == 2
            hero_crest_sources = {crest["source"] for crest in crest_rendering}
            assert any(source.endswith("/static/crests/1769.png") for source in hero_crest_sources)
            assert any(
                source.endswith("/static/crests/20064.png")
                for source in hero_crest_sources
            )
            for crest in crest_rendering:
                assert max(crest["corners"]) <= 8, crest
                assert crest["opaquePixels"] > 100, crest
                assert crest["background"] == "rgba(0, 0, 0, 0)", crest
                assert 60 <= crest["width"] <= 72, crest
                assert 60 <= crest["height"] <= 72, crest
            assert abs(crest_rendering[0]["width"] - crest_rendering[1]["width"]) < 1
            assert abs(crest_rendering[0]["height"] - crest_rendering[1]["height"]) < 1
            if screenshot_dir:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(100)
                page.screenshot(
                    path=str(Path(screenshot_dir) / "implemented-feminino-desktop.png"),
                    full_page=False,
                )

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(100)
            assert page.locator("#hero-hub").is_visible()
            assert page.locator("#calendar-hub").is_visible()
            feminine_mobile_order = page.evaluate(
                """() => {
                    const hero = document.querySelector('#hero-hub').getBoundingClientRect();
                    const calendar = document.querySelector('#calendar-hub').getBoundingClientRect();
                    return calendar.top >= hero.bottom;
                }"""
            )
            assert feminine_mobile_order, "feminine calendar is not below the hero"
            if screenshot_dir:
                page.evaluate("window.scrollTo(0, 0)")
                page.wait_for_timeout(100)
                page.screenshot(
                    path=str(Path(screenshot_dir) / "implemented-feminino-mobile.png"),
                    full_page=False,
                )

            notification_page = browser.new_page(
                viewport={"width": 1280, "height": 900},
                service_workers="block",
            )
            notification_page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            notification_page.on("pageerror", lambda error: page_errors.append(str(error)))
            notification_page.add_init_script(
                """
                (() => {
                    let subscriptionActive = true;
                    const subscription = {
                        toJSON: () => ({
                            endpoint: 'https://push.test/subscription',
                            keys: { p256dh: 'test', auth: 'test' },
                        }),
                        unsubscribe: async () => {
                            subscriptionActive = false;
                            return true;
                        },
                    };
                    const pushManager = {
                        getSubscription: async () => subscriptionActive ? subscription : null,
                        subscribe: async () => {
                            subscriptionActive = true;
                            return subscription;
                        },
                    };
                    const registration = { pushManager };
                    Object.defineProperty(window, 'PushManager', {
                        configurable: true,
                        value: class FakePushManager {},
                    });
                    Object.defineProperty(window, 'Notification', {
                        configurable: true,
                        value: {
                            permission: 'granted',
                            requestPermission: async () => 'granted',
                        },
                    });
                    Object.defineProperty(navigator, 'serviceWorker', {
                        configurable: true,
                        value: {
                            register: async () => registration,
                            ready: Promise.resolve(registration),
                            getRegistration: async () => registration,
                            addEventListener: () => {},
                        },
                    });
                    window.__notificationSubscriptionActive = () => subscriptionActive;
                })();
                """
            )

            def fulfill_push(route):
                if route.request.url.endswith("/push/public-key"):
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"publicKey":"AQ"}',
                    )
                else:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body="{}",
                    )

            notification_page.route("**/api/v1/push/**", fulfill_push)
            notification_page.goto(base_url, wait_until="domcontentloaded")
            notification_page.locator(
                '#quickNotifyButton[aria-pressed="true"]'
            ).wait_for(state="visible", timeout=10_000)
            assert notification_page.locator(".icon-alerts-on").is_visible()
            assert not notification_page.locator(".icon-alerts-off").is_visible()

            notification_page.locator("#tab-ajustes").click()
            enable_notifications = notification_page.locator("#enablePushButton")
            disable_notifications = notification_page.locator("#disablePushButton")
            assert enable_notifications.is_disabled()
            assert enable_notifications.inner_text() == "Alertas ativos"
            assert not disable_notifications.is_disabled()

            disable_notifications.click()
            notification_page.locator(
                '#quickNotifyButton[aria-pressed="false"]'
            ).wait_for(state="visible", timeout=10_000)
            assert not notification_page.evaluate(
                "window.__notificationSubscriptionActive()"
            )
            assert not enable_notifications.is_disabled()
            assert enable_notifications.inner_text() == "Ativar e salvar alertas"
            assert disable_notifications.is_disabled()

            notification_page.locator("#quickNotifyButton").click()
            notification_page.locator(
                '#quickNotifyButton[aria-pressed="true"]'
            ).wait_for(state="visible", timeout=10_000)
            assert notification_page.evaluate(
                "window.__notificationSubscriptionActive()"
            )
            assert enable_notifications.is_disabled()
            assert enable_notifications.inner_text() == "Alertas ativos"
            assert not disable_notifications.is_disabled()
            assert "ativos" in notification_page.locator("#pushStatus").inner_text().lower()
            if screenshot_dir:
                notification_page.screenshot(
                    path=str(Path(screenshot_dir) / "implemented-notifications-synced.png"),
                    full_page=False,
                )
            notification_page.close()

            native_notification_page = browser.new_page(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                service_workers="block",
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 "
                    "Chrome/140 Mobile Safari/537.36 PalmeirasAgendaAndroid/1.2.0"
                ),
            )
            native_notification_page.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            native_notification_page.on(
                "pageerror", lambda error: page_errors.append(str(error))
            )
            native_notification_page.add_init_script(
                """
                window.__nativeNotificationSettingsOpened = false;
                window.PalmeirasNative = {
                    getNotificationState: () => JSON.stringify({
                        active: true,
                        permission: 'authorized',
                    }),
                    openNotificationSettings: () => {
                        window.__nativeNotificationSettingsOpened = true;
                    },
                };
                """
            )
            native_notification_page.goto(base_url, wait_until="domcontentloaded")
            native_notification_page.locator(
                '#quickNotifyButton[aria-pressed="true"]'
            ).wait_for(state="visible", timeout=10_000)
            assert (
                native_notification_page.locator("#quickNotifyButton").get_attribute(
                    "aria-label"
                )
                == "Notificações ativas — abrir Ajustes"
            )
            native_notification_page.locator("#quickNotifyButton").click()
            assert native_notification_page.evaluate(
                "window.__nativeNotificationSettingsOpened"
            )
            native_notification_page.evaluate(
                """window.PalmeirasFeatures.setNativeNotificationState({
                    active: false,
                    permission: 'denied',
                })"""
            )
            assert (
                native_notification_page.locator("#quickNotifyButton").get_attribute(
                    "aria-pressed"
                )
                == "false"
            )
            assert (
                native_notification_page.locator("#quickNotifyButton").get_attribute(
                    "aria-label"
                )
                == "Notificações bloqueadas — abrir Ajustes"
            )
            if screenshot_dir:
                native_notification_page.screenshot(
                    path=str(
                        Path(screenshot_dir)
                        / "implemented-native-notification-alignment.png"
                    ),
                    full_page=False,
                )
            native_notification_page.close()

            assert not page_errors, f"page errors: {page_errors}"
            assert not console_errors, f"console errors: {console_errors}"
        finally:
            browser.close()

    print(
        "Web smoke test passed "
        "(synced notifications, floating desktop tabs, "
        "320–430px phone layouts, clean console)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
