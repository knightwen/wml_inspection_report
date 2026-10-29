'use strict';
let playwright;try{playwright=require('playwright');}catch{playwright=require('../.build/browser-deps/node_modules/playwright');}
const {chromium}=playwright,assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn,execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),qa=path.join(root,'.build/qa');fs.mkdirSync(qa,{recursive:true});
const folder=fs.mkdtempSync(path.join(qa,'layout-browser-')),python=process.env.WML_TEST_PYTHON||'python';
const server=spawn(python,[path.join(__dirname,'browser_test_server.py'),'--data-dir',folder],{cwd:root,windowsHide:true});
let browser,context,base,state;const errors=[];
const saved=page=>page.waitForFunction(()=>['已保存到本地','Saved locally'].includes(document.querySelector('#saveStatus')?.textContent)&&!document.querySelector('#templateSelect').disabled);
(async()=>{
 state=await new Promise((resolve,reject)=>{let text='';server.stdout.on('data',b=>{text+=b.toString();if(text.includes('\n'))resolve(JSON.parse(text.split('\n')[0]));});server.on('error',reject);server.on('exit',code=>reject(new Error('Server exited '+code)));setTimeout(()=>reject(new Error('Startup timeout')),15000).unref();});
 base='http://127.0.0.1:'+state.port;browser=await chromium.launch({channel:process.env.WML_TEST_BROWSER_CHANNEL==='chromium'?undefined:'msedge',headless:true});
 context=await browser.newContext({viewport:{width:1600,height:1100},acceptDownloads:true});const page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/?key='+state.token);await saved(page);
 assert.equal(await page.locator('.brand small').count(),0);assert.equal(await page.locator('.topbar #libraryButton').count(),0);assert(await page.locator('#inspectionWorkspace #libraryButton').isVisible());
 assert.deepEqual(await page.locator('#inspectionTree > button').allTextContents(),['1  项目介绍','2  外部建筑检查记录','3  修复工程建议','4  结论','5  费用估算说明']);
 assert.equal(await page.locator('#rating_element option[value="Columns"]').textContent(),'柱');assert.equal(await page.locator('#rating_priority option[value="High"]').textContent(),'高');
 assert(await page.locator('.subitems-container #subitemList').isVisible());assert(await page.locator('.subitems-container .editor-grid').isVisible());
 const before=await page.locator('#newProject').boundingBox();await page.locator('#meta_site').fill('A very long report name '.repeat(25));await saved(page);const after=await page.locator('#newProject').boundingBox();assert.equal(before.x,after.x);assert.equal(before.width,after.width);
 for(const width of [1600,1024,768,390]){await page.setViewportSize({width,height:1100});assert(await page.locator('#newProject').isVisible());assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1),'Horizontal page overflow at '+width);}
 await page.setViewportSize({width:1600,height:1100});await page.locator('#meta_site').fill('Rich inspection browser QA');await page.locator('#meta_project_number').fill('QA');await page.locator('#meta_report_number').fill('QA-01');
 await page.locator('#inspectionTree > button').nth(0).click();await page.locator('#section_introduction').fill('Introduction block retained.');
 await page.locator('#sectionTools_introduction').getByRole('button',{name:'＋ 表格',exact:true}).click();await page.locator('#sectionBlocks_introduction summary').click();await page.getByLabel('复制 Excel 单元格并粘贴到这里').fill('Name\tValue\nLoad\t=1+1');await page.getByRole('button',{name:'应用粘贴内容',exact:true}).click();
 const fixture=path.join(folder,'image.png');execFileSync(python,['-c','from PIL import Image;import sys;Image.new("RGB",(700,400),"#7eaa6c").save(sys.argv[1])',fixture],{windowsHide:true});
 await page.locator('#sectionBlocks_introduction input[type=file]').setInputFiles(fixture);await page.locator('#sectionBlocks_introduction .cal-content-image').waitFor();await page.getByLabel('图注',{exact:true}).fill('Inspection chapter figure');await saved(page);
 const draft=await page.locator('#projectSelect').inputValue();await page.reload();await saved(page);await page.locator('#inspectionTree > button').nth(0).click();assert.equal(await page.locator('#section_introduction').inputValue(),'Introduction block retained.');assert.equal(await page.getByLabel('单元格 2,2',{exact:true}).inputValue(),'=1+1');
 await page.locator('#inspectionTree > button').nth(1).click();await page.locator('#photoFiles').setInputFiles(fixture);await page.locator('#photoGrid img').waitFor();await saved(page);
 for(const [key,value] of Object.entries({element:'Columns',condition_rating:'3. Minor corrosion',likelihood:'Possible',severity:'Minor',priority:'Low'}))await page.locator('#rating_'+key).selectOption(value);
 await page.locator('#observationText').fill('Recorded condition.');await page.locator('#saveItem').click();await saved(page);assert.equal(await page.locator('.inspection-tree-parent').count(),1);assert.equal(await page.locator('.inspection-tree-child').count(),1);
 const download=page.waitForEvent('download');await page.locator('#generateButton').click();await (await download).saveAs(path.join(qa,'rich-inspection-browser.docx'));
 await page.locator('#inspectionTree > button').nth(0).click();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(qa,'inspection-rich-workspace.png'),fullPage:true});
 const backup=page.waitForEvent('download');await page.locator('#backupButton').click();const zip=path.join(folder,'rich.inspection.zip');await (await backup).saveAs(zip);await page.locator('#restoreFile').setInputFiles(zip);await saved(page);await page.locator('#inspectionTree > button').nth(0).click();assert.equal(await page.locator('#sectionBlocks_introduction .cal-block').count(),3);assert.equal(await page.getByLabel('图注',{exact:true}).inputValue(),'Inspection chapter figure');
 await page.locator('#templateSelect').selectOption('calculation');await saved(page);assert.equal(await page.locator('#calCoverReportTitle').count(),0);assert.equal(await page.getByRole('button',{name:'未命名模块',exact:true}).count(),2);
 const roles=await page.locator('#metadataFields').evaluate(el=>[...el.children].filter(c=>c.getBoundingClientRect().height).map(c=>c.querySelector('input,select')?.id));assert.deepEqual(roles.slice(-2),['meta_prepared_by','meta_reviewed_by']);
 const title=await page.locator('#calModuleTitle').boundingBox(),pagebreak=await page.locator('.chapter-heading .cal-checkbox').boundingBox();assert(Math.abs(title.y-pagebreak.y)<20);
 const rows=await page.locator('#calEditor > .cal-editor-tools > button').evaluateAll(buttons=>buttons.map(b=>Math.round(b.getBoundingClientRect().y)));assert.equal(new Set(rows).size,1);
 await page.locator('#calModuleTitle').fill('Renamed inline');assert((await page.locator('#calTree').textContent()).includes('Renamed inline'));await saved(page);
 await page.getByRole('button',{name:'未命名模块',exact:true}).first().click();await page.locator('#calModuleTitle').fill('Custom cover module');await page.locator('#calEditor').getByRole('button',{name:'＋ 文字',exact:true}).click();await page.getByLabel('章节文字',{exact:true}).fill('Cover module text.');await saved(page);
 await page.locator('#calEditor').evaluate(async host=>{const canvas=document.createElement('canvas');canvas.width=80;canvas.height=60;const blob=await new Promise(resolve=>canvas.toBlob(resolve));const data=new DataTransfer();data.items.add(new File([blob],'pasted.png',{type:'image/png'}));host.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,clipboardData:data}));});await page.locator('#calEditor .cal-content-image').waitFor();await saved(page);
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(qa,'cal-cover-tree-workspace.png'),fullPage:true});
 await page.locator('#templateSelect').selectOption('inspection');await saved(page);await page.locator('#projectSelect').selectOption(draft);await saved(page);
 await page.locator('#languageSelect').selectOption('en');await saved(page);assert.equal(await page.locator('#rating_element option[value="Columns"]').textContent(),'Columns');assert.equal(await page.locator('#rating_priority option[value="High"]').textContent(),'High');
 assert.deepEqual(await page.locator('#inspectionTree > button').allTextContents(),['1  Introduction','2  External Building Observations','3  Recommended Remedial Works','4  Conclusion','5  Cost Estimate']);
 const english=await page.locator('header strong, header button, #saveStatus, .report-toolbar label, .report-toolbar button, #metadataFields label, #ratingFields label, .column-title, #inspectionTree > button').allTextContents();assert(!/[\u4e00-\u9fff]/.test(english.join(' ')),english.join(' '));
 assert.deepEqual(errors,[]);console.log('Workspace layout, Chinese/English UI, ordered chapter tree, rich inspection content, backups, shared header, long titles, responsive layout and CAL cover/inline title passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
 if(context){for(const p of context.pages())p.on('dialog',d=>d.accept());await context.close();}if(browser)await browser.close();
 if(base&&state)await fetch(base+'/api/shutdown',{method:'POST',headers:{Cookie:'workbench='+state.token,'X-Workbench':'1'}}).catch(()=>{});server.kill();
});
