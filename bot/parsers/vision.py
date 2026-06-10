"""
VisionIAS 100Q parser.
Requires two PDFs: Test Booklet + Answer Key / Solutions.
Answer markers in solution PDF: "Q N. Letter" format.
"""
import re
import pdfplumber
from io import BytesIO

NOISE_VISION = [
    re.compile(r'www\.visionias\.in', re.I),
    re.compile(r'©Vision\s*IAS', re.I),
    re.compile(r'Vision\s*IAS', re.I),
    re.compile(r'Test Booklet Series', re.I),
    re.compile(r'GENERAL STUDIES.*TEST', re.I),
    re.compile(r'DO NOT OPEN THIS BOOKLET', re.I),
    re.compile(r'IMMEDIATELY AFTER THE COMMENCEMENT', re.I),
    re.compile(r'(?:BBOOKLET|BOOKLET\s+DOES\s+NOT\s+HAVE)', re.I),
    re.compile(r'ENCODE CLEARLY', re.I),
    re.compile(r'You have to enter your Roll Number', re.I),
    re.compile(r'This Test Booklet contains', re.I),
    re.compile(r'You have to mark all your responses', re.I),
    re.compile(r'All items carry equal marks', re.I),
    re.compile(r'Before you proceed to mark', re.I),
    re.compile(r'After you have completed', re.I),
    re.compile(r'Sheet for rough work', re.I),
    re.compile(r'ANSWERS\s*&\s*EXPLANATIONS', re.I),
    re.compile(r'ANSWERS AND EXPLANATIONS', re.I),
    re.compile(r'Time Allowed', re.I),
    re.compile(r'Maximum Marks', re.I),
    re.compile(r'^\d+$'),
]

OPT_RE = re.compile(r'^\(([a-d])\)\s+(.+)$', re.I)
QNUM_RE = re.compile(r'^(\d{1,3})\.\s+(.+)$')


def is_hf(line):
    return any(p.search(line.strip()) for p in NOISE_VISION)


def extract_pdf_pages(pdf_bytes):
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


def items_to_lines(items, y_tol=4):
    if not items:
        return []
    sorted_items = sorted(items, key=lambda t: (t['y'], t['x']))
    rows = []
    cur_row = [sorted_items[0]]
    for item in sorted_items[1:]:
        if abs(item['y'] - cur_row[0]['y']) <= y_tol:
            cur_row.append(item)
        else:
            rows.append(cur_row)
            cur_row = [item]
    rows.append(cur_row)
    result = []
    for row in rows:
        row.sort(key=lambda t: t['x'])
        text = ' '.join(t['text'] for t in row).strip()
        if text:
            result.append({
                'y': row[0]['y'],
                'x': min(t['x'] for t in row),
                'text': text
            })
    return result


def page_to_text_2col(page):
    """Convert page to text, left column before right column."""
    mid_x = page['width'] / 2
    left_items = [t for t in page['items'] if t['x'] < mid_x]
    right_items = [t for t in page['items'] if t['x'] >= mid_x]

    has_2col = len(left_items) > 5 and len(right_items) > 5

    if has_2col:
        left_lines = [l for l in items_to_lines(left_items) if not is_hf(l['text'])]
        right_lines = [l for l in items_to_lines(right_items) if not is_hf(l['text'])]
        return ('\n'.join(l['text'] for l in left_lines) + '\n' +
                '\n'.join(l['text'] for l in right_lines))
    else:
        all_lines = [l for l in items_to_lines(page['items']) if not is_hf(l['text'])]
        return '\n'.join(l['text'] for l in all_lines)


