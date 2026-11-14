"""Generate TubeGrab's icon and logo (run once, or after changing the design)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).with_name("assets")
ASSETS.mkdir(exist_ok=True)

S = 1024
TOP = (255, 58, 82)
BOTTOM = (176, 10, 44)


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius, fill=255)
    return mask


def build_icon() -> Image.Image:
    # vertical gradient
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel(
            (0, y),
            (
                round(TOP[0] + (BOTTOM[0] - TOP[0]) * t),
                round(TOP[1] + (BOTTOM[1] - TOP[1]) * t),
                round(TOP[2] + (BOTTOM[2] - TOP[2]) * t),
            ),
        )
    img = grad.resize((S, S))

    # soft top-left light
    glow = Image.new("L", (S, S), 0)
    ImageDraw.Draw(glow).ellipse((-S * 0.35, -S * 0.55, S * 0.95, S * 0.55), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    white = Image.new("RGB", (S, S), (255, 255, 255))
    img = Image.composite(white, img, glow.point(lambda v: v // 3))

    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(img, (0, 0), rounded_mask(S, 230))

    d = ImageDraw.Draw(icon)
    # download arrow
    d.rounded_rectangle((450, 190, 574, 560), radius=62, fill=(255, 255, 255, 255))
    d.polygon([(300, 500), (724, 500), (512, 744)], fill=(255, 255, 255, 255))
    # tray
    d.rounded_rectangle((300, 790, 724, 856), radius=33, fill=(255, 255, 255, 255))
    return icon


def main() -> None:
    icon = build_icon()
    icon.save(ASSETS / "logo.png")
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon_256.png")
    icon.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
