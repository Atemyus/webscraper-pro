from __future__ import annotations

import asyncio
import logging

import flet as ft

from app.gui.views.home_view import HomeView
from app.gui.views.results_view import ResultsView
from app.services import ScraperService

logger = logging.getLogger("scraper.gui")


class ScraperApp:
    APP_NAME = "WebScraper Pro"
    VERSION = "1.0.0"

    def __init__(self, page: ft.Page):
        self.page = page
        self.service = ScraperService()
        self._setup_page()
        self._build_ui()

    def _setup_page(self) -> None:
        self.page.title = f"{self.APP_NAME} v{self.VERSION}"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.spacing = 0
        self.page.window_width = 1400
        self.page.window_height = 900
        self.page.window_min_width = 1000
        self.page.window_min_height = 700

        self.page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.INDIGO,
            use_material3=True,

        )

        self.page.bgcolor = ft.Colors.with_opacity(1, "#0f1117")

    def _build_ui(self) -> None:
        self.page.appbar = self._build_appbar()

        self.home_view = HomeView(self)
        self.results_view = ResultsView(self)

        self.content = ft.AnimatedSwitcher(
            content=self.home_view,
            transition=ft.AnimatedSwitcherTransition.SCALE,
            duration=300,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_IN_OUT,
            switch_out_curve=ft.AnimationCurve.EASE_IN_OUT,
            expand=True,
        )

        sidebar = self._build_sidebar()

        layout = ft.Row(
            controls=[sidebar, ft.VerticalDivider(width=1, color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), self.content],
            spacing=0,
            expand=True,
        )

        self.page.add(layout)

    def _build_appbar(self) -> ft.AppBar:
        return ft.AppBar(
            leading=ft.Icon(ft.Icons.TRAVEL_EXPLORE, color=ft.Colors.INDIGO_400),
            leading_width=40,
            title=ft.Text(
                f"{self.APP_NAME}",
                size=20,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
            ),
            bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
            actions=[
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CIRCLE, size=8, color=ft.Colors.GREEN_400),
                            ft.Text("Ready", size=12, color=ft.Colors.GREY_400),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.Padding(right=16),
                ),
            ],
        )

    def _build_sidebar(self) -> ft.Container:
        nav_items = [
            ("home", ft.Icons.HOME_OUTLINED, "Home", True),
            ("results", ft.Icons.QUERY_STATS_OUTLINED, "Results", False),
            ("settings", ft.Icons.SETTINGS_OUTLINED, "Settings", False),
        ]

        def on_nav_click(e):
            idx = int(e.control.data)
            for i, item in enumerate(nav_btns):
                item.bgcolor = ft.Colors.with_opacity(0.1, ft.Colors.INDIGO_400) if i == idx else ft.Colors.TRANSPARENT
            self.page.update()
            self._navigate(nav_items[idx][0])

        nav_btns = []
        for i, (key, icon, label, active) in enumerate(nav_items):
            btn = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(icon, size=22, color=ft.Colors.INDIGO_200 if active else ft.Colors.GREY_400),
                        ft.Text(label, size=11, color=ft.Colors.INDIGO_200 if active else ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                width=80,
                height=64,
                padding=ft.padding.Padding(top=8, bottom=8),
                border_radius=12,
                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.INDIGO_400) if active else ft.Colors.TRANSPARENT,
                data=i,
                on_click=on_nav_click,
                ink=True,
            )
            nav_btns.append(btn)

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(height=16),
                    *nav_btns,
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.GREY_600),
                                ft.Text(f"v{self.VERSION}", size=10, color=ft.Colors.GREY_700),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=2,
                        ),
                        padding=ft.padding.Padding(bottom=12),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=96,
            bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
            border=ft.border.Border(right=ft.BorderSide(1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE))),
        )

    def _navigate(self, view: str) -> None:
        views = {
            "home": self.home_view,
            "results": self.results_view,
        }
        new_content = views.get(view, self.home_view)
        if new_content != self.content.content:
            self.content.content = new_content
            self.page.update()

    async def run_scrape(
        self,
        url: str,
        category: str | None = None,
        filters: dict | None = None,
    ) -> None:
        self.home_view.set_loading(True)
        self.page.update()

        try:
            keywords_text = (filters or {}).get("keywords", "")
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()] if keywords_text else None

            result = await self.service.scrape(
                url=url,
                keywords=keywords,
                category=category,
                filters=filters,
                headless=True,
                screenshot=True,
            )
            self.results_view.display_result(result, url, keywords)
            self._navigate("results")
        except Exception as e:
            logger.error("Scraping error: %s", e)
            self.home_view.show_error(str(e))
        finally:
            self.home_view.set_loading(False)
            self.page.update()

    async def export_result(self, fmt: str) -> str | None:
        result = self.results_view.current_result
        if result is None:
            return None
        name = self.results_view.current_name or "scrape_result"
        return await self.service.export(result, name, fmt)
