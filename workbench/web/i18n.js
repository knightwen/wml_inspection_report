'use strict';
(function(root){
 const translations=root.WorkbenchEnglish;
 const requested=new URLSearchParams(location.search).get('lang');
 let saved='zh';try{saved=localStorage.getItem('workbenchLanguage')||'zh';}catch{}
 const englishOnly=root.WorkbenchInterface?.englishOnly===true;
 const language=englishOnly?'en':['en','zh'].includes(requested)?requested:saved==='en'?'en':'zh';
 const substitute=(text,values)=>text.replace(/\{(\d+)\}/g,(_,index)=>String(values[index]??''));
 const escape=text=>text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const patterns=Object.entries(translations).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>{
  const indices=[];let previous=0,pattern='';
  for(const match of key.matchAll(/\{(\d+)\}/g)){pattern+=escape(key.slice(previous,match.index))+'([\\s\\S]*?)';indices.push(Number(match[1]));previous=match.index+match[0].length;}
  return {regex:new RegExp('^'+pattern+escape(key.slice(previous))+'$'),value,indices};
 });
 function t(source,...values){
  if(typeof source!=='string')return source??'';
  if(language==='zh'){
   const chinese=root.WorkbenchChinese||{};
   if(Object.hasOwn(chinese,source))return substitute(chinese[source],values);
   if(/[\u4e00-\u9fff]/.test(source)&&source.includes(' / ')&&/[A-Za-z]/.test(source.split(' / ').at(-1)))return substitute(source.split(' / ')[0],values);
   return substitute(source,values);
  }
  if(Object.hasOwn(translations,source))return substitute(translations[source],values);
  // Server messages contain interpolated names or page numbers. Match only
  // complete known messages, without touching report content or field values.
  for(const entry of patterns){const match=source.match(entry.regex);if(match){const args=[];entry.indices.forEach((index,n)=>args[index]=match[n+1]);return substitute(entry.value,args);}}
  if(/[\u4e00-\u9fff]/.test(source)&&source.includes(' / ')&&/[A-Za-z]/.test(source.split(' / ').at(-1)))return substitute(source.split(' / ').at(-1),values);
  return substitute(source,values);
 }
 function apply(){
  document.documentElement.lang=language==='en'?'en-AU':'zh-CN';
  for(const el of document.querySelectorAll('[data-i18n]')){
   if(el.firstChild?.nodeType===3)el.firstChild.nodeValue=t(el.dataset.i18n);
  }
  for(const el of document.querySelectorAll('[data-i18n-tail]')){
   if(el.nextSibling?.nodeType===3)el.nextSibling.nodeValue=t(el.dataset.i18nTail);
  }
  for(const attr of ['placeholder','title','aria-label'])for(const el of document.querySelectorAll('[data-i18n-'+attr+']'))el.setAttribute(attr,t(el.getAttribute('data-i18n-'+attr)));
 }
 function remember(value){if(!['en','zh'].includes(value))return;try{localStorage.setItem('workbenchLanguage',value);}catch{}}
 if(!englishOnly)remember(language);
 root.WorkbenchI18n={language,englishOnly,t,apply,remember,ready:Promise.resolve()};
})(window);
