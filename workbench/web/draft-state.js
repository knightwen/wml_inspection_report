'use strict';
// Shared save state, used by the real page and deterministic regression tests.
(function(root){
 class DraftSaver {
  constructor({snapshot,send,onSaved=()=>{},onChange=()=>{},onConflict=()=>{},delay=650}){Object.assign(this,{snapshot,send,onSaved,onChange,onConflict,delay});this.queue=Promise.resolve();this.reset();}
  reset(revision=0){clearTimeout(this.timer);this.timer=null;this.revision=revision;this.changed=0;this.saved=0;this.pending=0;this.sending=false;this.error=null;this.conflict=null;this.onChange(this);}
  get unsaved(){return !!(this.timer||this.pending||this.changed>this.saved||this.error||this.conflict);}
  mark(){this.changed++;this.onChange(this);}
  schedule(){this.mark();clearTimeout(this.timer);this.timer=setTimeout(()=>{this.timer=null;this.save().catch(()=>{});},this.delay);}
  save(force=false){
   clearTimeout(this.timer);this.timer=null;if(force)this.mark();
   if(this.conflict)return Promise.reject(this.conflict);
   const snapshot=structuredClone(this.snapshot()),generation=this.changed;
   this.pending++;this.onChange(this);
   const task=this.queue.then(async()=>{
    if(this.conflict)throw this.conflict;
    this.sending=true;this.onChange(this);snapshot.revision=this.revision;
    try {
     const result=await this.send(snapshot);this.revision=result.revision;this.saved=Math.max(this.saved,generation);this.error=null;this.onSaved(result);return result;
    }catch(error){this.error=error;if(error.code==='revision_conflict'){this.conflict=error;this.onConflict(error);}throw error;}
    finally{this.sending=false;}
   }).finally(()=>{this.pending--;this.onChange(this);});
   this.queue=task.catch(()=>{});return task;
  }
  flush(){return this.save(true);}
 }
 function manualPerson(metadata,key,prefix){metadata[key+'_id']='';metadata[prefix+'_qualifications']='';metadata[prefix+'_title']='';}
 const api={DraftSaver,manualPerson};root.WorkbenchState=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
