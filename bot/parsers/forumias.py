"""
ForumIAS SFG / Level test Solutions PDF parser.
Single PDF upload — solutions only.
Output format: Q{n}. text \n 😂 \n options (correct ✅) \n Ex: explanation
"""
import re
import pdfplumber
from io import BytesIO

NOISE_RE = [
    re.compile(r'Forum Learning Centre', re.I),
    re.compile(r'9311\d{6}'),
    re.compile(r'\d{10}\s*,\s*\d{10}'),
    re.compile(r'^\[\d+\]$'),
    re.compile(r'SFG 20\d\d\s*\|\s*Level', re.I),
    re.compile(r'^https?://', re.I),
    re.compile(r'admissions@forumias', re.I),
    re.compile(r'helpdesk@forumias', re.I),
    re.compile(r'Canal Road,\s*Patna', re.I),
    re.compile(r'Pusa Road,\s*Karol Bagh', re.I),
    re.compile(r'forumias\.academy', re.I),
    re.compile(r'forumias\.com', re.I),
    re.compile(r'^\d{4,5}\s*,\s*\d{4,5}'),
]

ROMAN_MAP = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'
}


def roman_to_num(r):
    return ROMAN_MAP.get(r.upper(), r)


def is_noise(line):
    return any(p.search(line) for p in NOISE_RE)


def extract_text_lines_from_pdf(pdf_bytes):
    """Extract ordered text lines from PDF using spatial grouping."""
    all_lines = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3,
                                       keep_blank_chars=False)
            if not words:
                continue
            rows = {}
            for w in words:
                y_key = round(w['top'] / 4) * 4
                if y_key not in rows:
                    rows[y_key] = []
                rows[y_key].append(w)
            for y in sorted(rows.keys()):
                row = sorted(rows[y], key=lambda w: w['x0'])
                line = ' '.join(w['text'] for w in row).strip()
                if line:
                    all_lines.append(line)
    return all_lines


def clean_lines(raw_lines):
    return [l for l in raw_lines if l.strip() and not is_noise(l)]


def is_question_start(line):
    return bool(re.match(r'^Q\.?\s*\d+\s*[).]', line, re.I))


def get_q_num(line):
    m = re.match(r'^Q\.?\s*(\d+)\s*[).]', line, re.I)
    return int(m.group(1)) if m else None


def strip_q_prefix(line):
    return re.sub(r'^Q\.?\s*\d+\s*[).]\s*', '', line, flags=re.I).strip()


def is_option(line):
    return bool(re.match(r'^[a-d]\s*[).]\s*.+', line, re.I))


def clean_opt(line):
    return re.sub(r'^[a-d]\s*[).]\s*', '', line, flags=re.I).strip()


def classify_body_line(line):
    m = re.match(r'^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[.)–\-]\s*(.*)', line, re.I)
    if m:
        return {'type': 'roman', 'num': roman_to_num(m.group(1)), 'rest': m.group(2).strip()}

    m = re.match(r'^Statement\s+(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[:.]\s*(.*)', line, re.I)
    if m:
        return {'type': 'statementWord', 'num': roman_to_num(m.group(1)), 'rest': m.group(2).strip()}

    m = re.match(r'^Statement\s+(\d+)\s*[:.]\s*(.*)', line, re.I)
    if m:
        return {'type': 'statementWord', 'num': m.group(1), 'rest': m.group(2).strip()}

    m = re.match(r'^(\d+)\s*[.)–\-]\s+(.*)', line)
    if m:
        return {'type': 'arabic', 'num': m.group(1), 'rest': m.group(2).strip()}

    if re.match(
        r'^(Which\b|How many\b|Select\b|In how many\b|Who\b|What\b|When\b|Where\b|'
        r'Name\b|Identify\b|Arrange\b|Among\b|Of the above|From the above|'
        r'Based on\b|In the above|The above)',
        line, re.I
    ):
        return {'type': 'directive', 'rest': line}

    return None


def is_table_header_row(line):
    return (bool(re.search(r'\s{4,}', line)) and
            not is_option(line) and
            not bool(re.search(r'\s{3,}', line) and
                     (bool(re.match(r'^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[.)–\-]', line, re.I)) or
                      bool(re.match(r'^\d+\s*[.)–\-]', line)))) and
            not re.match(r'^(Ans|Exp|Source|Subject|Topic|Subtopic)\s*[).]', line, re.I) and
            bool(re.match(r'^[A-Z]', line)))


def is_table_data_row(line):
    return (bool(re.search(r'\s{3,}', line)) and
            (bool(re.match(r'^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[.)–\-]', line, re.I)) or
             bool(re.match(r'^\d+\s*[.)–\-]', line))))


def table_to_items(table_lines):
    result = []
    row_num = 0
    for l in table_lines:
        if is_table_header_row(l):
            continue
        roman_m = re.match(r'^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[.)–\-]\s*(.*)', l, re.I)
        digit_m = re.match(r'^(\d+)\s*[.)–\-]\s*(.*)', l)
        if roman_m or digit_m:
            row_num += 1
            rest = (roman_m.group(2) if roman_m else digit_m.group(2)).strip()
            parts = [p.strip() for p in re.split(r'\s{3,}', rest) if p.strip()]
            result.append(str(row_num) + '. ' + ' — '.join(parts))
        elif row_num > 0 and result:
            parts = [p.strip() for p in re.split(r'\s{3,}', l) if p.strip()]
            result[-1] += ' ' + ' '.join(parts)
    return result


