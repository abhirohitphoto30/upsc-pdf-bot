/**
 * Vajiram & Ravi 100-Q Converter
 * Ported from the original HTML/JS to Node.js (Vercel serverless).
 * Uses two-column spatial parsing.
 */

const { getDocument } = require('pdfjs-dist');

async function extractPages(buffer) {
  const pdf = await getDocument({ data: buffer }).promise;
  const pages = [];
  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const vp = page.getViewport({ scale: 1.0 });
    const tc = await page.getTextContent();
    const items = tc.items
      .filter(i => i.str && i.str.trim())
      .map(i => ({
        text: i.str,
        x: Math.round(i.transform[4]),
        y: Math.round(vp.height - i.transform[5]),
        w: Math.round(i.width),
        h: Math.round(i.height || 10),
      }));
    pages.push({ items, width: vp.width, height: vp.height, pageNum: p });
  }
  return pages;
}

function consolidateSpatialTokens(tokensList, yTolerance = 4) {
  if (!tokensList.length) return [];
  const sorted = [...tokensList].sort((a, b) => a.y - b.y || a.x - b.x);
  const rows = [];
  let curRow = [sorted[0]];
  for (let i = 1; i < sorted.length; i++) {
    if (Math.abs(sorted[i].y - curRow[0].y) <= yTolerance) {
      curRow.push(sorted[i]);
    } else {
      rows.push(curRow);
      curRow = [sorted[i]];
    }
  }
  rows.push(curRow);
  return rows.map(bucket => {
    bucket.sort((a, b) => a.x - b.x);
    const text = bucket.map(t => t.text).join(' ').replace(/\s{2,}/g, ' ').trim();
    return { y: bucket[0].y, x: Math.min(...bucket.map(t => t.x)), text };
  }).filter(r => r.text.length > 0);
}

function isHeaderFooterNoise(line) {
  const s = line.trim().toUpperCase();
  if (s.length === 0) return true;
  const patterns = [
    /VAJIRAM\s*(&|AND)\s*RAVI/i, /PRELIMS\s*TEST\s*SERIES/i,
    /FULL\s*LENGTH\s*TEST/i, /TEST\s*BOOKLET/i,
    /MAXIMUM\s*MARKS/i, /TIME\s*ALLOWED/i, /DO\s*NOT\s*OPEN/i,
    /COMMENCEMENT\s*OF\s*THE\s*EXAMINATION/i, /UNPRINTED\s*OR\s*TORN/i,
    /CANDIDATE'S\s*RESPONSIBILITY/i, /ROLL\s*NUMBER/i,
    /OMR\s*ANSWER/i, /ANSWER\s*SHEET/i, /PENALTY\s*FOR\s*WRONG/i,
    /WRONG\s*ANSWERS\s*MARKED/i, /ALTERNATIVES\s*FOR\s*THE\s*ANSWER/i,
    /QUESTION\s*IS\s*LEFT\s*BLANK/i, /ECONOMICS\s*\(V\d+\)/i,
    /SCIENCE\s*&\s*TECHNOLOGY\s*\(V\d+\)/i, /POLITY\s*\(V\d+\)/i,
    /GS\s*TEST\s*-\s*\d+/i, /POWERUP\s*PRELIMS/i,
    /^\d{1,3}$/
  ];
  return patterns.some(p => p.test(line));
}

function isCoverPage(lines) {
  const combined = lines.map(l => l.text).join(' ');
  return !(/\(a\)/i.test(combined) || /\(b\)/i.test(combined));
}

function parseTestBooklet(pages, logFn) {
  const questionMap = {};
  for (const page of pages) {
    const masterLines = consolidateSpatialTokens(page.items);
    const filteredLines = masterLines.filter(l => !isHeaderFooterNoise(l.text));
    if (isCoverPage(filteredLines)) {
      if (logFn) logFn(`  Skipping non-question page: ${page.pageNum}`, 'warn');
      continue;
    }

    const midX = page.width / 2;
    const leftItems = page.items.filter(t => t.x < midX - 15);
    const rightItems = page.items.filter(t => t.x >= midX - 15);
    const isTwoColumn = leftItems.length > 6 && rightItems.length > 6;

    let unifiedText = '';
    if (isTwoColumn) {
      const leftLines = consolidateSpatialTokens(leftItems).filter(l => !isHeaderFooterNoise(l.text));
      const rightLines = consolidateSpatialTokens(rightItems).filter(l => !isHeaderFooterNoise(l.text));
      unifiedText = [...leftLines, ...rightLines].map(l => l.text).join('\n');
    } else {
      unifiedText = filteredLines.map(l => l.text).join('\n');
    }

    parseQuestionsFromText(unifiedText, questionMap);
  }
  return questionMap;
}

