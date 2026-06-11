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
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_results(self, result: ScrapeResult, url: str) -> ft.Column:
        header = self._build_header(result, url)
        stats_row = self._build_stats(result)
        tabs_content = self._build_tabs(result)

        controls = [header, stats_row]
        if result.notice:
            controls.append(self._build_notice(result.notice))
        controls.append(tabs_content)

        # Intestazione e statistiche restano fisse in alto; l'area dei tab
        # occupa lo spazio rimanente e scrolla internamente (le ListView/GridView
        # dei singoli tab hanno il proprio scroll). NON rendere scrollabile questa
        # Column esterna: andrebbe in conflitto con lo scroll interno dei tab,
        # rendendo lo scroll impossibile o a scatti.
        return ft.Column(
            controls=controls,
            spacing=20,
            expand=True,
        )

    def _build_notice(self, notice: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.AMBER_300),
                    ft.Text(notice, size=12, color=ft.Colors.AMBER_100, expand=True),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.padding.Padding(left=14, right=14, top=10, bottom=10),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.AMBER_400),
            border=ft.border.Border(
                left=ft.BorderSide(3, ft.Colors.AMBER_400),
                top=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                right=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                bottom=ft.BorderSide(0, ft.Colors.TRANSPARENT),
            ),
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
            ft.FilledButton(
                content="Scarica tutto",
                icon=ft.Icons.DOWNLOAD,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.Padding(left=16, right=16, top=8, bottom=8),
                    text_style=ft.TextStyle(size=12, weight=ft.FontWeight.W_600),
                ),
                tooltip="Esporta JSON + CSV + Excel e apri la cartella",
                on_click=lambda _: self._export_all(),
            ),
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
        tabs: list[ft.Tab] = []
        views: list[ft.Control] = []

        if result.texts:
            tabs.append(ft.Tab(label=f"Testi ({len(result.texts)})", icon=ft.Icons.TEXT_FIELDS))
            views.append(self._build_texts_tab(result.texts))

        if result.tables:
            tabs.append(ft.Tab(label=f"Tabelle ({len(result.tables)})", icon=ft.Icons.TABLE_CHART))
            views.append(self._build_tables_tab(result.tables))

        if result.links:
            tabs.append(ft.Tab(label=f"Link ({len(result.links)})", icon=ft.Icons.LINK))
            views.append(self._build_links_tab(result.links))

        if result.images:
            tabs.append(ft.Tab(label=f"Immagini ({len(result.images)})", icon=ft.Icons.IMAGE))
            views.append(self._build_images_tab(result.images))

        if not tabs:
            tabs.append(ft.Tab(label="Info", icon=ft.Icons.INFO))
            views.append(ft.Container(
                content=ft.Text("Nessun elemento estratto.", color=ft.Colors.GREY_400),
                padding=40,
            ))

        tabs_widget = ft.Tabs(
            length=len(tabs),
            selected_index=0,
            animation_duration=300,
            expand=True,
            content=ft.Column(
                controls=[
                    ft.TabBar(tabs=tabs, scrollable=True),
                    ft.TabBarView(controls=views, expand=True),
                ],
                spacing=0,
                expand=True,
            ),
        )

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
        headers = list(data.get("headers", []) or [])
        rows = data.get("rows", []) or []

        # Numero di colonne: il massimo fra header e righe. Le tabelle reali
        # hanno spesso righe di lunghezza diversa (colspan/rowspan): per evitare
        # il crash del DataTable di Flet ("DataRow deve avere tante celle quante
        # le colonne") normalizziamo TUTTE le righe e gli header a ncols.
        ncols = len(headers)
        for r in rows:
            ncols = max(ncols, len(r))
        if ncols == 0:
            return ft.Container(
                content=ft.Text("Tabella vuota", size=12, color=ft.Colors.GREY_500),
                padding=16,
            )
        if len(headers) < ncols:
            headers = headers + [f"Col {i+1}" for i in range(len(headers), ncols)]
        else:
            headers = headers[:ncols]

        def pad(seq, n):
            seq = list(seq)[:n]
            return seq + [""] * (n - len(seq))

        table_rows = []
        for r in rows[:50]:
            cells = [
                ft.DataCell(ft.Text(str(val)[:100], size=12, color=ft.Colors.GREY_300))
                for val in pad(r, ncols)
            ]
            table_rows.append(ft.DataRow(cells=cells))

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(f"Tabella ({len(rows)} righe x {ncols} colonne)", size=13, color=ft.Colors.GREY_400),
                    ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                    ft.Container(
                        content=ft.DataTable(
                            columns=[ft.DataColumn(ft.Text(str(h) or f"C{i}", size=12)) for i, h in enumerate(headers)],
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
                            ft.Text(text or "(no text)", size=13, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500),
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
            self._reveal_folder(path)
            self._show_snackbar(f"File {fmt.upper()} salvato in: {path}")
        else:
            self._show_snackbar("Nessun risultato da esportare", ft.Colors.RED_400)

    async def _export_all(self) -> None:
        paths = await self.app.export_all_results()
        if paths:
            folder = self.app.output_dir
            self._reveal_folder(folder)
            formats = ", ".join(sorted(p.upper() for p in paths))
            self._show_snackbar(f"Salvati {formats} nella cartella: {folder}")
        else:
            self._show_snackbar("Nessun risultato da esportare", ft.Colors.RED_400)

    def _reveal_folder(self, path: str) -> None:
        """Apre la cartella che contiene i file esportati nel file manager."""
        import os
        import platform
        import subprocess

        folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            # Apertura non riuscita (es. ambiente headless): il percorso resta
            # comunque mostrato nello snackbar.
            pass

    def _show_snackbar(self, msg: str, color=ft.Colors.GREEN_400) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(msg, size=13, color=color),
                bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
                duration=6000,
            )
        )
