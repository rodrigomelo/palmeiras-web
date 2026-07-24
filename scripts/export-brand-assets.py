#!/usr/bin/env python3
"""Export Palmeiras Agenda application identity assets."""

import shutil

from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web"
STATIC_DIR = WEB_DIR / "static"
BRAND_DIR = ROOT / "apps" / "web" / "static" / "brand"
ANDROID_RES_DIR = ROOT / "apps" / "android" / "app" / "src" / "main" / "res"
IOS_APP_ICON_DIR = ROOT / "apps" / "ios" / "PalmeirasAgenda" / "Assets.xcassets" / "AppIcon.appiconset"
IOS_APP_LOGO_DIR = ROOT / "apps" / "ios" / "PalmeirasAgenda" / "Assets.xcassets" / "PalmeirasAgendaLogo.imageset"

BRAND_ASSET_VERSION = "v12"
WEB_HEADER_GRADIENT = (
    (4, 53, 34),
    (6, 78, 49),
    (17, 55, 38),
)
GOLD = (201, 154, 61)
APP_ICON_ART_HEIGHT = 0.81
SOLID_ALPHA_THRESHOLD = 64

EXPORTS = [
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-mark-1024-v12.png", 1024, 1024),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-mark-small-200-v12.png", 200, 200),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v12.png", 1200, 630),
]

ANDROID_LAUNCHER_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

IOS_APP_ICON_SPECS = [
    ("Icon-20.png", 20),
    ("Icon-20@2x.png", 40),
    ("Icon-20@3x.png", 60),
    ("Icon-29.png", 29),
    ("Icon-29@2x.png", 58),
    ("Icon-29@3x.png", 87),
    ("Icon-40.png", 40),
    ("Icon-40@2x.png", 80),
    ("Icon-40@3x.png", 120),
    ("Icon-60@2x.png", 120),
    ("Icon-60@3x.png", 180),
    ("Icon-76.png", 76),
    ("Icon-76@2x.png", 152),
    ("Icon-83.5@2x.png", 167),
    ("Icon-1024.png", 1024),
]


def render_svg(page, svg_path: Path, out_path: Path, width: int, height: int) -> None:
    svg = svg_path.read_text(encoding="utf-8")
    sized_svg = svg.replace(
        "<svg ",
        f'<svg style="display:block;width:{width}px;height:{height}px" ',
        1,
    )
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(
        f"""<!doctype html>
<html>
  <head>
    <style>
      html, body {{
        margin: 0;
        width: {width}px;
        height: {height}px;
        background: transparent;
      }}
      body {{
        overflow: hidden;
      }}
    </style>
  </head>
  <body>{sized_svg}</body>
</html>""",
        wait_until="load",
    )
    page.locator("svg").screenshot(path=str(out_path), omit_background=True)


def assert_transparency(path: Path) -> None:
    image = Image.open(path).convert("RGBA")
    alpha = image.getpixel((0, 0))[3]
    if alpha != 0:
        raise RuntimeError(f"{path} is expected to have a transparent top-left corner")


def assert_opaque_icon(path: Path) -> None:
    image = Image.open(path).convert("RGBA")
    if image.getextrema()[3] != (255, 255):
        raise RuntimeError(f"{path} must be fully opaque")


def interpolate_color(start: tuple[int, int, int], end: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(start, end))


