"""
WebScraper Pro — Universal Web Scraping Tool

A modern, professional web scraping application with a Flet GUI.
Extract data from any website with ease.

Usage:
    python main.py
"""

from __future__ import annotations

"""
WebScraper Pro — Universal Web Scraping Tool

Usage:
    python main.py
"""

import logging

import flet as ft

from app.gui.app import ScraperApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    logger.info("Avvio WebScraper Pro...")

    def app_factory(page: ft.Page):
        ScraperApp(page)

    ft.app(target=app_factory)


if __name__ == "__main__":
    main()