function parseQuestionsFromText(textStream, targetMap) {
  const lines = textStream.split('\n').map(r => r.trim()).filter(r => r.length > 0);
  let activeQ = null;
  let bodyLines = [];
  let options = [];
  let inOptions = false;

  function flush() {
    if (activeQ === null) return;
    if (options.length >= 2) {
      if (!targetMap[activeQ] || options.length > targetMap[activeQ].options.length) {
        targetMap[activeQ] = { id: activeQ, body: [...bodyLines], options: [...options] };
      }
    }
    activeQ = null;
    bodyLines = [];
    options = [];
    inOptions = false;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const optMatch = line.match(/^\s*\(([a-d])\)\s+(.+)$/i);
    if (optMatch && activeQ !== null) {
      inOptions = true;
      options.push({ letter: optMatch[1].toLowerCase(), text: optMatch[2].trim() });
      continue;
    }

    const qMatch = line.match(/^\s*(\d{1,3})\.\s{1,6}(.+)$/);
    if (qMatch) {
      const num = parseInt(qMatch[1], 10);
      if (num >= 1 && num <= 100) {
        const isListItem = (
          activeQ !== null && !inOptions &&
          num !== activeQ + 1 && num <= 6
        );
        if (!isListItem || activeQ === null) {
          flush();
          activeQ = num;
          bodyLines = [qMatch[2].trim()];
          options = [];
          inOptions = false;
          continue;
        }
      }
    }

    if (inOptions && options.length > 0 && activeQ !== null) {
      if (!line.match(/^\s*\(([a-d])\)/i)) {
        options[options.length - 1].text += ' ' + line;
      }
      continue;
    }

    if (activeQ !== null && !inOptions) {
      bodyLines.push(line);
    }
  }
  flush();
}

function parseSolutions(pages, logFn) {
  const allLines = [];
  for (const page of pages) {
    const formatted = consolidateSpatialTokens(page.items)
      .filter(l => !isHeaderFooterNoise(l.text))
      .map(l => l.text);
    allLines.push(...formatted);
  }

  const fullText = allLines.join('\n');

  // Extract answer keys
  const answerKeys = {};
  const keyRegex = /\b(\d{1,3})\.\s*\(([a-d])\)/gi;
  let m;
  while ((m = keyRegex.exec(fullText)) !== null) {
    const num = parseInt(m[1], 10);
    if (num >= 1 && num <= 100) {
      answerKeys[num] = m[2].toLowerCase();
    }
  }

  if (logFn) logFn(`  Answer keys found: ${Object.keys(answerKeys).length}`);

  // Extract explanations
  const explanations = {};
  const blockRegex = /\nQ(\d{1,3})\.\s*\n/g;
  const blocks = [];
  while ((m = blockRegex.exec(fullText)) !== null) {
    blocks.push({ num: parseInt(m[1], 10), start: m.index + m[0].length });
  }

  for (let i = 0; i < blocks.length; i++) {
    const { num, start } = blocks[i];
    const end = i + 1 < blocks.length ? blocks[i + 1].start : fullText.length;
    const slice = fullText.slice(start, end);
    explanations[num] = cleanExplanation(slice);
  }

  // Fallback: if no blocks found, try inline
  if (blocks.length < 5) {
    const inlineRegex = /\bQ\s*(\d{1,3})\s*\.\s*([A-D])\b/g;
    while ((m = inlineRegex.exec(fullText)) !== null) {
      const num = parseInt(m[1], 10);
      if (num >= 1 && num <= 100 && !answerKeys[num]) {
        answerKeys[num] = m[2].toLowerCase();
      }
    }
  }

  return { answerKeys, explanations };
}

