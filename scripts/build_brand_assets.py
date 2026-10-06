"""Render the code-defined OK monogram to application icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw
import shutil

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
O = [(70, 160), (112, 118), (220, 118), (248, 146), (248, 350), (206, 392), (98, 392), (70, 364)]
HOLE = [(120, 176), (136, 160), (198, 160), (198, 334), (182, 350), (120, 350)]
K = [(278, 118), (328, 118), (328, 218), (394, 118), (452, 118), (364, 254), (452, 392), (392, 392), (328, 290), (328, 392), (278, 392)]


def render(background=True, color='#43e8c3'):
    scale = 4
    image = Image.new('RGBA', (512*scale, 512*scale))
    draw = ImageDraw.Draw(image)
    if background:
        draw.rounded_rectangle((0, 0, 512*scale-1, 512*scale-1), radius=104*scale, fill='#10182a')
    for points, fill in [(O, color), (HOLE, '#10182a' if background else (0,0,0,0)), (K, '#a797ff' if background else color)]:
        draw.polygon([(x*scale,y*scale) for x,y in points], fill=fill)
    return image.resize((512,512), Image.Resampling.LANCZOS)


def main():
    icon = render()
    icon.save(ASSETS / 'icon.png')
    icon.save(ASSETS / 'icon.ico', sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
    icon.save(ASSETS / 'tray_ready.png')
    render(color='#f6c768').save(ASSETS / 'tray_starting.png')
    render(False).save(ASSETS / 'okdev_without_bg.png')
    render(False, '#ffffff').save(ASSETS / 'golden_okdev.png')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="104" fill="#10182a"/>'
    for pts,color in [(O,'#43e8c3'),(HOLE,'#10182a'),(K,'#a797ff')]:
        svg += '<polygon points="' + ' '.join(f'{x},{y}' for x,y in pts) + '" fill="'+color+'"/>'
    (ASSETS / 'okdev.svg').write_text(svg+'</svg>', encoding='utf-8')
    resources = ROOT / 'vendor/PenguLoader-1.1.6/loader/Resources'
    for name in ('icon.png','icon_okdev.png'):
        shutil.copy2(ASSETS/'icon.png', resources/name)
    shutil.copy2(ASSETS/'icon.ico',resources/'icon.ico')
    frontend = ROOT / 'vendor/PenguLoader-1.1.6/plugins/src/views/assets'
    shutil.copy2(ASSETS/'icon.png',frontend/'okdev.png')


if __name__ == '__main__':
    main()
