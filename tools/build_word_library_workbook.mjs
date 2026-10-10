import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const data = JSON.parse(await fs.readFile(path.join(root, 'analysis/word_library_workbook_data.json'), 'utf8'));
const outDir = path.join(root, 'outputs/word_library_20261010');
await fs.mkdir(outDir, { recursive: true });
const wb = Workbook.create();
const names = ['Observation', 'Recommendation', '待确认合并', '确认项明细', '原始记录', '来源报告', '整理说明'];
const sheets = Object.fromEntries(names.map(n => [n, wb.worksheets.add(n)]));
const font = 'Microsoft YaHei';
const colors = { navy: '#263B53', input: '#FFF5D6', line: '#D8E1EA', ink: '#172B40', muted: '#64748B' };
const headerRow = 6;
const startRow = 7;
const specs = [];
const numericCells = [];

function column(n) {
  let s = '';
  for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + (n - 1) % 26) + s;
  return s;
}
function safeValue(v) { return typeof v === 'string' && v.startsWith('=') ? `'${v}` : v; }
function textLines(v, width) {
  if (v == null || v === '') return 1;
  return String(v).split('\n').reduce((sum, line) => {
    const weight = Array.from(line).reduce((n, c) => n + (c.charCodeAt(0) > 255 ? 1.9 : 1), 0);
    return sum + Math.max(1, Math.ceil(weight / Math.max(8, width - 2)));
  }, 0);
}
function baseSheet(sheet, title, note, headers, rows, widths, tableName, editable = [], numeric = []) {
  const end = headerRow + rows.length;
  const last = column(headers.length - 1);
  const used = sheet.getRange(`A2:${last}${end}`);
  used.format.font = { name: font, size: 10, color: colors.ink };
  used.format.verticalAlignment = 'center';
  sheet.showGridLines = false;
  sheet.getRange('A2').values = [[title]];
  sheet.getRange('A2').format.font = { name: font, size: 14, bold: true, color: colors.ink };
  sheet.getRange('A3').values = [[note]];
  sheet.getRange('A3').format.font = { name: font, size: 10, color: colors.muted };
  sheet.getRange('A2:A4').format.wrapText = false;
  sheet.getRange(`A2:${last}2`).format.rowHeight = 27;
  sheet.getRange(`A3:${last}3`).format.rowHeight = 23;
  sheet.getRange(`A4:${last}4`).format.rowHeight = 23;
  sheet.getRange(`A5:${last}5`).format.rowHeight = 8;
  sheet.getRange(`A6:${last}6`).values = [headers];
  if (rows.length) sheet.getRange(`A${startRow}:${last}${end}`).values = rows.map(r => r.map(safeValue));
  const table = sheet.tables.add(`A6:${last}${end}`, true, tableName);
  table.style = 'TableStyleMedium2';
  table.showFilterButton = true;
  table.showBandedColumns = false;
  const head = sheet.getRange(`A6:${last}6`);
  head.format.fill = colors.navy;
  head.format.font = { name: font, size: 10, bold: true, color: '#FFFFFF' };
  head.format.horizontalAlignment = 'center';
  head.format.wrapText = true;
  head.format.rowHeight = 34;
  head.format.borders = { insideVertical: { style: 'thin', color: '#FFFFFF' }, bottom: { style: 'thin', color: colors.line } };
  const body = sheet.getRange(`A7:${last}${end}`);
  body.format.wrapText = true;
  body.format.horizontalAlignment = 'left';
  widths.forEach((w, i) => sheet.getRange(`${column(i)}2:${column(i)}${end}`).format.columnWidth = w);
  for (const c of editable) sheet.getRange(`${column(c)}7:${column(c)}${end}`).format.fill = colors.input;
  for (const c of numeric) {
    sheet.getRange(`${column(c)}7:${column(c)}${end}`).setNumberFormat('0');
    sheet.getRange(`${column(c)}7:${column(c)}${end}`).format.horizontalAlignment = 'right';
    numericCells.push([sheet.name, c]);
  }
  rows.forEach((r, i) => {
    const lines = Math.max(...r.map((v, c) => textLines(v, widths[c])));
    const height = Math.max(37, lines * 14 + 13);
    if (height > 409) throw new Error(`Text exceeds Excel row-height capacity: ${sheet.name} row ${i + 7}`);
    sheet.getRange(`A${i+7}:${last}${i+7}`).format.rowHeight = height;
  });
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(2);
  specs.push({ name: sheet.name, rows: rows.length, columns: headers.length, end, tableName });
  return end;
}

