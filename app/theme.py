
"""配色方案与 Flet 主题应用。

每种方案自带浅/深属性；布局间距通过密度单位 ``u()`` 换算。
"""

import flet as ft

# 密度单位。布局优先用 expand / col；统一用 u()，避免到处写死 px。
U = 8.0


def u(n: float) -> float:
    """把密度单位换成像素值。
    :param n: 密度倍数
    :return: ``n * U``
    """
    return n * U


ColorSchemeId = str


def _scheme(*, dark: bool, **colors: str) -> dict[str, str | bool]:
    """构造一份配色字典。
    :param dark: 该方案是否按深色主题应用
    :param colors: 语义色名到十六进制颜色的映射
    :return: 含 ``dark`` 标记的配色表
    """
    return {"dark": dark, **colors}


# 每种配色自身就是浅色或深色，没有单独的深色模式开关。
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
    """把用户选择规范成已知方案 id。
    :param scheme: 配色 id；未知或为空则用默认
    :return: ``SCHEMES`` 中的键
    """
    if scheme in SCHEMES:
        return scheme
    return DEFAULT_SCHEME


def scheme_is_dark(scheme: str | None) -> bool:
    """判断配色是否应按深色主题应用。
    :param scheme: 配色 id
    :return: 深色则为 True
    """
    return bool(SCHEMES[resolve_scheme(scheme)].get("dark"))


def palette(scheme: str | None = None) -> dict[str, str]:
    """取出方案中的语义色（不含 dark 标记）。
    :param scheme: 配色 id
    :return: 颜色键到十六进制字符串的映射
    """
    family = SCHEMES[resolve_scheme(scheme)]
    return {key: str(family[key]) for key in SCHEME_COLOR_KEYS}


def apply_theme(page: ft.Page, scheme: str | None = None) -> dict[str, str]:
    """把配色应用到 Flet 页面并返回调色板。
    :param page: Flet 页面
    :param scheme: 配色 id
    :return: 语义色字典，供控件直接使用
    """
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
