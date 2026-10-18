import { useCallback, useEffect, useRef, useState } from 'react';
import { YardApiError, yardApi, yardETag } from './yard-api.ts';
import type { YardCommand, YardSnapshot } from './yard-api.ts';
import type { DemoPort } from './yard-demo.ts';
export function useYardBackend(port: DemoPort) {
  const [snapshot,setSnapshot]=useState<YardSnapshot|null>(null), [error,setError]=useState(''), [busy,setBusy]=useState(false), [connected,setConnected]=useState(false), [uncertain,setUncertain]=useState(false);
  const current=useRef<YardSnapshot|null>(null), alive=useRef(false), writing=useRef(false), fetching=useRef(false);
  const pending=useRef<{command:YardCommand;etag:string;key:string}|null>(null);
  const accept=useCallback((next:YardSnapshot)=>{
    if(!alive.current) return;
    if(current.current && next.workspaceId===current.current.workspaceId && next.revision<current.current.revision) return;
    current.current=next;setSnapshot(next);setConnected(true);
  },[]);
  const refresh=useCallback(async()=>{
    if(fetching.current||writing.current||pending.current) return;
    fetching.current=true;
    try { const next=await yardApi.snapshot(port,current.current?yardETag(current.current):undefined); if(next) accept(next); if(alive.current){setConnected(true);setError('');} }
    catch(error){if(alive.current){setConnected(false);setError(error instanceof Error?error.message:'Yard connection unavailable.');}}
    finally{fetching.current=false;}
  },[port,accept]);
  useEffect(()=>{
    alive.current=true;void refresh();
    const tick=window.setInterval(()=>{if(document.visibilityState==='visible')void refresh();},2000);
    const focus=()=>void refresh();window.addEventListener('focus',focus);
    return()=>{alive.current=false;clearInterval(tick);window.removeEventListener('focus',focus);};
  },[refresh]);
  const send=useCallback(async():Promise<boolean>=>{
    const intent=pending.current;if(!intent||writing.current)return false;
    writing.current=true;if(alive.current){setBusy(true);setError('');}
    try { const next=await yardApi.command(port,intent.command,intent.etag,intent.key);accept(next);pending.current=null;if(alive.current)setUncertain(false);return true; }
    catch(error){
      if(error instanceof YardApiError && error.status!==0 && error.status<500){
        pending.current=null;if(alive.current)setUncertain(false);
        try{const next=await yardApi.snapshot(port);if(next)accept(next);}catch{/* Preserve the last acknowledged snapshot. */}
      }else if(alive.current){setUncertain(true);setConnected(false);}
      if(alive.current)setError(error instanceof Error?error.message:'Save unavailable.');return false;
    }finally{writing.current=false;if(alive.current)setBusy(false);}
  },[port,accept]);
  const mutate=useCallback(async(command:YardCommand):Promise<boolean>=>{
    if(!current.current||writing.current||pending.current)return false;
    pending.current={command,etag:yardETag(current.current),key:crypto.randomUUID()};return send();
  },[send]);
  return {snapshot,error,busy,connected,uncertain,mutate,retry:send,refresh};
}
