import type { DemoBlock, DemoContainer, DemoPort, DemoScenario } from './yard-demo.ts';
import type { WorkflowEvent, YardRun } from './yard-workflow.ts';
export type YardSnapshot = { workspaceId: string; runId: string; revision: number; scenario: DemoScenario; updatedAt: string; run: YardRun; blocks: DemoBlock[]; catalog: DemoContainer[]; database: 'sqlite'; persisted: true; synthetic: true; policyVersion: string; agentEnabled: false };
export type YardCommand = Omit<Extract<WorkflowEvent, {type:'review'}>, 'at'> | Omit<Extract<WorkflowEvent, {type:'start'}>, 'at'> | Omit<Extract<WorkflowEvent, {type:'complete_work'}>, 'at'> | Omit<Extract<WorkflowEvent, {type:'verify'}>, 'at'> | Omit<Extract<WorkflowEvent, {type:'gate_out'}>, 'at'> | { type: 'scenario'; scenario: DemoScenario } | {type:'reset'} | {type:'observe'; containerId:string; issue:'customs'|'weight'|'temperature'|'sensor'; note:string};
export class YardApiError extends Error { status: number; constructor(status: number, message: string) { super(message); this.status=status; } }
let session: Promise<{workspaceId:string}> | null = null;
let workspace = '';
async function request(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers); headers.set('X-Yard-Request', '1');
  if (init.body) headers.set('Content-Type','application/json');
  let response: Response;
  try { response = await fetch(`/api/yard${path}`, {...init,headers,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000)}); }
  catch { throw new YardApiError(0,init.method === 'POST' ? 'Connection interrupted. The save may have reached the server; retry the same request to confirm.' : 'Connection interrupted. Showing the last acknowledged yard data.'); }
  if (response.status === 304) return { data: null, etag: response.headers.get('ETag') || '' };
  const data = await response.json().catch(()=>null);
  if (!response.ok) throw new YardApiError(response.status, typeof data?.detail === 'string' ? data.detail : `Yard request failed (${response.status}).`);
  return {data,etag:response.headers.get('ETag')||''};
}
export async function ensureYardSession() {
  if (!session) session = request('/session',{method:'POST'}).then(({data})=>{ if (typeof data?.workspaceId !== 'string') throw new YardApiError(502,'The yard server returned an invalid workspace.'); workspace=data.workspaceId; return data; }).catch(error=>{session=null;throw error;});
  return session;
}
function check(data: YardSnapshot, port: DemoPort) {
  if (data?.workspaceId !== workspace) throw new YardApiError(-1,'Previous workspace response discarded.');
  if (data?.run?.port !== port || !Array.isArray(data.blocks) || !data.blocks.length || !Array.isArray(data.catalog) || !data.catalog.length || !Number.isSafeInteger(data.revision) || typeof data.runId !== 'string' || data.database !== 'sqlite') throw new YardApiError(502,'The yard server returned an invalid snapshot.');
  return data;
}
export const yardApi = {
  async snapshot(port: DemoPort, etag?: string): Promise<YardSnapshot | null> {
    await ensureYardSession();
    let response;
    try { response=await request(`/ports/${port}/snapshot`,{headers:etag?{'If-None-Match':etag}:{}}); }
    catch(error) { if (!(error instanceof YardApiError)||error.status!==401) throw error; session=null; await ensureYardSession(); response=await request(`/ports/${port}/snapshot`); }
    return response.data ? check(response.data,port):null;
  },
  async command(port: DemoPort, command: YardCommand, etag: string, key: string): Promise<YardSnapshot> {
    await ensureYardSession();
    const {data}=await request(`/ports/${port}/commands`,{method:'POST',headers:{'If-Match':etag,'Idempotency-Key':key},body:JSON.stringify(command)});
    return check(data,port);
  },
};
export const yardETag = (snapshot: YardSnapshot) => `"${snapshot.runId}:${snapshot.revision}"`;