const libraryHeaders = ['词条编号', '启用', '标准描述（可编辑）', '常见构件（可编辑）', '使用次数', '原文数量', '关联确认项', '来源编号', '备注（可编辑）'];
for (const [field, name] of [['observation', 'Observation'], ['recommendation', 'Recommendation']]) {
  const sh = sheets[name];
  const end = baseSheet(sh, `${name} 精简文字库`, '黄色列可编辑；已统一格式，语义合并尚未应用。常见构件显示使用最多的前三项，完整构件见原始记录。',
    libraryHeaders, data.library[field], [14, 9, 82, 42, 11, 11, 65, 65, 36], `${name}Library`, [1, 2, 3, 8], [4, 5]);
  sh.tabColor = colors.navy;
  sh.getRange(`B7:B${end}`).dataValidation = { rule: { type: 'list', values: ['是', '否'] } };
  sh.getRange('A4').formulas = [[`="词条 "&COUNTA(A7:A${end})&"；启用 "&COUNTIF(B7:B${end},"是")&"；原报告使用 "&SUM(E7:E${end})&" 次"`]];
}

const review = sheets['待确认合并'];
const reviewRows = data.review.map(r => [...r, '']);
const reviewEnd = baseSheet(review, '待确认合并项', '填写确认结果和最终标准文字。确认不会自动删除或合并文字库；全部变体可按合并项编号在确认项明细中查找。',
  ['合并项编号', '类别', '确认结果', '最终标准文字（可编辑）', '整理方式', '差异与建议', '关联词条编号', '描述 A', '描述 B 或样例', '保留变量（可编辑）', '备注（可编辑）', '来源编号', '处理状态'],
  reviewRows, [15, 18, 16, 86, 21, 55, 42, 82, 82, 35, 40, 45, 19], 'MergeReview', [2, 3, 9, 10]);
review.tabColor = '#B7791F';
review.getRange(`C7:C${reviewEnd}`).dataValidation = { rule: { type: 'list', values: ['待确认', '同意合并', '保持独立', '使用模板', '提取短句', '需修改'] } };
review.getRange('M7').formulas = [['=IF(C7="待确认","待确认",IF(C7="需修改","需修改",IF(C7="保持独立","已确认",IF(OR(C7="同意合并",C7="使用模板",C7="提取短句"),IF(LEN(TRIM(D7))=0,"缺少标准文字","已确认"),"无效选择"))))']];
review.getRange(`M7:M${reviewEnd}`).fillDown();
review.getRange(`M7:M${reviewEnd}`).conditionalFormats.add('containsText', { text: '缺少', format: { fill: '#FCE4D6', font: { color: '#9C2F19' } } });
review.getRange(`M7:M${reviewEnd}`).conditionalFormats.add('containsText', { text: '无效', format: { fill: '#FCE4D6', font: { color: '#9C2F19' } } });
review.getRange('A4').formulas = [[`="确认项 "&COUNTA(A7:A${reviewEnd})&"；已确认 "&COUNTIF(M7:M${reviewEnd},"已确认")&"；待处理 "&(COUNTA(A7:A${reviewEnd})-COUNTIF(M7:M${reviewEnd},"已确认"))`]];

baseSheet(sheets['确认项明细'], '确认项完整描述', '每条变体单独一行。按合并项编号筛选；这里保留整理时的完整描述快照，修改标准文字请到文字库或待确认合并页。',
  ['合并项编号', '类别', '词条编号', '完整描述快照', '使用次数', '来源编号'], data.review_details,
  [15, 19, 15, 108, 13, 52], 'ReviewVariants', [], [4]);
