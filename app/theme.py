from __future__ import annotations

import flet as ft

from app.settings import ThemeMode

LIGHT = {
    "bg": "#F3F0E8",
    "surface": "#FFFDF8",
    "ink": "#1C2420",
    "muted": "#5A675F",
    "line": "#D5D0C4",
    "accent": "#0F6B4C",
    "accent_soft": "#D8EFE4",
    "danger": "#A33B2B",
}

DARK = {
    "bg": "#121816",
    "surface": "#1B2420",
    "ink": "#E8EFE9",
    "muted": "#9AADA2",
    "line": "#2E3A34",
    "accent": "#3DBA8A",
    "accent_soft": "#1E3A2E",
    "danger": "#E07060",
}


def palette(theme: ThemeMode) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


def apply_theme(page: ft.Page, theme: ThemeMode) -> dict[str, str]:
    colors = palette(theme)
    page.theme_mode = ft.ThemeMode.DARK if theme == "dark" else ft.ThemeMode.LIGHT
    page.bgcolor = colors["bg"]
    page.theme = ft.Theme(
        color_scheme_seed=colors["accent"],
        visual_density=ft.VisualDensity.COMFORTABLE,
    )
    return colors
