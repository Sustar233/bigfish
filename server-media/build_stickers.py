"""Build an original vector-style fish sticker set from simple drawing shapes."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CAPTIONS = {'收到': '收到，大人！', '开心': '好耶！', '疑惑': '嗯？', '委屈': '鱼鱼委屈',
            '得意': '小c有两下子', '围观': '让我康康', '递报': '大人，报纸！', '困了': '困成鱼干'}


def build(directory):
    out = Path(directory)
    out.mkdir(exist_ok=True)
    manifest = {}
    font_path = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
    for index, (name, caption) in enumerate(CAPTIONS.items()):
        im = Image.new('RGB', (512, 512), '#fffaf0')
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((12, 12, 500, 500), radius=45, fill='#f0f5e8', outline='#244d49', width=7)
        d.ellipse((90, 368, 428, 400), fill='#d7e5d1')
        d.polygon([(370, 245), (465, 165), (450, 340), (370, 290)], fill='#eeb15e', outline='#244d49', width=7)
        d.ellipse((66, 142, 407, 373), fill='#83c8bc', outline='#244d49', width=7)
        d.polygon([(224, 151), (263, 100), (309, 151)], fill='#eeb15e', outline='#244d49', width=6)
        d.arc((207, 225, 300, 340), 80, 260, fill='#244d49', width=6)
        if name == '困了':
            d.line([(113, 239), (160, 239)], fill='#244d49', width=7)
            d.line([(192, 239), (239, 239)], fill='#244d49', width=7)
            d.text((330, 80), 'Z z', font=ImageFont.truetype(font_path, 42), fill='#244d49')
        elif name == '得意':
            d.rounded_rectangle((100, 214, 167, 253), radius=10, fill='#244d49')
            d.rounded_rectangle((184, 214, 251, 253), radius=10, fill='#244d49')
            d.line([(160, 224), (190, 224)], fill='#244d49', width=7)
        elif name == '开心':
            d.arc((112, 216, 161, 259), 190, 345, fill='#244d49', width=7)
            d.arc((190, 216, 239, 259), 190, 345, fill='#244d49', width=7)
        else:
            for x in (137, 214):
                d.ellipse((x-10, 221, x+10, 245), fill='#244d49')
        d.ellipse((92, 264, 126, 281), fill='#edaaa0')
        if name == '委屈':
            d.polygon([(135, 253), (126, 285), (145, 285)], fill='#7baed9')
            d.arc((157, 282, 192, 310), 190, 345, fill='#244d49', width=5)
        elif name == '疑惑':
            d.ellipse((168, 280, 189, 303), outline='#244d49', width=4)
            d.text((359, 61), '?', font=ImageFont.truetype(font_path, 70), fill='#d7803a')
        else:
            d.arc((155, 266, 195, 300), 5, 175, fill='#244d49', width=5)
        if name == '递报':
            d.rounded_rectangle((259, 276, 403, 385), radius=7, fill='white', outline='#244d49', width=5)
            d.text((279, 282), '鱼塘早报', font=ImageFont.truetype(font_path, 22), fill='#244d49')
            for y in (321, 340, 359): d.line((279, y, 384, y), fill='#a2b5a8', width=4)
        font = ImageFont.truetype(font_path, 45 if len(caption) <= 6 else 39)
        box = d.textbbox((0, 0), caption, font=font)
        d.text(((512-(box[2]-box[0]))/2, 415), caption, font=font, fill='#244d49')
        filename = 'fish-' + str(index) + '.png'
        im.save(out/filename, optimize=True)
        manifest[name] = filename
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print('Built', len(manifest), 'original fish stickers')


if __name__ == '__main__':
    import sys
    build(sys.argv[1])