def _parse_body(body_lines):
    """
    Parse question body into: mainQ, subItems (numbered), subStem (directive), matchHeader.
    """
    main_parts = []
    sub_items = []
    sub_stem = ''
    match_header = None

    NUM_RE = re.compile(r'^\d+\.\s+')
    STEM_RE = re.compile(
        r'^(Which|How many|Select|In how many|Of the above|From the above|'
        r'Based on|According to)', re.I
    )
    MATCH_HDR_RE = re.compile(r'\s{3,}')

    for i, line in enumerate(body_lines):
        line = line.strip()
        if not line:
            continue
        if NUM_RE.match(line):
            if not sub_items and MATCH_HDR_RE.search(line):
                pass
            sub_items.append(line)
        elif STEM_RE.match(line):
            if sub_stem:
                sub_stem += ' ' + line
            else:
                sub_stem = line
        elif sub_items and not STEM_RE.match(line):
            sub_items[-1] += ' ' + line
        elif sub_stem:
            sub_stem += ' ' + line
        else:
            if MATCH_HDR_RE.search(line) and not NUM_RE.match(line) and not sub_items:
                match_header = line
            else:
                main_parts.append(line)

    main_q = re.sub(r'\s{2,}', ' ', ' '.join(main_parts)).strip()
    stem = re.sub(r'\s{2,}', ' ', sub_stem).strip()

    return {
        'mainQ': main_q,
        'subItems': sub_items,
        'subStem': stem,
        'matchHeader': match_header
    }


def parse_test_pdf_vision(pages):
    q_map = {}
    all_lines = []

    for page in pages:
        txt = page_to_text_2col(page)
        if not re.search(r'\(\s*[abcd]\s*\)', txt, re.I):
            continue
        ls = [l.strip() for l in txt.split('\n') if l.strip() and not is_hf(l.strip())]
        all_lines.extend(ls)

    a_idxs = [i for i, l in enumerate(all_lines)
               if OPT_RE.match(l) and OPT_RE.match(l).group(1).lower() == 'a']

    for ai, a_idx in enumerate(a_idxs):
        candidates = []
        for j in range(a_idx - 1, max(-1, a_idx - 80), -1):
            line = all_lines[j]
            om = OPT_RE.match(line)
            if om and om.group(1).lower() != 'a':
                break
            m = QNUM_RE.match(line)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 100:
                    candidates.append({'n': n, 'idx': j, 'text': m.group(2).strip()})

        if not candidates:
            continue

        q_num = candidates[-1]['n']
        q_line_idx = candidates[-1]['idx']
        q_first = candidates[-1]['text']

        body_lines = [q_first]
        for j in range(q_line_idx + 1, a_idx):
            line = all_lines[j]
            bm = OPT_RE.match(line)
            if bm and bm.group(1).lower() != 'a':
                break
            body_lines.append(line)

        options = []
        cur_opt = None
        next_a_idx = a_idxs[ai + 1] if ai + 1 < len(a_idxs) else len(all_lines)
        scan_end = min(next_a_idx, a_idx + 40)

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


def parse_sol_pdf_vision(pages):
    answers = {}
    explanations = {}

    all_lines = []
    for page in pages:
        ls = [l['text'] for l in items_to_lines(page['items']) if not is_hf(l['text'])]
        all_lines.extend(ls)

    full_text = '\n'.join(all_lines)

    marker_re = re.compile(r'^Q\s*(\d{1,3})\s*\.\s*([A-D])\s*$', re.M)
    blocks = []
    for m in marker_re.finditer(full_text):
        blocks.append({
            'num': int(m.group(1)),
            'letter': m.group(2).lower(),
            'start': m.start(),
            'end': m.end()
        })

    if len(blocks) < 5:
        inline_re = re.compile(r'\bQ\s*(\d{1,3})\s*\.\s*([A-D])\b')
        seen = {b['num'] for b in blocks}
        for m in inline_re.finditer(full_text):
            n = int(m.group(1))
            if 1 <= n <= 100 and n not in seen:
                blocks.append({
                    'num': n, 'letter': m.group(2).lower(),
                    'start': m.start(), 'end': m.end()
                })
                seen.add(n)
        blocks.sort(key=lambda b: b['start'])

    for b in blocks:
        answers[b['num']] = b['letter']

    for i, b in enumerate(blocks):
        next_pos = blocks[i + 1]['start'] if i + 1 < len(blocks) else len(full_text)
        raw = full_text[b['end']:next_pos]
        cl = _clean_explanation_vision(raw)
        if len(cl) > 10:
            explanations[b['num']] = cl

    return answers, explanations


