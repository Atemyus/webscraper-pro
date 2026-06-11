from __future__ import annotations

import flet as ft

from app.categories import (
    ALL_CATEGORIES,
    CategoryDef,
    FilterDef,
    detect_category,
    get_category,
)


class HomeView(ft.Container):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.expand = True
        self.padding = 40
        self._selected_category = ALL_CATEGORIES[0]
        self._filter_widgets: dict[str, ft.Control] = {}
        self._build()

    def _build(self) -> None:
        self.url_field = ft.TextField(
            label="Inserisci URL",
            hint_text="https://example.com",
            prefix_icon=ft.Icons.LINK,
            border_color=ft.Colors.with_opacity(0.3, ft.Colors.INDIGO_300),
            focus_color=ft.Colors.INDIGO_400,
            cursor_color=ft.Colors.INDIGO_300,
            text_style=ft.TextStyle(size=15),
            height=52,
            expand=True,
            on_change=self._on_url_change,
        )

        self.status_text = ft.Text("", size=13, color=ft.Colors.GREY_400, visible=False)

        self.scrape_btn = ft.FilledTonalButton(
            content="Avvia Scraping",
            icon=ft.Icons.PLAY_ARROW,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.padding.Padding(left=28, right=28, top=16, bottom=16),
                text_style=ft.TextStyle(size=15, weight=ft.FontWeight.W_600),
            ),
            on_click=self._on_scrape,
        )

        self.progress = ft.Container(
            content=ft.ProgressBar(color=ft.Colors.INDIGO_400, bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.INDIGO_200)),
            visible=False,
        )

        self.content = ft.Column(
            controls=[
                self._build_header(),
                self._build_category_tabs(),
                self._build_main_card(),
                self._build_filters_section(),
                self._build_action_row(),
                self.progress,
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_header(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Web Scraping Intelligence", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    ft.Text("Seleziona una categoria, inserisci l'URL, configura i filtri e avvia lo scraping.", size=14, color=ft.Colors.GREY_400),
                ],
                spacing=4,
            ),
            margin=ft.margin.Margin(bottom=24),
        )

    def _build_category_tabs(self) -> ft.Container:
        self._cat_btns: list[ft.Container] = []

        def on_cat_click(e):
            idx = int(e.control.data)
            self._select_category(ALL_CATEGORIES[idx])

        for i, cat in enumerate(ALL_CATEGORIES):
            active = cat == self._selected_category
            btn = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(cat.icon, size=20, color=cat.color if active else ft.Colors.GREY_500),
                        ft.Text(cat.label, size=11, weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL,
                                color=cat.color if active else ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                width=90,
                height=60,
                padding=ft.padding.Padding(top=8, bottom=4, left=4, right=4),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.12, cat.color) if active else ft.Colors.with_opacity(0.03, ft.Colors.WHITE),
                        data=i,
                on_click=on_cat_click,
                ink=True,
            )
            self._cat_btns.append(btn)

        return ft.Container(
            content=ft.Row(controls=self._cat_btns, spacing=8),
            margin=ft.margin.Margin(bottom=20),
        )

    def _build_main_card(self) -> ft.Container:
        self._cat_desc = ft.Text(
            self._selected_category.description,
            size=13,
            color=ft.Colors.GREY_400,
        )

        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Target URL", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                        self.url_field,
                        ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                        self._cat_desc,
                    ],
                    spacing=4,
                ),
                padding=20,
            ),
            bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
            elevation=2,
            margin=ft.margin.Margin(bottom=20),
        )

    def _build_filters_section(self) -> ft.Container:
        self._filters_container = ft.Container(
            content=self._build_filters_for_category(self._selected_category),
        )
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("Filtri", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_300),
                            ft.Icon(ft.Icons.TUNE, size=16, color=ft.Colors.GREY_500),
                            ft.Text("(tutti opzionali — puoi lasciarli vuoti)", size=12, italic=True, color=ft.Colors.GREY_500),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(height=6, color=ft.Colors.TRANSPARENT),
                    self._filters_container,
                ],
                spacing=4,
            ),
        )

    def _build_filters_for_category(self, cat: CategoryDef) -> ft.Column:
        self._filter_widgets = {}
        rows = []

        for flt in cat.filters:
            widget = self._create_filter_widget(flt)
            self._filter_widgets[flt.key] = widget

            if flt.filter_type == "checkbox":
                rows.append(ft.Row(controls=[widget], spacing=0))
            elif flt.filter_type == "expandable":
                rows.append(self._build_expandable_filter(flt, widget))
            else:
                rows.append(widget)

        if not cat.filters:
            rows.append(ft.Text("Nessun filtro disponibile per questa categoria", size=12, color=ft.Colors.GREY_600, italic=True))

        new_rows = []
        for i in range(0, len(rows), 2):
            if i + 1 < len(rows):
                new_rows.append(ft.Row(controls=[rows[i], rows[i + 1]], spacing=16))
            else:
                new_rows.append(ft.Row(controls=[rows[i]]))

        return ft.Column(controls=new_rows, spacing=12)

    def _create_filter_widget(self, flt: FilterDef) -> ft.Control:
        if flt.filter_type == "text":
            return ft.TextField(
                label=flt.label,
                hint_text=flt.hint,
                prefix_icon=ft.Icons.SEARCH,
                border_color=ft.Colors.with_opacity(0.2, ft.Colors.INDIGO_300),
                focus_color=ft.Colors.INDIGO_400,
                cursor_color=ft.Colors.INDIGO_300,
                text_style=ft.TextStyle(size=13),
                height=48,
                expand=True,
                value=flt.default or "",
            )

        elif flt.filter_type == "number":
            return ft.TextField(
                label=flt.label,
                hint_text=flt.hint,
                prefix_icon=ft.Icons.PIN,
                border_color=ft.Colors.with_opacity(0.2, ft.Colors.INDIGO_300),
                focus_color=ft.Colors.INDIGO_400,
                cursor_color=ft.Colors.INDIGO_300,
                text_style=ft.TextStyle(size=13),
                height=48,
                expand=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                value=flt.default or "",
            )

        elif flt.filter_type == "select":
            return ft.Dropdown(
                label=flt.label,
                options=[ft.dropdown.Option(o) for o in flt.options],
                border_color=ft.Colors.with_opacity(0.2, ft.Colors.INDIGO_300),
                text_style=ft.TextStyle(size=13),
                height=48,
                expand=True,
                value=flt.options[0] if flt.options else None,
            )

        elif flt.filter_type == "checkbox":
            return ft.Checkbox(
                label=flt.label,
                value=flt.default or False,
                check_color=ft.Colors.INDIGO_400,
            )

        elif flt.filter_type == "date":
            return ft.TextField(
                label=flt.label,
                hint_text="YYYY-MM-DD",
                prefix_icon=ft.Icons.CALENDAR_MONTH,
                border_color=ft.Colors.with_opacity(0.2, ft.Colors.INDIGO_300),
                focus_color=ft.Colors.INDIGO_400,
                cursor_color=ft.Colors.INDIGO_300,
                text_style=ft.TextStyle(size=13),
                height=48,
                expand=True,
                value=flt.default or "",
            )

        return ft.Text(f"Unknown filter: {flt.filter_type}", size=12, color=ft.Colors.RED_400)

    def _build_expandable_filter(self, flt: FilterDef, widget: ft.Control) -> ft.Container:
        expanded = ft.Column(controls=[widget], spacing=8, visible=False)

        def toggle(e):
            expanded.visible = not expanded.visible
            self.page.update()

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.EXPAND_MORE, size=18, color=ft.Colors.GREY_400),
                                ft.Text(flt.label, size=13, color=ft.Colors.GREY_300),
                            ],
                            spacing=4,
                        ),
                        on_click=toggle,
                        ink=True,
                    ),
                    expanded,
                ],
                spacing=4,
            ),
        )

    def _build_action_row(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    self.scrape_btn,
                    self.status_text,
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.margin.Margin(top=20),
        )

    def _select_category(self, cat: CategoryDef) -> None:
        self._selected_category = cat
        for i, btn in enumerate(self._cat_btns):
            c = ALL_CATEGORIES[i]
            active = c == cat
            content = btn.content
            if isinstance(content, ft.Column):
                icon_ctrl = content.controls[0]
                text_ctrl = content.controls[1]
                if isinstance(icon_ctrl, ft.Icon):
                    icon_ctrl.color = c.color if active else ft.Colors.GREY_500
                if isinstance(text_ctrl, ft.Text):
                    text_ctrl.color = c.color if active else ft.Colors.GREY_400
                    text_ctrl.weight = ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL
            btn.bgcolor = ft.Colors.with_opacity(0.12, c.color) if active else ft.Colors.with_opacity(0.03, ft.Colors.WHITE)

        self._cat_desc.value = cat.description
        self._filters_container.content = self._build_filters_for_category(cat)
        self.update()

    def _on_url_change(self, e) -> None:
        url = self.url_field.value.strip()
        detected = detect_category(url)
        if detected and detected != self._selected_category.key:
            self._select_category(get_category(detected))

    async def _on_scrape(self, e) -> None:
        url = self.url_field.value.strip()
        if not url:
            self._show_status("Inserisci un URL valido", ft.Colors.AMBER_400)
            return

        filters = self._collect_filters()
        self._show_status("Avvio scraping...", ft.Colors.INDIGO_300)
        await self.app.run_scrape(
            url=url,
            category=self._selected_category.key,
            filters=filters,
        )

    def _collect_filters(self) -> dict:
        collected = {}
        for key, widget in self._filter_widgets.items():
            if isinstance(widget, ft.TextField):
                val = widget.value.strip()
                if widget.keyboard_type == ft.KeyboardType.NUMBER:
                    val = val or "0"
                collected[key] = val
            elif isinstance(widget, ft.Dropdown):
                collected[key] = widget.value
            elif isinstance(widget, ft.Checkbox):
                collected[key] = widget.value
            elif isinstance(widget, ft.Container):
                pass
        return collected

    def set_loading(self, loading: bool) -> None:
        self.progress.visible = loading
        self.scrape_btn.disabled = loading
        self.url_field.disabled = loading
        for widget in self._filter_widgets.values():
            if hasattr(widget, "disabled"):
                try:
                    widget.disabled = loading
                except Exception:
                    pass

    def show_error(self, msg: str) -> None:
        self._show_status(f"Errore: {msg}", ft.Colors.RED_400)

    def show_progress(self, msg: str) -> None:
        self._show_status(msg, ft.Colors.INDIGO_200)

    def _show_status(self, msg: str, color=ft.Colors.GREY_400) -> None:
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        self.page.update()
