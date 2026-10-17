import { ExternalLink, KeyRound, LoaderCircle, ShieldCheck, Unplug } from 'lucide-react';
import { useState } from 'react';
import { api, ApiError } from './api.ts';
import type { ModelStatus } from './types.ts';
import { dateTime } from './state.ts';
import { Badge, Modal } from './Components.tsx';

export default function Settings({ model, onClose, onUpdate, onError }: { model: ModelStatus; onClose: () => void; onUpdate: (model: ModelStatus) => void; onError: (error: unknown) => void }) {
  const [key, setKey] = useState(''), [accessCode, setAccessCode] = useState(''), [modelId, setModelId] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const transportSafe = window.location.protocol === 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
  const teamConnected = model.configured && model.source === 'render_environment';
  function reportError(err: unknown) {
    if (err instanceof ApiError && err.status === -1) return;
    setError(err instanceof ApiError && err.status === 0 ? 'The change could not be confirmed. Close this dialog and refresh the workspace to check. No model call was made.' : err instanceof Error ? err.message : 'Could not update the Claude connection.');
    onError(err);
  }
  async function connectTeam(event: React.FormEvent) {
    event.preventDefault(); if (!transportSafe || !accessCode.trim() || busy) return;
    const secret = accessCode.trim(); setAccessCode(''); setBusy(true); setError('');
    try { onUpdate(await api.connectTeam(secret)); }
    catch (err) { reportError(err); }
    finally { setBusy(false); }
  }
  async function connectPersonal(event: React.FormEvent) {
    event.preventDefault(); if (!transportSafe || !key.trim() || !modelId.trim() || busy) return;
    const secret = key.trim(); setKey(''); setBusy(true); setError('');
    try { onUpdate(await api.configure(secret, modelId.trim())); }
    catch (err) { reportError(err); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true); setKey(''); setAccessCode(''); setError('');
    try { onUpdate(await api.disconnect()); }
    catch (err) { reportError(err); }
    finally { setBusy(false); }
  }
  const heading = teamConnected ? 'Connected to team Claude' : model.configured ? 'Personal key connected' : model.server_available ? 'Team Claude is ready' : 'Working with rules & templates';
  return <Modal title="Claude connection" subtitle="A shared connection, protected for your team." onClose={onClose}>
    <div className="settings-status"><div className="settings-icon"><KeyRound size={24} /></div><div><h3>{heading}</h3><p>{model.configured ? model.model : model.server_available ? 'Enter your team access code. You do not need the Claude API key.' : 'The operations worklist and numerical planner work while the owner sets up Claude.'}</p></div><Badge tone={model.configured ? 'teal' : ''}>{model.configured ? 'Connected' : model.server_available ? 'Access required' : 'Rules mode'}</Badge></div>
    <div className="key-privacy"><ShieldCheck size={19} /><div><strong>The team API key stays on the server.</strong><p>The owner adds it to Render environment variables. Team members use a separate access code; the API key is never returned to the browser. Claude is called only when you explicitly generate with “Use Claude” enabled. Those calls include synthetic container facts and draft context.</p></div></div>
    {!transportSafe && <div className="inline-error" role="alert">Claude connection is disabled over remote HTTP. Open this site with HTTPS. Localhost development is allowed.</div>}
    {model.server_available && !teamConnected && <form onSubmit={connectTeam} className="settings-form team-connection"><label htmlFor="team-access-code">Team access code<input id="team-access-code" name="team-access-code" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none" value={accessCode} disabled={busy || !transportSafe} onChange={event => setAccessCode(event.target.value)} placeholder="Ask the workspace owner for the team code" data-lpignore="true" /><small>This is a separate code, not an Anthropic API key. Cleared on submit and never written to browser storage. Access lasts up to 15 minutes.</small></label><div className="settings-actions"><button type="submit" className="button primary" disabled={busy || !transportSafe || !accessCode.trim()}>{busy ? <LoaderCircle size={15} className="spin" /> : <KeyRound size={15} />}Use team Claude</button></div></form>}
    {error && <div className="inline-error connection-error" role="alert">{error}</div>}
    {model.configured && <div className="settings-actions connection-disconnect"><button type="button" className="button secondary" disabled={busy} onClick={disconnect}><Unplug size={15} />{teamConnected ? 'Disconnect team access' : 'Disconnect & forget personal key'}</button></div>}
    {!model.server_available && <details className="connection-details"><summary>Workspace owner: set up team Claude</summary><div><p>In the Render service’s Environment settings, add these variables and redeploy:</p><dl className="environment-names"><dt>ANTHROPIC_API_KEY</dt><dd>Your project’s Claude API key.</dd><dt>ANTHROPIC_MODEL</dt><dd>An exact model ID available to your Anthropic account.</dd><dt>CONSOLE_TEAM_ACCESS_CODE</dt><dd>A separate, strong secret shared only with your team.</dd></dl><p>Keep the API key in Render. Share only the team access code with approved teammates. Refresh this workspace after the deployment finishes.</p></div></details>}
    <details className="connection-details"><summary>Advanced: use a personal key for this session</summary><div><p>This optional connection replaces team access for this session. The key is held only in temporary backend memory and expires after 15 minutes, at session expiry, or on backend restart.</p><form onSubmit={connectPersonal} className="settings-form"><label htmlFor="claude-key">Personal Claude API key<input id="claude-key" name="claude-api-key" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none" value={key} disabled={busy || !transportSafe} onChange={event => setKey(event.target.value)} placeholder="Paste a personal Anthropic API key" data-lpignore="true" /><small>Cleared from this form on submit. Never saved to browser storage or returned by the API. Use a dedicated key with a spending limit.</small></label><label htmlFor="claude-model">Exact model ID<input id="claude-model" value={modelId} disabled={busy} onChange={event => setModelId(event.target.value)} placeholder="A model ID available in your Anthropic account" spellCheck={false} autoCapitalize="none" autoComplete="off" /><small>Saving does not make a paid verification call. Team model settings are managed in Render.</small></label><div className="settings-actions"><button type="submit" className="button secondary" disabled={busy || !transportSafe || !key.trim() || !modelId.trim()}>{busy ? <LoaderCircle size={15} className="spin" /> : <KeyRound size={15} />}Use personal key temporarily</button></div></form></div></details>
    <div className="settings-explainer"><h4>How a call works</h4><ol><li>Connect team Claude, then set your port and scenario.</li><li>In Action assistant, enable “Use Claude” and click Generate.</li><li>The backend computes candidate fixes, then asks Claude for explanations and drafts.</li><li>You review and approve follow-up. Nothing is sent or released.</li></ol><p>{model.key_expires_at ? `This session’s Claude access expires ${dateTime(model.key_expires_at)}. ` : 'Claude access lasts up to 15 minutes per connection. '}Disconnecting revokes this session’s future access; it does not remove the team API key from Render. An already submitted request to Anthropic may still finish. Backend restarts clear sessions, personal keys, and preview plans.</p><a href="https://console.anthropic.com/" target="_blank" rel="noreferrer">Manage keys and spending in Anthropic Console <ExternalLink size={12} /></a></div>
  </Modal>;
}
