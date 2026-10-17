import { ExternalLink, KeyRound, LoaderCircle, ShieldCheck, Unplug } from 'lucide-react';
import { useState } from 'react';
import { api, ApiError } from './api.ts';
import type { ModelStatus } from './types.ts';
import { dateTime } from './state.ts';
import { Badge, Modal } from './Components.tsx';

export default function Settings({ model, onClose, onUpdate, onError }: { model: ModelStatus; onClose: () => void; onUpdate: (model: ModelStatus) => void; onError: (error: unknown) => void }) {
  const [key, setKey] = useState(''), [modelId, setModelId] = useState(model.model || ''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const transportSafe = window.location.protocol === 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
  async function connect(event: React.FormEvent) {
    event.preventDefault(); if (!transportSafe || !key.trim() || !modelId.trim() || busy) return;
    const secret = key.trim(); setKey(''); setBusy(true); setError('');
    try { const status = await api.configure(secret, modelId.trim()); onUpdate(status); }
    catch (err) { if (err instanceof ApiError && err.status === -1) return; setError(err instanceof ApiError && err.status === 0 ? 'The save could not be confirmed. The backend may have received it. Close this dialog and refresh the workspace to check. No model call was made.' : err instanceof Error ? err.message : 'Could not configure Claude.'); onError(err); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true); setKey(''); setError('');
    try { onUpdate(await api.disconnect()); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not disconnect Claude.'); onError(err); }
    finally { setBusy(false); }
  }
  return <Modal title="Claude connection" subtitle="Your key, your session, your explicit requests." onClose={onClose}>
    <div className="settings-status"><div className="settings-icon"><KeyRound size={24} /></div><div><h3>{model.configured ? 'Key configured for this session' : 'Working with rules & templates'}</h3><p>{model.configured ? model.model : 'A Claude key is optional. The operations worklist and numerical planner already work.'}</p></div><Badge tone={model.configured ? 'teal' : ''}>{model.configured ? 'Configured' : 'No key'}</Badge></div>
    <div className="key-privacy"><ShieldCheck size={19} /><div><strong>The key stays out of your frontend bundle and Git.</strong><p>It is sent to this backend over the current connection, held only in backend memory for this temporary session, and used with Anthropic when you explicitly generate with Claude enabled. It is never written to browser storage or returned by the API. Traffic to Anthropic includes synthetic container facts and draft context.</p></div></div>
    {!transportSafe && <div className="inline-error" role="alert">Key entry is disabled on a remote HTTP connection. Open the HTTPS version of this site to connect Claude. Localhost development is allowed.</div>}
    <form onSubmit={connect} className="settings-form"><label htmlFor="claude-key">Claude API key<input id="claude-key" name="claude-api-key" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none" value={key} disabled={busy || !transportSafe} onChange={event => setKey(event.target.value)} placeholder="Paste your Anthropic API key" data-lpignore="true" /><small>Cleared from this form as soon as you submit. Use a dedicated key with a spending limit.</small></label><label htmlFor="claude-model">Exact model ID<input id="claude-model" value={modelId} disabled={busy} onChange={event => setModelId(event.target.value)} placeholder="Enter an exact model ID available in your account" spellCheck={false} autoCapitalize="none" autoComplete="off" /><small>Copy the model identifier from your Anthropic account or API documentation. Saving does not make a paid verification call.</small></label>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="settings-actions">{model.configured && <button type="button" className="button secondary" disabled={busy} onClick={disconnect}><Unplug size={15} />Disconnect & forget key</button>}<button type="submit" className="button primary" disabled={busy || !transportSafe || !key.trim() || !modelId.trim()}>{busy ? <LoaderCircle size={15} className="spin" /> : <KeyRound size={15} />}{model.configured ? 'Replace configuration' : 'Save for this session'}</button></div>
    </form>
    <div className="settings-explainer"><h4>How a call works</h4><ol><li>Set your port and scenario.</li><li>In Action assistant, enable “Use Claude” and click Generate.</li><li>The backend computes candidate fixes, then asks Claude for explanations and drafts.</li><li>You review and approve follow-up. Nothing is sent or released.</li></ol><p>{model.key_expires_at ? `This key expires ${dateTime(model.key_expires_at)}. ` : 'Keys expire after 15 minutes. '}Backend restarts and session expiry also clear the connection. Disconnect prevents future use; an already submitted request to Anthropic may still finish. All preview decisions and plans are temporary.</p><a href="https://console.anthropic.com/" target="_blank" rel="noreferrer">Manage keys and spending in Anthropic Console <ExternalLink size={12} /></a></div>
  </Modal>;
}
