"""
Vajiram & Ravi 100Q parser.
Requires two PDFs: Test Booklet + Solutions/Answer Key.
Handles 2-column spatial layout in test PDF.
"""
import re
import pdfplumber
from io import BytesIO

NOISE_VAJ = [
    re.compile(r'VAJIRAM\s*(&|AND)\s*RAVI', re.I),
    re.compile(r'PRELIMS\s*TEST\s*SERIES', re.I),
    re.compile(r'FULL\s*LENGTH\s*TEST', re.I),
    re.compile(r'TEST\s*BOOKLET', re.I),
    re.compile(r'MAXIMUM\s*MARKS', re.I),
    re.compile(r'TIME\s*ALLOWED', re.I),
    re.compile(r'DO\s*NOT\s*OPEN', re.I),
    re.compile(r'COMMENCEMENT\s*OF\s*THE\s*EXAMINATION', re.I),
    re.compile(r'UNPRINTED\s*OR\s*TORN', re.I),
    re.compile(r"CANDIDATE'S\s*RESPONSIBILITY", re.I),
    re.compile(r'ROLL\s*NUMBER', re.I),
    re.compile(r'OMR\s*ANSWER', re.I),
    re.compile(r'ANSWER\s*SHEET', re.I),
    re.compile(r'PENALTY\s*FOR\s*WRONG', re.I),
    re.compile(r'WRONG\s*ANSWERS\s*MARKED', re.I),
    re.compile(r'ALTERNATIVES\s*FOR\s*THE\s*ANSWER', re.I),
    re.compile(r'QUESTION\s*IS\s*LEFT\s*BLANK', re.I),
    re.compile(r'GS\s*TEST\s*[-–]\s*\d+', re.I),
    re.compile(r'POWERUP\s*PRELIMS', re.I),
    re.compile(r'PowerUp Prelims', re.I),
    re.compile(r'Ancient and Medieval History', re.I),
    re.compile(r'V\d{4}', re.I),
    re.compile(r'^\d{1,3}$'),
    re.compile(r'Knowledge Box', re.I),
]

ROMAN_MAP_VAJ = {
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
    'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
    'XI': 11, 'XII': 12
}

NEW_LINE_PATTERNS = [
    re.compile(r'^\d{1,2}\.\s+\S'),
    re.compile(r'^Statement\s+[IVXLC]+\s*:', re.I),
    re.compile(
        r'^(Which|How\s+many|How\s+|What|Select|Arrange|In\s+how|Who\s+|'
        r'Where\s+|Among\s+|Identify|Of\s+the|With\s+reference|With\s+regard|'
        r'Consider|Regarding|As\s+per|According\s+to|In\s+which\s+of)', re.I
    ),
]


def is_noise_vaj(line):
    return any(p.search(line.strip()) for p in NOISE_VAJ)


def normalize_roman(line):
    def replace_roman(m):
        r = m.group(1).upper()
        n = ROMAN_MAP_VAJ.get(r)
        return str(n) + '. ' if n else m.group(0)
    return re.sub(r'^\s*(I{1,3}|IV|V?I{0,3}|IX|XI{0,3})\.\s+', replace_roman, line)


def extract_pages_with_coords(pdf_bytes):
    pages_data = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            items = [{
                'text': w['text'],
                'x': w['x0'],
                'y': w['top'],
                'w': w['x1'] - w['x0']
            } for w in words]
            pages_data.append({
                'items': items,
                'width': float(page.width),
                'height': float(page.height),
                'page_id': page.page_number
            })
    return pages_data


def consolidate_tokens_to_lines(items, y_tol=4):
    if not items:
        return []
    sorted_items = sorted(items, key=lambda t: (t['y'], t['x']))
    row_buckets = []
    working_row = [sorted_items[0]]
    for item in sorted_items[1:]:
        if abs(item['y'] - working_row[0]['y']) <= y_tol:
            working_row.append(item)
        else:
            row_buckets.append(working_row)
            working_row = [item]
    row_buckets.append(working_row)
    result = []
    for bucket in row_buckets:
        bucket.sort(key=lambda t: t['x'])
        text = ' '.join(t['text'] for t in bucket).strip()
        if text:
            result.append({
                'y': bucket[0]['y'],
                'x': min(t['x'] for t in bucket),
                'text': text
            })
    return result


