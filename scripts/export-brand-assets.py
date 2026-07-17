#!/usr/bin/env python3
"""Export Palmeiras Agenda brand assets from source SVG files."""

from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web"
BRAND_DIR = ROOT / "apps" / "web" / "static" / "brand"
STATIC_DIR = ROOT / "apps" / "web" / "static"
ANDROID_RES_DIR = ROOT / "apps" / "android" / "app" / "src" / "main" / "res"
IOS_APP_ICON_DIR = ROOT / "apps" / "ios" / "PalmeirasAgenda" / "Assets.xcassets" / "AppIcon.appiconset"

PLATFORM_ICON_BG = (243, 245, 239, 255)

EXPORTS = [
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-192.png", 192, 192),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-192-v2.png", 192, 192),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-192-v3.png", 192, 192),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-192-v4.png", 192, 192),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-192-v5.png", 192, 192),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-512.png", 512, 512),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-512-v2.png", 512, 512),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-512-v3.png", 512, 512),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-512-v4.png", 512, 512),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-512-v5.png", 512, 512),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-icon-1024-v5.png", 1024, 1024),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-favicon.png", 200, 200),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-favicon-v2.png", 200, 200),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-favicon-v3.png", 200, 200),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-favicon-v4.png", 200, 200),
    ("palmeiras-agenda-mark.svg", "palmeiras-agenda-favicon-v5.png", 200, 200),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-16.png", 16, 16),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-16-v2.png", 16, 16),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-16-v3.png", 16, 16),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-16-v4.png", 16, 16),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-16-v5.png", 16, 16),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-32.png", 32, 32),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-32-v2.png", 32, 32),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-32-v3.png", 32, 32),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-32-v4.png", 32, 32),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-32-v5.png", 32, 32),
    ("palmeiras-agenda-mark-small.svg", "palmeiras-agenda-favicon-64.png", 64, 64),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v2.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v3.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v4.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v5.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v6.png", 1200, 630),
    ("palmeiras-agenda-social-card.svg", "palmeiras-agenda-social-card-v7.png", 1200, 630),
]

LEGACY_EXPORTS = [
    ("palmeiras-agenda-mark.svg", STATIC_DIR / "icon-192.png", 192, 192),
    ("palmeiras-agenda-mark.svg", STATIC_DIR / "icon-512.png", 512, 512),
    ("palmeiras-agenda-mark.svg", STATIC_DIR / "favicon.png", 200, 200),
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


def compose_platform_icon(logo_path: Path, out_path: Path, size: int, round_mask: bool = False) -> None:
    logo = Image.open(logo_path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), PLATFORM_ICON_BG)
    canvas.alpha_composite(logo)

    if round_mask:
        mask = Image.new("L", (size, size), 0)
        # Pillow is already a dependency here, so keep the mask generation simple.
        from PIL import ImageDraw

        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)
        canvas.putalpha(mask)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".png" and not round_mask:
        canvas.convert("RGB").save(out_path)
    else:
        canvas.save(out_path)
    print(f"exported {out_path.relative_to(ROOT)}")


def export_web_platform_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-icon-1024-v5.png"
    compose_platform_icon(latest_logo, BRAND_DIR / "palmeiras-agenda-apple-touch-icon-v5.png", 180)
    compose_platform_icon(latest_logo, BRAND_DIR / "palmeiras-agenda-maskable-512-v5.png", 512)
    compose_platform_icon(latest_logo, BRAND_DIR / "palmeiras-agenda-app-icon-1024-v5.png", 1024)

    favicon_source = Image.open(BRAND_DIR / "palmeiras-agenda-favicon-v5.png").convert("RGBA")
    for ico_path in (WEB_DIR / "favicon.ico", STATIC_DIR / "favicon.ico"):
        ico_path.parent.mkdir(parents=True, exist_ok=True)
        favicon_source.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        print(f"exported {ico_path.relative_to(ROOT)}")


def export_android_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-icon-1024-v5.png"
    for density_dir, size in ANDROID_LAUNCHER_SIZES.items():
        base = ANDROID_RES_DIR / density_dir
        compose_platform_icon(latest_logo, base / "ic_launcher.png", size)
        compose_platform_icon(latest_logo, base / "ic_launcher_round.png", size, round_mask=True)


def export_ios_icons() -> None:
    latest_logo = BRAND_DIR / "palmeiras-agenda-icon-1024-v5.png"
    for filename, size in IOS_APP_ICON_SPECS:
        compose_platform_icon(latest_logo, IOS_APP_ICON_DIR / filename, size)


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

        for source, out_path, width, height in LEGACY_EXPORTS:
            render_svg(page, BRAND_DIR / source, out_path, width, height)
            assert_transparency(out_path)
            print(f"exported {out_path.relative_to(ROOT)}")

        browser.close()

    export_web_platform_icons()
    export_android_icons()
    export_ios_icons()


if __name__ == "__main__":
    main()
