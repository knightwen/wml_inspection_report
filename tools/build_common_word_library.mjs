// Rebuild the editable common wording workbook from the shipped JSON library.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook, SpreadsheetFile, FileBlob} from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const resources = path.join(root, 'workbench/resources');
const qa = path.join(root, '.build/qa/common-library');
await fs.mkdir(qa, {recursive:true});
if (process.argv.includes('--inspect-existing')) {
  const old = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(resources, 'word_library.xlsx')));
  console.log((await old.inspect({kind:'sheet',include:'id,name',maxChars:1800})).ndjson);
  for (const name of ['Observation','Recommendation']) {
    const preview = await old.render({sheetName:name,range:'A1:E10',scale:1,format:'png'});
    await fs.writeFile(path.join(qa, `before-${name}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
  process.exit(0);
}
const library = JSON.parse(await fs.readFile(path.join(resources,'library.json'),'utf8'));
const wb = Workbook.create();
const sheets = {};
for (const [key,name] of [['observation','Observation'],['recommendation','Recommendation']]) {
  const rows = library[key].map(r=>[r.id,'是',r.text,r.elements,r.frequency]);
  const sheet = wb.worksheets.add(name);
  sheets[name] = sheet;
  const end = rows.length + 6;
  sheet.showGridLines = false;
  sheet.getRange(`A2:E${end}`).format.font = {name:'Microsoft YaHei',size:10,color:'#172B40'};
  sheet.getRange(`A2:E${end}`).format.verticalAlignment = 'center';
  sheet.getRange('C2').values = [[`${name} 常用措辞`]];
  sheet.getRange('C2').format.font = {name:'Microsoft YaHei',size:14,bold:true,color:'#172B40'};
  sheet.getRange('C3').values = [['筛选标准：历史报告出现至少 2 次。保留原词条编号。']];
  sheet.getRange('C5').values = [['黄色列可编辑；新增从第 7 行起填写 A–D 列，编号须唯一。']];
  sheet.getRange('C3:C5').format.font = {name:'Microsoft YaHei',size:10,color:'#64748B'};
  sheet.getRange('A4').formulas = [[`="词条 "&COUNTA(A7:A${end})&"；启用 "&COUNTIF(B7:B${end},"是")`]];
  sheet.getRange('A6:E6').values = [['词条编号','启用','常用描述（可编辑）','常见构件（可编辑）','历史次数']];
  sheet.getRange(`A7:E${end}`).values = rows;
  const table = sheet.tables.add(`A6:E${end}`,true,`${name}Library`);
  table.style = 'TableStyleLight9';
  table.showFilterButton = true;
  sheet.getRange('A6:E6').format = {fill:'#263B53',font:{name:'Microsoft YaHei',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true,rowHeight:34};
  sheet.getRange('A6:E6').format.borders = {insideVertical:{style:'thin',color:'#FFFFFF'}};
  for (const [col,width] of [['A',14],['B',9],['C',82],['D',42],['E',12]]) {
    sheet.getRange(`${col}2:${col}${end}`).format.columnWidth = width;
  }
  sheet.getRange(`A7:E${end}`).format.wrapText = true;
  sheet.getRange(`A7:E${end}`).format.verticalAlignment = 'top';
  sheet.getRange(`B7:D${end}`).format.fill = '#FFF5D6';
  sheet.getRange(`E7:E${end}`).setNumberFormat('0');
  sheet.getRange(`E7:E${end}`).format.horizontalAlignment = 'right';
  sheet.getRange(`B7:B${end}`).dataValidation = {rule:{type:'list',values:['是','否']}};
  rows.forEach((r,i)=>{
    const lines = Math.max(Math.ceil(r[2].length/70),Math.ceil(r[3].length/35));
    sheet.getRange(`A${i+7}:E${i+7}`).format.rowHeight = Math.max(38,lines*15+12);
  });
  sheet.freezePanes.freezeRows(6);
  sheet.freezePanes.freezeColumns(2);
  sheet.getRange('B7').values = [['否']];
  if (sheet.getRange('A4').values[0][0] !== `词条 ${rows.length}；启用 ${rows.length-1}`) throw new Error('Enabled count did not respond to edit');
  sheet.getRange('B7').values = [['是']];
}
wb.recalculate();
for (const [key,name] of [['observation','Observation'],['recommendation','Recommendation']]) {
  const sheet = sheets[name];
  if (sheet.getRange('A4').values[0][0] !== `词条 ${library[key].length}；启用 ${library[key].length}`) throw new Error('Summary did not recalculate');
  console.log((await wb.inspect({kind:'table',range:`${name}!A6:E10`,include:'values,formulas',tableMaxRows:5,tableMaxCols:5,maxChars:1200})).ndjson);
  const preview = await wb.render({sheetName:name,range:'A1:E12',scale:1,format:'png'});
  await fs.writeFile(path.join(qa,`after-${name}.png`),new Uint8Array(await preview.arrayBuffer()));
}
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
const destination = path.join(resources,'word_library.xlsx');
await (await SpreadsheetFile.exportXlsx(wb)).save(destination);
// The exporter's inspection sidecar is authoring output, not a runtime resource.
await fs.rm(destination+'.inspect.ndjson',{force:true});
console.log('Saved common wording workbook.');
