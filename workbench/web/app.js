'use strict';
const $=id=>document.getElementById(id);
const fields=['element','condition_rating','likelihood','severity','priority'];
const labels={element:'Element · 构件',condition_rating:'Condition Rating · 状况',likelihood:'Likelihood · 可能性',severity:'Severity · 严重程度',priority:'Priority · 优先级'};
const metadataLabels={site:'地点 / 资产名称 *',client:'客户',report_number:'报告编号 *',project_number:'项目编号 *',revision:'Revision',report_date:'报告日期',prepared_by:'Prepared by',reviewed_by:'Reviewed by',purpose:'Purpose of issue',issued_to:'Issued to',document_name:'文档名称（留空自动生成）',author_qualifications:'作者资质',reviewer_qualifications:'审阅人资质',author_title:'作者职务',reviewer_title:'审阅人职务'};
let boot,project=null,busy=false,saveTimer,toastTimer,queue=Promise.resolve(),saveFailed=false;
const blankEditor=()=>({photos:[],...Object.fromEntries([...fields,'observation','recommendation'].map(k=>[k,'']))});
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
function status(text,error=false){$('saveStatus').textContent=text;$('saveStatus').classList.toggle('error',error);}
async function api(path,body,headers={}){
 const opts={headers:{'X-Workbench':'1',...headers}};
 if(body!==undefined){opts.method='POST';if(body instanceof Blob){opts.body=body;}else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}}
 const r=await fetch(path,opts);const data=await r.json();if(!r.ok)throw new Error(data.error||'操作失败');return data;
}
function scheduleSave(){status('有更改，正在保存…');clearTimeout(saveTimer);saveTimer=setTimeout(()=>persist().catch(()=>{}),650);}
function persist(){
 clearTimeout(saveTimer);saveTimer=null;if(!project)return Promise.resolve();
 const snapshot=structuredClone(project);
 const task=queue.catch(()=>{}).then(async()=>{
  snapshot.revision=project.revision;
  const saved=await api('/api/save',snapshot);if(project.id===saved.id){project.revision=saved.revision;project.updated=saved.updated;}
  const entry={id:saved.id,site:saved.metadata.site,report_number:saved.metadata.report_number,updated:saved.updated,count:saved.items.length};
  const position=boot.projects.findIndex(p=>p.id===saved.id);if(position>=0)boot.projects[position]=entry;else boot.projects.unshift(entry);renderProjects();
  saveFailed=false;status('已保存到本地');return saved;
 }).catch(e=>{saveFailed=true;status('保存失败，请重试',true);toast(e.message);throw e;});
 queue=task;return task;
}
async function flush(){clearTimeout(saveTimer);saveTimer=null;await persist();}
function setBusy(value){busy=value;for(const id of ['newProject','projectSelect','saveItem','generateButton','backupButton','restoreButton','resetEditor','exitButton','libraryButton'])if($(id))$(id).disabled=value;if($('reportSummary'))updateSummary();}
function action(fn){return async event=>{if(busy)return;setBusy(true);try{await fn(event);}catch(e){toast(e.message);}finally{setBusy(false);}};}
function confirmAction(title,text){
 $('confirmTitle').textContent=title;$('confirmText').textContent=text;const d=$('confirmDialog');d.showModal();
 return new Promise(resolve=>{const close=value=>{d.close();$('confirmOk').onclick=null;$('confirmCancel').onclick=null;d.oncancel=null;resolve(value);};$('confirmOk').onclick=()=>close(true);$('confirmCancel').onclick=()=>close(false);d.oncancel=e=>{e.preventDefault();close(false);};});
}
function buildFields(){
 for(const [key,label] of Object.entries(metadataLabels)){
  const box=node('label',label);const input=node('input');input.id='meta_'+key;input.type=key==='report_date'?'date':'text';input.maxLength=500;
  input.addEventListener('input',()=>{project.metadata[key]=input.value;updateTitle();scheduleSave();});box.append(input);$('metadataFields').append(box);
 }
 for(const key of fields){
  const box=node('div');const label=node('label',labels[key]);label.htmlFor='rating_'+key;
  const input=node('input');input.id='rating_'+key;input.setAttribute('list','options_'+key);input.placeholder='选择或输入';input.maxLength=1000;
  const list=node('datalist');list.id='options_'+key;
  for(const value of boot.options[key]){const option=node('option');option.value=value;list.append(option);}
  input.addEventListener('input',()=>{project.editor[key]=input.value;scheduleSave();});box.append(label,input,list);$('ratingFields').append(box);
 }
 for(const key of ['observation','recommendation']){
  $(key+'Search').addEventListener('input',()=>renderLibrary(key));
  $(key+'Select').addEventListener('change',()=>{
   const selected=boot.library[key].find(r=>r.id===$(key+'Select').value);if(!selected)return;
   project.editor[key]=selected.text;project.editor[key+'_source']=selected.id;
   $(key+'Text').value=selected.text;$(key+'Source').textContent='来源 '+selected.id+' · 可继续编辑';scheduleSave();
  });
  $(key+'Text').addEventListener('input',()=>{project.editor[key]=$(key+'Text').value;scheduleSave();});
 }
}
function renderLibrary(key){
 const select=$(key+'Select'),selected=select.value,search=$(key+'Search').value.toLowerCase().trim();select.replaceChildren();
 const first=node('option',search?'选择搜索结果…':'从文字库选择…');first.value='';select.append(first);
 const rows=boot.library[key].filter(r=>(r.text+' '+r.elements+' '+r.id).toLowerCase().includes(search));
 for(const r of rows){const opt=node('option',r.id+' · '+r.text);opt.value=r.id;select.append(opt);}
 if(rows.some(r=>r.id===selected))select.value=selected;
 $(key+'Count').textContent=search?`${rows.length} 个结果`:`${boot.library[key].length} 条`;
}
function updateTitle(){
 $('projectTitle').textContent=project.metadata.site||'新的检查报告';
 $('projectSubtitle').textContent=project.metadata.report_number?project.metadata.report_number+' · '+(project.metadata.client||'客户未填写'):'先填写报告信息，再整理现场照片。';
}
function updateSummary(){
 if(!project)return;
 const count=project.items.length,photos=project.items.reduce((n,i)=>n+i.photos.length,0);
 $('itemCount').textContent=count;$('reportSummary').textContent=count?`${count} 个检查项 · ${photos} 张照片`:'还没有已保存的检查项';
 $('generateButton').disabled=busy||count===0;
}
function renderProjects(){
 const select=$('projectSelect');select.replaceChildren();
 for(const p of boot.projects){const op=node('option',(p.site||'未命名报告')+` · ${p.count} 项`);op.value=p.id;select.append(op);}
 if(project){if(!boot.projects.some(p=>p.id===project.id)){const op=node('option',project.metadata.site||'新的检查报告');op.value=project.id;select.prepend(op);}select.value=project.id;}
}
function renderEditor(){
 for(const key of fields)$('rating_'+key).value=project.editor[key]||'';
 for(const key of ['observation','recommendation']){
  $(key+'Text').value=project.editor[key]||'';$(key+'Search').value='';renderLibrary(key);
  $(key+'Select').value=project.editor[key+'_source']||'';
  $(key+'Source').textContent=project.editor[key+'_source']?'来源 '+project.editor[key+'_source']+' · 可继续编辑':'手动输入';
 }
 $('editorTitle').textContent=project.editor_id?'编辑检查项 '+(project.items.findIndex(i=>i.id===project.editor_id)+1):'整理一个检查项';
 $('editingBadge').hidden=!project.editor_id;$('saveItem').textContent=project.editor_id?'Save · 保存修改':'Save · 保存检查项';renderPhotos();
}
function renderPhotos(){
 const grid=$('photoGrid');grid.replaceChildren();$('photoCount').textContent=project.editor.photos.length+' 张';
 project.editor.photos.forEach((photo,index)=>{
  const card=node('div',undefined,'photo-card');const image=node('img');image.src='/photos/'+photo.id+'.jpg';image.alt=photo.name;image.loading='lazy';
  const name=node('span',`${index+1}. ${photo.name}`,'name');name.title=photo.name;const controls=node('div',undefined,'photo-controls');
  for(const [label,title,fn] of [
   ['←','照片前移',()=>{if(index>0)[project.editor.photos[index-1],project.editor.photos[index]]=[photo,project.editor.photos[index-1]];renderPhotos();scheduleSave();}],
   ['→','照片后移',()=>{if(index<project.editor.photos.length-1)[project.editor.photos[index+1],project.editor.photos[index]]=[photo,project.editor.photos[index+1]];renderPhotos();scheduleSave();}],
   ['↻','顺时针旋转照片',async()=>{const p=await api('/api/rotate',{id:photo.id});project.editor.photos[index]=p;renderPhotos();await flush();}],
   ['×','移除当前照片',()=>{project.editor.photos.splice(index,1);renderPhotos();scheduleSave();}]
  ]){const b=node('button',label);b.title=title;b.setAttribute('aria-label',title);b.onclick=action(fn);controls.append(b);}
  card.append(image,name,controls);grid.append(card);
 });
}
function renderItems(){
 const list=$('savedItems');list.replaceChildren();
 if(!project.items.length){const empty=node('div',undefined,'empty-state');empty.append(node('strong','现场发现，从第一张照片开始。'),node('p','保存的检查项会出现在这里，可以编辑、调整顺序，然后一起生成报告。'));list.append(empty);}
 project.items.forEach((item,index)=>{
  const row=node('article',undefined,'saved-item');row.append(node('span',String(index+1).padStart(2,'0'),'item-number'));
  const image=node('img');image.src='/photos/'+item.photos[0].id+'.jpg';image.alt=item.photos[0].name;image.className='item-photo';row.append(image);
  const obs=node('div',undefined,'item-content');obs.append(node('strong',item.element),node('p',item.observation));
  const meta=node('div',undefined,'item-meta');const priority=node('span',item.priority,'priority');priority.dataset.priority=item.priority;meta.append(priority,node('span',item.photos.length+' 张照片'),node('span',item.condition_rating));obs.append(meta);row.append(obs);
  const rec=node('div',undefined,'item-content');rec.append(node('strong','Recommendation'),node('p',item.recommendation||'—'));row.append(rec);
  const actions=node('div',undefined,'item-actions');
  for(const [label,fn] of [
   ['编辑',async()=>{if(editorHasContent()&&project.editor_id!==item.id&&!(await confirmAction('切换到已保存项','当前编辑区已自动保存。切换后会替换编辑区内容，请先保存需要加入报告的检查项。')))return;project.editor=structuredClone(item);delete project.editor.id;project.editor_id=item.id;renderEditor();await flush();$('editorTitle').scrollIntoView({behavior:'smooth',block:'center'});}],
   ['↑',async()=>{if(index>0)[project.items[index-1],project.items[index]]=[item,project.items[index-1]];renderItems();await flush();}],
   ['↓',async()=>{if(index<project.items.length-1)[project.items[index+1],project.items[index]]=[item,project.items[index+1]];renderItems();await flush();}],
   ['删除',async()=>{if(!(await confirmAction('删除检查项',`从报告中删除第 ${index+1} 项？原始照片仍保存在本地。`)))return;project.items.splice(index,1);if(project.editor_id===item.id){project.editor=blankEditor();project.editor_id=null;renderEditor();}renderItems();await flush();}]
  ]){const b=node('button',label);b.onclick=action(fn);b.setAttribute('aria-label',label+'检查项 '+(index+1));actions.append(b);}
  row.append(actions);list.append(row);
 });updateSummary();
}
function editorHasContent(){return project.editor.photos.length||project.editor.observation||project.editor.recommendation;}
function loadProject(value){project=value;for(const key of Object.keys(metadataLabels))$('meta_'+key).value=project.metadata[key]||'';updateTitle();renderEditor();renderItems();renderProjects();status('已保存到本地');}
async function uploadPhotos(files){
 if(!files.length)return;if(project.editor.photos.length+files.length>100)throw new Error('一个检查项最多 100 张照片');
 const failures=[];
 for(let i=0;i<files.length;i++){
  const file=files[i];$('editorHint').textContent=`正在导入 ${i+1} / ${files.length}：${file.name}`;
  try{const photo=await api('/api/photo',file,{'X-Filename':encodeURIComponent(file.name)});project.editor.photos.push(photo);renderPhotos();await persist();}
  catch(e){failures.push(file.name+'：'+e.message);}
 }
 $('editorHint').textContent='已导入照片。填写描述与评级后，保存检查项。';
 if(failures.length)throw new Error('部分照片未导入：\n'+failures.join('\n'));
 toast('照片已导入并保存到草稿');
}
async function saveItem(){
 const e=project.editor;
 if(!e.photos.length)throw new Error('请先加入照片');
 if(fields.some(key=>!e[key]?.trim()))throw new Error('请填写 Element 和四项评级，可下拉选择或手动输入');
 if(!e.observation.trim())throw new Error('请填写 Observation');
 const item={...structuredClone(e),id:project.editor_id||crypto.randomUUID().replaceAll('-','')};
 const index=project.items.findIndex(i=>i.id===item.id),previousItem=index>=0?structuredClone(project.items[index]):null;if(index>=0)project.items[index]=item;else project.items.push(item);
 const previous=structuredClone(project.editor);const previousId=project.editor_id;
 project.editor=blankEditor();project.editor_id=null;
 try{await flush();renderItems();renderEditor();toast(index>=0?'检查项修改已保存':'检查项已保存，可以继续下一项');}
 catch(error){project.editor=previous;project.editor_id=previousId;if(index<0)project.items.pop();else project.items[index]=previousItem;throw error;}
}
async function init(){
 boot=await api('/api/bootstrap');buildFields();$('dataFolder').textContent='数据目录：'+boot.data_folder;
 $('appVersion').textContent='Version '+boot.version+' · 无需登录 · 离线使用';
 let last=localStorage.getItem('lastProject');let chosen=boot.projects.find(p=>p.id===last)||boot.projects[0];
 loadProject(chosen?await api('/api/project?id='+chosen.id):await api('/api/new',{}));localStorage.setItem('lastProject',project.id);
 $('saveItem').onclick=action(saveItem);
 $('newProject').onclick=action(async()=>{await flush();loadProject(await api('/api/new',{}));boot.projects=(await api('/api/bootstrap')).projects;renderProjects();localStorage.setItem('lastProject',project.id);$('reportDetails').open=true;});
 $('projectSelect').onchange=action(async e=>{const id=e.target.value;await flush();loadProject(await api('/api/project?id='+id));localStorage.setItem('lastProject',id);});
 $('resetEditor').onclick=action(async()=>{if(editorHasContent()&&!(await confirmAction('清空当前编辑区','已保存检查项保持不变。当前编辑区的照片和未保存文字会从草稿中移除。')))return;project.editor=blankEditor();project.editor_id=null;renderEditor();await flush();});
 $('dropzone').onclick=()=>{if(!busy)$('photoFiles').click();};$('dropzone').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!busy){e.preventDefault();$('photoFiles').click();}};
 $('photoFiles').onchange=action(async e=>{const files=[...e.target.files];e.target.value='';await uploadPhotos(files);});
 const drop=$('dropzone');for(const type of ['dragenter','dragover'])drop.addEventListener(type,e=>{e.preventDefault();drop.classList.add('drag');});
 drop.addEventListener('dragleave',()=>drop.classList.remove('drag'));
 drop.addEventListener('drop',action(async e=>{e.preventDefault();drop.classList.remove('drag');await uploadPhotos([...e.dataTransfer.files]);}));
 // Avoid browser navigation if a photo is dropped outside the target.
 document.addEventListener('dragover',e=>e.preventDefault());document.addEventListener('drop',e=>e.preventDefault());
 $('generateButton').onclick=action(async()=>{
  await flush();if(editorHasContent()&&!(await confirmAction('生成已保存的检查项','当前编辑区还有内容。报告只包含下方已保存检查项；若要包含当前项，请取消后点击 Save。')))return;
  const result=await api('/api/generate',{id:project.id});const a=node('a');a.href='/api/download?id='+result.id+'&name='+encodeURIComponent(result.name);a.download=result.name;document.body.append(a);a.click();a.remove();toast('Word 报告已生成；打开后按提示更新目录。');
 });
 $('backupButton').onclick=action(async()=>{await flush();const a=node('a');a.href='/api/backup?id='+project.id;a.download='inspection-draft.inspection.zip';document.body.append(a);a.click();a.remove();toast('草稿备份已导出，包含照片和文字。');});
 $('restoreButton').onclick=()=>{if(!busy)$('restoreFile').click();};
 $('restoreFile').onchange=action(async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;await flush();const p=await api('/api/restore',file);loadProject(p);boot.projects=(await api('/api/bootstrap')).projects;renderProjects();localStorage.setItem('lastProject',p.id);toast('草稿已导入为独立副本');});
 $('libraryButton').onclick=()=>{$('libraryStats').textContent=`Observation ${boot.library.observation.length} 条 · Recommendation ${boot.library.recommendation.length} 条`;$('libraryDialog').showModal();};
 $('closeLibrary').onclick=()=>$('libraryDialog').close();$('importLibraryButton').onclick=()=>$('libraryFile').click();
 $('libraryFile').onchange=action(async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;const result=await api('/api/library',file);boot.library=result.library;for(const key of ['observation','recommendation'])renderLibrary(key);$('libraryDialog').close();toast('文字库已更新。已保存检查项保持原样。');});
 $('exitButton').onclick=action(async()=>{await flush();if(!(await confirmAction('退出工作台','草稿已保存。退出后，下次双击程序可继续。')))return;await api('/api/shutdown',{});document.body.replaceChildren(node('main','工作台已退出，草稿已保存。可以关闭此页面。'));});
 window.addEventListener('beforeunload',e=>{if(saveTimer||busy||saveFailed){e.preventDefault();e.returnValue='';}});
 window.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&saveTimer)persist().catch(()=>{});});
}
init().catch(e=>{status('无法打开工作台',true);toast(e.message);});