def _clean_explanation_vision(raw):
    t = raw
    t = re.sub(r'Hence[,\s]+option\s*\([a-d]\)\s*is\s*(?:the\s+)?correct\s*(?:answer)?\.?[^\n]*',
               '', t, flags=re.I)
    t = re.sub(r'Hence\s+option\s*\(?[a-d]\)?\s*is[^.\n]*\.\s*', '', t, flags=re.I)
    t = re.sub(r'Hence\s+the\s+correct\s+(?:answer|option)[^.\n]*\.\s*', '', t, flags=re.I)
    t = re.sub(r'Hence\s+statement\s+\d+\s+is\s+(?:correct|not\s+correct)\.\s*', '', t, flags=re.I)
    t = re.sub(r'Hence\s+(?:the\s+)?statement\s+\d+\s+is[^.]*\.\s*', '', t, flags=re.I)
    t = re.sub(r'Therefore[,\s]+option\s*\(?[a-d]\)?[^.]*\.\s*', '', t, flags=re.I)
    t = re.sub(r'(?:Source|Note|Reference)\s*:[^\n]*', '', t, flags=re.I | re.M)
    t = re.sub(r'[●○•▪◆▸▹→‣]', '', t)
    t = re.sub(r'^\s*o\s+', ' ', t, flags=re.M)
    t = re.sub(r'^Q\s*\d{1,3}\s*\.\s*[A-D]\s*$', '', t, flags=re.M)
    lines = [l.strip() for l in t.split('\n') if len(l.strip()) > 3 and not is_hf(l.strip())]
    result = ' '.join(lines)
    result = re.sub(r'\s{2,}', ' ', result)
    result = re.sub(r'\.\s*\.', '.', result)
    return result.strip()


def _build_output(q_map, answers, explanations):
    lines_out = []
    nums = sorted(q_map.keys())

    for num in nums:
        q = q_map[num]
        parsed = q['parsed']
        options = q['options']
        ans_letter = answers.get(num, '')
        expl = explanations.get(num, '')

        main_q = parsed['mainQ']
        sub_items = parsed['subItems']
        sub_stem = parsed['subStem']
        match_header = parsed['matchHeader']

        if main_q:
            lines_out.append(f'Q{num}.{main_q}')
            if match_header:
                lines_out.append(match_header)
            for item in sub_items:
                lines_out.append(item)
            if sub_stem:
                lines_out.append(sub_stem)
        elif sub_stem:
            lines_out.append(f'Q{num}.{sub_stem}')
            if match_header:
                lines_out.append(match_header)
            for item in sub_items:
                lines_out.append(item)
        else:
            lines_out.append(f'Q{num}.')

        lines_out.append('😂')

        for lt in ['a', 'b', 'c', 'd']:
            opt = next((o for o in options if o['letter'] == lt), None)
            if not opt:
                continue
            txt = re.sub(r'\s{2,}', ' ', opt['text'])
            txt = re.sub(r'^\s*\([a-d]\)\s*', '', txt, flags=re.I).strip()
            mark = ' ✅' if ans_letter and opt['letter'] == ans_letter else ''
            lines_out.append(txt + mark)

        lines_out.append(f'Ex: {expl}' if expl else f'Ex: [Explanation not extracted for Q{num}]')
        lines_out.append('')

    return '\n'.join(lines_out)


def parse_vision(test_pdf_bytes: bytes, sol_pdf_bytes: bytes) -> str:
    """
    Parse VisionIAS test + solution PDFs.
    Returns formatted text string.
    """
    test_pages = extract_pdf_pages(test_pdf_bytes)
    q_map = parse_test_pdf_vision(test_pages)

    sol_pages = extract_pdf_pages(sol_pdf_bytes)
    answers, explanations = parse_sol_pdf_vision(sol_pages)

    return _build_output(q_map, answers, explanations)
