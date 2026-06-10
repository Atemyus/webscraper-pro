from __future__ import annotations

import flet as ft

from app.models.scrape_result import ScrapeResult
from app.gui.components.result_card import ResultCard


class ResultsView(ft.Container):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.current_result: ScrapeResult | None = None
        self.current_name: str | None = None
        self.current_keywords: list[str] | None = None
        self.expand = True
        self.padding = 32
        self.content = self._build_empty()

    def _build_empty(self) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Container(expand=True),
                ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.QUERY_STATS, size=64, color=ft.Colors.with_opacity(0.2, ft.Colors.INDIGO_300)),
                        ft.Text("Nessun risultato ancora", size=20, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_600),
                        ft.Text("Avvia uno scraping dalla home per vedere i risultati qui", size=13, color=ft.Colors.GREY_600),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                ft.Container(expand=True),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def display_result(
        self, result: ScrapeResult, url: str, keywords: list[str] | None
    ) -> None:
        self.current_result = result
        self.current_keywords = keywords

        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in domain)
        self.current_name = f"scrape_{safe_name}"

        if result.error:
            self.content = self._build_error(result)
        else:
            self.content = self._build_results(result, url)
        self.update()

    def _build_error(self, result: ScrapeResult) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color=ft.Colors.RED_400),
                            ft.Text("Errore durante lo scraping", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_300),
                            ft.Text(result.error or "Errore sconosciuto", size=14, color=ft.Colors.GREY_400),
                            ft.ElevatedButton(
                                "Torna alla Home",
                                icon=ft.Icons.ARROW_BACK,
                                on_click=lambda _: self.app._navigate("home"),
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    alignment=ft.alignment.center,
                    expand=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_results(self, result: ScrapeResult, url: str) -> ft.Column:
        header = self._build_header(result, url)
        stats_row = self._build_stats(result)
        tabs_content = self._build_tabs(result)

        return ft.Column(
            controls=[header, stats_row, tabs_content],
            spacing=20,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _build_header(self, result: ScrapeResult, url: str) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        result.title or "Risultati Scraping",
                        size=26,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Container(
                        content=ft.Text(
                            url,
                            size=13,
                            color=ft.Colors.INDIGO_300,
                            selectable=True,
                        ),
                        margin=ft.margin.Margin(top=4),
                    ),
                    ft.Row(
                        controls=[
                            ft.Chip(
                                label=ft.Text(f"{len(result.items)} elementi trovati", size=12),
                                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.INDIGO_400),
                            ),
                            *self._build_action_buttons(),
                        ],
                        spacing=12,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=4,
            ),
            margin=ft.margin.Margin(bottom=4),
        )

    def _build_action_buttons(self) -> list[ft.Control]:
        return [
            ft.FilledTonalButton(
                content="JSON",
                icon=ft.Icons.CODE,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.Padding(left=14, right=14, top=8, bottom=8),
                    text_style=ft.TextStyle(size=12),
                ),
                on_click=lambda _: self._export("json"),
            ),
            ft.FilledTonalButton(
                content="CSV",
                icon=ft.Icons.TABLE_CHART,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.Padding(left=14, right=14, top=8, bottom=8),
                    text_style=ft.TextStyle(size=12),
                ),
                on_click=lambda _: self._export("csv"),
            ),
            ft.FilledTonalButton(
                content="Excel",
                icon=ft.Icons.GRID_ON,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.Padding(left=14, right=14, top=8, bottom=8),
                    text_style=ft.TextStyle(size=12),
                ),
                on_click=lambda _: self._export("xlsx"),
            ),
            ft.IconButton(
                icon=ft.Icons.HOME_OUTLINED,
                tooltip="Home",
                on_click=lambda _: self.app._navigate("home"),
            ),
        ]

    def _build_stats(self, result: ScrapeResult) -> ft.Container:
        stats = [
            ("Testi", len(result.texts), ft.Icons.TEXT_FIELDS, ft.Colors.BLUE_300),
            ("Tabelle", len(result.tables), ft.Icons.TABLE_CHART, ft.Colors.GREEN_300),
            ("Link", len(result.links), ft.Icons.LINK, ft.Colors.AMBER_300),
            ("Immagini", len(result.images), ft.Icons.IMAGE, ft.Colors.PURPLE_300),
        ]

        cards = []
        for label, count, icon, color in stats:
            cards.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(icon, size=18, color=color),
                                    ft.Text(str(count), size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(label, size=12, color=ft.Colors.GREY_400),
                        ],
                        spacing=2,
                    ),
                    padding=18,
                    border_radius=12,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                    expand=True,
                )
            )

        return ft.Container(
            content=ft.Row(controls=cards, spacing=16),
        )

    def _build_tabs(self, result: ScrapeResult) -> ft.Container:
        tab_list = []

        if result.texts:
            t = ft.Tab(label=f"Testi ({len(result.texts)})", icon=ft.Icons.TEXT_FIELDS)
            t.content = self._build_texts_tab(result.texts)
            tab_list.append(t)

        if result.tables:
            t = ft.Tab(label=f"Tabelle ({len(result.tables)})", icon=ft.Icons.TABLE_CHART)
            t.content = self._build_tables_tab(result.tables)
            tab_list.append(t)

        if result.links:
            t = ft.Tab(label=f"Link ({len(result.links)})", icon=ft.Icons.LINK)
            t.content = self._build_links_tab(result.links)
            tab_list.append(t)

        if result.images:
            t = ft.Tab(label=f"Immagini ({len(result.images)})", icon=ft.Icons.IMAGE)
            t.content = self._build_images_tab(result.images)
            tab_list.append(t)

        if not tab_list:
            t = ft.Tab(label="Info", icon=ft.Icons.INFO)
            t.content = ft.Container(
                content=ft.Text("Nessun elemento estratto.", color=ft.Colors.GREY_400),
                padding=40,
            )
            tab_list.append(t)

        tabs_widget = ft.Tabs(
            content=ft.Container(expand=True),
            length=len(tab_list),
            selected_index=0,
            animation_duration=300,
            expand=True,
        )
        tabs_widget.tabs = tab_list

        return ft.Container(
            content=tabs_widget,
            expand=True,
        )

    def _build_texts_tab(self, texts) -> ft.ListView:
        lv = ft.ListView(spacing=8, padding=ft.padding.Padding(top=12, bottom=12), expand=True)
        for item in texts:
            card = ResultCard(item)
            lv.controls.append(card)
        return lv

    def _build_tables_tab(self, tables) -> ft.ListView:
        lv = ft.ListView(spacing=12, padding=ft.padding.Padding(top=12, bottom=12), expand=True)
        for item in tables:
            card = self._build_table_card(item)
            lv.controls.append(card)
        return lv

    def _build_links_tab(self, links) -> ft.ListView:
        lv = ft.ListView(spacing=4, padding=ft.padding.Padding(top=12, bottom=12), expand=True)
        for item in links:
            lv.controls.append(self._build_link_row(item))
        return lv

    def _build_images_tab(self, images) -> ft.GridView:
        gv = ft.GridView(
            expand=True,
            max_extent=200,
            child_aspect_ratio=1,
            spacing=8,
            run_spacing=8,
            padding=ft.padding.Padding(top=12, bottom=12),
        )
        for item in images:
            url = item.content.get("url", "")
            alt = item.content.get("alt", "")
            gv.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Container(
                                content=ft.Image(src=url, fit=ft.BoxFit.COVER, error_content=ft.Icon(ft.Icons.BROKEN_IMAGE, size=32)),
                                height=140,
                                border_radius=8,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                            ),
                            ft.Text(alt[:60] if alt else "(no alt)", size=11, color=ft.Colors.GREY_400, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=4,
                    ),
                    padding=8,
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
                    ink=True,
                )
            )

        return gv

    def _build_table_card(self, item) -> ft.Container:
        data = item.content
        headers = data.get("headers", [])
        rows = data.get("rows", [])

        if not headers and rows:
            headers = [f"Col {i+1}" for i in range(len(rows[0]))]

        table_rows = []
        if headers:
            table_rows.append(
                ft.DataRow(
                    cells=[ft.DataCell(ft.Text(h, weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.INDIGO_300)) for h in headers],
                    color=ft.Colors.with_opacity(0.05, ft.Colors.INDIGO_200),
                )
            )

        for r in rows[:50]:
            cells = []
            for ci, val in enumerate(r):
                cells.append(ft.DataCell(ft.Text(str(val)[:100], size=12, color=ft.Colors.GREY_300)))
            table_rows.append(ft.DataRow(cells=cells))

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(f"Tabella ({len(rows)} righe x {len(headers)} colonne)", size=13, color=ft.Colors.GREY_400),
                    ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                    ft.Container(
                        content=ft.DataTable(
                            columns=[ft.DataColumn(ft.Text(h or f"C{i}", size=12)) for i, h in enumerate(headers)],
                            rows=table_rows,
                            border=ft.border.Border(left=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), right=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), top=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE))),
                            border_radius=8,
                            data_row_color={"hovered": ft.Colors.with_opacity(0.05, ft.Colors.INDIGO_200)},
                            heading_row_color=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
                        ),
            border_radius=8,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    ),
                ],
            ),
            padding=16,
            border_radius=12,
            bgcolor=ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
        )

    def _build_link_row(self, item) -> ft.Container:
        url = item.content.get("url", "")
        text = item.content.get("text", "")
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.OPEN_IN_NEW, size=16, color=ft.Colors.INDIGO_400),
                    ft.Column(
                        controls=[
                            ft.Text(text or "(no text)", size=13, color=ft.Colors.WHITE, weight=ft.FontWeight.MEDIUM),
                            ft.Text(url, size=11, color=ft.Colors.INDIGO_300, selectable=True),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.Padding(left=16, right=16, top=10, bottom=10),
            border_radius=8,
            ink=True,
        )

    async def _export(self, fmt: str) -> None:
        path = await self.app.export_result(fmt)
        if path:
            self._show_snackbar(f"Esportato: {path}")
        else:
            self._show_snackbar("Nessun risultato da esportare", ft.Colors.RED_400)

    def _show_snackbar(self, msg: str, color=ft.Colors.GREEN_400) -> None:
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, size=13),
            bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
        )
        self.page.snack_bar.open = True
        self.page.update()
