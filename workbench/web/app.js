'use strict';
const $=id=>document.getElementById(id);
const t=(...args)=>WorkbenchI18n.t(...args);
const photoCountText=(count,short=false)=>WorkbenchI18n.language==='en'?count+(count===1?' photo':' photos'):count+(short?' 张':' 张照片');
const subitemCountText=count=>WorkbenchI18n.language==='en'?count+(count===1?' subitem':' subitems'):t('{0} 个子项',count);
const fields=['element','condition_rating','likelihood','severity','priority'];
const sectionLabels={introduction:t('Introduction · 项目介绍'),remedial_works:t('Recommended Remedial Works · 修复工程建议'),conclusion:t('Conclusion · 结论'),cost_estimate:t('Cost Estimate · 费用估算说明')};
const labels={element:t('Element · 构件'),condition_rating:t('Condition Rating · 状况'),likelihood:t('Likelihood · 发生可能性'),severity:t('Severity · 严重程度'),priority:t('Priority · 处理优先级')};
const metadataLabels={site:t('地点 / 资产名称 *'),client:t('客户'),report_number:t('报告编号 *'),project_number:t('项目编号 *'),revision:'Revision',report_date:t('报告日期'),purpose:'Purpose of issue',issued_to:'Issued to',document_name:t('文档名称（留空自动生成）'),prepared_by:'Prepared by',reviewed_by:'Reviewed by'};
const personRoles={prepared_by:{role:'author',label:t('作者 / Prepared by'),prefix:'author'},reviewed_by:{role:'reviewer',label:t('审阅者 / Reviewed by'),prefix:'reviewer'}};
let boot,project=null,busy=false,toastTimer,saver,previewJob=null,previewTimer;
let personnelEditorId=null,personnelDirty=false;
let itemDrag=null;
let photoEditor=null;
let activeSubitemId=null;
const blankSubitem=()=>({id:crypto.randomUUID().replaceAll('-',''),photos:[],observation:'',recommendation:''});
const blankEditor=()=>({...Object.fromEntries(fields.map(k=>[k,''])),subitems:[blankSubitem()]});
const itemPhotos=item=>item.subitems.flatMap(group=>group.photos);
function currentSubitem(){return project.editor.subitems.find(group=>group.id===activeSubitemId)||project.editor.subitems[0];}
function photoRange(item,index,parentNumber){const start=item.subitems.slice(0,index).reduce((n,g)=>n+g.photos.length,0)+1,count=item.subitems[index].photos.length;return count?parentNumber+'.'+start+(count>1?'–'+parentNumber+'.'+(start+count-1):''):'—';}
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function toast(text){$('toast').textContent=t(text);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500);}
function status(text,error=false){$('saveStatus').textContent=t(text);$('saveStatus').classList.toggle('error',error);}
async function api(path,body,headers={}){
 const opts={headers:{'X-Workbench':'1',...headers}};
 if(body!==undefined){opts.method='POST';if(body instanceof Blob){opts.body=body;}else{opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}}
 const r=await fetch(path,opts);const data=await r.json();if(!r.ok){const error=new Error(t(data.error)||t('操作失败'));error.code=data.code;throw error;}return data;
}
function saveStatus(state){
 if(state.conflict)status(t('保存冲突：当前修改尚未保存，请保留副本'),true);
 else if(state.sending)status(t('正在保存，请勿关闭页面…'));
 else if(state.pending)status(t('等待保存，请勿关闭页面…'));
 else if(state.error)status(t('保存失败，修改保留在当前页面'),true);
 else if(state.changed>state.saved)status(t('有未保存更改…'));else status(t('已保存到本地'));
 $('retrySave').hidden=!state.error||!!state.conflict;$('resolveConflict').hidden=!state.conflict;
}
function scheduleSave(){saver.schedule();}
function persist(){return saver.save(true);}
async function flush(){await saver.flush();}
function openSaveConflict(){if(!$('saveConflictDialog').open)$('saveConflictDialog').showModal();}
async function recoverConflict(loadLatest=false){
 await saver.queue;const previousId=project.id;const copy=await api('/api/project-copy',structuredClone(project));
 boot.projects=(await api('/api/bootstrap')).projects;loadProject(loadLatest?await api('/api/project?id='+previousId):copy);
 localStorage.setItem('lastProject',project.id);$('saveConflictDialog').close();toast(loadLatest?t('你的修改已保存为独立副本，已加载原草稿最新版本。'):t('你的修改已保存为独立副本。'));
}
async function downloadRecovery(){
 const response=await fetch('/api/recovery-backup',{method:'POST',headers:{'X-Workbench':'1','Content-Type':'application/json'},body:JSON.stringify(project)});
 if(!response.ok)throw new Error(t((await response.json()).error));
 const url=URL.createObjectURL(await response.blob()),a=node('a');a.href=url;a.download='unsaved-draft.inspection.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(t('当前修改与照片已下载；完成冲突处理前，请保留当前页面。'));
}
function setBusy(value){busy=value;for(const id of ['newProject','projectSelect','saveSections','saveItem','addSubitem','previewButton','generateButton','backupButton','restoreButton','resetEditor','exitButton','libraryButton','managePersonnel','savePersonnel','deletePersonnel','newPersonnel','closePersonnel','languageSelect'])if($(id))$(id).disabled=value;if($('reportSummary'))updateSummary();if(photoEditor)renderPhotoEditor();}
function action(fn){return async event=>{if(busy)return;setBusy(true);try{await fn(event);}catch(e){toast(e.message);}finally{setBusy(false);}};}
function confirmAction(title,text){
 $('confirmTitle').textContent=title;$('confirmText').textContent=text;const d=$('confirmDialog');d.showModal();
 return new Promise(resolve=>{const close=value=>{d.close();$('confirmOk').onclick=null;$('confirmCancel').onclick=null;d.oncancel=null;resolve(value);};$('confirmOk').onclick=()=>close(true);$('confirmCancel').onclick=()=>close(false);d.oncancel=e=>{e.preventDefault();close(false);};});
}
function buildFields(){
 for(const [key,label] of Object.entries(sectionLabels)){
  const box=node('label',label,'section-field'),input=node('textarea');input.id='section_'+key;input.maxLength=60000;input.rows=6;input.spellcheck=true;
  input.placeholder=key==='cost_estimate'?t('填写估算依据、排除项、预算说明或限制条件。'):t('输入正文；换行分段。留空则保留空白模板。');
  input.addEventListener('input',()=>{project.sections[key]=input.value;scheduleSave();});box.append(input);if(key==='cost_estimate'){const wrapper=node('div',undefined,'cost-editor');wrapper.append(box);const scroll=node('div',undefined,'cost-table-scroll');scroll.innerHTML=t('<table class=cost-table><thead><tr><th>Item</th><th>Description</th><th>Quantity</th><th>Unit</th><th>Rate</th><th>Cost</th><th>Priority</th><th>操作</th></tr></thead><tbody id=costRows></tbody></table>');wrapper.append(scroll);const footer=node('div',undefined,'cost-footer');const add=node('button',t('＋ 新增费用项'));add.id='addCostRow';add.type='button';add.onclick=()=>{project.cost_rows.push({description:'',quantity:'',unit:'',rate:'',priority:''});renderCosts();scheduleSave();};const total=node('strong');total.id='costTotal';total.setAttribute('aria-live','polite');footer.append(add,total);wrapper.append(footer);$('sectionFields').append(wrapper);}else $('sectionFields').append(box);
 }
 for(const [key,label] of Object.entries(metadataLabels)){
  if(personRoles[key]){buildPersonField(key);continue;}
  const box=node('label',label);const input=node('input');input.id='meta_'+key;input.type=key==='report_date'?'date':'text';input.maxLength=500;
  input.addEventListener('input',()=>{project.metadata[key]=input.value;updateTitle();scheduleSave();});box.append(input);$('metadataFields').append(box);
 }
 for(const key of fields){
  const box=node('div');const label=node('label',labels[key]);label.htmlFor='rating_'+key;
  const select=node('select');select.id='rating_'+key;
  const empty=node('option',t('请选择…'));empty.value='';select.append(empty);
  for(const value of boot.options[key]){const option=node('option',value);option.value=value;select.append(option);}
  const custom=node('option',t('手动填写 / 补充描述…'));custom.value='__manual__';select.append(custom);
  const input=node('input');input.id='manual_rating_'+key;input.placeholder=t('填写或补充描述');input.maxLength=1000;input.hidden=true;input.setAttribute('aria-label',labels[key]+t('手动填写'));
  select.addEventListener('change',()=>{
   input.hidden=select.value!=='__manual__';
   if(!input.hidden){input.value=project.editor[key]||'';input.focus();}
   else project.editor[key]=select.value;
   scheduleSave();
  });
  input.addEventListener('input',()=>{project.editor[key]=input.value;scheduleSave();});box.append(label,select,input);$('ratingFields').append(box);
 }
 for(const key of ['observation','recommendation']){
  $(key+'Search').addEventListener('input',()=>renderLibrary(key));
  $(key+'Select').addEventListener('change',()=>{
   const selected=boot.library[key].find(r=>r.id===$(key+'Select').value);if(!selected)return;
   currentSubitem()[key]=selected.text;currentSubitem()[key+'_source']=selected.id;
   $(key+'Search').value='';renderLibrary(key);$(key+'Select').value=selected.id;
   $(key+'Text').value=selected.text;$(key+'Source').textContent=t('来源 ')+selected.id+t(' · 可继续编辑');renderSubitems();scheduleSave();
  });
  $(key+'Text').addEventListener('input',()=>{currentSubitem()[key]=$(key+'Text').value;renderSubitems();scheduleSave();});
 }
}
function costValue(row){
 if(row.quantity.trim()===''||row.rate.trim()==='')return null;
 const parse=text=>{if(!/^(?:[0-9]+(?:\.[0-9]{0,6})?|\.[0-9]{1,6})$/.test(text.trim()))return null;const [whole,fraction='']=text.trim().split('.');return BigInt(whole)*1000000n+BigInt(fraction.padEnd(6,'0'));};
 const qty=parse(row.quantity),rate=parse(row.rate);if(qty===null||rate===null)return null;
 return (qty*rate+5000000000n)/10000000000n;
}
function money(cents){return (cents/100n).toLocaleString('en-AU')+'.'+(cents%100n).toString().padStart(2,'0');}
function updateCostTotal(){let total=0n,complete=true;project.cost_rows.forEach((row,index)=>{const value=costValue(row);if(value===null)complete=false;else total+=value;const cell=$('costValue_'+index);if(cell)cell.textContent=value===null?'—':money(value);});$('costTotal').textContent=(complete?t('Total · 合计：'):t('Subtotal · 已填写项小计：'))+money(total);}
function renderCosts(){
 const body=$('costRows');body.replaceChildren();
 project.cost_rows.forEach((row,index)=>{
  const tr=node('tr');tr.append(node('td',String(index+1)));
  for(const key of ['description','quantity','unit','rate','priority']){
   const cell=node('td'),input=node(key==='priority'?'select':key==='description'?'textarea':'input');input.setAttribute('aria-label',t("费用项 {0} {1}",index+1,key));
   if(key==='priority'){
    for(const value of ['',...boot.options.priority]){const option=node('option',value||t('请选择'));option.value=value;input.append(option);}
    // Preserve older cost-row ratings without offering them on new rows.
    if(row.priority&&!boot.options.priority.includes(row.priority)){const option=node('option',row.priority+t('（已有值）'));option.value=row.priority;input.append(option);}
   }
   else {input.maxLength=key==='description'?5000:100;if(['quantity','rate'].includes(key))input.inputMode='decimal';}
   input.value=row[key]||'';input.addEventListener(key==='priority'?'change':'input',()=>{row[key]=input.value;updateCostTotal();scheduleSave();});cell.append(input);tr.append(cell);
   if(key==='rate'){const value=node('td');value.id='costValue_'+index;value.className='cost-money';tr.append(value);}
  }
  const cell=node('td'),remove=node('button',t('删除'));remove.type='button';remove.setAttribute('aria-label',t("删除费用项 {0}",index+1));remove.onclick=async()=>{if(await confirmAction(t('删除费用项'),t('确认删除这条费用记录？'))){project.cost_rows.splice(index,1);renderCosts();scheduleSave();}};cell.append(remove);tr.append(cell);body.append(tr);
 });updateCostTotal();
}
function buildPersonField(key){
 const box=node('div',undefined,'person-field');const label=node('label',personRoles[key].label);label.htmlFor='meta_'+key;
 const select=node('select');select.id='meta_'+key;
 const manual=node('input');manual.id='manual_'+key;manual.maxLength=500;manual.placeholder=t('手动填写姓名');manual.setAttribute('aria-label',personRoles[key].label+t('姓名'));manual.hidden=true;
 const details=node('p',undefined,'person-details');details.id='details_'+key;details.setAttribute('aria-live','polite');
 select.addEventListener('change',()=>{
  if(select.value==='__manual__'){manual.hidden=false;WorkbenchState.manualPerson(project.metadata,key,personRoles[key].prefix);manual.value=project.metadata[key]||'';manual.focus();}
  else {
   const person=boot.personnel.people.find(p=>p.id===select.value),prefix=personRoles[key].prefix;
   project.metadata[key]=person?.name||'';project.metadata[key+'_id']=person?.id||'';
   project.metadata[prefix+'_qualifications']=person?.qualifications||'';project.metadata[prefix+'_title']=person?.title||'';
   manual.hidden=true;
  }
  renderPersonDetails(key);
  scheduleSave();
 });
 manual.addEventListener('input',()=>{project.metadata[key]=manual.value;WorkbenchState.manualPerson(project.metadata,key,personRoles[key].prefix);renderPersonDetails(key);scheduleSave();});
 box.append(label,select,manual,details);$('metadataFields').append(box);
}
function renderPersonDetails(key){
 const prefix=personRoles[key].prefix;
 const values=[project.metadata[prefix+'_qualifications'],project.metadata[prefix+'_title']].filter(value=>value?.trim());
 $('details_'+key).textContent=values.join(' · ');$('details_'+key).hidden=!values.length;
}
function renderPersonChoices(){
 if(!project)return;
 for(const [key,spec] of Object.entries(personRoles)){
  const select=$('meta_'+key);select.replaceChildren();
  const empty=node('option',t(spec.role==='author'?'请选择作者…':'请选择审阅者…'));empty.value='';select.append(empty);
  const people=boot.personnel.people.filter(p=>p.roles.includes(spec.role));
  for(const person of people){const option=node('option',person.name);option.value=person.id;select.append(option);}
  const manual=node('option',t('手动填写姓名'));manual.value='__manual__';select.append(manual);
  const name=project.metadata[key]||'',ref=project.metadata[key+'_id'];
  const selected=people.find(p=>p.name===name&&(!ref||p.id===ref));
  select.value=selected?selected.id:name?'__manual__':'';
  $('manual_'+key).hidden=select.value!=='__manual__';$('manual_'+key).value=name;
  renderPersonDetails(key);
 }
}
function loadPersonnelEditor(person=null){
 personnelEditorId=person?.id||null;personnelDirty=false;
 $('personnelEditorTitle').textContent=person?t('编辑人员'):t('新增人员');
 for(const key of ['name','qualifications','title'])$('personnel_'+key).value=person?.[key]||'';
 $('personnel_author').checked=person?person.roles.includes('author'):true;
 $('personnel_reviewer').checked=person?person.roles.includes('reviewer'):true;
 $('deletePersonnel').hidden=!person;$('savePersonnel').textContent=person?t('保存修改'):t('添加人员');
 renderPersonnelList();
}
function renderPersonnelList(){
 const list=$('personnelList');list.replaceChildren();
 if(!boot.personnel.people.length)list.append(node('p',t('人员库为空，添加人员后即可在报告中选择。'),'personnel-empty'));
 for(const person of boot.personnel.people){
  const button=node('button',undefined,'personnel-card');button.type='button';button.classList.toggle('selected',person.id===personnelEditorId);
  button.append(node('strong',person.name),node('small',person.title||t('职位未填写')),node('small',person.roles.map(r=>r==='author'?t('作者'):t('审阅者')).join(WorkbenchI18n.language==='en'?', ':'、')));
  button.onclick=action(async()=>{if(await discardPersonnelChanges())loadPersonnelEditor(person);});list.append(button);
 }
}
async function discardPersonnelChanges(){return !personnelDirty||await confirmAction(t('放弃未保存的人员修改'),t('人员资料尚未保存。是否放弃本次修改？'));}
async function openPersonnel(){
 boot.personnel=await api('/api/personnel');renderPersonChoices();loadPersonnelEditor(boot.personnel.people[0]);$('personnelDialog').showModal();
}
async function savePersonnel(){
 const person={id:personnelEditorId||crypto.randomUUID().replaceAll('-',''),roles:[]};
 for(const key of ['name','qualifications','title'])person[key]=$('personnel_'+key).value.trim();
 for(const role of ['author','reviewer'])if($('personnel_'+role).checked)person.roles.push(role);
 if(!person.name)throw new Error(t('请填写姓名'));if(!person.roles.length)throw new Error(t('请选择作者或审阅者角色'));
 const snapshot=structuredClone(boot.personnel),index=snapshot.people.findIndex(p=>p.id===person.id);
 if(index>=0)snapshot.people[index]=person;else snapshot.people.push(person);
 boot.personnel=await api('/api/personnel',snapshot);loadPersonnelEditor(boot.personnel.people.find(p=>p.id===person.id));renderPersonChoices();toast(t('人员资料已保存'));
}
async function deletePersonnel(){
 const person=boot.personnel.people.find(p=>p.id===personnelEditorId);if(!person)return;
 if(!(await confirmAction(t('删除人员'),t("从人员库删除 {0}？已填写报告中的姓名、资质和职位会保留。",person.name))))return;
 const snapshot=structuredClone(boot.personnel);snapshot.people=snapshot.people.filter(p=>p.id!==person.id);
 boot.personnel=await api('/api/personnel',snapshot);loadPersonnelEditor(boot.personnel.people[0]);renderPersonChoices();toast(t('人员已删除'));
}
async function closePersonnel(){if(await discardPersonnelChanges())$('personnelDialog').close();}
function renderLibrary(key){
 const select=$(key+'Select'),selected=select.value,search=$(key+'Search').value.toLowerCase().trim();select.replaceChildren();
 const first=node('option',search?t('选择搜索结果…'):t('从文字库选择…'));first.value='';select.append(first);
 const rows=boot.library[key].filter(r=>(r.text+' '+r.elements+' '+r.id).toLowerCase().includes(search));
 for(const r of rows){const opt=node('option',r.id+' · '+r.text);opt.value=r.id;select.append(opt);}
 if(rows.some(r=>r.id===selected))select.value=selected;
 $(key+'Count').textContent=search?t("{0} 个结果",rows.length):t("{0} 条",boot.library[key].length);
}
function updateTitle(){
 $('projectTitle').textContent=project.metadata.site||t('新的检查报告');
 $('projectSubtitle').textContent=project.metadata.report_number?project.metadata.report_number+' · '+(project.metadata.client||t('客户未填写')):t('先填写报告信息，再整理现场照片。');
}
function updateSummary(){
 if(!project)return;
 const count=project.items.length,photos=project.items.reduce((n,i)=>n+itemPhotos(i).length,0);
 $('itemCount').textContent=count;$('reportSummary').textContent=count?(WorkbenchI18n.language==='en'?count+(count===1?' inspection item':' inspection items')+' · '+photoCountText(photos):t("{0} 个检查项 · {1} 张照片",count,photos)):t('还没有已保存的检查项');
 $('generateButton').disabled=busy||count===0;$('previewButton').disabled=busy||count===0;$('previewButton').textContent=previewJob?t('查看预览进度 / 结果'):t('预览报告');
}
function renderProjects(){
 const select=$('projectSelect');select.replaceChildren();
 for(const p of boot.projects){const count=WorkbenchI18n.language==='en'?' · '+p.count+(p.count===1?' item':' items'):t(" · {0} 项",p.count);const op=node('option',(p.site||t('未命名报告'))+count);op.value=p.id;select.append(op);}
 if(project){if(!boot.projects.some(p=>p.id===project.id)){const op=node('option',project.metadata.site||t('新的检查报告'));op.value=project.id;select.prepend(op);}select.value=project.id;}
}
function renderEditor(){
 activeSubitemId=currentSubitem().id;
 for(const key of fields){
  const value=project.editor[key]||'',custom=!!value&&!boot.options[key].includes(value);
  $('rating_'+key).value=custom?'__manual__':value;
  $('manual_rating_'+key).hidden=!custom;$('manual_rating_'+key).value=value;
 }
 for(const key of ['observation','recommendation']){
  $(key+'Text').value=currentSubitem()[key]||'';$(key+'Search').value='';renderLibrary(key);
  $(key+'Select').value=currentSubitem()[key+'_source']||'';
  $(key+'Source').textContent=currentSubitem()[key+'_source']?t('来源 ')+currentSubitem()[key+'_source']+t(' · 可继续编辑'):t('手动输入');
 }
 updateEditorTitle();
 $('editingBadge').hidden=!project.editor_id;$('saveItem').textContent=project.editor_id?t('Save · 保存修改'):t('Save · 保存检查项');renderPhotos();renderSubitems();
}
function renderSubitems(){
 clearItemDrag();const list=$('subitemList');list.replaceChildren();
 const item=project.editor,parentNumber=project.editor_id?project.items.findIndex(i=>i.id===project.editor_id)+1:project.items.length+1;
 item.subitems.forEach((group,index)=>{
  const row=node('div',undefined,'subitem-card');row.dataset.itemId=group.id;row.dataset.dropLabel=t('松开鼠标放到这里');row.classList.toggle('selected',group.id===currentSubitem().id);
  const grip=node('button','⠿','subitem-grip');grip.type='button';grip.disabled=item.subitems.length<2;grip.setAttribute('aria-label',t('拖动排序子项 {0}',index+1));bindItemDrag(grip,row,group.id,list,moveSubitem);row.append(grip);
  const select=node('button',undefined,'subitem-select');select.type='button';select.setAttribute('aria-pressed',String(group.id===currentSubitem().id));
  if(group.photos.length){const image=node('img');image.src='/photos/'+group.photos[0].id+'.jpg';image.alt='';select.append(image);}
  const text=node('span',undefined,'subitem-card-text');text.append(node('strong',t('子项 {0}',index+1)),node('small',group.observation||t('填写这组照片的现场描述')));select.append(text,node('span',photoRange(item,index,parentNumber)+' · '+photoCountText(group.photos.length),'subitem-photo-range'));
  select.onclick=()=>{if(!busy){activeSubitemId=group.id;renderEditor();}};row.append(select);
  const controls=node('div',undefined,'subitem-actions');
  for(const [label,title,disabled,fn] of [
   ['↑',t('子项前移'),index===0,()=>moveSubitem(group.id,item.subitems[index-1].id)],
   ['↓',t('子项后移'),index===item.subitems.length-1,()=>moveSubitem(group.id,item.subitems[index+1].id,true)],
   ['×',t('删除子项'),item.subitems.length===1,async()=>{if((group.photos.length||group.observation||group.recommendation)&&!(await confirmAction(t('删除子项'),t('删除这组照片和描述？原始照片仍保留在本地。'))))return;item.subitems.splice(index,1);if(activeSubitemId===group.id)activeSubitemId=item.subitems[Math.min(index,item.subitems.length-1)].id;renderEditor();await flush();}]
  ]){const button=node('button',label);button.type='button';button.title=title;button.setAttribute('aria-label',title+' '+(index+1));button.disabled=disabled;button.onclick=action(fn);controls.append(button);}
  row.append(controls);list.append(row);
 });
 const index=item.subitems.findIndex(g=>g.id===currentSubitem().id);
 $('activeSubitemTitle').textContent=t('编辑子项 {0}',index+1);
 $('activeSubitemRange').textContent=t('照片编号：{0}',photoRange(item,index,parentNumber));
}
async function moveSubitem(id,targetId,after=false){
 const groups=project.editor.subitems,from=groups.findIndex(g=>g.id===id),target=groups.findIndex(g=>g.id===targetId);if(from<0||target<0||from===target)return;
 let to=target+(after?1:0);if(from<to)to--;if(from===to)return;
 const previous=[...groups],[group]=groups.splice(from,1);groups.splice(to,0,group);renderEditor();
 try{await flush();}catch(error){if(error.code!=='revision_conflict')project.editor.subitems=previous;renderEditor();throw error;}
}
function renderPhotos(){
 const group=currentSubitem(),grid=$('photoGrid');grid.replaceChildren();$('photoCount').textContent=photoCountText(group.photos.length,true);
 group.photos.forEach((photo,index)=>{
  const card=node('div',undefined,'photo-card');const image=node('img');image.src='/photos/'+photo.id+'.jpg';image.alt=photo.caption||photo.name;image.loading='lazy';
  const name=node('span',`${index+1}. ${photo.name}`,'name');name.title=photo.name;const controls=node('div',undefined,'photo-controls');
  const caption=node('input');caption.className='photo-caption';caption.value=photo.caption||'';caption.maxLength=200;caption.placeholder=t('照片名称（可留空）');caption.setAttribute('aria-label',t('照片 ')+(index+1)+t(' 名称'));
  caption.addEventListener('input',()=>{photo.caption=caption.value;image.alt=photo.caption||photo.name;scheduleSave();});
  for(const [label,title,fn] of [
   ['←',t('照片前移'),()=>{if(index>0)[group.photos[index-1],group.photos[index]]=[photo,group.photos[index-1]];renderPhotos();renderSubitems();scheduleSave();}],
   ['→',t('照片后移'),()=>{if(index<group.photos.length-1)[group.photos[index+1],group.photos[index]]=[photo,group.photos[index+1]];renderPhotos();renderSubitems();scheduleSave();}],
   [t('编辑'),t('编辑照片'),()=>openPhotoEditor(photo,index)],
   ['↻',t('顺时针旋转照片'),async()=>{const p=await api('/api/rotate',{id:photo.id});group.photos[index]={...photo,...p};renderPhotos();renderSubitems();await flush();}],
   ['×',t('移除当前照片'),()=>{group.photos.splice(index,1);renderPhotos();renderSubitems();scheduleSave();}]
  ]){const b=node('button',label);b.title=title;b.setAttribute('aria-label',title);b.onclick=action(fn);controls.append(b);}
  card.append(image,name,caption,controls);grid.append(card);
 });
}
async function openPhotoEditor(photo,index){
 const image=new Image();image.src='/photos/'+photo.id+'.jpg';await image.decode();
 photoEditor={image,index,subitemId:currentSubitem().id,photoId:photo.id,projectId:project.id,operations:[],redo:[],tool:'crop',selection:null,drag:null,zoom:1};
 $('photoCropRatio').value='0';$('photoMarkColor').value='#e32636';$('photoMarkWidth').value='1';
 $('photoEditorDialog').showModal();setPhotoCrop();renderPhotoEditor();
}
function drawPhotoMark(ctx,op){
 ctx.save();ctx.strokeStyle=op.color||'#e32636';ctx.lineWidth=op.width||Math.max(2,Math.round(Math.min(ctx.canvas.width,ctx.canvas.height)/150));ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();
 if(op.type==='pen'){ctx.moveTo(...op.points[0]);for(const point of op.points.slice(1))ctx.lineTo(...point);}
 else{
  const [x0,y0,x1,y1]=op.box;
  if(op.type==='circle')ctx.ellipse((x0+x1-1)/2,(y0+y1-1)/2,Math.max(0,(x1-x0-1)/2),Math.max(0,(y1-y0-1)/2),0,0,Math.PI*2);
  if(op.type==='rectangle')ctx.rect(x0,y0,x1-x0-1,y1-y0-1);
  if(op.type==='arrow'){
   ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);const angle=Math.atan2(y1-y0,x1-x0),length=Math.min(Math.hypot(x1-x0,y1-y0)*.4,Math.max(12,ctx.lineWidth*4));
   ctx.moveTo(x1-length*Math.cos(angle-.5),y1-length*Math.sin(angle-.5));ctx.lineTo(x1,y1);ctx.lineTo(x1-length*Math.cos(angle+.5),y1-length*Math.sin(angle+.5));
  }
 }
 ctx.stroke();ctx.restore();
}
function photoEditImage(){
 let canvas=document.createElement('canvas');canvas.width=photoEditor.image.naturalWidth;canvas.height=photoEditor.image.naturalHeight;canvas.getContext('2d').drawImage(photoEditor.image,0,0);
 for(const op of photoEditor.operations){
  if(op.type==='crop'){
   const [x0,y0,x1,y1]=op.box,next=document.createElement('canvas');next.width=x1-x0;next.height=y1-y0;next.getContext('2d').drawImage(canvas,x0,y0,x1-x0,y1-y0,0,0,next.width,next.height);canvas=next;
  }else if(op.type==='rotate'){
   const next=document.createElement('canvas');next.width=canvas.height;next.height=canvas.width;const ctx=next.getContext('2d');ctx.translate(next.width/2,next.height/2);ctx.rotate(op.turn*Math.PI/2);ctx.drawImage(canvas,-canvas.width/2,-canvas.height/2);canvas=next;
  }else drawPhotoMark(canvas.getContext('2d'),op);
 }
 return canvas;
}
function photoRendered(){return photoEditor.rendered||(photoEditor.rendered=photoEditImage());}
function setPhotoCrop(){
 if(!photoEditor)return;const image=photoRendered(),ratio=Number($('photoCropRatio').value);let w=image.width,h=image.height;
 if(ratio){if(w/h>ratio)w=Math.round(h*ratio);else h=Math.round(w/ratio);}
 photoEditor.selection=[Math.round((image.width-w)/2),Math.round((image.height-h)/2),Math.round((image.width+w)/2),Math.round((image.height+h)/2)];
}
function photoMarkStyle(){const image=photoRendered();return {color:$('photoMarkColor').value,width:Math.max(2,Math.min(60,Math.round(Math.min(image.width,image.height)/150*Number($('photoMarkWidth').value))))};}
function renderPhotoEditor(){
 if(!photoEditor)return;const image=photoRendered(),canvas=$('photoEditCanvas'),stage=$('photoEditStage');
 if(canvas.width!==image.width)canvas.width=image.width;if(canvas.height!==image.height)canvas.height=image.height;
 const scale=Math.min((stage.clientWidth-24)/image.width,(stage.clientHeight-24)/image.height,1)*photoEditor.zoom;
 canvas.style.width=Math.max(1,Math.round(image.width*scale))+'px';canvas.style.height=Math.max(1,Math.round(image.height*scale))+'px';canvas.style.cursor=photoEditor.tool==='pan'?'grab':'crosshair';
 const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const selection=photoEditor.selection;
 if(photoEditor.tool==='crop'&&selection){
  const [x0,y0,x1,y1]=selection;ctx.save();ctx.fillStyle='#0008';ctx.fillRect(0,0,canvas.width,y0);ctx.fillRect(0,y1,canvas.width,canvas.height-y1);ctx.fillRect(0,y0,x0,y1-y0);ctx.fillRect(x1,y0,canvas.width-x1,y1-y0);
  ctx.strokeStyle='#fff';ctx.lineWidth=1.5/scale;ctx.strokeRect(x0,y0,x1-x0,y1-y0);ctx.globalAlpha=.5;ctx.beginPath();for(const f of [1/3,2/3]){ctx.moveTo(x0+(x1-x0)*f,y0);ctx.lineTo(x0+(x1-x0)*f,y1);ctx.moveTo(x0,y0+(y1-y0)*f);ctx.lineTo(x1,y0+(y1-y0)*f);}ctx.stroke();ctx.globalAlpha=1;
  const handle=8/scale;for(const [x,y] of [[x0,y0],[x1,y0],[x0,y1],[x1,y1]]){ctx.fillStyle='#fff';ctx.fillRect(x-handle/2,y-handle/2,handle,handle);}ctx.restore();
 }else if(photoEditor.drag?.mark){drawPhotoMark(ctx,photoEditor.drag.mark);}
 for(const tool of ['crop','circle','rectangle','arrow','pen','pan'])$('photoTool'+tool[0].toUpperCase()+tool.slice(1)).setAttribute('aria-pressed',photoEditor.tool===tool);
 $('photoCropSettings').hidden=photoEditor.tool!=='crop';$('photoMarkSettings').hidden=['crop','pan'].includes(photoEditor.tool);
 const hints={crop:t('拖动框内移动范围，拖动四角调整大小；框外拖动可重新框选。'),circle:t('拖动绘制圆圈，标出需要注意的区域。'),rectangle:t('拖动框选标注区域。'),arrow:t('从起点拖向需要指示的位置。'),pen:t('按住鼠标自由绘制。'),pan:t('放大后拖动照片查看细节。')};
 $('photoEditHint').textContent=hints[photoEditor.tool];$('photoEditSize').textContent=image.width+' × '+image.height+' px';$('photoZoomValue').textContent=Math.round(scale*100)+'%';
 $('applyPhotoCrop').disabled=busy||!selection||selection[2]-selection[0]<10||selection[3]-selection[1]<10;
 for(const id of ['undoPhotoEdit','resetPhotoEdit','savePhotoEdit'])$(id).disabled=busy||!photoEditor.operations.length;
 $('redoPhotoEdit').disabled=busy||!photoEditor.redo.length;$('photoZoomOut').disabled=photoEditor.zoom<=1;$('photoZoomIn').disabled=photoEditor.zoom>=4;
}
function closePhotoEditor(){if(busy)return;$('photoEditorDialog').close();photoEditor=null;}
function commitPhotoEdit(operation){
 if(photoEditor.operations.length>=50){toast(t('最多支持 50 步编辑，请先保存照片。'));return;}
 photoEditor.operations.push(operation);photoEditor.redo=[];photoEditor.rendered=null;photoEditor.selection=null;
 if(photoEditor.tool==='crop')setPhotoCrop();renderPhotoEditor();
}
function changePhotoHistory(redo=false){
 if(busy||!photoEditor||photoEditor.drag)return;const from=redo?photoEditor.redo:photoEditor.operations,to=redo?photoEditor.operations:photoEditor.redo;
 if(!from.length)return;to.push(from.pop());photoEditor.selection=null;photoEditor.rendered=null;if(photoEditor.tool==='crop')setPhotoCrop();renderPhotoEditor();
}
function setupPhotoEditor(){
 const canvas=$('photoEditCanvas'),stage=$('photoEditStage');
 const point=event=>{const r=canvas.getBoundingClientRect();return [Math.round(Math.max(0,Math.min(canvas.width-1,(event.clientX-r.left)*canvas.width/r.width))),Math.round(Math.max(0,Math.min(canvas.height-1,(event.clientY-r.top)*canvas.height/r.height)))];};
 const ready=()=>!busy&&photoEditor&&!photoEditor.drag;
 for(const tool of ['crop','circle','rectangle','arrow','pen','pan'])$('photoTool'+tool[0].toUpperCase()+tool.slice(1)).onclick=()=>{
  if(!ready())return;photoEditor.tool=tool;photoEditor.selection=null;if(tool==='crop')setPhotoCrop();renderPhotoEditor();
 };
 canvas.onpointerdown=event=>{
  if(busy||event.button!==0||!photoEditor||photoEditor.drag)return;event.preventDefault();canvas.focus();const start=point(event),tool=photoEditor.tool;
  const drag={start,pointerId:event.pointerId,screen:[event.clientX,event.clientY],scroll:[stage.scrollLeft,stage.scrollTop]};
  if(tool==='crop'){
   const s=photoEditor.selection,threshold=12*canvas.width/canvas.getBoundingClientRect().width;
   const corners=s?[[s[0],s[1]],[s[2],s[1]],[s[0],s[3]],[s[2],s[3]]]:[];
   const corner=corners.findIndex(p=>Math.hypot(p[0]-start[0],p[1]-start[1])<threshold);
   if(corner>=0){drag.mode='resize';drag.anchor=corners[3-corner];}
   else if(s&&start[0]>s[0]&&start[0]<s[2]&&start[1]>s[1]&&start[1]<s[3]){drag.mode='move';drag.original=[...s];}
   else {drag.mode='resize';drag.anchor=start;photoEditor.selection=null;}
  }else if(tool!=='pan')drag.mark={type:tool,...photoMarkStyle(),...(tool==='pen'?{points:[start]}:{box:[...start,...start]})};
  photoEditor.drag=drag;canvas.setPointerCapture(event.pointerId);renderPhotoEditor();
 };
 canvas.onpointermove=event=>{
  const drag=photoEditor?.drag;if(!drag||event.pointerId!==drag.pointerId)return;
  const end=point(event),tool=photoEditor.tool;
  if(tool==='pan'){stage.scrollLeft=drag.scroll[0]+drag.screen[0]-event.clientX;stage.scrollTop=drag.scroll[1]+drag.screen[1]-event.clientY;return;}
  if(tool==='crop'){
   if(drag.mode==='move'){
    const s=drag.original,dx=Math.max(-s[0],Math.min(canvas.width-s[2],end[0]-drag.start[0])),dy=Math.max(-s[1],Math.min(canvas.height-s[3],end[1]-drag.start[1]));photoEditor.selection=[s[0]+dx,s[1]+dy,s[2]+dx,s[3]+dy];
   }else{
    const a=drag.anchor,ratio=Number($('photoCropRatio').value),sx=end[0]>=a[0]?1:-1,sy=end[1]>=a[1]?1:-1;let w=Math.abs(end[0]-a[0]),h=Math.abs(end[1]-a[1]);
    if(ratio){w=Math.min(Math.max(w,h*ratio),sx>0?canvas.width-a[0]:a[0],(sy>0?canvas.height-a[1]:a[1])*ratio);h=w/ratio;}
    const b=[Math.round(a[0]+sx*w),Math.round(a[1]+sy*h)];photoEditor.selection=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];
   }
  }else if(tool==='pen'){
   const pts=drag.mark.points,last=pts.at(-1);if(pts.length<2000&&Math.hypot(end[0]-last[0],end[1]-last[1])>=1)pts.push(end);
  }else drag.mark.box=tool==='arrow'?[...drag.start,...end]:[Math.min(drag.start[0],end[0]),Math.min(drag.start[1],end[1]),Math.max(drag.start[0],end[0]),Math.max(drag.start[1],end[1])];
  renderPhotoEditor();
 };
 canvas.onpointerup=event=>{
  const drag=photoEditor?.drag;if(!drag||event.pointerId!==drag.pointerId)return;canvas.onpointermove(event);photoEditor.drag=null;if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);
  const mark=drag.mark;if(mark){const valid=mark.type==='pen'?mark.points.length>=2:mark.type==='arrow'?Math.hypot(mark.box[2]-mark.box[0],mark.box[3]-mark.box[1])>=3:mark.box[2]-mark.box[0]>=3&&mark.box[3]-mark.box[1]>=3;if(valid)commitPhotoEdit(mark);}
  renderPhotoEditor();
 };
 const cancelDrag=()=>{if(photoEditor?.drag){photoEditor.drag=null;renderPhotoEditor();}};canvas.onpointercancel=cancelDrag;canvas.onlostpointercapture=cancelDrag;
 $('photoCropRatio').onchange=()=>{if(ready()){setPhotoCrop();renderPhotoEditor();}};
 $('applyPhotoCrop').onclick=()=>{if(ready()&&!$('applyPhotoCrop').disabled)commitPhotoEdit({type:'crop',box:[...photoEditor.selection]});};
 $('undoPhotoEdit').onclick=()=>changePhotoHistory();$('redoPhotoEdit').onclick=()=>changePhotoHistory(true);
 $('resetPhotoEdit').onclick=()=>{if(!ready())return;photoEditor.operations=[];photoEditor.redo=[];photoEditor.selection=null;photoEditor.rendered=null;photoEditor.zoom=1;if(photoEditor.tool==='crop')setPhotoCrop();renderPhotoEditor();};
 for(const [id,turn] of [['rotatePhotoLeft',-1],['rotatePhotoRight',1]])$(id).onclick=()=>{if(ready())commitPhotoEdit({type:'rotate',turn});};
 const zoom=value=>{if(ready()){photoEditor.zoom=Math.max(1,Math.min(4,value));renderPhotoEditor();}};
 $('photoZoomOut').onclick=()=>{if(photoEditor)zoom(photoEditor.zoom-.5);};$('photoZoomIn').onclick=()=>{if(photoEditor)zoom(photoEditor.zoom+.5);};$('photoZoomFit').onclick=()=>zoom(1);
 $('photoEditorDialog').addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'&&!['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName)){event.preventDefault();changePhotoHistory(event.shiftKey);}});
 window.addEventListener('resize',()=>{if(photoEditor)renderPhotoEditor();});
 $('closePhotoEditor').onclick=closePhotoEditor;$('cancelPhotoEdit').onclick=closePhotoEditor;
 $('photoEditorDialog').oncancel=event=>{event.preventDefault();closePhotoEditor();};
 $('savePhotoEdit').onclick=action(async()=>{
  const edit=photoEditor;if(!edit?.operations.length)return;
  if(edit.drag)throw new Error(t('请完成当前操作后保存'));
  const group=project.editor.subitems.find(g=>g.id===edit.subitemId);
  if(project.id!==edit.projectId||group?.photos[edit.index]?.id!==edit.photoId)throw new Error(t('照片已改变，请重新打开编辑窗口'));
  const saved=await api('/api/photo-edit',{id:edit.photoId,operations:edit.operations});
  const previous=group.photos[edit.index];group.photos[edit.index]={...previous,...saved};
  try{await flush();}catch(error){if(error.code!=='revision_conflict')group.photos[edit.index]=previous;throw error;}
  $('photoEditorDialog').close();photoEditor=null;renderPhotos();renderSubitems();toast(t('照片已保存；点击 Save 将修改加入检查项。'));
 });
}
function updateEditorTitle(){$('editorTitle').textContent=project.editor_id?t('编辑检查项 ')+(project.items.findIndex(i=>i.id===project.editor_id)+1):t('整理一个检查项');}
function clearItemDrag(){
 const previous=itemDrag;
 itemDrag=null;
 if(previous?.frame)cancelAnimationFrame(previous.frame);
 previous?.ghost?.remove();
 if(previous?.handle.hasPointerCapture(previous.pointerId))previous.handle.releasePointerCapture(previous.pointerId);
 document.body.classList.remove('item-sorting');
 for(const row of previous?.container?.children||[]){row.classList.remove('dragging');row.style.removeProperty('transform');}
}
function itemDragTarget(){
 if(!itemDrag?.active)return;
 const drag=itemDrag,bounds=drag.container.getBoundingClientRect(),y=drag.y+window.scrollY;
 const inside=drag.x>=bounds.left&&drag.x<=bounds.right&&drag.y>=bounds.top-24&&drag.y<=bounds.bottom+24;
 const others=drag.rows.filter(entry=>entry.id!==drag.id);
 // Use original document coordinates so animated rows never move the hit targets.
 const position=inside?others.filter(entry=>y>entry.top+entry.height/2).length:drag.originalIndex;
 drag.target=inside?(position<others.length?{id:others[position].id,after:false}:{id:others.at(-1).id,after:true}):null;
 if(position===drag.position)return;
 drag.position=position;
 const ordered=[...others];ordered.splice(position,0,drag.rows[drag.originalIndex]);
 let top=drag.rows[0].top;
 for(const entry of ordered){entry.row.style.transform=`translate3d(0,${top-entry.top}px,0)`;top+=entry.height+drag.gap;}
}
function scrollItemDrag(){
 if(!itemDrag?.active)return;
 const edge=48,step=itemDrag.y<edge?-18:itemDrag.y>window.innerHeight-edge?18:0;
 if(step){window.scrollBy(0,step);itemDragTarget();}
 itemDrag.frame=requestAnimationFrame(scrollItemDrag);
}
function startItemDrag(row){
 const bounds=row.getBoundingClientRect(),ghost=row.cloneNode(true);
 ghost.classList.remove('dragging');ghost.classList.add('item-drag-preview');ghost.setAttribute('aria-hidden','true');ghost.inert=true;
 ghost.style.width=bounds.width+'px';ghost.style.left='0';ghost.style.top='0';document.body.append(ghost);
 itemDrag.ghost=ghost;itemDrag.offsetX=itemDrag.startX-bounds.left;itemDrag.offsetY=itemDrag.startY-bounds.top;
 itemDrag.rows=[...itemDrag.container.children].map(row=>{const rect=row.getBoundingClientRect();return {row,id:row.dataset.itemId,top:rect.top+window.scrollY,height:rect.height};});
 itemDrag.gap=itemDrag.rows.length>1?itemDrag.rows[1].top-itemDrag.rows[0].top-itemDrag.rows[0].height:0;
 itemDrag.originalIndex=itemDrag.rows.findIndex(entry=>entry.id===itemDrag.id);itemDrag.position=itemDrag.originalIndex;
 row.classList.add('dragging');document.body.classList.add('item-sorting');updateItemDragPreview();scrollItemDrag();
}
function updateItemDragPreview(){
 if(itemDrag?.ghost)itemDrag.ghost.style.transform=`translate3d(${itemDrag.x-itemDrag.offsetX}px,${itemDrag.y-itemDrag.offsetY}px,0) scale(1.015)`;
}
function bindItemDrag(handle,row,id,container,move){
 handle.addEventListener('pointerdown',event=>{
  if(event.button!==0||busy||handle.disabled)return;
  event.preventDefault();handle.focus();
  itemDrag={id,container,projectId:project.id,pointerId:event.pointerId,handle,startX:event.clientX,startY:event.clientY,x:event.clientX,y:event.clientY,active:false};handle.setPointerCapture(event.pointerId);
 });
 handle.addEventListener('pointermove',event=>{
  if(!itemDrag||itemDrag.pointerId!==event.pointerId)return;
  itemDrag.x=event.clientX;itemDrag.y=event.clientY;
  if(!itemDrag.active&&Math.hypot(itemDrag.x-itemDrag.startX,itemDrag.y-itemDrag.startY)>5){itemDrag.active=true;startItemDrag(row);}
  updateItemDragPreview();itemDragTarget();
 });
 handle.addEventListener('pointerup',event=>{
  if(!itemDrag||itemDrag.pointerId!==event.pointerId)return;
  itemDrag.x=event.clientX;itemDrag.y=event.clientY;itemDragTarget();
  const source=itemDrag;clearItemDrag();
  if(source.active&&source.target&&source.projectId===project.id)action(()=>move(source.id,source.target.id,source.target.after))();
 });
 handle.addEventListener('pointercancel',clearItemDrag);handle.addEventListener('lostpointercapture',clearItemDrag);
 handle.addEventListener('keydown',event=>{if(event.key==='Escape')clearItemDrag();});
}
async function moveItem(id,targetId,after=false){
 const from=project.items.findIndex(item=>item.id===id),target=project.items.findIndex(item=>item.id===targetId);
 if(from<0||target<0||from===target)return;
 let to=target+(after?1:0);if(from<to)to--;if(from===to)return;
 const previous=[...project.items];const [item]=project.items.splice(from,1);project.items.splice(to,0,item);renderItems();
 try{await flush();}catch(error){if(error.code!=='revision_conflict')project.items=previous;renderItems();throw error;}
}
function renderItems(){
 clearItemDrag();
 const list=$('savedItems');list.replaceChildren();
 if(!project.items.length){const empty=node('div',undefined,'empty-state');empty.append(node('strong',t('现场发现，从第一张照片开始。')),node('p',t('保存的检查项会出现在这里，可以编辑、调整顺序，然后一起生成报告。')));list.append(empty);}
 project.items.forEach((item,index)=>{
  const row=node('article',undefined,'saved-item');row.dataset.itemId=item.id;row.dataset.dropLabel=t('松开鼠标放到这里');
  const handle=node('button',undefined,'item-number item-drag-handle');handle.type='button';handle.disabled=project.items.length<2;
  handle.title=t('拖动排序');handle.setAttribute('aria-label',t('拖动排序检查项 ')+(index+1));handle.append(node('span','⠿','item-grip'),node('span',String(index+1).padStart(2,'0')));row.append(handle);
  bindItemDrag(handle,row,item.id,list,moveItem);
  const photos=itemPhotos(item),first=photos[0];const image=node('img');image.src='/photos/'+first.id+'.jpg';image.alt=first.caption||first.name;image.className='item-photo';image.draggable=false;row.append(image);
  const obs=node('div',undefined,'item-content');obs.append(node('strong',item.element),node('p',subitemCountText(item.subitems.length)));
  const meta=node('div',undefined,'item-meta');const priority=node('span',item.priority,'priority');priority.dataset.priority=item.priority;meta.append(priority,node('span',photoCountText(photos.length)),node('span',item.condition_rating));obs.append(meta);row.append(obs);
  const rec=node('div',undefined,'item-content');rec.append(node('strong',t('共用评级')),node('p',item.likelihood+' · '+item.severity));row.append(rec);
  const actions=node('div',undefined,'item-actions');
  for(const [label,fn] of [
   [t('编辑'),async()=>{if(editorHasContent()&&project.editor_id!==item.id&&!(await confirmAction(t('切换到已保存项'),t('当前编辑区已自动保存。切换后会替换编辑区内容，请先保存需要加入报告的检查项。'))))return;project.editor=structuredClone(item);delete project.editor.id;project.editor_id=item.id;renderEditor();await flush();$('editorTitle').scrollIntoView({behavior:'smooth',block:'center'});}],
   ['↑',async()=>{if(index>0)await moveItem(item.id,project.items[index-1].id);}],
   ['↓',async()=>{if(index<project.items.length-1)await moveItem(item.id,project.items[index+1].id,true);}],
   [t('删除'),async()=>{if(!(await confirmAction(t('删除检查项'),t("从报告中删除第 {0} 项？原始照片仍保存在本地。",index+1))))return;project.items.splice(index,1);if(project.editor_id===item.id){project.editor=blankEditor();project.editor_id=null;renderEditor();}renderItems();await flush();}]
  ]){const b=node('button',label);b.onclick=action(fn);b.setAttribute('aria-label',label+t('检查项 ')+(index+1));actions.append(b);}
  row.append(actions);
  const groups=node('div',undefined,'saved-subitems');item.subitems.forEach((group,gi)=>{
   const detail=node('div',undefined,'saved-subitem'),pictures=node('div',undefined,'saved-subitem-photos');
   for(const photo of group.photos){const thumb=node('img');thumb.src='/photos/'+photo.id+'.jpg';thumb.alt=photo.caption||photo.name;thumb.loading='lazy';pictures.append(thumb);}
   const content=node('div');content.append(node('strong',t('子项 {0}',gi+1)+' · '+photoRange(item,gi,index+1)),node('p',group.observation));if(group.recommendation)content.append(node('p','Recommendation — '+group.recommendation));detail.append(pictures,content);groups.append(detail);
  });row.append(groups);list.append(row);
 });updateSummary();updateEditorTitle();
}
function editorHasContent(){return project.editor.subitems.some(g=>g.photos.length||g.observation||g.recommendation);}
function loadProject(value){project=value;activeSubitemId=null;project.sections??={};project.cost_rows??=[];renderCosts();saver.reset(value.revision);for(const key of Object.keys(sectionLabels))$('section_'+key).value=project.sections[key]||'';for(const key of Object.keys(metadataLabels))if(!personRoles[key])$('meta_'+key).value=project.metadata[key]||'';renderPersonChoices();updateTitle();renderEditor();renderItems();renderProjects();}
async function uploadPhotos(files){
 if(!files.length)return;if(itemPhotos(project.editor).length+files.length>100)throw new Error(t('一个检查项最多 100 张照片'));
 const group=currentSubitem(),failures=[];
 for(let i=0;i<files.length;i++){
  const file=files[i];$('editorHint').textContent=t("正在导入 {0} / {1}：{2}",i+1,files.length,file.name);
  try{const photo=await api('/api/photo',file,{'X-Filename':encodeURIComponent(file.name)});group.photos.push(photo);renderPhotos();renderSubitems();await persist();}
  catch(e){failures.push(file.name+'：'+e.message);}
 }
 $('editorHint').textContent=t('已导入照片。填写描述与评级后，保存检查项。');
 if(failures.length)throw new Error(t('部分照片未导入：\n')+failures.join('\n'));
 toast(t('照片已导入并保存到草稿'));
}
async function saveItem(){
 const e=project.editor;
 if(fields.some(key=>!e[key]?.trim()))throw new Error(t('请填写 Element 和四项评级，可下拉选择或手动输入'));
 for(const [index,group] of e.subitems.entries()){if(!group.photos.length||!group.observation.trim()){activeSubitemId=group.id;renderEditor();throw new Error(t('子项 {0} 需要照片和 Observation',index+1));}}
 const item={...structuredClone(e),id:project.editor_id||crypto.randomUUID().replaceAll('-','')};
 const index=project.items.findIndex(i=>i.id===item.id),previousItem=index>=0?structuredClone(project.items[index]):null;if(index>=0)project.items[index]=item;else project.items.push(item);
 const previous=structuredClone(project.editor);const previousId=project.editor_id;
 project.editor=blankEditor();project.editor_id=null;
 try{await flush();renderItems();renderEditor();toast(index>=0?t('检查项修改已保存'):t('检查项已保存，可以继续下一项'));}
 catch(error){if(error.code!=='revision_conflict'){project.editor=previous;project.editor_id=previousId;if(index<0)project.items.pop();else project.items[index]=previousItem;}renderItems();renderEditor();throw error;}
}
async function beginPreview(){
 if(previewJob){if(!$('reportPreviewDialog').open)$('reportPreviewDialog').showModal();await pollPreview();return;}
 await flush();if(editorHasContent()&&!(await confirmAction(t('预览已保存的检查项'),t('当前编辑区还有内容。预览只包含已保存检查项；若要包含当前项，请取消后点击 Save。'))))return;
 clearTimeout(previewTimer);$('reportPreviewPages').replaceChildren();$('previewDownloads').hidden=true;$('retryPreview').hidden=true;
 if(!$('reportPreviewDialog').open)$('reportPreviewDialog').showModal();$('previewProgress').textContent=t('正在提交报告快照…');
 try{previewJob=await api('/api/preview',{id:project.id});updateSummary();await pollPreview();}
 catch(error){previewJob=null;$('previewProgress').textContent=error.message;$('retryPreview').hidden=false;updateSummary();}
}
async function pollPreview(){
 if(!previewJob)return;
 try{
  const result=await api('/api/preview-job?id='+previewJob.id);previewJob=result;$('previewProgress').textContent=t(result.message);
  $('previewSnapshot').textContent=t("{0} · 草稿版本 {1}（后续编辑不会改变此份预览）",result.site,result.project_revision);
  if(result.status==='failed')throw new Error(t(result.error));
  if(result.status==='ready'){
   $('reportPreviewPages').replaceChildren();
   for(let page=1;page<=result.pages;page++){
    const sheet=node('figure'),image=node('img');image.src='/api/preview-page?id='+result.report_id+'&page='+page;image.alt=t('报告第 ')+page+t(' 页');image.loading='lazy';sheet.append(image,node('figcaption',t('第 ')+page+' / '+result.pages+t(' 页')));$('reportPreviewPages').append(sheet);
   }
   $('openPreviewPdf').href='/api/preview-pdf?id='+result.report_id;$('downloadPreviewWord').href='/api/download?id='+result.report_id+'&name='+encodeURIComponent(result.name);$('downloadPreviewWord').download=result.name;
   $('previewDownloads').hidden=false;$('retryPreview').hidden=false;$('retryPreview').textContent=t('重新预览已保存报告');updateSummary();return;
  }
  previewTimer=setTimeout(pollPreview,600);
 }catch(error){previewJob=null;$('previewProgress').textContent=error.message;$('retryPreview').hidden=false;updateSummary();}
}
async function init(){
 await WorkbenchI18n.ready;WorkbenchI18n.apply();
 boot=await api('/api/bootstrap');buildFields();setupPhotoEditor();$('dataFolder').textContent=t('数据目录：')+boot.data_folder;
 window.addEventListener('blur',clearItemDrag);window.addEventListener('resize',clearItemDrag);
 $('appVersion').textContent='Version '+boot.version+t(' · 本地运行 · 无需登录');
 saver=new WorkbenchState.DraftSaver({snapshot:()=>project,send:snapshot=>api('/api/save',snapshot),onChange:saveStatus,onConflict:openSaveConflict,onSaved:saved=>{
  if(project.id===saved.id){project.revision=saved.revision;project.updated=saved.updated;}
  const entry={id:saved.id,site:saved.metadata.site,report_number:saved.metadata.report_number,updated:saved.updated,count:saved.items.length},index=boot.projects.findIndex(p=>p.id===saved.id);
  if(index>=0)boot.projects[index]=entry;else boot.projects.unshift(entry);renderProjects();
 }});
 if($('languageSelect')){
 $('languageSelect').value=WorkbenchI18n.language;
 $('languageSelect').onchange=action(async event=>{
  const choice=event.target.value;event.target.value=WorkbenchI18n.language;
  if(personnelDirty||photoEditor?.operations.length){toast(t('请先保存人员资料或照片编辑，再切换语言。'));return;}
  await flush();
  if(previewJob)sessionStorage.setItem('workbenchLanguagePreview',JSON.stringify({project:project.id,job:previewJob}));
  WorkbenchI18n.remember(choice);window.location.assign('/?lang='+choice);
 });
 }
 $('retrySave').onclick=action(flush);$('resolveConflict').onclick=openSaveConflict;
 $('saveSections').onclick=action(async()=>{await flush();toast(t('报告章节已保存到本地'));});
 $('conflictCopy').onclick=action(()=>recoverConflict());$('conflictLatest').onclick=action(()=>recoverConflict(true));$('conflictDownload').onclick=action(downloadRecovery);
 $('conflictKeepEditing').onclick=()=>$('saveConflictDialog').close();
 $('saveConflictDialog').oncancel=()=>{};
 $('managePersonnel').onclick=action(openPersonnel);
 $('newPersonnel').onclick=action(async()=>{if(await discardPersonnelChanges())loadPersonnelEditor();});
 const submitPersonnel=action(savePersonnel);$('personnelForm').onsubmit=e=>{e.preventDefault();submitPersonnel(e);};
 $('deletePersonnel').onclick=action(deletePersonnel);$('closePersonnel').onclick=action(closePersonnel);
 $('personnelDialog').oncancel=e=>{e.preventDefault();if(!busy)action(closePersonnel)(e);};
 for(const key of ['name','qualifications','title','author','reviewer'])$('personnel_'+key).addEventListener('input',()=>{personnelDirty=true;});
 let last=localStorage.getItem('lastProject');let chosen=boot.projects.find(p=>p.id===last)||boot.projects[0];
 loadProject(chosen?await api('/api/project?id='+chosen.id):await api('/api/new',{}));localStorage.setItem('lastProject',project.id);
 try{const previous=JSON.parse(sessionStorage.getItem('workbenchLanguagePreview'));if(previous?.project===project.id){previewJob=previous.job;updateSummary();}sessionStorage.removeItem('workbenchLanguagePreview');}catch{}
 $('saveItem').onclick=action(saveItem);
 $('addSubitem').onclick=action(async()=>{if(project.editor.subitems.length>=100)throw new Error(t('每个检查项需要 1 至 100 个子项'));const group=blankSubitem();project.editor.subitems.push(group);activeSubitemId=group.id;renderEditor();await flush();});
 $('newProject').onclick=action(async()=>{await flush();loadProject(await api('/api/new',{}));boot.projects=(await api('/api/bootstrap')).projects;renderProjects();localStorage.setItem('lastProject',project.id);$('reportDetails').open=true;});
 $('projectSelect').onchange=action(async e=>{const id=e.target.value;await flush();loadProject(await api('/api/project?id='+id));localStorage.setItem('lastProject',id);});
 $('resetEditor').onclick=action(async()=>{if(editorHasContent()&&!(await confirmAction(t('清空当前编辑区'),t('已保存检查项保持不变。当前编辑区的照片和未保存文字会从草稿中移除。'))))return;project.editor=blankEditor();project.editor_id=null;renderEditor();await flush();});
 $('dropzone').onclick=()=>{if(!busy)$('photoFiles').click();};$('dropzone').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!busy){e.preventDefault();$('photoFiles').click();}};
 $('photoFiles').onchange=action(async e=>{const files=[...e.target.files];e.target.value='';await uploadPhotos(files);});
 const drop=$('dropzone');for(const type of ['dragenter','dragover'])drop.addEventListener(type,e=>{e.preventDefault();drop.classList.add('drag');});
 drop.addEventListener('dragleave',()=>drop.classList.remove('drag'));
 drop.addEventListener('drop',action(async e=>{e.preventDefault();drop.classList.remove('drag');await uploadPhotos([...e.dataTransfer.files]);}));
 // Avoid browser navigation if a photo is dropped outside the target.
 document.addEventListener('dragover',e=>e.preventDefault());document.addEventListener('drop',e=>e.preventDefault());
 $('closeReportPreview').onclick=()=>$('reportPreviewDialog').close();
 $('reportPreviewDialog').addEventListener('close',()=>{updateSummary();});
 $('previewButton').onclick=action(beginPreview);$('retryPreview').onclick=action(async()=>{previewJob=null;await beginPreview();});
 $('generateButton').onclick=action(async()=>{
  await flush();if(editorHasContent()&&!(await confirmAction(t('生成已保存的检查项'),t('当前编辑区还有内容。报告只包含下方已保存检查项；若要包含当前项，请取消后点击 Save。'))))return;
  const result=await api('/api/generate',{id:project.id});const a=node('a');a.href='/api/download?id='+result.id+'&name='+encodeURIComponent(result.name);a.download=result.name;document.body.append(a);a.click();a.remove();toast(t('Word 报告已生成；打开后按提示更新目录。'));
 });
 $('backupButton').onclick=action(async()=>{await flush();const a=node('a');a.href='/api/backup?id='+project.id;a.download='inspection-draft.inspection.zip';document.body.append(a);a.click();a.remove();toast(t('草稿备份已导出，包含照片和文字。'));});
 $('restoreButton').onclick=()=>{if(!busy)$('restoreFile').click();};
 $('restoreFile').onchange=action(async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;await flush();const p=await api('/api/restore',file);loadProject(p);boot.projects=(await api('/api/bootstrap')).projects;renderProjects();localStorage.setItem('lastProject',p.id);toast(t('草稿已导入为独立副本'));});
 $('libraryButton').onclick=()=>{$('libraryStats').textContent=t("Observation {0} 条 · Recommendation {1} 条",boot.library.observation.length,boot.library.recommendation.length);$('libraryDialog').showModal();};
 $('closeLibrary').onclick=()=>$('libraryDialog').close();$('importLibraryButton').onclick=()=>$('libraryFile').click();
 $('libraryFile').onchange=action(async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;const result=await api('/api/library',file);boot.library=result.library;for(const key of ['observation','recommendation'])renderLibrary(key);$('libraryDialog').close();toast(t('文字库已更新。已保存检查项保持原样。'));});
 $('exitButton').onclick=action(async()=>{await flush();if(!(await confirmAction(t('退出工作台'),t('草稿已保存。退出后，下次双击程序可继续。'))))return;await api('/api/shutdown',{});document.body.replaceChildren(node('main',t('工作台已退出，草稿已保存。可以关闭此页面。')));});
 window.addEventListener('beforeunload',e=>{if(saver.unsaved||busy||personnelDirty||photoEditor?.operations.length){e.preventDefault();e.returnValue='';}});
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&saver.timer)saver.save().catch(()=>{});});
}
init().catch(e=>{status(t('无法打开工作台'),true);toast(e.message);});
