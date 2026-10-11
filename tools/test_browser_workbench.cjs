'use strict';
let playwright;try{playwright=require('playwright');}catch{playwright=require('../.build/browser-deps/node_modules/playwright');}const {chromium}=playwright;
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),qa=path.join(root,'.build','qa'),folder=fs.mkdtempSync(path.join(qa,'browser-'));
const python=process.env.WML_TEST_PYTHON||'python';
const server=spawn(python,[path.join(__dirname,'browser_test_server.py'),'--data-dir',folder],{cwd:root,windowsHide:true});
let browser,context,state,base,errors=[];
const saved=page=>page.locator('#saveStatus').filter({hasText:'已保存到本地'}).waitFor();
async function seedItem(page,text,fixture){
 await page.locator('#photoFiles').setInputFiles(fixture);await page.locator('#photoGrid img').first().waitFor();
 for(const [key,value] of Object.entries({element:'Columns',condition_rating:'5. Major deterioration',likelihood:'Likely',severity:'Severe',priority:'High'}))await page.locator('#rating_'+key).selectOption(value);
 await page.locator('#observationText').fill(text);await page.locator('#recommendationText').fill('Repair the recorded condition.');
}
(async()=>{
 state=await new Promise((resolve,reject)=>{let data='';server.stdout.on('data',b=>{data+=b.toString();if(data.includes('\n'))resolve(JSON.parse(data.split('\n')[0]));});server.on('error',reject);server.on('exit',code=>reject(new Error('QA server exited '+code)));setTimeout(()=>reject(new Error('QA server timeout')),15000).unref();});
 base='http://127.0.0.1:'+state.port;
 const channel=process.env.WML_TEST_BROWSER_CHANNEL||'msedge';
 browser=await chromium.launch({...(channel==='chromium'?{}:{channel}),headless:true});context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 context.on('page',p=>{p.setDefaultTimeout(12000);p.on('dialog',d=>d.accept());});const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base+'/?key='+state.token);await saved(page);
 await page.locator('#languageSelect').selectOption('en');await page.locator('#saveStatus').filter({hasText:'Saved locally'}).waitFor();assert.equal(await page.locator('html').getAttribute('lang'),'en-AU');
 const bilingualText='Browser draft / 中文手动内容';await page.locator('#meta_site').fill(bilingualText);await page.locator('#languageSelect').selectOption('zh');await saved(page);assert.equal(await page.locator('#meta_site').inputValue(),bilingualText);
 assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');
 await page.locator('#meta_site').fill('Browser Regression');await page.locator('#meta_report_number').fill('QA-BROWSER');await page.locator('#meta_project_number').fill('QA');await saved(page);

 for(const key of ['introduction','remedial_works','conclusion','cost_estimate'])await page.locator('#section_'+key).fill(key+' paragraph one.\n\nSecond paragraph.');
 await page.locator('#saveSections').click();await saved(page);await page.reload();await page.waitForFunction(()=>document.querySelector('#section_introduction')?.value==='introduction paragraph one.\n\nSecond paragraph.');await saved(page);
 for(const key of ['introduction','remedial_works','conclusion','cost_estimate'])assert.equal(await page.locator('#section_'+key).inputValue(),key+' paragraph one.\n\nSecond paragraph.');

 await page.locator('#addCostRow').click();for(const [key,value] of Object.entries({description:'Cost browser test',quantity:'3',unit:'each',rate:'0.335'}))await page.getByLabel('费用项 1 '+key,{exact:true}).fill(value);await page.getByLabel('费用项 1 priority',{exact:true}).selectOption('High');assert((await page.locator('#costTotal').textContent()).includes('1.01'));await page.locator('#saveSections').click();await saved(page);await page.reload();await page.waitForFunction(()=>document.querySelector('#costTotal')?.textContent.includes('1.01'));assert.equal(await page.getByLabel('费用项 1 description',{exact:true}).inputValue(),'Cost browser test');
 await page.locator('#managePersonnel').click();await page.locator('#personnel_qualifications').fill('Old qualification');await page.locator('#personnel_title').fill('Old title');await page.locator('#savePersonnel').click();await page.locator('#closePersonnel').click();
 const person=await page.locator('#meta_prepared_by option').nth(1).getAttribute('value');await page.locator('#meta_prepared_by').selectOption(person);assert((await page.locator('#details_prepared_by').textContent()).includes('Old qualification'));
 await page.locator('#meta_prepared_by').selectOption('__manual__');await page.locator('#manual_prepared_by').fill('Manual Browser Author');assert(await page.locator('#details_prepared_by').isHidden());await saved(page);
 for(const id of ['observation','recommendation']){await page.locator('#'+id+'Select').selectOption({index:1});await page.locator('#'+id+'Select').selectOption({index:2});assert((await page.locator('#'+id+'Text').inputValue()).length>0);}
 const fixture=path.join(qa,'upload-fixtures','landscape.jpg');await seedItem(page,'FIRST browser condition',fixture);
 await page.locator('#photoGrid button').filter({hasText:'编辑'}).first().click();await page.locator('#photoToolCircle').click();
 const canvas=await page.locator('#photoEditCanvas').boundingBox();await page.mouse.move(canvas.x+canvas.width*.25,canvas.y+canvas.height*.25);await page.mouse.down();await page.mouse.move(canvas.x+canvas.width*.6,canvas.y+canvas.height*.6,{steps:10});await page.mouse.up();await page.locator('#savePhotoEdit').click();
 await page.locator('#saveItem').click();await page.locator('#savedItems .saved-item').first().waitFor();
 await seedItem(page,'SECOND browser condition',fixture);await page.locator('#saveItem').click();await saved(page);
 await page.locator('#reportSections summary').click();await page.locator('#savedItems').scrollIntoViewIfNeeded();
 const handles=page.locator('#savedItems .item-drag-handle');assert.equal(await handles.count(),2);
 const a=await handles.nth(0).boundingBox(),b=await handles.nth(1).boundingBox();await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height+10,{steps:15});await page.mouse.up();await saved(page);
 assert((await page.locator('#savedItems').textContent()).indexOf('SECOND')<(await page.locator('#savedItems').textContent()).indexOf('FIRST'));
 // The first request is delayed while newer edits are made. No false "saved" state.
 let delayed=false;await page.route('**/api/save',async route=>{if(!delayed){delayed=true;await new Promise(r=>setTimeout(r,1200));}await route.continue();});
 await page.locator('#meta_site').fill('Queued A');await page.locator('#saveStatus').filter({hasText:'正在保存'}).waitFor();await page.locator('#meta_site').fill('Queued B');
 assert(await page.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}));await saved(page);assert.equal(await page.locator('#meta_site').inputValue(),'Queued B');await page.unroute('**/api/save');
 await page.route('**/api/save',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'QA temporary save failure'})}));
 await page.locator('#meta_site').fill('Recoverable save failure');await page.locator('#retrySave').waitFor({state:'visible'});assert.equal(await page.locator('#meta_site').inputValue(),'Recoverable save failure');
 await page.unroute('**/api/save');await page.locator('#retrySave').click();await saved(page);
 // A second page wins an optimistic revision race; local changes are recoverable.
 const other=await context.newPage();await other.goto(base+'/?key='+state.token);await saved(other);await other.locator('#meta_site').fill('REMOTE SAVED');await saved(other);
 await page.locator('#meta_site').fill('LOCAL UNSAVED');await page.locator('#saveConflictDialog').waitFor({state:'visible'});
 const download=page.waitForEvent('download');await page.locator('#conflictDownload').click();const downloaded=await download;assert((await downloaded.path())!==null);
 await page.locator('#conflictCopy').click();await saved(page);assert.equal(await page.locator('#meta_site').inputValue(),'LOCAL UNSAVED');assert((await page.locator('#savedItems').textContent()).includes('SECOND'));
 // Preview uses a fixed snapshot while a subsequent edit is saved independently.
 await page.locator('#previewButton').click();await page.locator('#previewProgress').filter({hasText:'转换'}).waitFor();await page.locator('#closeReportPreview').click();
 await page.locator('#meta_site').fill('EDIT DURING PREVIEW');await saved(page);await page.locator('#previewButton').click();await page.locator('#previewProgress').filter({hasText:'预览已完成'}).waitFor();assert((await page.locator('#previewSnapshot').textContent()).includes('LOCAL UNSAVED'));assert(await page.locator('#downloadPreviewWord').isVisible());
 await page.screenshot({path:path.join(qa,'browser-stability.png'),fullPage:true});await page.locator('#closeReportPreview').click();
 await page.locator('#meta_site').fill('QA FAIL PREVIEW');await saved(page);await page.locator('#previewButton').click();await page.locator('#retryPreview').click();await page.locator('#previewProgress').filter({hasText:'QA conversion failure'}).waitFor();
 await page.locator('#closeReportPreview').click();await page.locator('#meta_site').fill('Recovered preview');await saved(page);await page.locator('#previewButton').click();await page.locator('#previewProgress').filter({hasText:'预览已完成'}).waitFor();await page.locator('#closeReportPreview').click();
 assert.deepEqual(errors,[]);await other.close();await page.close();
 fs.writeFileSync(path.join(qa,'browser-stability-result.json'),JSON.stringify({status:'passed',checks:['personnel selection and manual clearing','continuous wording selection','photo annotation','item drag sorting','rapid saves and beforeunload','save failure and retry','two-page conflict and ZIP recovery/copy','background preview with concurrent save and fixed snapshot','preview failure and retry'],preview_converter:'controlled fixture; PDFium renderer real'},null,2));
 console.log('Browser stability regression passed.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(state){await fetch(base+'/api/shutdown',{method:'POST',headers:{'Cookie':'workbench='+state.token,'X-Workbench':'1','Content-Type':'application/json'},body:'{}'}).catch(()=>{});}else server.kill();if(browser)await browser.close();});
