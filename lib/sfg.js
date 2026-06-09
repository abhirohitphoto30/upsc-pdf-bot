/**
 * ForumIAS SFG 50-Q Converter
 * Ported from the original HTML/JS to Node.js (Vercel serverless).
 */

const { getDocument } = require('pdfjs-dist');

function setStatus(dot, text) {
  return { dot: dot || 'loading', text: text || 'Processing...' };
}

function extractPageText(content) {
  if (!content.items.length) return '';
  const items = content.items
    .filter(it => it.str && it.str.trim())
    .sort((a, b) => {
      const dy = b.transform[5] - a.transform[5];
      if (Math.abs(dy) > 3) return dy;
      return a.transform[4] - b.transform[4];
    });

  const rows = [];
  let currentY = null;
  let currentRow = [];

  for (const item of items) {
    const y = item.transform[5];
    if (currentY === null || Math.abs(y - currentY) > 4) {
      if (currentRow.length) rows.push(currentRow);
      currentRow = [item];
      currentY   = y;
    } else {
      currentRow.push(item);
    }
  }
  if (currentRow.length) rows.push(currentRow);
  return rows.map(row => row.map(it => it.str).join(' ')).join('\n');
}

function cleanLines(rawText) {
  const lines = rawText.split('\n');
  const cleaned = [];
  for (let line of lines) {
    line = line.trim();
    if (!line) continue;
    if (/^Forum Learning Centre/i.test(line)) continue;
    if (/^9311\d{6}/.test(line)) continue;
    if (/^\d{10}\s*,\s*\d{10}/.test(line)) continue;
    if (/^\[\d+\]$/.test(line)) continue;
    if (/^SFG 20\d\d\s*\|\s*Level/i.test(line)) continue;
    if (/^https?:\/\//i.test(line) && line.length < 120) continue;
    if (/^admissions@forumias/i.test(line)) continue;
    if (/^helpdesk@forumias/i.test(line)) continue;
    if (/^\d{4,5}\s*,\s*\d{4,5}/.test(line)) continue;
    cleaned.push(line);
  }
  return cleaned;
}

function parseAndFormat(rawText) {
  const lines  = cleanLines(rawText);
  const output = [];
  let i        = 0;
  let qNumber  = 0;

  const ROMAN_MAP = { I:'1',II:'2',III:'3',IV:'4',V:'5',VI:'6',VII:'7',VIII:'8',IX:'9',X:'10' };
  function romanDigit(r) { return ROMAN_MAP[r.toUpperCase()] || r; }

  function isQuestionStart(l) { return /^Q\.?\s*\d+\s*[)\.]/i.test(l); }
  function getQNum(l)         { const m = l.match(/^Q\.?\s*(\d+)\s*[)\.]/i); return m ? parseInt(m[1]) : null; }
  function stripQPrefix(l)    { return l.replace(/^Q\.?\s*\d+\s*[)\.]\s*/i, '').trim(); }
  function isOption(l)        { return /^[a-d]\s*[)\.]\s*.{1,}/i.test(l); }
  function cleanOpt(l)        { return l.replace(/^[a-d]\s*[)\.]\s*/i, '').trim(); }

  function classifyBodyLine(l) {
    const roman = l.match(/^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[\.\)\-]\s*(.*)/i);
    if (roman) return { type:'roman', num: romanDigit(roman[1]), rest: roman[2].trim() };
    const stmtRoman = l.match(/^Statement\s+(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[:\.]\s*(.*)/i);
    if (stmtRoman) return { type:'statementWord', num: romanDigit(stmtRoman[1]), rest: stmtRoman[2].trim() };
    const stmtArabic = l.match(/^Statement\s+(\d+)\s*[:\.]\s*(.*)/i);
    if (stmtArabic) return { type:'statementWord', num: stmtArabic[1], rest: stmtArabic[2].trim() };
    const arabic = l.match(/^(\d+)\s*[\.\)\-]\s+(.*)/);
    if (arabic) return { type:'arabic', num: arabic[1], rest: arabic[2].trim() };
    if (/^(Which\b|How many\b|Select\b|In how many\b|Who\b|What\b|When\b|Where\b|Name\b|Identify\b|Arrange\b|Among\b|Of the above|From the above|Based on\b|In the above|The above)/i.test(l))
      return { type:'directive', rest: l };
    return null;
  }

  function isTableDataRow(l) {
    return /\s{3,}/.test(l) &&
           (/^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[\.\)\-]/i.test(l) || /^\d+\s*[\.\)\-]/.test(l));
  }
  function isTableHeaderRow(l) {
    return /\s{4,}/.test(l) &&
           !isOption(l) &&
           !isTableDataRow(l) &&
           !/^(Ans|Exp|Source|Subject|Topic|Subtopic)\s*[)\.]/i.test(l) &&
           /^[A-Z]/.test(l);
  }

  function tableToItems(tableLines) {
    const result = [];
    let rowNum = 0;
    for (const l of tableLines) {
      if (isTableHeaderRow(l)) continue;
      const romanRow = l.match(/^(I{1,3}|IV|V|VI{1,3}|IX|X)\s*[\.\)\-]\s*(.*)/i);
      const digitRow = l.match(/^(\d+)\s*[\.\)\-]\s*(.*)/);
      if (romanRow || digitRow) {
        rowNum++;
        const rest  = (romanRow ? romanRow[2] : digitRow[2]).trim();
        const parts = rest.split(/\s{3,}/).map(p => p.trim()).filter(Boolean);
        result.push(rowNum + '. ' + parts.join(' — '));
      } else if (rowNum > 0 && result.length) {
        const parts = l.split(/\s{3,}/).map(p => p.trim()).filter(Boolean);
        result[result.length - 1] += ' ' + parts.join(' ');
      }
    }
    return result;
  }

  function buildQuestionBody(firstStemLine, bodyLines) {
    const items = [{ text: firstStemLine, kind: 'stem' }];
    let stmtCounter = 0;
    let inTable     = false;
    const tableBuffer = [];

    const flushTable = () => {
      if (!tableBuffer.length) return;
      tableToItems(tableBuffer).forEach(t => items.push({ text: t, kind: 'statement' }));
      tableBuffer.length = 0;
      inTable = false;
    };

    for (const l of bodyLines) {
      if (!l) continue;
      if (isTableHeaderRow(l)) { flushTable(); inTable = true; tableBuffer.push(l); continue; }
      if (inTable && isTableDataRow(l)) { tableBuffer.push(l); continue; }
      if (inTable) {
        if (/\s{3,}/.test(l) && !/^(Ans|Exp|Source|Subject|Topic)/i.test(l)) { tableBuffer.push(l); continue; }
        flushTable();
      }
      const cls = classifyBodyLine(l);
      if (cls && cls.type === 'roman') { stmtCounter++; items.push({ text: stmtCounter + '. ' + cls.rest, kind: 'statement' }); continue; }
      if (cls && cls.type === 'statementWord') { stmtCounter++; items.push({ text: stmtCounter + '. ' + cls.rest, kind: 'statement' }); continue; }
      if (cls && cls.type === 'arabic') { items.push({ text: cls.num + '. ' + cls.rest, kind: 'statement' }); continue; }
      if (cls && cls.type === 'directive') { items.push({ text: cls.rest, kind: 'directive' }); continue; }
      if (items.length > 0) { items[items.length - 1].text += ' ' + l; }
      else { items.push({ text: l, kind: 'stem' }); }
    }
    flushTable();
    return items.map(it => it.text.trim()).filter(Boolean);
  }

  function extractExplanation(block) {
    let expIdx = -1;
    for (let j = 0; j < block.length; j++) {
      if (/^Exp\s*[)\.]/i.test(block[j])) { expIdx = j; break; }
    }
    if (expIdx === -1) return '';
    const parts = [];
    for (let j = expIdx; j < block.length; j++) {
      const l = block[j].trim();
      if (/^(Source|Subject|Topic|Subtopic)\s*[)\.:]/.test(l)) break;
      if (/^Source\s*[)\.:]/.test(l)) break;
      if (/^https?:\/\//i.test(l)) continue;
      if (/^Exp\s*[)\.]\s*Option\s+[a-d]\s+is\s+the\s+correct/i.test(l)) {
        const after = l.replace(/^Exp\s*[)\.]\s*Option\s+[a-d]\s+is\s+the\s+correct\s+answer[,\.]?\s*/i, '').trim();
        if (after) parts.push(after);
        continue;
      }
      if (j === expIdx && /^Exp\s*[)\.]/i.test(l)) {
        const after = l.replace(/^Exp\s*[)\.]\s*/i, '').trim();
        if (after) parts.push(after);
        continue;
      }
      const clean = l.replace(/^[●•·▪▸►\*\-]\s+/, '').trim();
      if (clean) parts.push(clean);
    }
    return parts.join(' ').replace(/\s{2,}/g, ' ').replace(/\*\*/g, '').trim();
  }

  while (i < lines.length) {
    if (!isQuestionStart(lines[i])) { i++; continue; }
    qNumber++;
    const qNum = getQNum(lines[i]) || qNumber;
    const block = [lines[i++]];
    while (i < lines.length && !isQuestionStart(lines[i])) block.push(lines[i++]);

    let optionStart = -1, answerIdx = -1;
    for (let j = 1; j < block.length; j++) {
      if (optionStart === -1 && isOption(block[j])) { optionStart = j; }
      if (/^Ans\s*[)\.]/i.test(block[j]))            { answerIdx  = j; }
    }

    const bodyEnd  = optionStart > -1 ? optionStart : (answerIdx > -1 ? answerIdx : block.length);
    const bodyRaw  = block.slice(1, bodyEnd).map(l => l.trim()).filter(Boolean);
    const qLines   = buildQuestionBody(stripQPrefix(block[0]), bodyRaw);
    const qText    = qLines.join('\n');

    const opts = [];
    if (optionStart > -1) {
      for (let j = optionStart; j < block.length; j++) {
        const ol = block[j].trim();
        if (isOption(ol)) { opts.push(ol); }
        else if (/^Ans\s*[)\.]/i.test(ol) || /^Exp\s*[)\.]/i.test(ol)) { break; }
        else if (opts.length > 0 && ol && !/^(Source|Subject|Topic|Subtopic)/i.test(ol)) { opts[opts.length - 1] += ' ' + ol; }
      }
    }

    let ansLetter = '';
    if (answerIdx > -1) {
      const m = block[answerIdx].match(/^Ans\s*[)\.]\s*([a-d])/i);
      if (m) ansLetter = m[1].toLowerCase();
    }
    const ansIdx = ansLetter ? ansLetter.charCodeAt(0) - 97 : -1;
    const expText = extractExplanation(block);

    if (!qText && opts.length === 0) continue;
    output.push(`Q${qNum}. ${qText}`);
    output.push('😂');
    opts.forEach((opt, idx) => {
      const txt = cleanOpt(opt.trim());
      output.push(idx === ansIdx ? `${txt} ✅` : txt);
    });
    if (expText) output.push(`Ex: ${expText}`);
    output.push('');
  }
  return output.join('\n');
}

async function processSfg(buffer, onProgress) {
  try {
    if (onProgress) onProgress(5);

    // Convert Buffer to Uint8Array for pdfjs compatibility
    const dataArray = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    const pdf = await getDocument({ data: dataArray }).promise;
    const totalPages = pdf.numPages;
    if (onProgress) onProgress(10);

    let fullText = '';
    for (let p = 1; p <= totalPages; p++) {
      const page = await pdf.getPage(p);
      const content = await page.getTextContent({ normalizeWhitespace: false });
      fullText += extractPageText(content) + '\n';
      if (onProgress) onProgress(10 + Math.round((p / totalPages) * 50));
    }

    if (onProgress) onProgress(65);
    const formatted = parseAndFormat(fullText);
    if (onProgress) onProgress(95);

    const qCount = (formatted.match(/^Q\d+\./gm) || []).length;
    const lines = formatted.split('\n').length;

    if (onProgress) onProgress(100);

    return {
      success: true,
      output: formatted,
      questionCount: qCount,
      lineCount: lines,
    };
  } catch (err) {
    return {
      success: false,
      error: err.message || String(err),
    };
  }
}

module.exports = { processSfg };