def header_surface(size: int) -> Image.Image:
    """Render the same branded surface used behind the Web header logo."""
    strip = Image.new("RGB", (size * 2, 1))
    pixels = strip.load()
    for x in range(size * 2):
        progress = x / max(1, size * 2 - 1)
        if progress <= 0.54:
            color = interpolate_color(WEB_HEADER_GRADIENT[0], WEB_HEADER_GRADIENT[1], progress / 0.54)
        else:
            color = interpolate_color(WEB_HEADER_GRADIENT[1], WEB_HEADER_GRADIENT[2], (progress - 0.54) / 0.46)
        pixels[x, 0] = color
    surface = strip.transform(
        (size, size),
        Image.Transform.AFFINE,
        (1, 1, 0, 0, 0, 0),
        resample=Image.Resampling.BILINEAR,
    ).convert("RGBA")

    wash_alpha = Image.new("L", (size * 2, 1))
    wash_pixels = wash_alpha.load()
    for x in range(size * 2):
        progress = x / max(1, size * 2 - 1)
        wash_pixels[x, 0] = round(46 * max(0, 1 - progress / 0.38))
    wash_alpha = wash_alpha.transform(
        (size, size),
        Image.Transform.AFFINE,
        (1, 1, 0, 0, 0, 0),
        resample=Image.Resampling.BILINEAR,
    )
    wash = Image.new("RGBA", (size, size), (*GOLD, 0))
    wash.putalpha(wash_alpha)
    surface.alpha_composite(wash)

    grid = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(grid)
    grid_step = max(8, round(size * 68 / 368))
    for position in range(0, size + 1, grid_step):
        draw.line((position, 0, position, size), fill=(255, 255, 255, 9), width=max(1, round(size / 1024)))
        draw.line((0, position, size, position), fill=(255, 255, 255, 9), width=max(1, round(size / 1024)))
    surface.alpha_composite(grid)
    return surface


def fit_centered_logo(
    logo_path: Path,
    size: int,
    art_height: float,
) -> tuple[Image.Image, tuple[float, float]]:
    """Resize artwork and return the solid-art anchor, excluding its soft shadow."""
    logo = Image.open(logo_path).convert("RGBA")
    alpha = logo.getchannel("A")
    visible_bounds = alpha.getbbox()
    solid_bounds = alpha.point(
        lambda value: 255 if value >= SOLID_ALPHA_THRESHOLD else 0
    ).getbbox()
    if visible_bounds is None or solid_bounds is None:
        raise RuntimeError(f"{logo_path} has no visible artwork")
    logo = logo.crop(visible_bounds)
    solid_height = solid_bounds[3] - solid_bounds[1]
    scale = (size * art_height) / solid_height
    target_width = max(1, round(logo.width * scale))
    target_height = max(1, round(logo.height * scale))
    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
    solid_center = (
        ((solid_bounds[0] + solid_bounds[2]) / 2 - visible_bounds[0]) * scale,
        ((solid_bounds[1] + solid_bounds[3]) / 2 - visible_bounds[1]) * scale,
    )
    return logo, solid_center


def compose_platform_icon(
    logo_path: Path,
    out_path: Path,
    size: int,
    round_mask: bool = False,
    art_height: float = APP_ICON_ART_HEIGHT,
) -> None:
    logo, solid_center = fit_centered_logo(logo_path, size, art_height)
    canvas = header_surface(size)
    offset = (
        round(size / 2 - solid_center[0]),
        round(size / 2 - solid_center[1]),
    )
    canvas.alpha_composite(logo, offset)

    if round_mask:
        mask = Image.new("L", (size, size), 0)
        # Pillow is already a dependency here, so keep the mask generation simple.
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        canvas.putalpha(mask)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".png" and not round_mask:
        canvas.convert("RGB").save(out_path)
        assert_opaque_icon(out_path)
    else:
        canvas.save(out_path)
    print(f"exported {out_path.relative_to(ROOT)}")