baseSheet(sheets['原始记录'], '原始逐条记录', '保留正式报告以及审阅和辅助文档的原始提取文字。精简库只统计正式报告；辅助原文没有对应正式词条时，精简编号留空。',
  ['原始记录编号', '类别', '原始文字', '构件', '来源编号', '精简词条编号', '源文件类别', '表格序号', '表内行号', '照片数', 'Condition Rating', 'Likelihood', 'Severity', 'Priority'],
  data.raw, [17, 19, 108, 38, 15, 17, 24, 12, 12, 11, 38, 22, 42, 22], 'OriginalRecords', [], [7, 8, 9]);
baseSheet(sheets['来源报告'], '来源报告索引', '报告路径相对于本项目的 reference_reports/REVA 文件夹。来源编号可与原始记录和文字库相互查找。',
  ['来源编号', '文件类别', '报告文件名', '相对路径', '检查构件组数'], data.sources,
  [15, 24, 88, 115, 19], 'ReportSources', [], [4]);

const guide = sheets['整理说明'];
guide.showGridLines = false;
guide.getRange('A2:B21').format.font = { name: font, size: 10, color: colors.ink };
guide.getRange('A2:B21').format.verticalAlignment = 'center';
guide.getRange('A2').values = [['报告文字库整理说明']];
guide.getRange('A2').format.font = { name: font, size: 14, bold: true, color: colors.ink };
guide.getRange('A2:B2').format.rowHeight = 28;
guide.getRange('A3').values = [['第一版仅应用格式整理；所有语义合并和模板化建议均保留待确认。']];
guide.getRange('A3').format.font = { name: font, size: 10, color: colors.muted };
guide.getRange('A2:A3').format.wrapText = false;
guide.getRange('A3:B3').format.rowHeight = 23;
guide.getRange('A2:A21').format.columnWidth = 33;
guide.getRange('B2:B21').format.columnWidth = 118;
guide.getRange('A5:B12').values = [
  ['工作表', '查看和编辑方式'],
  ['Observation 和 Recommendation', '黄色列可编辑。可以改标准描述、构件标签和备注，并用启用的下拉菜单决定是否保留词条。使用次数是整理时的历史频次。'],
  ['待确认合并', '在确认结果列选择待确认、同意合并、保持独立、使用模板、提取短句或需修改。合并、模板和短句操作需要填写最终标准文字。'],
  ['确认项明细', '筛选合并项编号查看全部完整变体，尤其适用于位置模板和多条建议共用一个短句的情况。'],
  ['原始记录', '保留原始文字、构件、评级、照片数和表格位置。正式记录与辅助记录分开标识，避免把审阅版本再次计入文字库频次。'],
  ['来源报告', '通过 SRC 编号找到报告文件和相对路径。原始 Word 文档以及原始 JSON 提取文件保持不变。'],
  ['确认后如何处理', '确认结果只是复核记录，不会自动合并或删除主文字库里的词条。确认完成后可依据决定生成下一版，避免交叉合并项产生冲突。'],
  ['保留现场差异', '程度、局部或全部范围、构件编号、数值、材料、处理方法、条件及章节引用均需保留。提取复用短句时，完整建议中的其他要求仍保留。'],
];
guide.getRange('A5:B5').format.fill = colors.navy;
guide.getRange('A5:B5').format.font = { name: font, size: 10, bold: true, color: '#FFFFFF' };
guide.getRange('A5:B5').format.rowHeight = 29;
guide.getRange('A5:B5').format.horizontalAlignment = 'center';
guide.getRange('A6:B12').format.wrapText = true;
guide.getRange('A6:B12').format.rowHeight = 49;
guide.getRange('A15').formulas = [[`="精简词条：Observation "&COUNTA('Observation'!A7:A${6+data.counts.observation})&"；Recommendation "&COUNTA('Recommendation'!A7:A${6+data.counts.recommendation})`]];
guide.getRange('A16').formulas = [[`="正式记录：Observation "&SUM('Observation'!E7:E${6+data.counts.observation})&"；Recommendation "&SUM('Recommendation'!E7:E${6+data.counts.recommendation})`]];
guide.getRange('A17').formulas = [[`="原始记录合计："&COUNTA('原始记录'!A7:A${6+data.counts.raw})&"；其中正式记录 "&COUNTIF('原始记录'!G7:G${6+data.counts.raw},"正式报告")&"；审阅或辅助记录 "&COUNTIF('原始记录'!G7:G${6+data.counts.raw},"审阅或辅助文档")`]];
guide.getRange('A18').formulas = [[`="确认项："&COUNTA('待确认合并'!A7:A${reviewEnd})&"；已确认 "&COUNTIF('待确认合并'!M7:M${reviewEnd},"已确认")`]];
guide.getRange('A19').values = [[`确认项包括：近似描述 ${data.review_methods['近似描述核对']} 项，位置模板 ${data.review_methods['位置模板']} 项，同义表达 ${data.review_methods['同义表达核对']} 项，复用短句 ${data.review_methods['提取复用短句']} 项。`]];
guide.getRange('A15:A19').format.wrapText = false;
guide.getRange('A15:B19').format.rowHeight = 25;

