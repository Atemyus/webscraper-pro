from __future__ import annotations

import asyncio

import flet as ft

from app import config


class SettingsView(ft.Container):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.expand = True
        self.padding = 40
        self._build()

    def _build(self) -> None:
        self.proxy_field = ft.TextField(
            label="Proxy (opzionale)",
            hint_text="http://utente:password@host:porta",
            prefix_icon=ft.Icons.VPN_LOCK,
            value=config.get_proxy(),
            border_color=ft.Colors.with_opacity(0.3, ft.Colors.INDIGO_300),
            focus_color=ft.Colors.INDIGO_400,
            cursor_color=ft.Colors.INDIGO_300,
            text_style=ft.TextStyle(size=14),
            height=54,
            expand=True,
        )

        self.show_browser_cb = ft.Checkbox(
            label="Mostra il browser durante lo scraping (aiuta a superare Cloudflare su fbref/footystats)",
            value=config.get_show_browser(),
            check_color=ft.Colors.INDIGO_400,
        )

        self.status_text = ft.Text("", size=13, color=ft.Colors.GREY_400, visible=False)

        save_btn = ft.FilledButton(
            content="Salva",
            icon=ft.Icons.SAVE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.Padding(left=22, right=22, top=14, bottom=14),
            ),
            on_click=self._on_save,
        )
        test_btn = ft.FilledTonalButton(
            content="Verifica IP",
            icon=ft.Icons.NETWORK_CHECK,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.Padding(left=22, right=22, top=14, bottom=14),
            ),
            on_click=self._on_test,
        )

        self.content = ft.Column(
            controls=[
                ft.Text("Impostazioni", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text("Configura il proxy per i siti protetti (Cloudflare) o bloccati per IP.",
                        size=14, color=ft.Colors.GREY_400),
                ft.Divider(height=24, color=ft.Colors.TRANSPARENT),
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.VPN_LOCK, size=18, color=ft.Colors.INDIGO_300),
                                        ft.Text("Proxy di rete", size=15, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                                    ],
                                    spacing=8,
                                ),
                                ft.Text(
                                    "Per i siti bloccati a livello di IP (es. footystats da connessioni "
                                    "datacenter) serve un proxy, preferibilmente residenziale. Verrà usato "
                                    "sia dal browser sia dai fallback HTTP.",
                                    size=12, color=ft.Colors.GREY_400,
                                ),
                                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                                self.proxy_field,
                                ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
                                self.show_browser_cb,
                                ft.Text(
                                    "Suggerimento per fbref/footystats: attiva questa opzione e, se "
                                    "compare la verifica Cloudflare nella finestra del browser, "
                                    "risolvila tu una volta — il crawler riuserà il via libera.",
                                    size=11, color=ft.Colors.GREY_500, italic=True,
                                ),
                                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                                ft.Row(controls=[save_btn, test_btn], spacing=12),
                                self.status_text,
                            ],
                            spacing=8,
                        ),
                        padding=24,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.95, "#1a1d27"),
                    elevation=2,
                ),
                ft.Divider(height=16, color=ft.Colors.TRANSPARENT),
                ft.Text(
                    "Suggerimento: lascia vuoto per la connessione diretta. soccerstats non "
                    "richiede proxy; footystats/sofascore sì se il tuo IP è bloccato.",
                    size=12, color=ft.Colors.GREY_500, italic=True,
                ),
            ],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        )

    def _on_save(self, e) -> None:
        config.set_proxy(self.proxy_field.value or "")
        config.set_show_browser(bool(self.show_browser_cb.value))
        val = config.get_proxy()
        browser = "browser visibile" if self.show_browser_cb.value else "browser nascosto"
        proxy = "proxy attivo" if val else "connessione diretta"
        self._show_status(f"Salvato: {proxy}, {browser}.", ft.Colors.GREEN_400)

    async def _on_test(self, e) -> None:
        # Salva prima, così il test usa il valore corrente del campo.
        config.set_proxy(self.proxy_field.value or "")
        self._show_status("Verifica in corso...", ft.Colors.INDIGO_300)
        ok, msg = await asyncio.to_thread(config.check_exit_ip)
        self._show_status(msg, ft.Colors.GREEN_400 if ok else ft.Colors.RED_400)

    def _show_status(self, msg: str, color=ft.Colors.GREY_400) -> None:
        self.status_text.value = msg
        self.status_text.color = color
        self.status_text.visible = True
        self.page.update()
