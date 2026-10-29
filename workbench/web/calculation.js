'use strict';
// The CAL editor owns per-draft modules; persistence and conflicts use the shared saver.
(function(root){
 const uid=()=>crypto.randomUUID().replaceAll('-','');
 const label=(zh,en)=>root.WorkbenchI18n.language==='en'?en:zh;
 const $=id=>document.getElementById(id);
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 let config,active=null,drag=null;
 const blankModule=()=>({id:uid(),title:label('新章节','New chapter'),page_break:false,blocks:[],children:[]});
 const walk=(nodes,prefix=[])=>nodes.flatMap((m,i)=>[{module:m,number:[...prefix,i+1].join('.'),siblings:nodes,index:i},...walk(m.children,[...prefix,i+1])]);
 const project=()=>config.getProject();
 const entries=()=>walk(project().modules);
 const coverEntries=()=>project().cal_cover.modules.map((module,index)=>({module,index,number:'',siblings:project().cal_cover.modules,cover:true}));
 const selected=()=>[...entries(),...coverEntries()].find(e=>e.module.id===active);
 const button=(text,fn,cls)=>{const b=el('button',text,cls);b.type='button';b.onclick=config.action(fn);return b;};
 const changed=()=>config.schedule();
 function parseTable(text){
  // Excel quotes cells containing tabs/newlines and doubles embedded quotes.
  const rows=[];let row=[],cell='',quoted=false;
  text=text.replace(/\r\n/g,'\n').replace(/\r/g,'\n');
  for(let i=0;i<text.length;i++){
   const c=text[i];
   if(c==='"'&&(quoted||cell==='')){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
   else if(!quoted&&(c==='\t'||c==='\n')){row.push(cell);cell='';if(c==='\n'){rows.push(row);row=[];}}
   else cell+=c;
  }
  if(cell!==''||row.length){row.push(cell);rows.push(row);}
  if(!rows.length)return [['']];
  const columns=Math.max(...rows.map(r=>r.length));
  if(columns>20||rows.length>200||rows.some(r=>r.some(c=>c.length>2000)))throw new Error(label('表格最多 200 行、20 列，每格 2000 字符','Maximum 200 rows, 20 columns and 2,000 characters per cell'));
  return rows.map(r=>Array.from({length:columns},(_,i)=>r[i]||''));
 }
 function renderTree(){
  const tree=$('calTree');tree.replaceChildren();
  const coverHeading=el('div',undefined,'cal-outline-heading');coverHeading.append(el('h3',label('封面','Cover')),button(label('＋ 模块','+ Module'),async()=>{const m={id:uid(),title:'',blocks:[]};project().cal_cover.modules.push(m);active=m.id;render();changed();}));tree.append(coverHeading);
  for(const entry of coverEntries()){
   const row=el('div',undefined,'cal-tree-row cal-cover-row'+(entry.module.id===active?' active':''));
   const select=button(entry.module.title||label('未命名模块','Untitled module'),async()=>{active=entry.module.id;render();},'cal-tree-select');select.setAttribute('aria-pressed',String(active===entry.module.id));row.append(select);tree.append(row);
  }
  const revisions=button(label('修订记录','Revision history'),async()=>{active='cover-revisions';render();},'cal-tree-select');revisions.classList.toggle('active',active==='cover-revisions');tree.append(revisions,el('h3',label('正文','Body'),'tree-group-title'));
  for(const entry of entries()){
   const {module,number,siblings,index}=entry;
   const row=el('div',undefined,'cal-tree-row'+(module.id===active?' active':''));row.style.paddingLeft=(number.split('.').length-1)*16+'px';
   const handle=el('span','⠿','cal-drag');handle.draggable=true;handle.setAttribute('aria-label',label('拖动章节','Drag chapter'));handle.title=label('拖动调整同级顺序','Drag to reorder siblings');
   handle.ondragstart=e=>{drag=module.id;e.dataTransfer.setData('text/plain',module.id);e.dataTransfer.effectAllowed='move';};handle.ondragend=()=>{drag=null;};
   row.ondragover=e=>{if(entries().find(x=>x.module.id===drag)?.siblings===siblings)e.preventDefault();};
   row.ondrop=config.action(async e=>{e.preventDefault();const source=entries().find(x=>x.module.id===drag);if(source?.siblings!==siblings||source.module===module)return;source.siblings.splice(source.index,1);siblings.splice(siblings.indexOf(module),0,source.module);renderTree();renderEditor();changed();});
   const select=button(number+'  '+module.title,async()=>{active=module.id;render();},'cal-tree-select');select.setAttribute('aria-pressed',String(active===module.id));row.append(handle,select);tree.append(row);
  }
  if(!project().modules.length)tree.append(el('p',label('添加章节开始编辑','Add a chapter to begin')));
 }
 function field(title,input){const box=el('label',title,'cal-field');box.append(input);return box;}
 function input(value,onInput,options={}){const n=el(options.multiline?'textarea':'input');n.value=value;n.maxLength=options.max||60000;if(options.multiline)n.rows=options.rows||5;n.oninput=()=>{onInput(n.value);changed();};return n;}
 async function move(direction){const e=selected();if(!e)return;const at=e.index+direction;if(at<0||at>=e.siblings.length)return;[e.siblings[e.index],e.siblings[at]]=[e.siblings[at],e.siblings[e.index]];renderTree();renderEditor();changed();}
 function renderEditor(){
  const host=$('calEditor');host.onpaste=null;host.replaceChildren();const entry=selected();
  if(active==='cover-revisions'){
   host.append(el('h2',label('修订记录','Revision history')));const revisions=el('div');revisions.id='calRevisions';host.append(revisions,button(label('＋ 修订记录','+ Revision'),async()=>{project().cal_cover.revisions.push({revision:'',date:'',status:'',designed:'',checked:'',approved:''});renderRevisions();changed();}));renderRevisions();return;
  }
  if(!entry){host.append(el('p',label('选择或添加章节。','Select or add a chapter.')));return;}
  const module=entry.module,heading=el('div',undefined,'chapter-heading');
  if(!entry.cover)heading.append(el('span',entry.number,'chapter-number'));
  const title=el('input');title.value=module.title;title.maxLength=500;title.id='calModuleTitle';title.className='chapter-name';title.placeholder=label('填写模块标题','Enter a module title');title.setAttribute('aria-label',label('章节名称','Chapter name'));
  title.oninput=()=>{if(entry.cover||title.value.trim()){module.title=title.value;renderTree();changed();}};
  title.onblur=()=>{if(!entry.cover&&!title.value.trim())title.value=module.title;};title.onkeydown=e=>{if(e.key==='Enter')title.blur();};heading.append(title);
  if(!entry.cover){const page=el('input');page.type='checkbox';page.checked=module.page_break;page.onchange=()=>{module.page_break=page.checked;changed();};const pageLabel=field(label('从新页开始','Start on a new page'),page);pageLabel.classList.add('cal-checkbox');heading.append(pageLabel);}
  host.append(heading);
  const tools=el('div',undefined,'cal-editor-tools');
  tools.append(button('↑',()=>move(-1)),button('↓',()=>move(1)));
  if(!entry.cover)tools.append(button(label('增加缩进','Indent'),async()=>{
   const e=selected();if(!e||!e.index||e.cover)return;
   const previous=e.siblings[e.index-1];const deepest=walk([e.module]).reduce((n,x)=>Math.max(n,x.number.split('.').length),0);
   if(e.number.split('.').length+deepest>6)throw new Error(label('章节最多六级','Maximum six chapter levels'));
   e.siblings.splice(e.index,1);previous.children.push(e.module);render();changed();
  }),button(label('减少缩进','Outdent'),async()=>{
   const e=selected(),parent=entries().find(x=>x.module.children===e?.siblings);if(!parent)return;
   e.siblings.splice(e.index,1);parent.siblings.splice(parent.index+1,0,e.module);render();changed();
  }));
  if(!entry.cover)tools.append(button(label('＋ 子章节','+ Subchapter'),async()=>{if(entry.number.split('.').length>=6)return;const m=blankModule();module.children.push(m);active=m.id;render();changed();}));
  tools.append(button(label('删除章节','Delete chapter'),async()=>{
   if(!await config.confirm(label('删除章节','Delete chapter'),label('同时删除该章节下的内容和子章节？','Delete this chapter, its content and subchapters?')))return;
   const current=selected();if(!current)return;current.siblings.splice(current.index,1);active=(entry.cover?coverEntries():entries())[0]?.module.id;render();changed();
  },'quiet'));
  host.append(tools);const blocks=el('div',undefined,'cal-blocks');host.append(blocks);
  root.ContentBlocks.render(blocks,module.blocks,config,tools,{fileInput:$('calImageFiles'),pasteTarget:host});
 }

 function renderRevisions(){
  const host=$('calRevisions');host.replaceChildren();
  const table=el('table',undefined,'cal-content-table'),head=el('tr'),keys=['revision','date','status','designed','checked','approved'];
  for(const key of keys)head.append(el('th',label({revision:'版本',date:'日期',status:'状态',designed:'设计',checked:'校核',approved:'批准'}[key],key.toUpperCase())));head.append(el('th',''));table.append(head);
  project().cal_cover.revisions.forEach((row,index)=>{const tr=el('tr');for(const key of keys){const cell=el('td');cell.append(input(row[key]||'',v=>row[key]=v,{max:500}));tr.append(cell);}const del=el('td');del.append(button('×',async()=>{project().cal_cover.revisions.splice(index,1);renderRevisions();changed();}));tr.append(del);table.append(tr);});host.append(table);
 }
 function render(){
  const cal=project()?.template_id==='calculation';document.body.dataset.reportType=cal?'calculation':'inspection';$('calWorkspace').hidden=!cal;
  document.querySelector('.brand strong').textContent='WML Report Workbench';
  document.title='WML Report Workbench · '+label(cal?'计算报告':'检查报告',cal?'Calculation Report':'Inspection Report');
  $('templateSelect').value=cal?'calculation':'inspection';
  for(const [key,zh,en] of [['site',cal?'项目名称':'地点 / 资产名称 *',cal?'Project':'Site / asset name *'],['project_number',cal?'项目编号':'项目编号 *',cal?'Job No.':'Project No. *'],['report_number',cal?'计算报告编号':'报告编号 *',cal?'Calc. No.':'Report No. *'],['location','项目地点','Location'],['subject','报告主题','Subject']]){
   const field=$('meta_'+key);if(field?.parentElement.firstChild?.nodeType===3)field.parentElement.firstChild.nodeValue=label(zh,en);
  }
  if(!cal)return;
  const cover=project().cal_cover;
  cover.modules??=[['introduction','INTRODUCTION'],['materials','MATERIAL PROPERTIES']].map(([key,fallback])=>({id:uid(),title:cover[key+'_title']??fallback,blocks:cover[key]?[{id:uid(),type:'text',text:cover[key]}]:[]}));
  if(!selected()&&active!=='cover-revisions')active=entries()[0]?.module.id||coverEntries()[0]?.module.id;
  renderTree();renderEditor();
 }
 function sheetHeader(cal){
  const header=el('div',undefined,'template-sheet-header'),logo=el('img');logo.src='/wml-logo-horizontal.png';logo.alt='WML';header.append(logo,el('strong',cal?(project().cal_cover.title??'CALCULATION REPORT'):'INSPECTION REPORT'));
  const details=el('div',undefined,'template-info');
  for(const name of cal?['Project','Job No.','Location','Rev.','Calc. No.','Date','Subject']:['Site','Project No.','Client','Rev.','Report No.','Date'])details.append(el('div',name+'：________________'));
  const wrapper=el('div');wrapper.append(header,details);return wrapper;
 }
 function showTemplate(){
  const cal=project().template_id==='calculation',host=$('templatePreviewPages');host.replaceChildren();
  const addPage=()=>{const page=el('article',undefined,'template-sheet');page.append(sheetHeader(cal));host.append(page);return page;};
  const cover=addPage();
  if(cal){cover.classList.add('template-cover');const content=el('div',undefined,'template-cover-body');for(const module of project().cal_cover.modules){const box=el('section');box.append(el('h2',module.title));content.append(box);}cover.append(content);}
  else cover.append(el('h2',label('报告信息','REPORT INFORMATION')),el('div','','template-blank'));
  cover.append(el('p',label('作者','PREPARED BY')+'：________________'),el('p',label('审阅者','REVIEWED BY')+'：________________'),el('p',label('版本 | 日期 | 状态 | 设计 | 校核 | 批准','REVISION | DATE | STATUS | DESIGNED | CHECKED | APPROVED')));
  const page=addPage();page.append(el('h2',label(cal?'目录':'检查项',cal?'CONTENTS':'INSPECTION ITEMS')));
  if(cal){
   for(const {module,number} of entries()){const h=el('h3',number+'  '+module.title);h.style.marginLeft=number.split('.').length*8+'px';page.append(h);}
   let reportPage=addPage();
   for(const [index,{module,number}] of entries().entries()){
    if(index&&module.page_break)reportPage=addPage();
    reportPage.append(el('h3',number+'  '+module.title));
    for(const block of module.blocks){
     if(block.type==='table'){
      const table=el('table',undefined,'cal-content-table');for(const row of block.rows.slice(0,5)){const tr=el('tr');for(const _ of row){const td=el('td','\u00a0');tr.append(td);}table.append(tr);}reportPage.append(table);
     }else{const placeholder=el('div',block.type==='image'?'IMAGE':'', 'template-blank');if(block.type==='image')placeholder.style.width=block.width+'%';reportPage.append(placeholder);}
    }
   }
  }
  else{for(const name of (root.WorkbenchI18n.language==='en'?['Element','Condition Rating','Likelihood','Severity','Priority']:['构件','状况','发生可能性','严重程度','处理优先级']))page.append(el('div',name+'：________________','template-rating'));const placeholder=el('div',label('照片 | 现场描述 / 处理建议','PHOTO | OBSERVATION / RECOMMENDATION'),'template-blank');page.append(placeholder);}
  $('templatePreviewDialog').showModal();
 }
 function init(options){
  config=options;
  $('addCalModule').onclick=config.action(async()=>{const m=blankModule();project().modules.push(m);active=m.id;render();changed();});
  $('calSave').onclick=config.action(async()=>{await config.save();config.notify(label('报告已保存','Report saved'));});
  $('calPreview').onclick=config.action(()=>config.preview(null));
  $('calExport').onclick=config.action(async()=>{const format=$('calExportFormat').value;await config.save();if(format==='pdf'||format==='xlsx'){await config.preview(format);return;}const result=await config.api('/api/generate',{id:project().id,format});config.download(result,format);});
  $('templatePreview').onclick=showTemplate;$('closeTemplatePreview').onclick=()=>$('templatePreviewDialog').close();
  for(const [id,zh,en] of [['calOutlineTitle','报告章节','Report chapters'],['addCalModule','＋ 章节','+ Chapter'],['calSave','保存报告','Save report'],['calPreview','预览报告','Preview report'],['calExport','导出','Export']])$(id).textContent=label(zh,en);
 }
 root.CalculationWorkbench={init,render,showTemplate,setBusy(value){for(const button of document.querySelectorAll('#calWorkspace button'))button.disabled=value;}};
 root.CalContent={parseTable,walk};
 if(typeof module!=='undefined')module.exports={parseTable,walk};
})(globalThis);
