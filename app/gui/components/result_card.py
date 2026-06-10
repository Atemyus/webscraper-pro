from __future__ import annotations

import flet as ft

from app.models.scrape_result import ScrapedItem


class ResultCard(ft.Container):
    def __init__(self, item: ScrapedItem):
        super().__init__()
        self.item = item
        self.padding = 14
        self.border_radius = 10
        self.bgcolor = ft.Colors.with_opacity(0.03, ft.Colors.WHITE)
        self.content = self._build()

    def _build(self) -> ft.Control:
        tag = self.item.attributes.get("tag", "")
        tag_colors = {
            "h1": ft.Colors.INDIGO_300,
            "h2": ft.Colors.BLUE_300,
            "h3": ft.Colors.CYAN_300,
            "h4": ft.Colors.TEAL_300,
            "h5": ft.Colors.GREEN_300,
            "h6": ft.Colors.GREEN_200,
            "p": ft.Colors.GREY_300,
            "article": ft.Colors.AMBER_300,
            "blockquote": ft.Colors.ORANGE_300,
            "section": ft.Colors.PURPLE_300,
        }
        tag_color = tag_colors.get(tag, ft.Colors.GREY_400)

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Text(
                                tag.upper(),
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color=tag_color,
                            ),
                            padding=ft.padding.Padding(left=6, right=6, top=2, bottom=2),
                            border_radius=4,
                            bgcolor=ft.Colors.with_opacity(0.15, tag_color),
                        ),
                        ft.Text(
                            str(len(str(self.item.content))),
                            size=11,
                            color=ft.Colors.GREY_500,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Container(
                    content=ft.Text(
                        str(self.item.content),
                        size=13,
                        color=ft.Colors.GREY_200,
                        selectable=True,
                    ),
                    margin=ft.margin.Margin(top=6),
                ),
                ft.Container(
                    content=ft.Text(
                        f"selector: {self.item.selector or '-'}",
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True,
                    ),
                    margin=ft.margin.Margin(top=4),
                ),
            ],
            spacing=0,
        )
