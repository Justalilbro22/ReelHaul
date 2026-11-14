"""Generate the dark-branded Inno Setup wizard images (run after changing art)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).with_name("assets")
BG = (10, 12, 17)
CARD = (17, 21, 29)
TEXT = (238, 242, 249)
MUTED = (138, 147, 166)
DIM = (93, 102, 120)
ACCENT = (255, 46, 77)
ACCENT_DARK = (176, 10, 44)

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.FreeTypeFont) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def build_side() -> Image.Image:
    width, height = 328, 628
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # soft red glow from the top
    glow = Image.new("L", (width, height), 0)
    ImageDraw.Draw(glow).ellipse((-120, -140, width + 60, 260), fill=70)
    from PIL import ImageFilter

    glow = glow.filter(ImageFilter.GaussianBlur(60))
    red = Image.new("RGB", (width, height), ACCENT_DARK)
    img = Image.composite(red, img, glow)
    draw = ImageDraw.Draw(img)

    # bottom fade to black for depth
    fade = Image.new("L", (1, height))
    for y in range(height):
        fade.putpixel((0, y), max(0, int((y - height * 0.7) / (height * 0.3) * 120)))
    fade = fade.resize((width, height))
    black = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.composite(black, img, fade)
    draw = ImageDraw.Draw(img)

    logo = Image.open(ASSETS / "logo.png").resize((96, 96), Image.LANCZOS)
    img.paste(logo, (36, 48), logo)
    draw = ImageDraw.Draw(img)

    draw.text((36, 168), "ReelHaul", font=font(FONT_BOLD, 36), fill=TEXT)
    draw.text((37, 214), "Free 4K & 8K video", font=font(FONT_REG, 17), fill=MUTED)
    draw.text((37, 236), "and audio downloader", font=font(FONT_REG, 17), fill=MUTED)

    features = [
        "Up to 8K quality",
        "Playlists in one click",
        "MP3 at 320 kbps",
        "Subtitles & thumbnails",
        "SponsorBlock built in",
        "Works with 1000+ sites",
    ]
    y = 300
    for feature in features:
        draw.ellipse((39, y + 6, 47, y + 14), fill=ACCENT)
        draw.text((58, y), feature, font=font(FONT_REG, 16), fill=TEXT)
        y += 34

    draw.text((36, height - 44), "free  ·  no ads  ·  no limits", font=font(FONT_REG, 15), fill=DIM)
    return img


def build_small() -> Image.Image:
    size = (110, 116)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    logo = Image.open(ASSETS / "logo.png").resize(size, Image.LANCZOS)
    img.alpha_composite(logo)
    return img


def main() -> None:
    build_side().save(ASSETS / "installer_side.png")
    build_small().save(ASSETS / "installer_small.png")
    print("installer art written")


if __name__ == "__main__":
    main()