def build_question_body(first_stem_line, body_lines):
    items = [{'text': first_stem_line, 'kind': 'stem'}]
    stmt_counter = 0
    in_table = False
    table_buffer = []

    def flush_table():
        nonlocal in_table, table_buffer
        if not table_buffer:
            return
        for t in table_to_items(table_buffer):
            items.append({'text': t, 'kind': 'statement'})
        table_buffer.clear()
        in_table = False

    for l in body_lines:
        if not l:
            continue

        if is_table_header_row(l):
            flush_table()
            in_table = True
            table_buffer.append(l)
            continue

        if in_table and is_table_data_row(l):
            table_buffer.append(l)
            continue

        if in_table:
            if (bool(re.search(r'\s{3,}', l)) and
                    not re.match(r'^(Ans|Exp|Source|Subject|Topic)', l, re.I)):
                table_buffer.append(l)
                continue
            flush_table()

        cls = classify_body_line(l)
        if cls:
            if cls['type'] == 'roman':
                stmt_counter += 1
                items.append({'text': str(stmt_counter) + '. ' + cls['rest'], 'kind': 'statement'})
            elif cls['type'] == 'statementWord':
                stmt_counter += 1
                items.append({'text': str(stmt_counter) + '. ' + cls['rest'], 'kind': 'statement'})
            elif cls['type'] == 'arabic':
                items.append({'text': cls['num'] + '. ' + cls['rest'], 'kind': 'statement'})
            elif cls['type'] == 'directive':
                items.append({'text': cls['rest'], 'kind': 'directive'})
        else:
            if items:
                items[-1]['text'] += ' ' + l
            else:
                items.append({'text': l, 'kind': 'stem'})

    flush_table()
    return [item['text'].strip() for item in items if item['text'].strip()]


def extract_explanation(block):
    exp_idx = -1
    for j, line in enumerate(block):
        if re.match(r'^Exp\s*[).]', line, re.I):
            exp_idx = j
            break
    if exp_idx == -1:
        return ''

    parts = []
    for j in range(exp_idx, len(block)):
        l = block[j].strip()
        if re.match(r'^(Source|Subject|Topic|Subtopic)\s*[).:]', l):
            break
        if re.match(r'^https?://', l, re.I):
            continue
        if j == exp_idx and re.match(
                r'^Exp\s*[).]\s*Option\s+[a-d]\s+is\s+the\s+correct', l, re.I):
            after = re.sub(
                r'^Exp\s*[).]\s*Option\s+[a-d]\s+is\s+the\s+correct\s+answer[,.]?\s*',
                '', l, flags=re.I).strip()
            if after:
                parts.append(after)
            continue
        if j == exp_idx and re.match(r'^Exp\s*[).]', l, re.I):
            after = re.sub(r'^Exp\s*[).]\s*', '', l, flags=re.I).strip()
            if after:
                parts.append(after)
            continue
        clean = re.sub(r'^[●•·▪▸►*\-]\s+', '', l).strip()
        if clean:
            parts.append(clean)

    return re.sub(r'\s{2,}', ' ', ' '.join(parts)).replace('**', '').strip()


def parse_forumias_pdf(pdf_bytes: bytes) -> str:
    """
    Parse ForumIAS SFG / Level solutions PDF.
    Returns formatted text string.
    """
    raw_lines = extract_text_lines_from_pdf(pdf_bytes)
    lines = clean_lines(raw_lines)

    output = []
    i = 0
    q_number = 0

    while i < len(lines):
        if not is_question_start(lines[i]):
            i += 1
            continue

        q_number += 1
        q_num = get_q_num(lines[i]) or q_number
        block = [lines[i]]
        i += 1
        while i < len(lines) and not is_question_start(lines[i]):
            block.append(lines[i])
            i += 1

        option_start = -1
        answer_idx = -1
        for j in range(1, len(block)):
            if option_start == -1 and is_option(block[j]):
                option_start = j
            if re.match(r'^Ans\s*[).]', block[j], re.I):
                answer_idx = j

        body_end = (option_start if option_start > -1 else
                    (answer_idx if answer_idx > -1 else len(block)))
        body_raw = [l.strip() for l in block[1:body_end] if l.strip()]
        q_lines = build_question_body(strip_q_prefix(block[0]), body_raw)
        q_text = '\n'.join(q_lines)

        opts = []
        if option_start > -1:
            for j in range(option_start, len(block)):
                ol = block[j].strip()
                if is_option(ol):
                    opts.append(ol)
                elif re.match(r'^(Ans|Exp)\s*[).]', ol, re.I):
                    break
                elif opts and ol and not re.match(
                        r'^(Source|Subject|Topic|Subtopic)', ol, re.I):
                    opts[-1] += ' ' + ol

        ans_letter = ''
        if answer_idx > -1:
            m = re.match(r'^Ans\s*[).]\s*([a-d])', block[answer_idx], re.I)
            if m:
                ans_letter = m.group(1).lower()

        ans_idx = ord(ans_letter) - ord('a') if ans_letter else -1
        exp_text = extract_explanation(block)

        if not q_text and not opts:
            continue

        output.append(f'Q{q_num}. {q_text}')
        output.append('😂')
        for idx, opt in enumerate(opts):
            txt = clean_opt(opt.strip())
            output.append(f'{txt} ✅' if idx == ans_idx else txt)
        if exp_text:
            output.append(f'Ex: {exp_text}')
        output.append('')

    return '\n'.join(output)