def is_cover_or_instructions(lines):
    combined = ' '.join(l['text'] for l in lines)
    return not (re.search(r'\(\s*[abcd]\s*\)', combined, re.I))


def parse_test_booklet_structure(pages_data):
    q_map = {}
    for page in pages_data:
        all_lines = consolidate_tokens_to_lines(page['items'])
        filtered = [l for l in all_lines if not is_noise_vaj(l['text'])]
        if is_cover_or_instructions(filtered):
            continue

        mid_x = page['width'] / 2
        left_items = [t for t in page['items'] if t['x'] < mid_x - 15]
        right_items = [t for t in page['items'] if t['x'] >= mid_x - 15]
        has_two_cols = len(left_items) > 6 and len(right_items) > 6

        if has_two_cols:
            left_lines = [l for l in consolidate_tokens_to_lines(left_items)
                          if not is_noise_vaj(l['text'])]
            right_lines = [l for l in consolidate_tokens_to_lines(right_items)
                           if not is_noise_vaj(l['text'])]
            text = ('\n'.join(l['text'] for l in left_lines) + '\n' +
                    '\n'.join(l['text'] for l in right_lines))
        else:
            text = '\n'.join(l['text'] for l in filtered)

        _parse_test_text_into_map(text, q_map)

    return q_map


def _parse_test_text_into_map(text, q_map):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    active_q_id = None
    body_lines = []
    options = []
    in_options = False

    def flush():
        nonlocal active_q_id, body_lines, options, in_options
        if active_q_id is None:
            return
        if len(options) >= 2:
            if (active_q_id not in q_map or
                    len(options) > len(q_map[active_q_id]['options'])):
                q_map[active_q_id] = {
                    'id': active_q_id,
                    'body_lines': list(body_lines),
                    'options': list(options)
                }
        active_q_id = None
        body_lines = []
        options = []
        in_options = False

    for line in lines:
        opt_m = re.match(r'^\s*\(([a-d])\)\s+(.+)$', line, re.I)
        if opt_m and active_q_id is not None:
            in_options = True
            options.append({
                'letter': opt_m.group(1).lower(),
                'text': opt_m.group(2).strip()
            })
            continue

        q_m = re.match(r'^(\d{1,3})\.\s{1,6}(.+)$', line)
        if q_m:
            num = int(q_m.group(1))
            if 1 <= num <= 100:
                is_internal_stmt = (
                    active_q_id is not None and not in_options and
                    num != active_q_id + 1 and num <= 6
                )
                if not is_internal_stmt:
                    flush()
                    active_q_id = num
                    body_lines = [q_m.group(2).strip()]
                    options = []
                    in_options = False
                    continue

        if in_options and options and active_q_id is not None:
            if not re.match(r'^\s*\(([a-d])\)', line, re.I):
                options[-1]['text'] += ' ' + line
            continue

        if active_q_id is not None and not in_options:
            body_lines.append(line)

    flush()


def parse_solutions_booklet(pages_data):
    answers = {}
    explanations = {}

    all_text_parts = []
    for page in pages_data:
        lines = [l['text'] for l in consolidate_tokens_to_lines(page['items'])
                 if not is_noise_vaj(l['text'])]
        all_text_parts.append('\n'.join(lines))
    all_text = '\n'.join(all_text_parts)

    for m in re.finditer(r'\b(\d{1,3})\.\s*\(([a-d])\)', all_text, re.I):
        num = int(m.group(1))
        if 1 <= num <= 100:
            answers[num] = m.group(2).lower()

    splits = []
    for m in re.finditer(r'\nQ(\d{1,3})\.\s*\n', all_text):
        splits.append({'num': int(m.group(1)), 'start': m.end()})

    for i, split in enumerate(splits):
        end = splits[i + 1]['start'] if i + 1 < len(splits) else len(all_text)
        raw = all_text[split['start']:end]
        explanations[split['num']] = _sanitize_explanation_vaj(raw)

    return answers, explanations


