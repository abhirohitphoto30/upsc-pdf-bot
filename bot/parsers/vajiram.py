"""
Vajiram & Ravi 100Q parser.
Requires two PDFs: Test Booklet + Solutions/Answer Key.
Handles 2-column spatial layout in test PDF.
"""
import re
import pdfplumber
from io import BytesIO

# Only match clear header/footer lines — DO NOT filter content words
NOISE_VAJ = [
    re.compile(r'VAJIRAM\s*(&|AND)\s*RAVI', re.I),
    re.compile(r'PRELIMS\s*TEST\s*SERIES', re.I),
    re.compile(r'FULL\s*LENGTH\s*TEST', re.I),
    re.compile(r'MAXIMUM\s*MARKS\s*:', re.I),
    re.compile(r'TIME\s*ALLOWED\s*:', re.I),
    re.compile(r'DO\s*NOT\s*OPEN\s*THIS', re.I),
    re.compile(r'COMMENCEMENT\s*OF\s*THE\s*EXAMINATION', re.I),
    re.compile(r"CANDIDATE.S\s*RESPONSIBILITY", re.I),
    re.compile(r'ROLL\s*NUMBER\s*:', re.I),
    re.compile(r'OMR\s*ANSWER\s*SHEET', re.I),
    re.compile(r'PENALTY\s*FOR\s*WRONG\s*ANSWER', re.I),
    re.compile(r'WRONG\s*ANSWERS?\s*MARKED', re.I),
    re.compile(r'GS\s*TEST\s*[-–]\s*\d+\s*[-–]', re.I),   # "GS Test - 11 -"
    re.compile(r'PowerUp\s*Prelims', re.I),
    re.compile(r'UNPRINTED\s*OR\s*TORN', re.I),
    re.compile(r'ALTERNATIVES?\s*FOR\s*THE\s*ANSWER', re.I),
    re.compile(r'QUESTION\s*IS\s*LEFT\s*BLANK', re.I),
    re.compile(r'^\s*\d{1,3}\s*$'),   # standalone page number only
]

ROMAN_MAP = {
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
    'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
    'XI': 11, 'XII': 12
}

NEW_LINE_RE = [
    re.compile(r'^\d{1,2}\.\s+\S'),
    re.compile(r'^Statement\s+[IVXLC]+\s*:', re.I),
    re.compile(
        r'^(Which|How\s+many|What|Select|Arrange|In\s+how|Who\b|'
        r'Where\b|Among\s+|Identify|Of\s+the|With\s+reference|'
        r'With\s+regard|Consider|Regarding|As\s+per|According\s+to|'
        r'In\s+which\s+of)', re.I
    ),
]