def export_web_platform_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-mark-1024-v12.png"
    compose_platform_icon(latest_logo, BRAND_DIR / f"palmeiras-agenda-app-icon-192-{BRAND_ASSET_VERSION}.png", 192)
    compose_platform_icon(latest_logo, BRAND_DIR / f"palmeiras-agenda-app-icon-512-{BRAND_ASSET_VERSION}.png", 512)
    compose_platform_icon(latest_logo, BRAND_DIR / f"palmeiras-agenda-app-icon-1024-{BRAND_ASSET_VERSION}.png", 1024)
    compose_platform_icon(latest_logo, BRAND_DIR / f"palmeiras-agenda-apple-touch-icon-{BRAND_ASSET_VERSION}.png", 180)
    compose_platform_icon(
        latest_logo,
        BRAND_DIR / f"palmeiras-agenda-maskable-512-{BRAND_ASSET_VERSION}.png",
        512,
        art_height=0.68,
    )

    favicon_logo = BRAND_DIR / "palmeiras-agenda-mark-small-200-v12.png"
    compose_platform_icon(favicon_logo, BRAND_DIR / f"palmeiras-agenda-favicon-16-{BRAND_ASSET_VERSION}.png", 16)
    compose_platform_icon(favicon_logo, BRAND_DIR / f"palmeiras-agenda-favicon-32-{BRAND_ASSET_VERSION}.png", 32)
    compose_platform_icon(favicon_logo, BRAND_DIR / f"palmeiras-agenda-favicon-{BRAND_ASSET_VERSION}.png", 200)

    # Keep historical root/static paths aligned with the current installable icon.
    compose_platform_icon(latest_logo, STATIC_DIR / "icon-192.png", 192)
    compose_platform_icon(latest_logo, STATIC_DIR / "icon-512.png", 512)
    compose_platform_icon(favicon_logo, STATIC_DIR / "favicon.png", 200)

    favicon_source = Image.open(BRAND_DIR / f"palmeiras-agenda-favicon-{BRAND_ASSET_VERSION}.png").convert("RGBA")
    for ico_path in (WEB_DIR / "favicon.ico", STATIC_DIR / "favicon.ico"):
        ico_path.parent.mkdir(parents=True, exist_ok=True)
        favicon_source.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        print(f"exported {ico_path.relative_to(ROOT)}")


def export_android_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-mark-1024-v12.png"
    for density_dir, size in ANDROID_LAUNCHER_SIZES.items():
        base = ANDROID_RES_DIR / density_dir
        compose_platform_icon(latest_logo, base / "ic_launcher.png", size)
        compose_platform_icon(latest_logo, base / "ic_launcher_round.png", size, round_mask=True)

    adaptive_background = ANDROID_RES_DIR / "drawable-nodpi" / "ic_launcher_background.png"
    header_surface(432).convert("RGB").save(adaptive_background)
    assert_opaque_icon(adaptive_background)
    print(f"exported {adaptive_background.relative_to(ROOT)}")

    adaptive_foreground = Image.new("RGBA", (432, 432), (0, 0, 0, 0))
    logo, solid_center = fit_centered_logo(latest_logo, 432, 0.63)
    logo_offset = (round(216 - solid_center[0]), round(216 - solid_center[1]))
    adaptive_foreground.alpha_composite(logo, logo_offset)
    adaptive_path = ANDROID_RES_DIR / "drawable-nodpi" / "ic_launcher_foreground.png"
    adaptive_path.parent.mkdir(parents=True, exist_ok=True)
    adaptive_foreground.save(adaptive_path)
    assert_transparency(adaptive_path)
    print(f"exported {adaptive_path.relative_to(ROOT)}")

    interface_logo = ANDROID_RES_DIR / "drawable-nodpi" / "palmeiras_agenda_logo.png"
    shutil.copyfile(latest_logo, interface_logo)
    print(f"exported {interface_logo.relative_to(ROOT)}")

def export_ios_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-mark-1024-v12.png"
    for filename, size in IOS_APP_ICON_SPECS:
        compose_platform_icon(latest_logo, IOS_APP_ICON_DIR / filename, size)

    IOS_APP_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    interface_logo = IOS_APP_LOGO_DIR / "palmeiras-agenda-logo.png"
    shutil.copyfile(latest_logo, interface_logo)
    print(f"exported {interface_logo.relative_to(ROOT)}")

def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for source, output, width, height in EXPORTS:
            out_path = BRAND_DIR / output
            render_svg(page, BRAND_DIR / source, out_path, width, height)
            if width == height:
                assert_transparency(out_path)
            print(f"exported {out_path.relative_to(ROOT)}")

        browser.close()

    export_web_platform_icons()
    export_android_icons()
    export_ios_icons()


if __name__ == "__main__":
    main()
