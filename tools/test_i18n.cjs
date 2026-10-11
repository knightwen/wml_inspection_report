'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const web=path.join(__dirname,'../workbench/web');
function load(search,saved,englishOnly=false){
 const storage=new Map(saved?[['workbenchLanguage',saved]]:[]);
 const title={firstChild:{nodeType:3,nodeValue:'报告信息'},dataset:{i18n:'报告信息'}};
 const role={nextSibling:{nodeType:3,nodeValue:'作者'},dataset:{i18nTail:'作者'}};
 const placeholder={value:'用户手动输入内容',attributes:{'data-i18n-placeholder':'照片名称（可留空）'},getAttribute(k){return this.attributes[k];},setAttribute(k,v){this.attributes[k]=v;}};
 const document={documentElement:{},querySelectorAll(selector){return selector==='[data-i18n]'?[title]:selector==='[data-i18n-tail]'?[role]:selector==='[data-i18n-placeholder]'?[placeholder]:[];}};
 const context={WorkbenchInterface:{englishOnly},URLSearchParams,location:{search},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},document};context.window=context;
 vm.createContext(context);for(const file of ['translations-en.js','i18n.js'])vm.runInContext(fs.readFileSync(path.join(web,file),'utf8'),context);
 return {ui:context.WorkbenchI18n,title,role,placeholder,document,storage};
}
const en=load('?lang=en','zh');en.ui.apply();
assert.equal(en.ui.language,'en');assert.equal(en.document.documentElement.lang,'en-AU');
assert.equal(en.title.firstChild.nodeValue,'Report details');assert.equal(en.role.nextSibling.nodeValue,'author');
assert.equal(en.placeholder.attributes.placeholder,'Photo caption (optional)');assert.equal(en.placeholder.value,'用户手动输入内容');
assert.equal(en.ui.t('费用项 {0} {1}',3,'quantity'),'Cost item 3 quantity');
assert.equal(en.ui.t('正在渲染第 2 / 10 页…'),'Rendering page 2 / 10…');
assert.equal(en.ui.t('Excel 缺少 Observation 工作表'),'Excel worksheet missing: Observation');
assert.equal(en.ui.t('Word 模板缺少章节：C1.[A]+'),'The Word template is missing section: C1.[A]+');
assert.equal(en.ui.t('My unrecognised message'),'My unrecognised message');
assert.equal(load('','en').ui.language,'en');assert.equal(load('?lang=invalid','en').ui.language,'en');
assert.equal(load('?lang=zh','zh',true).ui.language,'en');
assert.equal(load('?lang=zh','zh',true).storage.get('workbenchLanguage'),'zh');
const zh=load('?lang=zh','en');zh.ui.apply();assert.equal(zh.ui.language,'zh');assert.equal(zh.title.firstChild.nodeValue,'报告信息');
assert.equal(zh.ui.t('费用项 {0} {1}',3,'quantity'),'费用项 3 quantity');
en.ui.remember('zh');assert.equal(en.storage.get('workbenchLanguage'),'zh');en.ui.remember('invalid');assert.equal(en.storage.get('workbenchLanguage'),'zh');
console.log('Language selection, static labels, dynamic server messages and user-content preservation passed.');