function cleanExplanation(raw) {
  let t = raw;
  t = t.replace(/^Answer\s*:\s*[a-d]\s*$/gmi, '');
  t = t.replace(/^Explanation\s*:\s*$/gmi, '');
  t = t.replace(/Therefore[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*/gi, '');
  t = t.replace(/So[,\s]+option\s*\([a-d]\)\s*is\s*the\s*correct\s*answer\.?[^\n]*/gi, '');
  t = t.replace(/Therefore[,\s]+the\s*correct\s*answer[^\n]*/gi, '');
  t = t.replace(/Relevance\s*:[^\n]*/gi, '');
  t = t.replace(/^(?:Source|Ref|Reference)\s*:[^\n]*/gmi, '');
  t = t.replace(/^[\s]*[●○•▪◆▸▹→\-–—]+\s*/gm, '');
  t = t.replace(/^Q\d{1,3}\.\s*/gm, '');
  const cleaned = t.split('\n').map(l => l.trim()).filter(l => l.length > 2);
  return cleaned.join(' ').replace(/\s{2,}/g, ' ').replace(/\.\s*\./g, '.').trim();
}

function compileQuestionCoreLines(rawLines) {
  const normalized = rawLines.map(l => normalizeRoman(l.trim())).filter(l => l.length > 0);
  if (!normalized.length) return [];

  const newLineRe = [
    /^\d{1,2}\.\s+\S/,
    /^Statement\s+[IVXLC]+\s*:/i,
    /^(Which|How\s+many|How\s+|What|Select|Arrange|In\s+how|Who\s+|Where\s+|Among\s+|Identify|Of\s+the|With\s+reference|With\s+regard|Consider|Regarding|As\s+per|According\s+to|In\s+which\s+of\s+the\s+above)/i,
  ];

  const output = [];
  let buf = '';
  for (let i = 0; i < normalized.length; i++) {
    const line = normalized[i];
    const isNew = i === 0 || newLineRe.some(p => p.test(line));
    if (isNew) {
      if (buf) output.push(buf.replace(/\s{2,}/g, ' ').trim());
      buf = line;
    } else {
      buf += ' ' + line;
    }
  }
  if (buf) output.push(buf.replace(/\s{2,}/g, ' ').trim());
  return output;
}

function normalizeRoman(line) {
  return line.replace(
    /^\s*(I{1,3}|IV|V?I{0,3}|IX|XI{0,3})\.\s+/,
    (match, roman) => {
      const map = { I:1, II:2, III:3, IV:4, V:5, VI:6, VII:7, VIII:8, IX:9, X:10, XI:11, XII:12 };
      const digit = map[roman.toUpperCase()];
      return digit ? digit + '. ' : match;
    }
  );
}

function unpackOptions(rawOptions) {
  const combined = rawOptions.map(o => `(${o.letter}) ${o.text}`).join(' ');
  const matchA = combined.match(/\(a\)\s*([\s\S]*?)(?=\s*\(b\)|$)/i);
  const matchB = combined.match(/\(b\)\s*([\s\S]*?)(?=\s*\(c\)|$)/i);
  const matchC = combined.match(/\(c\)\s*([\s\S]*?)(?=\s*\(d\)|$)/i);
  const matchD = combined.match(/\(d\)\s*([\s\S]*?)$/i);
  const textA = matchA ? matchA[1] : 'Only one';
  const textB = matchB ? matchB[1] : 'Only two';
  const textC = matchC ? matchC[1] : 'Only three';
  const textD = matchD ? matchD[1] : 'All the four';
  const pure = s => s.replace(/^\s*\(?[a-d]\)?\s*\.?\s*/i, '').trim();
  return [
    { letter: 'a', text: pure(textA) },
    { letter: 'b', text: pure(textB) },
    { letter: 'c', text: pure(textC) },
    { letter: 'd', text: pure(textD) },
  ];
}

async function processVajiram(testBuffer, solBuffer, onProgress) {
  try {
    if (onProgress) onProgress(15, 'Decoding Test Booklet...');

    const testPages = await extractPages(testBuffer);
    if (onProgress) onProgress(40, 'Compiling questions...');

    const questionMap = parseTestBooklet(testPages);
    const qCount = Object.keys(questionMap).length;
    if (onProgress) onProgress(45, `Parsed ${qCount} questions from test booklet`);

    if (qCount === 0) {
      return {
        success: false,
        error: 'Zero valid questions found in Test PDF. Please check that it is a valid Vajiram test booklet with (a)(b)(c)(d) options.',
      };
    }

    if (onProgress) onProgress(60, 'Decoding Solution Booklet...');

    const solPages = await extractPages(solBuffer);
    if (onProgress) onProgress(85, 'Cross-referencing answers...');

    const { answerKeys, explanations } = parseSolutions(solPages, (msg) => {
      if (onProgress) onProgress(85 + (onProgress._inc || 0), msg);
    });

    if (onProgress) onProgress(95, 'Building output...');

    const sortedKeys = Object.keys(questionMap).map(Number).sort((a, b) => a - b);
    const lines = [];

    for (const key of sortedKeys) {
      const q = questionMap[key];
      const ansLetter = answerKeys[key];
      const expl = explanations[key] || 'Explanation not found for this question.';

      const coreLines = compileQuestionCoreLines(q.body);
      lines.push(`Q${key}. ${coreLines[0] || ''}`);
      for (let i = 1; i < coreLines.length; i++) lines.push(coreLines[i]);

      lines.push('😂');

      const opts = unpackOptions(q.options);
      for (const opt of opts) {
        const mark = (ansLetter && opt.letter === ansLetter) ? ' ✅' : '';
        lines.push(opt.text + mark);
      }

      lines.push(`Ex: ${expl.trim()}`);
      lines.push('');
    }

    const output = lines.join('\n');
    if (onProgress) onProgress(100, 'Done!');

    return {
      success: true,
      output,
      questionCount: qCount,
      lineCount: lines.length,
    };
  } catch (err) {
    return {
      success: false,
      error: err.message || String(err),
    };
  }
}

module.exports = { processVajiram };
