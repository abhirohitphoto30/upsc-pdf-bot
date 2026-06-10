"""
VisionIAS 100Q parser.
Requires two PDFs: Test Booklet + Answer Key / Solutions.
Answer markers in solution PDF: "Q N. Letter" (uppercase) format.
"""
import re
import pdfplumber
from io import BytesIO

# Only match clear header/footer lines — keep question/explanation content intact
NOISE_VISION = [
    re.compile(r'www\.visionias\.in', re.I),
    re.compile(r'©\s*Vision', re.I),
    re.compile(r'^\s*Test Booklet Series\s*$', re.I),
    re.compile(r'DO NOT OPEN THIS BOOKLET', re.I),
    re.compile(r'IMMEDIATELY AFTER THE COMMENCEMENT', re.I),
    re.compile(r'CANDIDATE.*RESPONSIBILITY', re.I),
    re.compile(r'ENCODE CLEARLY', re.I),
    re.compile(r'You have to enter your Roll Number', re.I),
    re.compile(r'This Test Booklet contains', re.I),
    re.compile(r'You have to mark all your responses', re.I),
    re.compile(r'All items carry equal marks', re.I),
    re.compile(r'Before you proceed to mark', re.I),
    re.compile(r'After you have completed', re.I),
    re.compile(r'Sheet for rough work', re.I),
    re.compile(r'ANSWERS\s*[&AND]+\s*EXPLANATIONS', re.I),
    re.compile(r'^\s*Time Allowed\s*:', re.I),
    re.compile(r'^\s*Maximum Marks\s*:', re.I),
    re.compile(r'^\s*\d{1,3}\s*$'),   # standalone page numbers
]

OPT_RE = re.compile(r'^\(([a-d])\)\s+(.+)$', re.I)
QNUM_RE = re.compile(r'^(\d{1,3})\.\s+(.+)$')

# Sub-item line starters in question body
NUM_STMT_RE = re.compile(r'^\d+\.\s')
STEM_RE = re.compile(
    r'^(Which|How\s+many|Select|In\s+how\s+many|Of\s+the\s+above|'
    r'From\s+the\s+above|Based\s+on)', re.I
)
MATCH_HDR_RE = re.compile(r'\s{3,}')


