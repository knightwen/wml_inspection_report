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
 const selected=()=>entries().find(e=>e.module.id===active);
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
 function updateBlockOrder(module,index,direction){const at=index+direction;if(at<0||at>=module.blocks.length)return;[module.blocks[index],module.blocks[at]]=[module.blocks[at],module.blocks[index]];renderEditor();changed();}
 async function upload(files){
  const module=selected()?.module;if(!module)return;
  const errors=[];
  for(const file of files){
   try{const photo=await config.api('/api/photo',file,{'X-Filename':encodeURIComponent(file.name||'clipboard.png')});module.blocks.push({id:uid(),type:'image',photo,width:100});await config.save();}
   catch(error){errors.push(file.name+': '+error.message);}
  }
  renderEditor();if(errors.length)throw new Error(errors.join('\n'));
 }
 function renderTable(block,container){
  const toolbar=el('div',undefined,'cal-block-toolbar');
  const resize=(axis,delta)=>{
   const rows=block.rows,cols=rows[0].length;
   if(axis==='row'){if(delta>0&&rows.length<200)rows.push(Array(cols).fill(''));else if(delta<0&&rows.length>1)rows.pop();}
   else{if(delta>0&&cols<20)rows.forEach(r=>r.push(''));else if(delta<0&&cols>1)rows.forEach(r=>r.pop());}
   renderEditor();changed();
  };
  for(const [text,axis,delta] of [[label('＋ 行','+ Row'),'row',1],[label('－ 行','− Row'),'row',-1],[label('＋ 列','+ Column'),'column',1],[label('－ 列','− Column'),'column',-1]])toolbar.append(button(text,async()=>resize(axis,delta)));
  container.append(toolbar);
  const scroll=el('div',undefined,'cal-table-scroll'),table=el('table',undefined,'cal-content-table');
  block.rows.forEach((row,ri)=>{const tr=el('tr');row.forEach((value,ci)=>{const cell=el(ri?'td':'th'),edit=input(value,v=>{block.rows[ri][ci]=v;},{multiline:true,rows:2,max:2000});edit.setAttribute('aria-label',label('单元格','Cell')+' '+(ri+1)+','+(ci+1));cell.append(edit);tr.append(cell);});table.append(tr);});scroll.append(table);container.append(scroll);
  const details=el('details'),summary=el('summary',label('从 Excel 粘贴表格','Paste a table from Excel'));details.append(summary);
  const paste=el('textarea');paste.rows=3;paste.placeholder=label('复制 Excel 单元格并粘贴到这里','Copy Excel cells and paste here');paste.setAttribute('aria-label',paste.placeholder);
  details.append(paste,button(label('应用粘贴内容','Apply pasted table'),async()=>{block.rows=parseTable(paste.value);renderEditor();changed();}));container.append(details);
 }
 function renderEditor(){
  const host=$('calEditor');host.replaceChildren();const entry=selected();
  if(!entry){host.append(el('p',label('选择或添加章节。','Select or add a chapter.')));return;}
  const module=entry.module;
  const title=input(module.title,v=>{module.title=v;renderTree();},{max:500});title.id='calModuleTitle';
  host.append(field(label('章节标题','Chapter title')+' · '+entry.number,title));
  const tools=el('div',undefined,'cal-editor-tools');
  tools.append(button('↑',()=>move(-1)),button('↓',()=>move(1)));
  tools.append(button(label('增加缩进','Indent'),async()=>{
   const e=selected();if(!e||!e.index)return;
   const previous=e.siblings[e.index-1];const deepest=walk([e.module]).reduce((n,x)=>Math.max(n,x.number.split('.').length),0);
   if(e.number.split('.').length+deepest>6)throw new Error(label('章节最多六级','Maximum six chapter levels'));
   e.siblings.splice(e.index,1);previous.children.push(e.module);render();changed();
  }),button(label('减少缩进','Outdent'),async()=>{
   const e=selected(),parent=entries().find(x=>x.module.children===e?.siblings);if(!parent)return;
   e.siblings.splice(e.index,1);parent.siblings.splice(parent.index+1,0,e.module);render();changed();
  }));
  tools.append(button(label('＋ 子章节','+ Subchapter'),async()=>{if(entry.number.split('.').length>=6)return;const m=blankModule();module.children.push(m);active=m.id;render();changed();}));
  tools.append(button(label('删除章节','Delete chapter'),async()=>{
   if(!await config.confirm(label('删除章节','Delete chapter'),label('同时删除该章节下的内容和子章节？','Delete this chapter, its content and subchapters?')))return;
   const current=selected();if(!current)return;current.siblings.splice(current.index,1);active=entries()[0]?.module.id;render();changed();
  },'quiet'));
  const page=el('input');page.type='checkbox';page.checked=module.page_break;page.onchange=()=>{module.page_break=page.checked;changed();};const pageLabel=field(label('从新页开始','Start on a new page'),page);pageLabel.classList.add('cal-checkbox');tools.append(pageLabel);host.append(tools);
  const blocks=el('div',undefined,'cal-blocks');
  module.blocks.forEach((block,index)=>{
   const box=el('section',undefined,'cal-block');box.dataset.blockId=block.id;
   const top=el('div',undefined,'cal-block-toolbar');top.append(el('strong',label({text:'文字',table:'表格',image:'图片'}[block.type],{text:'Text',table:'Table',image:'Image'}[block.type])));
   top.append(button('↑',async()=>updateBlockOrder(module,index,-1)),button('↓',async()=>updateBlockOrder(module,index,1)),button(label('删除','Delete'),async()=>{if(await config.confirm(label('删除内容块','Delete content block'),label('删除这个内容块？','Delete this content block?'))){module.blocks.splice(index,1);renderEditor();changed();}},'quiet'));box.append(top);
   if(block.type==='text'){const edit=input(block.text,v=>block.text=v,{multiline:true});edit.setAttribute('aria-label',label('章节文字','Chapter text'));box.append(edit);}
   else if(block.type==='table')renderTable(block,box);
   else{
    const image=el('img');image.src='/photos/'+block.photo.id+'.jpg';image.alt=block.photo.caption||block.photo.name;image.style.width=block.width+'%';image.className='cal-content-image';box.append(image);
    const caption=input(block.photo.caption||'',v=>{block.photo.caption=v;image.alt=v||block.photo.name;},{max:200});box.append(field(label('图注','Caption'),caption));
    const width=el('input');width.type='range';width.min=20;width.max=100;width.value=block.width;const output=el('output',block.width+'%');width.oninput=()=>{block.width=Number(width.value);image.style.width=block.width+'%';output.textContent=block.width+'%';changed();};const widthLabel=field(label('图片宽度','Image width'),width);widthLabel.append(output);box.append(widthLabel);
    box.append(button(label('旋转图片','Rotate image'),async()=>{block.photo={...block.photo,...await config.api('/api/rotate',{id:block.photo.id})};renderEditor();await config.save();}));
   }
   blocks.append(box);
  });host.append(blocks);
  const add=el('div',undefined,'cal-add-content');
  add.append(button(label('＋ 文字','+ Text'),async()=>{module.blocks.push({id:uid(),type:'text',text:''});renderEditor();changed();}),button(label('＋ 表格','+ Table'),async()=>{module.blocks.push({id:uid(),type:'table',rows:[['','',''],['','','']]});renderEditor();changed();}),button(label('＋ 图片','+ Images'),async()=>$('calImageFiles').click()));host.append(add);
  if(!module.blocks.length)host.append(el('p',label('此章节为空。添加文字、表格或图片，也可以直接粘贴截图。','This chapter is empty. Add text, tables or images, or paste a screenshot.'),'cal-empty'));
 }
 function renderRevisions(){
  const host=$('calRevisions');host.replaceChildren();
  const table=el('table',undefined,'cal-content-table'),head=el('tr'),keys=['revision','date','status','designed','checked','approved'];
  for(const key of keys)head.append(el('th',key.toUpperCase()));head.append(el('th',''));table.append(head);
  project().cal_cover.revisions.forEach((row,index)=>{const tr=el('tr');for(const key of keys){const cell=el('td');cell.append(input(row[key]||'',v=>row[key]=v,{max:500}));tr.append(cell);}const del=el('td');del.append(button('×',async()=>{project().cal_cover.revisions.splice(index,1);renderRevisions();changed();}));tr.append(del);table.append(tr);});host.append(table);
 }
 function renderCover(){
  const host=$('calCoverFields');host.replaceChildren();
  for(const [key,title] of [['introduction',label('简介','Introduction')],['materials',label('材料说明','Material properties')]])host.append(field(title,input(project().cal_cover[key],v=>project().cal_cover[key]=v,{multiline:true,rows:3})));
  host.append(el('h3',label('修订记录','Revision history')));const revisions=el('div');revisions.id='calRevisions';host.append(revisions,button(label('＋ 修订记录','+ Revision'),async()=>{project().cal_cover.revisions.push({revision:'',date:'',status:'',designed:'',checked:'',approved:''});renderRevisions();changed();}));renderRevisions();
 }
 function render(){
  const cal=project()?.template_id==='calculation';document.body.dataset.reportType=cal?'calculation':'inspection';$('calWorkspace').hidden=!cal;
  document.querySelector('.brand strong').textContent='WML Report Workbench';
  document.querySelector('.brand small').textContent=cal?label('章节、表格与计算报告','Chapters, tables and calculation reports'):label('照片、现场记录与 Word 报告','Photos, field notes and Word reports');
  document.title='WML Report Workbench · '+(cal?'CAL':'Inspection');
  $('templateSelect').value=cal?'calculation':'inspection';
  for(const [key,zh,en] of [['site',cal?'项目名称':'地点 / 资产名称 *',cal?'Project':'Site / asset name *'],['project_number',cal?'项目编号':'项目编号 *',cal?'Job No.':'Project No. *'],['report_number',cal?'计算报告编号':'报告编号 *',cal?'Calc. No.':'Report No. *'],['location','项目地点','Location'],['subject','报告主题','Subject']]){
   const field=$('meta_'+key);if(field?.parentElement.firstChild?.nodeType===3)field.parentElement.firstChild.nodeValue=label(zh,en);
  }
  if(!cal)return;
  if(!selected())active=entries()[0]?.module.id;
  renderTree();renderEditor();renderCover();
 }
 function sheetHeader(cal){
  const header=el('div',undefined,'template-sheet-header'),logo=el('img');logo.src='/wml-logo.png';logo.alt='WML';header.append(logo,el('strong',cal?'CALCULATION REPORT':'INSPECTION REPORT'));
  const details=el('div',undefined,'template-info');
  for(const name of cal?['Project','Job No.','Location','Rev.','Calc. No.','Date','Subject']:['Site','Project No.','Client','Rev.','Report No.','Date'])details.append(el('div',name+'：________________'));
  const wrapper=el('div');wrapper.append(header,details);return wrapper;
 }
 function showTemplate(){
  const cal=project().template_id==='calculation',host=$('templatePreviewPages');host.replaceChildren();
  const addPage=()=>{const page=el('article',undefined,'template-sheet');page.append(sheetHeader(cal));host.append(page);return page;};
  const cover=addPage();cover.append(el('h2',cal?'INTRODUCTION':'REPORT INFORMATION'),el('div','', 'template-blank'),el('h2',cal?'MATERIAL PROPERTIES':'PREPARED FOR'),el('div','','template-blank'),el('p','PREPARED BY：________________'),el('p','REVIEWED BY：________________'),el('p','REVISION  |  DATE  |  STATUS  |  DESIGNED  |  CHECKED  |  APPROVED'));
  const page=addPage();page.append(el('h2',cal?'CONTENTS':'INSPECTION ITEMS'));
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
  else{for(const name of ['Element','Condition Rating','Likelihood','Severity','Priority'])page.append(el('div',name+'：________________','template-rating'));const placeholder=el('div','PHOTO  |  OBSERVATION / RECOMMENDATION','template-blank');page.append(placeholder);}
  $('templatePreviewDialog').showModal();
 }
 function init(options){
  config=options;
  $('addCalModule').onclick=config.action(async()=>{const m=blankModule();project().modules.push(m);active=m.id;render();changed();});
  $('calImageFiles').onchange=config.action(async e=>{const files=[...e.target.files];e.target.value='';await upload(files);});
  $('calWorkspace').addEventListener('paste',e=>{if(project()?.template_id!=='calculation')return;const files=[...e.clipboardData.items].filter(i=>i.type.startsWith('image/')).map(i=>i.getAsFile()).filter(Boolean);if(files.length){e.preventDefault();config.action(()=>upload(files))(e);}});
  $('calSave').onclick=config.action(async()=>{await config.save();config.notify(label('报告已保存','Report saved'));});
  $('calPreview').onclick=config.action(()=>config.preview(null));
  $('calExport').onclick=config.action(async()=>{const format=$('calExportFormat').value;await config.save();if(format==='pdf'||format==='xlsx'){await config.preview(format);return;}const result=await config.api('/api/generate',{id:project().id,format});config.download(result,format);});
  $('templatePreview').onclick=showTemplate;$('closeTemplatePreview').onclick=()=>$('templatePreviewDialog').close();
  for(const [id,zh,en] of [['calOutlineTitle','报告章节','Report chapters'],['addCalModule','＋ 章节','+ Chapter'],['calCoverTitle','封面与修订记录','Cover and revisions'],['calSave','保存报告','Save report'],['calPreview','预览报告','Preview report'],['calExport','导出','Export']])$(id).textContent=label(zh,en);
 }
 root.CalculationWorkbench={init,render,showTemplate,setBusy(value){for(const button of document.querySelectorAll('#calWorkspace button'))button.disabled=value;}};
 root.CalContent={parseTable,walk};
 if(typeof module!=='undefined')module.exports={parseTable,walk};
})(globalThis);
