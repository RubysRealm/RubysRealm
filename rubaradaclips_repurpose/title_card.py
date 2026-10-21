"""Pixel-measured, individually centered typography for Rubarata videos."""
from functools import lru_cache
from itertools import combinations
from pathlib import Path
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont


FONT_PATH = Path(__file__).parent / 'assets' / 'fonts' / 'Inter-Variable.ttf'
STYLE = 'inter-centered-v1'
WIDTH, HEIGHT = 1080, 1920
CARD_WIDTH = 920
TEXT_WIDTH = 808


def display_title(value):
    # Decorative emoji have no glyph in the title font. Preserve the full title
    # text, punctuation and currency amounts instead of drawing missing-glyph boxes.
    text = unicodedata.normalize('NFC', str(value or ''))
    text = ''.join(c for c in text if c.isspace() or
                   unicodedata.category(c)[0] in 'LNP' or
                   unicodedata.category(c) in ('Mn', 'Mc', 'Sc'))
    text = text.replace('\ufe0f', '').replace("'", '\u2019')
    return re.sub(r'\s+', ' ', text).strip() or 'His Story'


@lru_cache(maxsize=24)
def font(size, weight):
    face = ImageFont.truetype(str(FONT_PATH), size)
    face.set_variation_by_axes([32, weight])
    return face


def balanced_lines(title, face, max_lines=3):
    """Choose whole-word lines by measured width, balancing their actual lengths."""
    words = title.split()
    widths = {}

    def width(text):
        if text not in widths:
            bounds = face.getbbox(text)
            widths[text] = bounds[2] - bounds[0]
        return widths[text]

    weak_endings = {'a', 'an', 'the', 'and', 'or', 'to', 'of', 'on', 'in', 'at', 'for'}
    for count in range(1, min(max_lines, len(words)) + 1):
        candidates = []
        for cuts in combinations(range(1, len(words)), count - 1):
            stops = (0, *cuts, len(words))
            lines = [' '.join(words[a:b]) for a, b in zip(stops, stops[1:])]
            lengths = [width(line) for line in lines]
            if max(lengths) > TEXT_WIDTH:
                continue
            mean = sum(lengths) / count
            score = sum((length - mean) ** 2 for length in lengths)
            score += 12000 * sum(line.split()[-1].lower() in weak_endings for line in lines[:-1])
            score += 18000 * sum(len(line.split()) == 1 for line in lines)
            candidates.append((score, lines))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
    return None


def create_title_card(title, index, total, picture_top, destination):
    if not 1 <= index <= total:
        raise ValueError('Invalid part label')
    title = display_title(title)
    for size in range(68, 41, -2):
        title_font = font(size, 750)
        lines = balanced_lines(title, title_font)
        if lines:
            break
    else:
        raise ValueError('The complete story title does not fit the title area')

    # Every line uses its own visible glyph bounds. This avoids the old renderer's
    # left-aligned second line inside an otherwise centered multi-line text block.
    bounds = [title_font.getbbox(line) for line in lines]
    line_height = max(box[3] - box[1] for box in bounds)
    line_gap = 16
    title_height = line_height * len(lines) + line_gap * (len(lines) - 1)
    padding, label_gap, pill_height = 42, 30, 52
    card_height = padding * 2 + title_height + label_gap + pill_height
    card_top = max(104, int(round(picture_top / 2 - card_height / 2)))
    if card_top + card_height > picture_top - 48:
        raise ValueError('The title card would overlap the original video')
    left = (WIDTH - CARD_WIDTH) // 2
    image = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((left, card_top, left + CARD_WIDTH, card_top + card_height),
                           radius=28, fill=(15, 17, 22, 218),
                           outline=(255, 255, 255, 28), width=1)
    y = card_top + padding
    placements = []
    for line, box in zip(lines, bounds):
        width, height = box[2] - box[0], box[3] - box[1]
        ink_left = (WIDTH - width) / 2
        ink_top = y + (line_height - height) / 2
        draw.text((ink_left - box[0], ink_top - box[1]), line,
                  font=title_font, fill=(250, 250, 252, 255))
        placements.append({'text': line, 'bounds': [ink_left, ink_top, ink_left + width, ink_top + height]})
        y += line_height + line_gap

    label = f'PART {index} OF {total}'
    display_label = label.replace(' ', '\u2002')
    label_font = font(28, 650)
    box = label_font.getbbox(display_label)
    label_width, label_height = box[2] - box[0], box[3] - box[1]
    pill_width = max(226, label_width + 52)
    pill_left = (WIDTH - pill_width) / 2
    pill_top = card_top + padding + title_height + label_gap
    draw.rounded_rectangle((pill_left, pill_top, pill_left + pill_width, pill_top + pill_height),
                           radius=pill_height / 2, fill=(242, 242, 244, 255))
    label_left, label_top = (WIDTH - label_width) / 2, pill_top + (pill_height - label_height) / 2
    draw.text((label_left - box[0], label_top - box[1]), display_label,
              font=label_font, fill=(21, 23, 29, 255))
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return {'style': STYLE, 'font': 'Inter', 'titleFontSize': size,
            'titleLines': placements, 'partLabel': label,
            'partBounds': [label_left, label_top, label_left + label_width, label_top + label_height],
            'cardBounds': [left, card_top, left + CARD_WIDTH, card_top + card_height]}
