from __future__ import annotations

import flet as ft

# Density unit. Prefer expand / col for layout; use u() instead of one-off px.
U = 8.0


def u(n: float) -> float:
    return n * U


ColorSchemeId = str


def _scheme(*, dark: bool, **colors: str) -> dict[str, str | bool]:
    return {"dark": dark, **colors}


# Each scheme is itself light or dark. No separate dark-mode switch.
SCHEMES: dict[str, dict[str, str | bool]] = {
    "snow": _scheme(
        dark=False,
        bg="#E8E8E2",
        surface="#FFFFFF",
        surface_alt="#D8D8D0",
        paper="#FFFFFF",
        ink="#111110",
        muted="#3A3A34",
        line="#8E8E84",
        accent="#0B6B42",
        accent_2="#B03A10",
        accent_soft="#C5EBD6",
        on_accent="#FFFFFF",
        danger="#B42318",
        veil="#99C5EBD6",
        shadow="#33000000",
    ),
    "ink": _scheme(
        dark=True,
        bg="#08080A",
        surface="#16161A",
        surface_alt="#22222A",
        paper="#101014",
        ink="#F8F8F3",
        muted="#C8C8BE",
        line="#5A5A66",
        accent="#3DDC97",
        accent_2="#FFB020",
        accent_soft="#124830",
        on_accent="#062016",
        danger="#FF8A80",
        veil="#99124830",
        shadow="#99000000",
    ),
    "sage": _scheme(
        dark=False,
        bg="#B7E0C8",
        surface="#F3FBF6",
        surface_alt="#8FCBAA",
        paper="#FFFEFB",
        ink="#0A2216",
        muted="#1F4F36",
        line="#3D8A60",
        accent="#0E7044",
        accent_2="#D97706",
        accent_soft="#7ED0A4",
        on_accent="#FFFFFF",
        danger="#B91C1C",
        veil="#997ED0A4",
        shadow="#330E7044",
    ),
    "meadow": _scheme(
        dark=False,
        bg="#D4EE6A",
        surface="#F4FAD0",
        surface_alt="#B5D63A",
        paper="#FFFEF4",
        ink="#1A2608",
        muted="#3A520C",
        line="#6A8C14",
        accent="#3F6F00",
        accent_2="#C81E3A",
        accent_soft="#C3E85A",
        on_accent="#FFFFFF",
        danger="#B42318",
        veil="#99C3E85A",
        shadow="#333F6F00",
    ),
    "citrus": _scheme(
        dark=False,
        bg="#E8F06A",
        surface="#F7FBB8",
        surface_alt="#D0DC3A",
        paper="#FFFFF4",
        ink="#1E2608",
        muted="#4A5C0C",
        line="#8A9A18",
        accent="#4A7A00",
        accent_2="#E07800",
        accent_soft="#D4E85A",
        on_accent="#FFFFFF",
        danger="#C2410C",
        veil="#99D4E85A",
        shadow="#334A7A00",
    ),
    "sky": _scheme(
        dark=False,
        bg="#8EDCE2",
        surface="#E8F8F9",
        surface_alt="#5EC8D0",
        paper="#F7FFFE",
        ink="#0A2A30",
        muted="#1A5560",
        line="#2A8890",
        accent="#0A7A70",
        accent_2="#1D4ED8",
        accent_soft="#7EE0D6",
        on_accent="#FFFFFF",
        danger="#B91C1C",
        veil="#997EE0D6",
        shadow="#330A7A70",
    ),
    "peach": _scheme(
        dark=False,
        bg="#F5C4A8",
        surface="#FDEEE4",
        surface_alt="#E8A888",
        paper="#FFF8F3",
        ink="#1C1410",
        muted="#5A3A2C",
        line="#C47A58",
        accent="#0E7044",
        accent_2="#C2410C",
        accent_soft="#B8E0C8",
        on_accent="#FFFFFF",
        danger="#B91C1C",
        veil="#99B8E0C8",
        shadow="#330E7044",
    ),
    "grape": _scheme(
        dark=False,
        bg="#C8B8F0",
        surface="#F4EEFC",
        surface_alt="#A898E0",
        paper="#FCFAFF",
        ink="#160E28",
        muted="#3A2A5C",
        line="#6A58B0",
        accent="#4C3BCF",
        accent_2="#0E7044",
        accent_soft="#C4B8F8",
        on_accent="#FFFFFF",
        danger="#B91C1C",
        veil="#99C4B8F8",
        shadow="#334C3BCF",
    ),
}

DEFAULT_SCHEME = "sage"
SCHEME_IDS = tuple(SCHEMES.keys())
SCHEME_COLOR_KEYS = (
    "bg",
    "surface",
    "surface_alt",
    "paper",
    "ink",
    "muted",
    "line",
    "accent",
    "accent_2",
    "accent_soft",
    "on_accent",
    "danger",
    "veil",
    "shadow",
)


def resolve_scheme(scheme: str | None) -> str:
    if scheme in SCHEMES:
        return scheme
    return DEFAULT_SCHEME


def scheme_is_dark(scheme: str | None) -> bool:
    return bool(SCHEMES[resolve_scheme(scheme)].get("dark"))


def palette(scheme: str | None = None) -> dict[str, str]:
    family = SCHEMES[resolve_scheme(scheme)]
    return {key: str(family[key]) for key in SCHEME_COLOR_KEYS}


def apply_theme(page: ft.Page, scheme: str | None = None) -> dict[str, str]:
    colors = palette(scheme)
    dark = scheme_is_dark(scheme)
    page.theme_mode = ft.ThemeMode.DARK if dark else ft.ThemeMode.LIGHT
    page.bgcolor = colors["bg"]
    page.theme = ft.Theme(
        color_scheme_seed=colors["accent"],
        color_scheme=ft.ColorScheme(
            primary=colors["accent"],
            on_primary=colors["on_accent"],
            secondary=colors["accent_2"],
            surface=colors["surface"],
            on_surface=colors["ink"],
            outline=colors["line"],
            error=colors["danger"],
        ),
        visual_density=ft.VisualDensity.STANDARD,
    )
    return colors