def is_hf(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    return any(p.search(s) for p in NOISE_VISION)


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
                'page_num': page.page_number
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


def _page_to_text(page: dict) -> str:
    """Extract page text handling 2-column layout (left col before right col)."""
    mid_x = page['width'] / 2
    left = [t for t in page['items'] if t['x'] < mid_x]
    right = [t for t in page['items'] if t['x'] >= mid_x]
    has_2col = len(left) > 5 and len(right) > 5

    if has_2col:
        l_lines = [l for l in _items_to_lines(left) if not is_hf(l['text'])]
        r_lines = [l for l in _items_to_lines(right) if not is_hf(l['text'])]
        return ('\n'.join(l['text'] for l in l_lines) + '\n' +
                '\n'.join(l['text'] for l in r_lines))
    else:
        all_lines = [l for l in _items_to_lines(page['items']) if not is_hf(l['text'])]
        return '\n'.join(l['text'] for l in all_lines)


# ── Body parser — matches JS parseBody logic ───────────────────────────────────

def _parse_body(body_lines: list) -> dict:
    """
    Parse question body lines into:
      mainQ      — main question text (may be empty for statement-only questions)
      subItems   — numbered sub-statements ("1. ...", "2. ...")
      subStem    — directive stem ("Which of the above...", "How many...")
      matchHeader — column header for match-type questions
    Mirrors the JavaScript parseBody() function in the original HTML.
    """
    main_parts = []
    sub_items = []
    sub_stem = ''
    match_header = None
    saw_num = False
    saw_stem = False

    for line in body_lines:
        line = line.strip()
        if not line:
            continue

        if NUM_STMT_RE.match(line):
            saw_num = True
            sub_items.append(line)
        elif STEM_RE.match(line):
            saw_stem = True
            if sub_stem:
                sub_stem += ' ' + line
            else:
                sub_stem = line
        elif MATCH_HDR_RE.search(line) and not NUM_STMT_RE.match(line) and not saw_num:
            # Spaced header line before numbered match rows
            match_header = line
        elif saw_num:
            # Continuation of last sub-item
            sub_items[-1] += ' ' + line
        elif saw_stem:
            sub_stem += ' ' + line
        else:
            main_parts.append(line)

    main_q = re.sub(r'\s{2,}', ' ', ' '.join(main_parts)).strip()
    stem = re.sub(r'\s{2,}', ' ', sub_stem).strip()

    # Normalize "How many" + "select correct" stem
    if re.search(r'how\s+many', main_q, re.I) and sub_items and re.search(r'select\s+the\s+correct', stem, re.I):
        stem = 'How many of the above are correct?'

    return {'mainQ': main_q, 'subItems': sub_items, 'subStem': stem, 'matchHeader': match_header}


# ── Test PDF parser ────────────────────────────────────────────────────────────

def _parse_test_pdf(pages: list) -> dict:
    """Anchor-on-option-a method: find (a) anchors, walk backwards to find Q number."""
    q_map = {}
    all_lines = []

    for page in pages:
        txt = _page_to_text(page)
        if not re.search(r'\(\s*[abcd]\s*\)', txt, re.I):
            continue
        ls = [l.strip() for l in txt.split('\n') if l.strip() and not is_hf(l.strip())]
        all_lines.extend(ls)

    # All indices where line is "(a) ..."
    a_idxs = [i for i, l in enumerate(all_lines)
               if OPT_RE.match(l) and OPT_RE.match(l).group(1).lower() == 'a']

    for ai, a_idx in enumerate(a_idxs):
        # Walk backwards from (a) to find question number
        candidates = []
        for j in range(a_idx - 1, max(-1, a_idx - 80), -1):
            line = all_lines[j]
            om = OPT_RE.match(line)
            if om and om.group(1).lower() != 'a':
                break   # hit a non-a option → stop
            m = QNUM_RE.match(line)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 100:
                    candidates.append({'n': n, 'idx': j, 'text': m.group(2).strip()})

        if not candidates:
            continue

        # The deepest (earliest) candidate is the question number
        q_num = candidates[-1]['n']
        q_line_idx = candidates[-1]['idx']
        q_first = candidates[-1]['text']

        # Collect body lines between question number and (a)
        body_lines = [q_first]
        for j in range(q_line_idx + 1, a_idx):
            line = all_lines[j]
            bm = OPT_RE.match(line)
            if bm and bm.group(1).lower() != 'a':
                break
            body_lines.append(line)

        # Collect options (a)(b)(c)(d)
        options = []
        cur_opt = None
        next_a = a_idxs[ai + 1] if ai + 1 < len(a_idxs) else len(all_lines)
        scan_end = min(next_a, a_idx + 40)

        for j in range(a_idx, scan_end):
            m = OPT_RE.match(all_lines[j])
            if m:
                if cur_opt:
                    options.append(cur_opt)
                cur_opt = {'letter': m.group(1).lower(), 'text': m.group(2).strip()}
                if m.group(1).lower() == 'd':
                    options.append(cur_opt)
                    cur_opt = None
                    break
            elif cur_opt:
                if QNUM_RE.match(all_lines[j]) and len(options) < 3:
                    break
                if j in a_idxs and j != a_idx:
                    break
                cur_opt['text'] += ' ' + all_lines[j]

        if cur_opt and not any(o['letter'] == cur_opt['letter'] for o in options):
            options.append(cur_opt)

        if len(options) >= 2:
            parsed = _parse_body(body_lines)
            if q_num not in q_map or len(options) > len(q_map[q_num]['options']):
                q_map[q_num] = {'parsed': parsed, 'options': options}

    return q_map


# ── Solution PDF parser ────────────────────────────────────────────────────────

def _parse_sol_pdf(pages: list) -> tuple:
    """Extract answers and explanations from VisionIAS solution PDF."""
    answers = {}
    explanations = {}

    all_lines = []
    for page in pages:
        ls = [l['text'] for l in _items_to_lines(page['items']) if not is_hf(l['text'])]
        all_lines.extend(ls)

    full_text = '\n'.join(all_lines)

    # Primary: standalone "Q N. D" lines
    blocks = []
    marker_re = re.compile(r'^Q\s*(\d{1,3})\s*\.\s*([A-D])\s*$', re.M)
    for m in marker_re.finditer(full_text):
        blocks.append({'num': int(m.group(1)), 'letter': m.group(2).lower(),
                       'start': m.start(), 'end': m.end()})

    # Fallback: inline "Q1.B" or "Q 1. B" anywhere in text
    if len(blocks) < 5:
        seen = {b['num'] for b in blocks}
        inline_re = re.compile(r'\bQ\s*(\d{1,3})\s*\.\s*([A-D])\b')
        for m in inline_re.finditer(full_text):
            n = int(m.group(1))
            if 1 <= n <= 100 and n not in seen:
                blocks.append({'num': n, 'letter': m.group(2).lower(),
                               'start': m.start(), 'end': m.end()})
                seen.add(n)
        blocks.sort(key=lambda b: b['start'])

    for b in blocks:
        answers[b['num']] = b['letter']

    for i, b in enumerate(blocks):
        next_pos = blocks[i + 1]['start'] if i + 1 < len(blocks) else len(full_text)
        raw = full_text[b['end']:next_pos]
        cl = _clean_expl(raw)
        if len(cl) > 10:
            explanations[b['num']] = cl

    return answers, explanations


def _clean_expl(raw: str) -> str:
    t = raw
    t = re.sub(r'Hence[,\s]+option\s*\([a-d]\)\s*is\s*(?:the\s+)?correct\s*(?:answer)?\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'Hence\s+option\s*\(?[a-d]\)?\s*is[^.\n]*\.?\s*', '', t, flags=re.I)
    t = re.sub(r'Hence\s+the\s+correct\s+(?:answer|option)[^.\n]*\.?\s*', '', t, flags=re.I)
    t = re.sub(r'Hence\s+statement\s+\d+\s+is[^.]*\.?\s*', '', t, flags=re.I)
    t = re.sub(r'Therefore[,\s]+option\s*\(?[a-d]\)?[^.]*\.?\s*', '', t, flags=re.I)
    t = re.sub(r'(?:Source|Note|Reference)\s*:[^\n]*', '', t, flags=re.I | re.M)
    t = re.sub(r'[●○•▪◆▸▹→‣]', '', t)
    t = re.sub(r'^\s*o\s+', ' ', t, flags=re.M)
    t = re.sub(r'^Q\s*\d{1,3}\s*\.\s*[A-D]\s*$', '', t, flags=re.M)
    lines = [l.strip() for l in t.split('\n') if len(l.strip()) > 3 and not is_hf(l.strip())]
    result = re.sub(r'\s{2,}', ' ', ' '.join(lines))
    return re.sub(r'\.\s*\.', '.', result).strip()


# ── Output builder ─────────────────────────────────────────────────────────────

def _build_output(q_map: dict, answers: dict, explanations: dict) -> str:
    lines_out = []
    for num in sorted(q_map.keys()):
        q = q_map[num]
        parsed = q['parsed']
        options = q['options']
        ans = answers.get(num, '')
        expl = explanations.get(num, '')

        main_q = parsed['mainQ']
        sub_items = parsed['subItems']
        sub_stem = parsed['subStem']
        match_hdr = parsed['matchHeader']

        # Question header line
        if main_q:
            lines_out.append(f'Q{num}.{main_q}')
            if match_hdr:
                lines_out.append(match_hdr)
            lines_out.extend(sub_items)
            if sub_stem:
                lines_out.append(sub_stem)
        elif sub_items or sub_stem:
            # Statement-only question (no main intro)
            stem_line = sub_stem or (sub_items[0] if sub_items else '')
            lines_out.append(f'Q{num}.{stem_line}')
            if match_hdr:
                lines_out.append(match_hdr)
            rest = sub_items[1:] if sub_stem else sub_items
            lines_out.extend(rest)
            if sub_stem and sub_items:
                pass  # stem already used as header
        else:
            lines_out.append(f'Q{num}.')

        lines_out.append('😂')

        for lt in ['a', 'b', 'c', 'd']:
            opt = next((o for o in options if o['letter'] == lt), None)
            if not opt:
                continue
            txt = re.sub(r'\s{2,}', ' ', opt['text'])
            txt = re.sub(r'^\s*\([a-d]\)\s*', '', txt, flags=re.I).strip()
            mark = ' ✅' if ans and opt['letter'] == ans else ''
            lines_out.append(txt + mark)

        lines_out.append(f'Ex: {expl}' if expl else f'Ex: [Explanation not extracted for Q{num}]')
        lines_out.append('')

    return '\n'.join(lines_out)


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_vision(test_pdf_bytes: bytes, sol_pdf_bytes: bytes) -> str:
    """Parse VisionIAS test + solution PDFs. Returns formatted text."""
    test_pages = _extract_pages(test_pdf_bytes)
    q_map = _parse_test_pdf(test_pages)

    sol_pages = _extract_pages(sol_pdf_bytes)
    answers, explanations = _parse_sol_pdf(sol_pages)

    return _build_output(q_map, answers, explanations)
