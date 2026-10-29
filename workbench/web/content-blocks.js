'use strict';
(function(root){
 const uid=()=>crypto.randomUUID().replaceAll('-','');
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const tr=(zh,en)=>root.WorkbenchI18n.language==='en'?en:zh;
 function render(host,blocks,config,tools,options={}){
  host.replaceChildren();
  const changed=()=>{options.onchange?.();config.schedule();};
  const button=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=config.action(fn);return b;};
  const field=(text,input)=>{const label=el('label',text,'cal-field');label.append(input);return label;};
  const edit=(value,fn,multiline=false,max=60000)=>{const n=el(multiline?'textarea':'input');n.value=value;n.maxLength=max;if(multiline)n.rows=5;n.oninput=()=>{fn(n.value);changed();};return n;};
  const refresh=()=>render(host,blocks,config,tools,options);
  const move=(index,delta)=>{const at=index+delta;if(at<0||at>=blocks.length)return;[blocks[index],blocks[at]]=[blocks[at],blocks[index]];refresh();changed();};
  async function upload(files){
   const failures=[];
   for(const file of files){try{const photo=await config.api('/api/photo',file,{'X-Filename':encodeURIComponent(file.name||'clipboard.png')});blocks.push({id:uid(),type:'image',photo,width:100});changed();await config.save();}catch(error){failures.push(error.message);}}
   refresh();if(failures.length)throw new Error(failures.join('\n'));
  }
  const file=options.fileInput||el('input');file.type='file';file.accept='.jpg,.jpeg,.png,.webp,.heic,.heif';file.multiple=true;file.hidden=true;
  file.onchange=config.action(async()=>{const files=[...file.files];file.value='';await upload(files);});
  if(!options.fileInput)host.append(file);
  (options.pasteTarget||host).onpaste=e=>{if(e.defaultPrevented)return;const files=[...e.clipboardData.items].filter(i=>i.type.startsWith('image/')).map(i=>i.getAsFile()).filter(Boolean);if(files.length){e.preventDefault();config.action(()=>upload(files))(e);}};
  if(tools){
   tools.querySelectorAll('[data-add-content]').forEach(n=>n.remove());
   for(const [kind,zh,en] of [['text','＋ 文字','+ Text'],['table','＋ 表格','+ Table'],['image','＋ 图片','+ Images']]){
    const b=button(tr(zh,en),async()=>{if(kind==='image'){file.click();return;}blocks.push(kind==='text'?{id:uid(),type:kind,text:''}:{id:uid(),type:kind,rows:[['','',''],['','','']]});refresh();changed();});b.dataset.addContent=kind;tools.append(b);
   }
  }
  blocks.forEach((block,index)=>{
   const box=el('section',undefined,'cal-block');box.dataset.blockId=block.id;
   const top=el('div',undefined,'cal-block-toolbar');top.append(el('strong',tr({text:'文字',table:'表格',image:'图片'}[block.type],{text:'Text',table:'Table',image:'Image'}[block.type])));
   const up=button('↑',async()=>move(index,-1)),down=button('↓',async()=>move(index,1));up.disabled=index===0;down.disabled=index===blocks.length-1;up.setAttribute('aria-label',tr('上移内容块','Move content block up'));down.setAttribute('aria-label',tr('下移内容块','Move content block down'));
   top.append(up,down,button(tr('删除','Delete'),async()=>{if(await config.confirm(tr('删除内容块','Delete content block'),tr('删除这个内容块？','Delete this content block?'))){blocks.splice(index,1);refresh();changed();}}));box.append(top);
   if(block.type==='text'){
    const text=edit(block.text,v=>block.text=v,true);text.setAttribute('aria-label',options.textLabel||tr('章节文字','Chapter text'));if(index===0&&options.textId)text.id=options.textId;box.append(text);
   }else if(block.type==='table'){
    const toolbar=el('div',undefined,'cal-block-toolbar');
    for(const [zh,en,axis,delta] of [['＋ 行','+ Row','row',1],['－ 行','− Row','row',-1],['＋ 列','+ Column','col',1],['－ 列','− Column','col',-1]])toolbar.append(button(tr(zh,en),async()=>{
     if(axis==='row'){if(delta>0&&block.rows.length<200)block.rows.push(Array(block.rows[0].length).fill(''));else if(delta<0&&block.rows.length>1)block.rows.pop();}
     else if(delta>0&&block.rows[0].length<20)block.rows.forEach(r=>r.push(''));else if(delta<0&&block.rows[0].length>1)block.rows.forEach(r=>r.pop());refresh();changed();
    }));box.append(toolbar);
    const scroll=el('div',undefined,'cal-table-scroll'),table=el('table',undefined,'cal-content-table');
    block.rows.forEach((row,ri)=>{const trnode=el('tr');row.forEach((value,ci)=>{const cell=el(ri?'td':'th'),input=edit(value,v=>block.rows[ri][ci]=v,true,2000);input.rows=2;input.setAttribute('aria-label',tr('单元格','Cell')+' '+(ri+1)+','+(ci+1));cell.append(input);trnode.append(cell);});table.append(trnode);});scroll.append(table);box.append(scroll);
    const details=el('details');details.append(el('summary',tr('从 Excel 粘贴表格','Paste a table from Excel')));const paste=el('textarea');paste.rows=3;paste.placeholder=tr('复制 Excel 单元格并粘贴到这里','Copy Excel cells and paste here');paste.setAttribute('aria-label',paste.placeholder);
    details.append(paste,button(tr('应用粘贴内容','Apply pasted table'),async()=>{block.rows=root.CalContent.parseTable(paste.value);refresh();changed();}));box.append(details);
   }else{
    const image=el('img');image.src='/photos/'+block.photo.id+'.jpg';image.alt=block.photo.caption||block.photo.name;image.style.width=block.width+'%';image.className='cal-content-image';box.append(image);
    box.append(field(tr('图注','Caption'),edit(block.photo.caption||'',v=>{block.photo.caption=v;image.alt=v||block.photo.name;},false,200)));
    const width=el('input');width.type='range';width.min=20;width.max=100;width.value=block.width;const output=el('output',block.width+'%');width.oninput=()=>{block.width=Number(width.value);image.style.width=block.width+'%';output.textContent=block.width+'%';changed();};const label=field(tr('图片宽度','Image width'),width);label.append(output);box.append(label);
    box.append(button(tr('旋转图片','Rotate image'),async()=>{block.photo={...block.photo,...await config.api('/api/rotate',{id:block.photo.id})};changed();await config.save();refresh();}));
   }
   host.append(box);
  });
 }
 root.ContentBlocks={render,uid};
})(window);
