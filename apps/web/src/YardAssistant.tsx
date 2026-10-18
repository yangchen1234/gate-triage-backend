import { Check, ChevronDown, Copy, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, Sparkles, Unplug } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from './api.ts';
import type { ModelStatus } from './types.ts';
import { useYardLocale } from './YardLocale.tsx';
import { ISSUE, issuePresentation } from './yard-demo.ts';
import type { Issue } from './yard-demo.ts';
import { YardApiError, yardETag } from './yard-api.ts';
import type { YardSnapshot } from './yard-api.ts';
import { advisoryIsStale, assistantConnectionState, assistantModel, yardAssistantApi } from './yard-assistant-api.ts';
import type { AdvisoryRequest, YardAdvisory } from './yard-assistant-api.ts';
import './yard-assistant.css';
const agentErrorCopy = (message:string) => message.replace(/\bClaude\b/g,'agent provider').replace(/^agent provider/,'The agent provider');

export default function YardAssistant({snapshot,containerId,issue,disabled}:{snapshot:YardSnapshot;containerId:string;issue:Exclude<Issue,'clear'>;disabled:boolean}) {
 const {t,formatTime}=useYardLocale();
 const [model,setModel]=useState<ModelStatus|null>(null),[connectionOpen,setConnectionOpen]=useState(false),[connectionBusy,setConnectionBusy]=useState(false);
 const [code,setCode]=useState(''),[personalKey,setPersonalKey]=useState(''),[modelId,setModelId]=useState('');
 const [job,setJob]=useState<YardAdvisory|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[uncertain,setUncertain]=useState(false),[copied,setCopied]=useState(false);
 const [tab,setTab]=useState<'guidance'|'email'|'evidence'>('email'),[subject,setSubject]=useState(''),[body,setBody]=useState('');
 const [now,setNow]=useState(Date.now),[checking,setChecking]=useState(false);
 const mounted=useRef(true),lock=useRef(false),started=useRef(false),intent=useRef<{body:AdvisoryRequest;etag:string;key:string}|null>(null);
 const port=snapshot.run.port;
 const container=snapshot.catalog.find(c=>c.id===containerId);
 const issueLabel=container?issuePresentation(container,issue).short:ISSUE[issue].short;
 const transportSafe=window.location.protocol==='https:'||['127.0.0.1','localhost','[::1]'].includes(window.location.hostname);
 const stale=!!job&&advisoryIsStale(job,snapshot.runId,snapshot.revision);
 const running=busy||job?.status==='running';
 const connection=assistantConnectionState(model,now);
 useEffect(()=>{
  mounted.current=true;
  void assistantModel().then(m=>{if(mounted.current)setModel(m);}).catch(()=>{if(mounted.current)setError(t('Could not load the agent connection.'));});
  void yardAssistantApi.latest(port,containerId,issue).then(j=>{if(mounted.current&&!started.current)setJob(j);}).catch(()=>{if(mounted.current)setError(t('Could not load saved drafts.'));});
  return()=>{mounted.current=false;};
 },[port,containerId,issue,t]);
 useEffect(()=>{
  let active=true,checking=false;
  const check=async()=>{
   if(checking||document.visibilityState!=='visible')return;checking=true;
   try{const status=await assistantModel();if(active)setModel(status);}
   catch{if(active)setModel(null);}
   finally{checking=false;}
  };
  const timer=window.setInterval(()=>void check(),60000),clock=window.setInterval(()=>setNow(Date.now()),1000);window.addEventListener('focus',check);
  return()=>{active=false;clearInterval(timer);clearInterval(clock);window.removeEventListener('focus',check);};
 },[]);
 useEffect(()=>{
  if(job?.status!=='running')return;
  let active=true,polling=false;
  const poll=async()=>{
   if(polling||document.visibilityState!=='visible')return;polling=true;
   try{const next=await yardAssistantApi.job(port,job.id);if(active){setJob(next);setError('');}}
   catch{if(active)setError(t('Draft status is unavailable. Reconnect to check; generation is not repeated.'));}
   finally{polling=false;}
  };
  const timer=window.setInterval(()=>void poll(),1500);window.addEventListener('focus',poll);
  return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',poll);};
 },[job?.id,job?.status,port,t]);
 useEffect(()=>{if(job?.result){setSubject(job.result.subject);setBody(job.result.body);setCopied(false);}},[job?.id,job?.status]);
 async function refreshConnection(){
  setConnectionBusy(true);setError('');
  try{setModel(await assistantModel());}catch{setError(t('Could not load the agent connection.'));}
  finally{setConnectionBusy(false);}
 }
 async function connect(personal:boolean){
  if(connectionBusy||!transportSafe)return;
  const secret=(personal?personalKey:code).trim();setPersonalKey('');setCode('');setConnectionBusy(true);setError('');
  try{await assistantModel();setModel(personal?await api.configure(secret,modelId.trim()):await api.connectTeam(secret));setNow(Date.now());setConnectionOpen(false);}
  catch(e){setError(e instanceof Error?e.message:t('Agent connection failed.'));}
  finally{setConnectionBusy(false);}
 }
 async function disconnect(){
  setConnectionBusy(true);
  try{setModel(await api.disconnect());setCode('');setPersonalKey('');}catch(e){setError(e instanceof Error?e.message:t('Agent connection failed.'));}
  finally{setConnectionBusy(false);}
 }
 async function generate(retry=false){
  if(lock.current||disabled||job?.status==='running')return;
  // Preflight is read-only: an expired connection opens authentication instead of
  // leaving a dead button or submitting an unauthorized paid request.
  if(!retry){
   lock.current=true;setChecking(true);setError('');
   try{
    const current=await assistantModel();if(!mounted.current)return;
    setModel(current);setNow(Date.now());
    if(assistantConnectionState(current)!=='ready'){setConnectionOpen(true);return;}
   }catch{if(mounted.current){setError(t('Could not load the agent connection.'));setConnectionOpen(true);}return;}
   finally{lock.current=false;if(mounted.current)setChecking(false);}
  }
  if(!retry)intent.current={body:{containerId,issue,question:''},etag:yardETag(snapshot),key:crypto.randomUUID()};
  const request=intent.current;if(!request)return;
  lock.current=true;started.current=true;setBusy(true);setError('');
  try{
   const next=await yardAssistantApi.generate(port,request.body,request.etag,request.key);
   if(mounted.current){setJob(next);setUncertain(false);setTab('email');}intent.current=null;
  }catch(e){
   if(!mounted.current)return;
   if(e instanceof YardApiError && e.status!==0 && e.status<500){intent.current=null;setUncertain(false);}
   else{
    setUncertain(true);
    // Recover a committed job after a lost POST response, without a second model call.
    try{const latest=await yardAssistantApi.latest(port,containerId,issue);if(latest?.requestId===request.key){setJob(latest);setUncertain(false);intent.current=null;return;}}catch{/* Retry uses the original key and body. */}
   }
   setError(e instanceof Error?e.message:t('Draft request failed.'));
   if(e instanceof YardApiError&&(e.status===401||e.status===409))void assistantModel().then(m=>{if(mounted.current)setModel(m);}).catch(()=>{});
  }finally{lock.current=false;if(mounted.current)setBusy(false);}
 }
 async function copyDraft(){
  try{await navigator.clipboard.writeText(`${t('To role')}: ${job?.result?.recipientRole}\n${t('Cc roles')}: ${(job?.result?.ccRoles||job?.context.ccRoles||[]).join('; ')}\n${t('Subject')}: ${subject}\n\n${body}`);setCopied(true);}
  catch{setError(t('Select and copy the draft text manually.'));}
 }
 return <section className="yd-assistant" aria-label={t('Agent suggestions panel')}>
  <div className="yd-assistant-heading"><div><Sparkles size={17}/><h3>{t('Agent suggestions')}</h3></div><span>{t('DRAFT ONLY')}</span></div>
  <p className="yd-assistant-intro">{t('Draft a notification email for the responsible team, with the problem, impact and requested actions.')}</p>
  <button className="yd-assistant-connection" aria-expanded={connectionOpen} onClick={()=>setConnectionOpen(v=>!v)}><KeyRound size={13}/><span>{t(connection==='ready'?'Agent connected':connection==='expired'?'Agent access expired':connection==='checking'?'Checking agent connection…':model?.server_available?'Team access required':'Connect agent')}</span><ChevronDown size={13}/></button>
  {connection==='ready'&&model?.key_expires_at&&<small className="yd-assistant-hint">{t('Access until')} {formatTime(model.key_expires_at)}</small>}
  {connectionOpen&&<div className="yd-assistant-auth">
   <div><strong>{t('Agent connection')}</strong><button className="yd-text-button" disabled={connectionBusy} onClick={()=>void refreshConnection()} aria-label={t('Refresh agent connection')}><RefreshCw size={13}/></button></div>
   {connection==='ready'?<><p>{t(model?.source==='render_environment'?'Team key stays on the server.':'Personal key is held in temporary server memory.')}</p><button className="yd-secondary" disabled={connectionBusy||running} onClick={()=>void disconnect()}><Unplug size={13}/>{t('Disconnect agent')}</button></>:<>
    {model?.server_available?<form onSubmit={e=>{e.preventDefault();void connect(false);}}><label htmlFor="yd-team-code">{t('Team access code')}</label><input id="yd-team-code" type="password" value={code} maxLength={256} autoComplete="new-password" onChange={e=>setCode(e.target.value)} disabled={connectionBusy||!transportSafe}/><button className="yd-primary" disabled={connectionBusy||!code.trim()||!transportSafe}>{t('Connect team agent')}</button></form>:<p>{t('Team access needs API credentials and a separate access code configured on the server.')}</p>}
    <details><summary>{t('Use a temporary personal key')}</summary><form onSubmit={e=>{e.preventDefault();void connect(true);}}><label htmlFor="yd-personal-key">{t('Provider API key')}</label><input id="yd-personal-key" type="password" value={personalKey} maxLength={2048} autoComplete="new-password" onChange={e=>setPersonalKey(e.target.value)} disabled={connectionBusy||!transportSafe}/><label htmlFor="yd-model-id">{t('Exact model ID')}</label><input id="yd-model-id" value={modelId} placeholder="claude-sonnet-4-6" maxLength={87} autoComplete="off" onChange={e=>setModelId(e.target.value)} disabled={connectionBusy||!transportSafe}/><button className="yd-primary" disabled={connectionBusy||!personalKey.trim()||!modelId.trim()||!transportSafe}>{t('Connect temporarily')}</button></form></details>
    <small>{t('Credentials are cleared on submit and never saved in browser storage. Access lasts up to 15 minutes.')}</small>
   </>}
   {!transportSafe&&<p role="alert">{t('Use HTTPS or localhost to connect the agent.')}</p>}
  </div>}

  <div className="yd-assistant-context"><span>{containerId}</span><span>{t(issueLabel)}</span></div>
  <button className="yd-primary yd-assistant-generate" disabled={disabled||running||uncertain||checking||connectionBusy} onClick={()=>void generate()}>{running||checking?<LoaderCircle size={14} className="spin"/>:<Sparkles size={14}/>} {t(running?'Generating…':checking?'Checking connection…':'Generate')}</button>
  {connection!=='ready'&&<small className="yd-assistant-hint" role="status">{t(connection==='expired'?'Agent access expired after 15 minutes. Click Generate to reconnect.':connection==='team_required'?'Server credentials are configured. Click Generate to connect with the team access code.':connection==='checking'?'Click Generate to check the connection.':'Connect the agent to draft an email. Click Generate to open connection settings.')}</small>}
  {disabled&&<small className="yd-assistant-hint" role="status">{t('Wait for the current yard update to finish.')}</small>}
  {uncertain&&<small className="yd-assistant-hint" role="status">{t('Request status is uncertain. Check the same request before generating another draft.')}</small>}
  {error&&<div className="yd-assistant-error" role="alert">{t(agentErrorCopy(error))}</div>}
  {uncertain&&<button className="yd-secondary" disabled={busy||disabled} onClick={()=>void generate(true)}>{t('Check the same request')}</button>}
  {job?.status==='failed'&&<div className="yd-assistant-error" role="alert">{t(agentErrorCopy(job.error||'Draft request failed.'))}</div>}
  {job?.result&&<div className="yd-assistant-result">
   <div className="yd-assistant-result-meta"><span>{t('Agent-generated')}</span><time>{formatTime(job.result.generatedAt)}</time></div>
   {stale&&<div className="yd-assistant-stale" role="status">{t('Yard data changed. This draft is out of date; generate again before using it.')}</div>}
   <div className="yd-assistant-tabs" role="tablist" aria-label={t('Assistant output')}>{(['email','guidance','evidence'] as const).map(key=><button key={key} role="tab" id={`yd-assistant-tab-${key}`} aria-selected={tab===key} aria-controls="yd-assistant-output" onClick={()=>setTab(key)}>{t(key==='guidance'?'Suggestions':key==='email'?'Notification email':'Source facts')}</button>)}</div>
   <div id="yd-assistant-output" role="tabpanel" aria-labelledby={`yd-assistant-tab-${tab}`}>
    {tab==='guidance'?<><p>{job.result.summary}</p><div className={`yd-assistant-escalation ${job.context.escalation==='supervisor_now'?'urgent':''}`}><ShieldCheck size={14}/><span>{t(job.context.escalation==='supervisor_now'?'Escalate to supervisor now':'Coordinate with responsible team')}</span></div><ol>{job.result.recommendations.map((r,i)=><li key={i}><strong>{r.action}</strong><p>{r.rationale}</p><small>{r.evidenceIds.join(' · ')}</small></li>)}</ol>{job.result.missingInformation.length>0&&<div className="yd-assistant-missing"><h4>{t('Still needs verification')}</h4><ul>{job.result.missingInformation.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}</>:tab==='email'?<><div className="yd-assistant-routing"><p>{t('To role')}: <strong>{job.result.recipientRole}</strong></p>{(job.result.ccRoles||job.context.ccRoles||[]).length>0&&<p>{t('Cc roles')}: <strong>{(job.result.ccRoles||job.context.ccRoles||[]).join(' · ')}</strong></p>}<small>{t('Recipient roles are suggested. Confirm the actual email addresses before sending.')}</small></div><label htmlFor="yd-email-subject">{t('Subject')}</label><input id="yd-email-subject" value={subject} maxLength={180} onChange={e=>{setSubject(e.target.value);setCopied(false);}}/><label htmlFor="yd-email-body">{t('Email draft')}</label><textarea id="yd-email-body" rows={10} value={body} maxLength={4000} onChange={e=>{setBody(e.target.value);setCopied(false);}}/><button className="yd-secondary" disabled={stale||!subject.trim()||!body.trim()} onClick={()=>void copyDraft()}>{copied?<Check size={13}/>:<Copy size={13}/>} {t(copied?'Copied':'Copy draft')}</button></>:<dl className="yd-assistant-facts">{job.context.facts.map(f=><div key={f.id}><dt>{f.id} · {f.label}</dt><dd>{typeof f.value==='string'?f.value:JSON.stringify(f.value,null,2)}</dd></div>)}</dl>}
   </div>
  </div>}
  <p className="yd-assistant-footnote"><ShieldCheck size={12}/>{t('Advisory only. No email is sent and no container status is changed.')}</p>
 </section>;
}