def is_noise_vaj(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    return any(p.search(s) for p in NOISE_VAJ)


def normalize_roman(line: str) -> str:
    def _rep(m):
        key = m.group(1).upper()
        n = ROMAN_MAP.get(key)
        return (str(n) + '. ') if n else m.group(0)
    return re.sub(r'^\s*(I{1,3}|IV|V?I{0,3}|IX|XI{0,3})\.\s+', _rep, line)


# ── PDF extraction ─────────────────────────────────────────────────────────────

def _extract_pages(pdf_bytes: bytes) -> list:
    pages = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            items = [{'text': w['text'], 'x': w['x0'], 'y': w['top']} for w in words]
            pages.append({
                'items': items,
                'width': float(page.width),
                'height': float(page.height),
                'page_id': page.page_number
            })
    return pages


def _items_to_lines(items: list, y_tol: int = 4) -> list:
    if not items:
        return []
    srt = sorted(items, key=lambda t: (t['y'], t['x']))
    buckets, cur = [], [srt[0]]
    for tok in srt[1:]:
        if abs(tok['y'] - cur[0]['y']) <= y_tol:
            cur.append(tok)
        else:
            buckets.append(cur)
            cur = [tok]
    buckets.append(cur)
    result = []
    for bkt in buckets:
        bkt.sort(key=lambda t: t['x'])
        txt = ' '.join(t['text'] for t in bkt).strip()
        if txt:
            result.append({'y': bkt[0]['y'], 'x': min(t['x'] for t in bkt), 'text': txt})
    return result


def _is_content_page(lines: list) -> bool:
    """Return True if page has actual question content (has (a)/(b) options)."""
    combined = ' '.join(l['text'] for l in lines)
    return bool(re.search(r'\(\s*[abcd]\s*\)', combined, re.I))


# ── Test booklet parser ────────────────────────────────────────────────────────

def _parse_test_booklet(pages: list) -> dict:
    q_map = {}
    for page in pages:
        all_lines = _items_to_lines(page['items'])
        filtered = [l for l in all_lines if not is_noise_vaj(l['text'])]

        if not _is_content_page(filtered):
            continue

        mid_x = page['width'] / 2
        left_items = [t for t in page['items'] if t['x'] < mid_x - 15]
        right_items = [t for t in page['items'] if t['x'] >= mid_x - 15]
        has_two_cols = len(left_items) > 6 and len(right_items) > 6

        if has_two_cols:
            left_lines = [l for l in _items_to_lines(left_items) if not is_noise_vaj(l['text'])]
            right_lines = [l for l in _items_to_lines(right_items) if not is_noise_vaj(l['text'])]
            text = ('\n'.join(l['text'] for l in left_lines) + '\n' +
                    '\n'.join(l['text'] for l in right_lines))
        else:
            text = '\n'.join(l['text'] for l in filtered)

        _parse_text_into_map(text, q_map)

    return q_map


def _parse_text_into_map(text: str, q_map: dict):
    """State-machine parser: extract question body + options from raw text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    active_id = None
    body = []
    opts = []
    in_opts = False

    def flush():
        nonlocal active_id, body, opts, in_opts
        if active_id is None:
            return
        if len(opts) >= 2:
            if active_id not in q_map or len(opts) > len(q_map[active_id]['options']):
                q_map[active_id] = {
                    'id': active_id,
                    'body_lines': list(body),
                    'options': list(opts)
                }
        active_id = None
        body = []
        opts = []
        in_opts = False

    OPT_RE = re.compile(r'^\s*\(([a-d])\)\s+(.+)$', re.I)
    # Question line: "N. text..." — use \s+ to handle any spacing
    Q_RE = re.compile(r'^(\d{1,3})\.\s+(.+)$')

    for line in lines:
        opt_m = OPT_RE.match(line)
        if opt_m and active_id is not None:
            in_opts = True
            opts.append({'letter': opt_m.group(1).lower(), 'text': opt_m.group(2).strip()})
            continue

        q_m = Q_RE.match(line)
        if q_m:
            num = int(q_m.group(1))
            if 1 <= num <= 100:
                # Decide: new question OR statement inside current question body?
                # Rule: treat as statement if we're in body (not opts), have body lines,
                # AND num is small enough to plausibly be a list item (<= 10),
                # AND it's NOT the expected next question (num != active_id + 1)
                # EXCEPTION: if we have no body yet, always start new question
                is_stmt = (
                    active_id is not None and
                    not in_opts and
                    len(body) > 0 and
                    num <= 10 and
                    num != active_id + 1
                )
                # Extra check: if num > active_id, very likely new question
                # (don't let large table row numbers bleed through)
                if is_stmt and num > active_id:
                    # Only trust it's internal if num is small (1-6 typical for statements)
                    is_stmt = num <= 6

                if not is_stmt:
                    flush()
                    active_id = num
                    body = [q_m.group(2).strip()]
                    opts = []
                    in_opts = False
                    continue
                # else: fall through and add to body

        if in_opts and opts and active_id is not None:
            if not OPT_RE.match(line):
                opts[-1]['text'] += ' ' + line
            continue

        if active_id is not None and not in_opts:
            body.append(line)

    flush()


# ── Solutions parser ───────────────────────────────────────────────────────────

def _parse_solutions(pages: list) -> tuple:
    answers = {}
    explanations = {}

    all_text = '\n'.join(
        '\n'.join(l['text'] for l in _items_to_lines(p['items'])
                  if not is_noise_vaj(l['text']))
        for p in pages
    )

    # Answer key: "N. (letter)" pattern
    for m in re.finditer(r'\b(\d{1,3})\.\s*\(([a-d])\)', all_text, re.I):
        num = int(m.group(1))
        if 1 <= num <= 100:
            answers[num] = m.group(2).lower()

    # Explanations: split on "QN." blocks (Vajiram solution format)
    splits = []
    for m in re.finditer(r'\nQ(\d{1,3})\.\s*\n', all_text):
        splits.append({'num': int(m.group(1)), 'start': m.end()})

    if not splits:
        # Fallback: try "QN." without blank line requirement
        for m in re.finditer(r'\bQ(\d{1,3})\.\s*\n', all_text):
            splits.append({'num': int(m.group(1)), 'start': m.end()})

    for i, sp in enumerate(splits):
        end = splits[i + 1]['start'] if i + 1 < len(splits) else len(all_text)
        raw = all_text[sp['start']:end]
        explanations[sp['num']] = _clean_expl(raw)

    return answers, explanations


def _clean_expl(raw: str) -> str:
    t = raw
    t = re.sub(r'Therefore[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'So[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'Therefore[,\s]+the\s*correct\s*answer[^\n]*', '', t, flags=re.I)
    t = re.sub(r'Relevance\s*:[^\n]*', '', t, flags=re.I)
    t = re.sub(r'(?:Source|Ref|Reference)\s*:[^\n]*', '', t, flags=re.I | re.M)
    t = re.sub(r'^[\s]*[●○•▪◆▸▹→\-–—]+\s*', '', t, flags=re.M)
    t = re.sub(r'^Q\d{1,3}\.\s*', '', t, flags=re.M)
    lines = [l.strip() for l in t.split('\n') if len(l.strip()) > 2]
    flat = re.sub(r'\s{2,}', ' ', ' '.join(lines))
    return re.sub(r'\.\s*\.', '.', flat).strip()


# ── Body line compilation ──────────────────────────────────────────────────────

def _compile_body(raw_lines: list) -> list:
    """Join continuation lines and normalize Roman numerals."""
    normalized = [normalize_roman(l.strip()) for l in raw_lines if l.strip()]
    if not normalized:
        return []
    out, current = [], ''
    for i, line in enumerate(normalized):
        starts_new = i == 0 or any(p.match(line) for p in NEW_LINE_RE)
        if starts_new:
            if current:
                out.append(re.sub(r'\s{2,}', ' ', current).strip())
            current = line
        else:
            current = re.sub(r'\s{2,}', ' ', current + ' ' + line)
    if current:
        out.append(re.sub(r'\s{2,}', ' ', current).strip())
    return out


def _unpack_options(options: list) -> list:
    """Extract clean option text from parsed (letter, text) pairs."""
    unified = ' '.join(f'({o["letter"]}) {o["text"]}' for o in options)
    result = []
    for i, letter in enumerate(['a', 'b', 'c', 'd']):
        next_letter = chr(ord(letter) + 1) if letter != 'd' else None
        if next_letter:
            pat = rf'\({re.escape(letter)}\)\s*([\s\S]*?)(?=\s*\({re.escape(next_letter)}\)|$)'
        else:
            pat = rf'\({re.escape(letter)}\)\s*([\s\S]*)$'
        m = re.search(pat, unified, re.I)
        txt = m.group(1).strip() if m else ''
        txt = re.sub(r'^\s*\(?[a-d]\)?\s*\.?\s*', '', txt, flags=re.I).strip()
        result.append({'letter': letter, 'text': txt or f'Option {letter.upper()}'})
    return result


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_vajiram(test_pdf_bytes: bytes, sol_pdf_bytes: bytes) -> str:
    """Parse Vajiram & Ravi test + solution PDFs. Returns formatted text."""
    test_pages = _extract_pages(test_pdf_bytes)
    q_map = _parse_test_booklet(test_pages)

    sol_pages = _extract_pages(sol_pdf_bytes)
    answers, explanations = _parse_solutions(sol_pages)

    output = []
    for num in sorted(q_map.keys()):
        q = q_map[num]
        ans = answers.get(num, '')
        expl = explanations.get(num, '').strip()

        body = _compile_body(q['body_lines'])
        output.append(f'Q{num}. {body[0]}' if body else f'Q{num}.')
        for line in body[1:]:
            output.append(line)
        output.append('😂')

        for opt in _unpack_options(q['options']):
            mark = ' ✅' if ans and opt['letter'] == ans else ''
            output.append(opt['text'] + mark)

        output.append(f'Ex: {expl}' if expl else f'Ex: [Explanation not extracted for Q{num}]')
        output.append('')

    return '\n'.join(output)