// Verify that editing decisions cannot appear complete with missing standard wording.
const oldChoice = review.getRange('C7').values[0][0];
const oldWording = review.getRange('D7').values[0][0];
const scenarios = [['同意合并', '', '缺少标准文字'], ['同意合并', 'Reviewed wording.', '已确认'], ['保持独立', '', '已确认'], ['需修改', 'Reviewed wording.', '需修改']];
for (const [choice, wording, expected] of scenarios) {
  review.getRange('C7').values = [[choice]];
  review.getRange('D7').values = [[wording]];
  const actual = review.getRange('M7').values[0][0];
  if (actual !== expected) throw new Error(`Decision status mismatch: ${actual} expected ${expected}`);
}
review.getRange('C7').values = [[oldChoice]];
review.getRange('D7').values = [[oldWording]];
wb.recalculate();

for (const name of ['Observation', 'Recommendation']) {
  const sum = sheets[name].getRange('A4').values[0][0];
  if (!String(sum).includes(name === 'Observation' ? '791' : '505')) throw new Error('Library frequency summary mismatch.');
}
if (review.getRange('M7').values[0][0] !== '待确认') throw new Error('Review sample was not restored.');
const errorScan = await wb.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 30 }, maxChars: 3500 });
await fs.writeFile(path.join(outDir, 'formula_check.json'), JSON.stringify(errorScan, null, 2));
console.log((await wb.inspect({ kind: 'table', range: '待确认合并!A4:F8', include: 'values,formulas', tableMaxRows: 5, tableMaxCols: 6, maxChars: 1800 })).ndjson);

const renderRanges = { Observation: 'A2:F10', Recommendation: 'A2:F10', '待确认合并': 'A2:F10', '确认项明细': 'A2:E10', '原始记录': 'A2:G10', '来源报告': 'A2:C10', '整理说明': 'A2:B19' };
for (const [name, range] of Object.entries(renderRanges)) {
  const preview = await wb.render({ sheetName: name, range, scale: 1.25, format: 'png' });
  await fs.writeFile(path.join(outDir, `preview_${name}.png`), new Uint8Array(await preview.arrayBuffer()));
  console.log(`Rendered ${name}`);
}
const outputPath = path.join(outDir, '报告文字库_精简初稿.xlsx');
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outputPath);
await fs.writeFile(path.join(outDir, 'workbook_spec.json'), JSON.stringify({ outputPath, sheets: specs, counts: data.counts, reviewMethods: data.review_methods, scenariosTested: scenarios.length }, null, 2));
console.log(JSON.stringify({ outputPath, counts: data.counts, reviewMethods: data.review_methods }));