def _sanitize_explanation_vaj(raw):
    t = raw
    t = re.sub(r'Therefore[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'So[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'Therefore[,\s]+the\s*correct\s*answer[^\n]*', '', t, flags=re.I)
    t = re.sub(r'Relevance\s*:[^\n]*', '', t, flags=re.I)
    t = re.sub(r'(?:Source|Ref|Reference)\s*:[^\n]*', '', t, flags=re.I | re.M)
    t = re.sub(r'^[\s]*[●○•▪◆▸▹→\-–—]+\s*', '', t, flags=re.M)
    t = re.sub(r'^\s+[●○•▪]+\s*', ' ', t, flags=re.M)
    t = re.sub(r'^Q\d{1,3}\.\s*', '', t, flags=re.M)
    lines = [l.strip() for l in t.split('\n') if len(l.strip()) > 2]
    flat = ' '.join(lines)
    flat = re.sub(r'\s{2,}', ' ', flat)
    flat = re.sub(r'\.\s*\.', '.', flat)
    return flat.strip()


def _compile_body_lines(raw_lines):
    normalized = [normalize_roman(l.strip()) for l in raw_lines if l.strip()]
    if not normalized:
        return []
    output = []
    current = ''
    for i, line in enumerate(normalized):
        is_new = i == 0 or any(p.match(line) for p in NEW_LINE_PATTERNS)
        if is_new:
            if current:
                output.append(re.sub(r'\s{2,}', ' ', current).strip())
            current = line
        else:
            current = re.sub(r'\s{2,}', ' ', current + ' ' + line)
    if current:
        output.append(re.sub(r'\s{2,}', ' ', current).strip())
    return output


def _unpack_options(options):
    unified = ' '.join(f'({o["letter"]}) {o["text"]}' for o in options)
    result = []
    for letter in ['a', 'b', 'c', 'd']:
        next_letter = chr(ord(letter) + 1)
        if letter != 'd':
            pattern = rf'\({letter}\)\s*([\s\S]*?)(?=\s*\({next_letter}\)|$)'
        else:
            pattern = rf'\({letter}\)\s*([\s\S]*)$'
        m = re.search(pattern, unified, re.I)
        text = m.group(1).strip() if m else ''
        text = re.sub(r'^\s*\(?[a-d]\)?\s*\.?\s*', '', text, flags=re.I).strip()
        if not text:
            text = f'Option {letter.upper()}'
        result.append({'letter': letter, 'text': text})
    return result


def parse_vajiram(test_pdf_bytes: bytes, sol_pdf_bytes: bytes) -> str:
    """
    Parse Vajiram & Ravi test + solution PDFs.
    Returns formatted text string.
    """
    test_pages = extract_pages_with_coords(test_pdf_bytes)
    q_map = parse_test_booklet_structure(test_pages)

    sol_pages = extract_pages_with_coords(sol_pdf_bytes)
    answers, explanations = parse_solutions_booklet(sol_pages)

    output = []
    for num in sorted(q_map.keys()):
        q = q_map[num]
        ans_letter = answers.get(num, '')
        expl = explanations.get(num, '').strip()

        body = _compile_body_lines(q['body_lines'])
        first_line = body[0] if body else ''
        output.append(f'Q{num}. {first_line}')
        for line in body[1:]:
            output.append(line)
        output.append('😂')

        unpacked = _unpack_options(q['options'])
        for opt in unpacked:
            mark = ' ✅' if ans_letter and opt['letter'] == ans_letter else ''
            output.append(opt['text'] + mark)

        output.append(f'Ex: {expl}' if expl else f'Ex: [Explanation not extracted for Q{num}]')
        output.append('')

    return '\n'.join(output)
