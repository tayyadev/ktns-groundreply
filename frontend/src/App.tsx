import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api, setCsrf } from './api';
import type { Citation, DocumentItem, EvalCase, EvalRun, Me, Overview, Page, Ticket } from './types';

const menu: {key: Page; label: string; glyph: string}[] = [
  {key: 'overview', label: 'Overview', glyph: '◫'},
  {key: 'inbox', label: 'Ticket inbox', glyph: '▤'},
  {key: 'knowledge', label: 'Knowledge base', glyph: '▣'},
  {key: 'evaluations', label: 'AI evaluations', glyph: '◇'},
  {key: 'team', label: 'Team', glyph: '♧'},
  {key: 'billing', label: 'Plans & usage', glyph: '◈'},
  {key: 'audit', label: 'Audit trail', glyph: '≡'},
];

function shortDate(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'});
}
function badgeStyle(status: string) {
  if (['approved', 'ready', 'completed', 'succeeded'].includes(status)) return 'pill success';
  if (['needs_review', 'failed', 'dead', 'rejected'].includes(status)) return 'pill danger';
  if (['awaiting_approval'].includes(status)) return 'pill attention';
  return 'pill neutral';
}
function Badge({status}: {status: string}) {
  return <span className={badgeStyle(status)}>{status.replaceAll('_', ' ')}</span>;
}
function Panel({title, hint, actions, children}: {title: string; hint?: string; actions?: ReactNode; children: ReactNode}) {
  return <section className="panel"><div className="panel-head"><div><h3>{title}</h3>{hint && <p className="muted subline">{hint}</p>}</div>{actions}</div>{children}</section>;
}
function Empty({icon, title, desc}: {icon: string; title: string; desc: string}) {
  return <div className="empty"><div className="empty-icon">{icon}</div><b>{title}</b><p>{desc}</p></div>;
}
function Field({label, children}: {label: string; children: ReactNode}) {
  return <label className="field"><span>{label}</span>{children}</label>;
}
function Heading({eyebrow, title, description, action}: {eyebrow: string; title: string; description: string; action?: ReactNode}) {
  return <div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lead">{description}</p></div>{action}</div>;
}
function useData<T>(path: string, refreshMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    try { setData(await api<T>(path)); setError(''); } catch(e) { setError((e as Error).message); }
  }, [path]);
  useEffect(() => {
    void reload();
    if (!refreshMs) return;
    const interval = window.setInterval(() => void reload(), refreshMs);
    return () => clearInterval(interval);
  }, [reload, refreshMs]);
  return {data, reload, error};
}

function Auth({onSuccess}: {onSuccess: () => void}) {
  const inviteToken = new URLSearchParams(window.location.search).get('invite');
  const [mode, setMode] = useState<'login'|'register'|'invite'>(inviteToken ? 'invite' : 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [org, setOrg] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (mode === 'invite') {
        await api('/auth/accept-invite', 'POST', {token: inviteToken, password});
        window.history.replaceState({}, '', '/');
      } else if (mode === 'register') {
        await api('/auth/register', 'POST', {email, password, organization_name: org});
      } else { await api('/auth/login', 'POST', {email, password}); }
      onSuccess();
    } catch(e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="auth-screen"><div className="auth-brand"><div className="large-logo">✦</div><span>KTNS <b>GroundReply</b></span></div>
    <div className="auth-layout"><div className="auth-story">
      <div className="hero-label">AI support operations • Human approved</div>
      <h1>Support that knows<br/>your business.</h1>
      <p>Turn your team's knowledge into cited, reviewable customer responses. AI handles the first draft. Your team remains in control.</p>
      <div className="hero-step"><b>01</b><span>Connect your knowledge</span></div>
      <div className="hero-step"><b>02</b><span>Specialist agents research and draft</span></div>
      <div className="hero-step"><b>03</b><span>Review, approve, and reply</span></div>
      <div className="hero-note">Private workspaces · Grounded citations · Audit trails</div>
    </div>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-icon">✳</div>
        <h2>{mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create your workspace' : 'Join your workspace'}</h2>
        <p className="muted">{mode === 'login' ? 'Sign in to your AI support console.' : mode === 'invite' ? 'You have a private team invitation.' : 'Start with 25 included draft tickets per month.'}</p>
        {mode !== 'invite' && <Field label="Work email"><input type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com"/></Field>}
        {mode === 'register' && <Field label="Workspace name"><input required minLength={2} value={org} onChange={e => setOrg(e.target.value)} placeholder="Your company"/></Field>}
        <Field label="Password"><input type="password" required minLength={mode === 'login' ? 1 : 12} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === 'login' ? 'Your password' : 'At least 12 characters'}/></Field>
        {error && <div className="error-box">{error}</div>}
        <button className="primary full" disabled={busy}>{busy ? 'Working…' : mode === 'login' ? 'Sign in →' : mode === 'register' ? 'Create workspace →' : 'Accept invitation →'}</button>
        {!inviteToken && <p className="auth-switch">{mode === 'login' ? 'New to GroundReply?' : 'Already have an account?'} <button type="button" className="link-btn" onClick={() => {setMode(mode === 'login' ? 'register' : 'login'); setError('');}}>{mode === 'login' ? 'Create a workspace' : 'Sign in'}</button></p>}
      </form>
    </div><p className="auth-footer">© KTNSINNOVATIONS LLC · Built for teams that value accuracy</p>
  </div>;
}

function OverviewPage({go}: {go: (page: Page) => void}) {
  const {data, error} = useData<Overview>('/overview', 8000);
  const {data: tickets} = useData<Ticket[]>('/tickets', 8000);
  const metrics = [
    {label:'Tickets this month', value: data?.this_month ?? '—', icon: '↗', note:'AI draft requests'},
    {label:'Awaiting review', value: data?.needs_action ?? '—', icon: '⌁', note:'Require your decision'},
    {label:'Approved replies', value: data?.approved ?? '—', icon: '✓', note:'Human approved'},
    {label:'Knowledge sources', value: data?.ready_documents ?? '—', icon: '▣', note:'Indexed and searchable'},
  ];
  return <><Heading eyebrow="WORKSPACE HOME" title="Command center" description="A clear view of your support workflow, from knowledge to approved answers." action={<button className="primary" onClick={() => go('inbox')}>+ New support ticket</button>}/>
    {error && <p className="error-box">{error}</p>}
    <div className="metric-grid">{metrics.map(m => <div key={m.label} className="metric"><div className="metric-top"><span>{m.label}</span><span className="metric-symbol">{m.icon}</span></div><strong>{m.value}</strong><small>{m.note}</small></div>)}</div>
    <div className="overview-grid"><Panel title="Recent support tickets" hint="Always reviewed by a human before being sent" actions={<button className="text-action" onClick={() => go('inbox')}>View inbox →</button>}>
      {tickets?.length ? <div className="item-list">{tickets.slice(0,6).map(t => <div className="list-row" key={t.id}><span className="list-avatar">✉</span><div className="list-main"><b>{t.subject}</b><small>{shortDate(t.created_at)}</small></div><Badge status={t.status}/></div>)}</div> : <Empty icon="▤" title="Your inbox is clear" desc="Create a ticket to see the agent pipeline in action."/>}
      </Panel><Panel title="Workspace activity" hint="Current monthly usage and safeguards">
        <div className="usage-bar-title"><b>AI draft allowance</b><span>{data?.this_month ?? 0} / {data?.monthly_limit ?? 25}</span></div>
        <div className="progress"><div style={{width:`${Math.min(100, 100 * (data?.this_month ?? 0) / (data?.monthly_limit || 25))}%`}}/></div>
        <p className="muted details-line">Resets each calendar month (UTC).</p>
        <div className="statline"><span>Model input tokens</span><strong>{(data?.input_tokens ?? 0).toLocaleString()}</strong></div>
        <div className="statline"><span>Model output tokens</span><strong>{(data?.output_tokens ?? 0).toLocaleString()}</strong></div>
        <div className="callout"><span>✦</span><div><b>Human-in-the-loop</b><p>No reply is automatically sent to customers. Approved responses can be copied to your support channel.</p></div></div>
      </Panel></div>
    <div className="bottom-note"><span>◉</span> AI answers cite workspace knowledge. Low-confidence, unsupported, and sensitive requests are escalated for review.</div>
  </>;
}

function TicketsPage({role}: {role: string}) {
  const canEdit = role !== 'viewer';
  const {data: tickets, reload, error: loadError} = useData<Ticket[]>('/tickets', 3500);
  const [selected, setSelected] = useState<string | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [showComposer, setShowComposer] = useState(false);
  const [subject, setSubject] = useState('');
  const [question, setQuestion] = useState('');
  const [email, setEmail] = useState('');
  const [draftText, setDraftText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!selected && tickets?.length) setSelected(tickets[0].id);
  }, [tickets, selected]);
  useEffect(() => {
    if (!selected) return;
    let mounted = true;
    const refresh = async () => {
      try { const result = await api<Ticket>(`/tickets/${selected}`); if(mounted) setTicket(result); } catch { if(mounted) setTicket(null); }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3500);
    return () => { mounted = false; window.clearInterval(interval); };
  }, [selected]);
  useEffect(() => { setDraftText(ticket?.draft ?? ''); }, [ticket?.id, ticket?.draft]);
  async function createTicket(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const record = await api<Ticket>('/tickets', 'POST', {subject, question, requester_email: email || null});
      setShowComposer(false); setSubject(''); setQuestion(''); setEmail(''); setSelected(record.id); setTicket(record); await reload();
    } catch(err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  async function decide(decision: 'approve' | 'reject') {
    if (!ticket) return;
    setBusy(true); setError('');
    try {
      const saved = await api<Ticket>(`/tickets/${ticket.id}/decision`, 'POST', {decision, edited_draft: draftText || null});
      setTicket(saved); await reload();
    } catch(err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <><Heading eyebrow="SUPPORT OPERATIONS" title="Ticket inbox" description="Draft replies with specialized AI agents, grounded evidence, and approval controls." action={canEdit && <button className="primary" onClick={() => {setShowComposer(!showComposer); setError('');}}>+ Create ticket</button>}/>
    {showComposer && <Panel title="New support ticket" hint="This starts a four-stage agent workflow in the background"><form className="composer" onSubmit={createTicket}>
      <div className="two-col"><Field label="Ticket subject"><input required minLength={3} maxLength={220} value={subject} onChange={e => setSubject(e.target.value)} placeholder="Question about a refund policy"/></Field>
      <Field label="Customer email (optional)"><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="customer@example.com"/></Field></div>
      <Field label="Customer message"><textarea required minLength={5} maxLength={6000} rows={4} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Paste the customer's question here…"/></Field>
      <div className="actions"><button type="button" className="secondary" onClick={() => setShowComposer(false)}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Creating…' : 'Run AI agents →'}</button></div>
      </form></Panel>}
    {loadError && <div className="error-box">{loadError}</div>}{error && <div className="error-box">{error}</div>}
    <div className="inbox-grid"><Panel title={`All tickets ${tickets ? `(${tickets.length})` : ''}`} hint="Select a ticket to inspect its AI reasoning trace">
      {tickets?.length ? <div className="ticket-list">{tickets.map(t => <button key={t.id} className={`ticket-row ${selected === t.id ? 'active' : ''}`} onClick={() => setSelected(t.id)}><div className="ticket-row-first"><b>{t.subject}</b><small>{shortDate(t.created_at)}</small></div><p>{t.requester_email || 'Internal inquiry'}</p><Badge status={t.status}/></button>)}</div> : <Empty icon="✉" title="No support tickets" desc="Click Create ticket to get started."/>}
    </Panel>
    <div className="ticket-detail">{ticket ? <>
      <Panel title={ticket.subject} hint={`${ticket.requester_email || 'Internal inquiry'}  ·  ${shortDate(ticket.created_at)}`} actions={<Badge status={ticket.status}/>}>
        <div className="question-box"><div className="question-label">ORIGINAL QUESTION</div>{ticket.question}</div>
        <div className="pipeline"><span className="step-complete">1. Triage</span><span>→</span><span className={ticket.category ? 'step-complete' : ''}>2. Research</span><span>→</span><span className={ticket.draft ? 'step-complete' : ''}>3. Draft</span><span>→</span><span className={ticket.trace?.some(s => s.step === 'review') ? 'step-complete' : ''}>4. Review</span></div>
        {ticket.category && <p className="metadata">Category: <b>{ticket.category}</b><span className="dot">•</span> Priority: <b>{ticket.priority}</b></p>}
        {(ticket.status === 'queued' || ticket.status === 'processing') && <div className="processing"><span className="spinner"/> Specialist agents are processing this ticket…</div>}
        {ticket.error && <div className="error-box">{ticket.error}</div>}
        {ticket.status === 'failed' && canEdit && <div className="pad"><button className="secondary" onClick={() => void api(`/tickets/${ticket.id}/retry`, 'POST').then(saved => setTicket(saved as Ticket)).catch(e => setError(e.message))}>Retry AI processing ↻</button></div>}
        {ticket.draft && <><div className="draft-top"><h4>AI suggested response</h4><span>Editable before approval</span></div>
          <textarea className="draft-editor" value={draftText} readOnly={!canEdit || !['awaiting_approval', 'needs_review'].includes(ticket.status)} onChange={e => setDraftText(e.target.value)} rows={9}/>
          {ticket.review_flags && ticket.review_flags.length > 0 && <div className="risk-callout"><b>⚑ Review notes</b>{ticket.review_flags.map((f, i) => <p key={i}>• {f}</p>)}</div>}
          <div className="actions spread">{canEdit && ['awaiting_approval', 'needs_review'].includes(ticket.status) ? <><button className="secondary" disabled={busy} onClick={() => void decide('reject')}>Reject draft</button><button className="primary" disabled={busy || !draftText.trim()} onClick={() => void decide('approve')}>{busy ? 'Saving…' : '✓ Approve reply'}</button></> : <><span className="muted small">{ticket.status === 'approved' ? 'Approved for manual delivery' : 'A review decision is not available'}</span>{draftText && ticket.status === 'approved' && <button className="secondary" onClick={() => void navigator.clipboard.writeText(draftText)}>Copy approved reply ↗</button>}</>}</div>
        </>}
      </Panel>
      <Panel title={`Grounding evidence (${ticket.citations?.length || 0})`} hint="Citations are matched against retrieved passages, not fabricated by the model">
        {ticket.citations?.length ? <div className="citation-stack">{ticket.citations.map((c: Citation) => <div className="citation" key={c.ref}><div className="citation-top"><b>{c.ref} · {c.title}</b><small>Similarity {(c.similarity * 100).toFixed(0)}%</small></div><p>{c.excerpt}</p></div>)}</div> : <p className="muted pad">No verified knowledge excerpts yet. Add relevant documents if retrieval abstains.</p>}
      </Panel>
      <Panel title="Agent trace" hint="Operational stages only; private prompts are not exposed"><div className="trace">{ticket.trace?.length ? ticket.trace.map((entry, i) => <div key={i} className="trace-item"><span>{i+1}</span><b>{entry.step.replaceAll('_',' ')}</b><small>{Object.entries(entry).filter(([key]) => key !== 'step').map(([k,v]) => `${k}: ${String(v)}`).join(' · ')}</small></div>) : <p className="muted">The trace will appear after processing.</p>}</div></Panel>
    </> : <Panel title="Ticket details"><Empty icon="▤" title="Select a ticket" desc="Choose one from the list to inspect its response, evidence, and review status."/></Panel>}</div></div>
  </>;
}

function KnowledgePage({role}: {role: string}) {
  const canEdit = role !== 'viewer';
  const {data: docs, reload, error: loadError} = useData<DocumentItem[]>('/documents', 4000);
  const [showAdd, setShowAdd] = useState(false);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function add(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/documents', 'POST', {title, content}); setTitle(''); setContent(''); setShowAdd(false); await reload(); }
    catch(err) {setError((err as Error).message);} finally {setBusy(false);}
  }
  async function remove(id: string) {
    if (!window.confirm('Delete this knowledge source and its vector index?')) return;
    try { await api(`/documents/${id}`, 'DELETE'); await reload(); } catch(e) { setError((e as Error).message); }
  }
  return <><Heading eyebrow="KNOWLEDGE ENGINE" title="Knowledge base" description="Your approved business information becomes the evidence behind AI drafts." action={canEdit && <button className="primary" onClick={() => setShowAdd(!showAdd)}>+ Add source</button>}/>
    <div className="info-banner"><span>ⓘ</span><p>Only add information you're authorized to process. Documents are indexed into tenant-scoped vector embeddings; embedded text is treated as untrusted reference data.</p></div>
    {showAdd && <Panel title="Add knowledge source" hint="Paste plain text such as FAQs, service instructions, support policies, or troubleshooting guides"><form onSubmit={add} className="composer"><Field label="Source title"><input required minLength={3} maxLength={220} value={title} onChange={e => setTitle(e.target.value)} placeholder="Returns & refunds policy"/></Field><Field label="Source content"><textarea required rows={11} minLength={50} maxLength={120000} value={content} onChange={e => setContent(e.target.value)} placeholder="Paste policy text (minimum 50 characters)…"/></Field><div className="actions"><button type="button" className="secondary" onClick={() => setShowAdd(false)}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Add and index →'}</button></div></form></Panel>}
    {loadError && <div className="error-box">{loadError}</div>}{error && <div className="error-box">{error}</div>}
    <Panel title="Indexed sources" hint={`${docs?.length || 0} knowledge documents in your workspace`}>
      {docs?.length ? <div className="knowledge-list">{docs.map(doc => <div className="knowledge-row" key={doc.id}><div className="doc-avatar">▧</div><div className="list-main"><b>{doc.title}</b><small>{doc.chunk_count} passages · Added {shortDate(doc.created_at)}</small>{doc.error && <small className="error-text">{doc.error}</small>}</div><Badge status={doc.status}/>{canEdit && doc.status === 'failed' && <button className="secondary" onClick={() => void api(`/documents/${doc.id}/retry`, 'POST').then(reload).catch(e => setError(e.message))}>Retry ↻</button>}{canEdit && <button className="icon-btn" title="Delete knowledge source" onClick={() => void remove(doc.id)}>✕</button>}</div>)}</div> : <Empty icon="▣" title="Build your knowledge base" desc="Add a policy or FAQ so the AI has verified information to cite."/>}
    </Panel>
  </>;
}

function EvaluationsPage({role}: {role: string}) {
  const canEdit = role !== 'viewer';
  const {data: cases, reload: reloadCases} = useData<EvalCase[]>('/evaluations/cases', 12000);
  const {data: runs, reload: reloadRuns} = useData<EvalRun[]>('/evaluations/runs', 4000);
  const [question, setQuestion] = useState('');
  const [must, setMust] = useState('');
  const [abstain, setAbstain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function add(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {await api('/evaluations/cases', 'POST', {question, must_include: must || null, expect_abstain: abstain}); setQuestion(''); setMust(''); setAbstain(false); await reloadCases();}
    catch(err) {setError((err as Error).message);} finally {setBusy(false);}
  }
  async function run() {
    setBusy(true); setError('');
    try {await api('/evaluations/run', 'POST'); await reloadRuns();}
    catch(err) {setError((err as Error).message);} finally {setBusy(false);}
  }
  return <><Heading eyebrow="QUALITY ASSURANCE" title="AI evaluations" description="Catch regressions with repeatable, knowledge-grounded test cases and measurable results." action={canEdit && <button className="primary" disabled={busy || !cases?.length} onClick={() => void run()}>◇ Run evaluation</button>}/>
    <div className="info-banner"><span>⌁</span><p>Evaluations check expected phrases, citations, and abstention behavior. They are not proof of factual correctness; humans should inspect failures and borderline answers.</p></div>
    {error && <div className="error-box">{error}</div>}
    <div className="eval-grid"><Panel title="Test cases" hint="Create up to 20 reusable cases per workspace">
      {canEdit && <form onSubmit={add} className="composer compact"><Field label="Customer question"><textarea required rows={3} minLength={5} value={question} onChange={e => setQuestion(e.target.value)} placeholder="What is your return window?"/></Field><Field label="Phrase that must appear (optional)"><input value={must} onChange={e => setMust(e.target.value)} maxLength={180} placeholder="30 days"/></Field><label className="check-row"><input type="checkbox" checked={abstain} onChange={e => setAbstain(e.target.checked)}/> Expected answer is “unknown” (must abstain)</label><button className="secondary" disabled={busy}>+ Add test case</button></form>}
      {cases?.length ? <div className="eval-cases">{cases.map(c => <div className="eval-case" key={c.id}><div><b>{c.question}</b><p>{c.expect_abstain ? 'Expected: abstain' : c.must_include ? `Must include: ${c.must_include}` : 'Requires verified citation'}</p></div>{canEdit && <button className="icon-btn" onClick={() => void api(`/evaluations/cases/${c.id}`, 'DELETE').then(reloadCases).catch(e => setError(e.message))}>✕</button>}</div>)}</div> : <p className="muted pad">Create your first regression case above.</p>}
    </Panel><Panel title="Latest evaluation runs" hint="A result appears here when workers finish processing">
      {runs?.length ? <div className="eval-runs">{runs.map(r => <div className="run" key={r.id}><div className="run-head"><b>{shortDate(r.created_at)}</b><Badge status={r.status}/></div><div className="run-score">{r.status === 'completed' ? `${r.passed}/${r.total} passed` : `${r.total} test cases`}</div>{r.status === 'completed' && <div className="progress"><div style={{width:`${r.total ? (r.passed/r.total)*100 : 0}%`}}/></div>}{r.error && <p className="error-text">{r.error}</p>}{r.results?.length > 0 && <div className="results">{r.results.map(result => <div className="result" key={result.case_id}><span>{result.passed ? '✓' : '✕'}</span><div><b>{result.question}</b><small>{result.preview}</small></div></div>)}</div>}</div>)}</div> : <Empty icon="◇" title="No evaluation runs yet" desc="Add cases and run the evaluation suite."/>}
    </Panel></div>
  </>;
}

function TeamPage({me}: {me: Me}) {
  const {data, reload} = useData<{email: string; role: string}[]>('/team');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('agent');
  const [inviteLink, setInviteLink] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function invite(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {const result = await api<{invite_url: string}>('/team/invite', 'POST', {email, role}); setInviteLink(result.invite_url); setEmail(''); await reload();}
    catch(err) {setError((err as Error).message);} finally {setBusy(false);}
  }
  return <><Heading eyebrow="ACCESS CONTROL" title="Team members" description="Collaborate securely with workspace roles and private, single-use invitations."/>
    <div className="two-panels"><Panel title="Workspace members" hint="Owner and agent roles can review tickets">
      {data?.map(person => <div className="list-row" key={person.email}><div className="member-avatar">{person.email[0]?.toUpperCase()}</div><div className="list-main"><b>{person.email}</b><small>Active workspace member</small></div><Badge status={person.role}/></div>)}
    </Panel><Panel title="Invite a teammate" hint="Invitations expire after 72 hours and can only be accepted once">
      {me.role === 'owner' ? <form onSubmit={invite} className="composer"><Field label="Team member email"><input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="teammate@company.com"/></Field><Field label="Access role"><select value={role} onChange={e => setRole(e.target.value)}><option value="agent">Agent — manage tickets & knowledge</option><option value="viewer">Viewer — read only</option></select></Field><button className="primary" disabled={busy}>{busy ? 'Creating…' : 'Create invitation link'}</button></form> : <p className="muted pad">Only workspace owners can invite members.</p>}
      {error && <div className="error-box">{error}</div>}{inviteLink && <div className="invite-box"><b>Invitation ready — copy now</b><p>This link will not be shown again.</p><input readOnly value={inviteLink}/><button className="secondary" onClick={() => void navigator.clipboard.writeText(inviteLink)}>Copy invitation link</button></div>}
    </Panel></div>
  </>;
}

function BillingPage({me}: {me: Me}) {
  const {data} = useData<{plan: string; monthly_ticket_limit: number; checkout_enabled: boolean}>('/billing');
  const {data: totals} = useData<Overview>('/overview');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function openCheckout(plan: 'starter' | 'growth') {
    setBusy(true); setError('');
    try { const result = await api<{url: string}>('/billing/checkout', 'POST', {plan}); window.location.assign(result.url); }
    catch(err) { setError((err as Error).message); setBusy(false); }
  }
  async function openPortal() {
    setBusy(true); setError('');
    try { const result = await api<{url: string}>('/billing/portal', 'POST'); window.location.assign(result.url); }
    catch(err) { setError((err as Error).message); setBusy(false); }
  }
  return <><Heading eyebrow="SUBSCRIPTION" title="Plans & usage" description="Choose the ticket volume that fits your support team."/>
    {error && <div className="error-box">{error}</div>}
    <div className="plan-grid">{[
      {key:'trial', label:'Free workspace', count:25, summary:'Evaluate the product on real support questions'},
      {key:'starter', label:'Starter', count:500, summary:'For growing teams with regular support volume'},
      {key:'growth', label:'Growth', count:5000, summary:'For larger support operations and teams'},
    ].map(plan => <div key={plan.key} className={`plan-card ${me.plan === plan.key ? 'selected-plan' : ''}`}><div className="plan-head"><h3>{plan.label}</h3>{me.plan === plan.key && <span className="pill success">Current plan</span>}</div><strong>{plan.count.toLocaleString()}</strong><small>draft tickets per month</small><p>{plan.summary}</p>{plan.key !== 'trial' && <button className={me.plan === plan.key ? 'secondary full' : 'primary full'} disabled={busy || me.role !== 'owner' || me.plan === plan.key || !data?.checkout_enabled} onClick={() => void openCheckout(plan.key as 'starter'|'growth')}>{me.plan === plan.key ? 'Current plan' : data?.checkout_enabled ? 'Select plan →' : 'Contact sales to enable'}</button>}</div>)}</div>
    <Panel title="Account usage" hint="Draft limits renew on the first day of each calendar month (UTC)"><div className="usage-bar-title"><b>Used this month</b><span>{totals?.this_month || 0} / {data?.monthly_ticket_limit || 25} tickets</span></div><div className="progress"><div style={{width:`${Math.min(100, 100 * (totals?.this_month || 0) / (data?.monthly_ticket_limit || 25))}%`}}/></div>{me.role === 'owner' && me.plan !== 'trial' && data?.checkout_enabled && <button className="secondary top-gap" disabled={busy} onClick={() => void openPortal()}>Manage subscription ↗</button>}
      <p className="muted top-gap">Subscription payments are securely hosted by Stripe. Model API usage may create separate infrastructure costs.</p></Panel>
  </>;
}

function AuditPage() {
  const {data, error} = useData<{action: string; entity_id: string | null; created_at: string}[]>('/audit', 7000);
  return <><Heading eyebrow="TRUST & GOVERNANCE" title="Audit trail" description="Track key workspace changes, ticket approvals, and evaluation activity."/>
    {error && <div className="error-box">{error}</div>}
    <Panel title="Recent activity" hint="Last 60 meaningful workspace events">{data?.length ? data.map((event, index) => <div className="list-row" key={index}><span className="list-avatar">⟳</span><div className="list-main"><b>{event.action.replaceAll('.', ' · ').replaceAll('_', ' ')}</b><small>{event.entity_id?.slice(0,8) || 'Workspace event'}</small></div><small className="muted">{shortDate(event.created_at)}</small></div>) : <Empty icon="≡" title="No activity yet" desc="Changes will appear here."/>}</Panel>
  </>;
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const [page, setPage] = useState<Page>('overview');
  const [logoutBusy, setLogoutBusy] = useState(false);
  const getMe = useCallback(async () => {
    try { const result = await api<Me>('/auth/me'); setCsrf(result.csrf_token); setMe(result); }
    catch { setMe(null); setCsrf(''); }
    finally {setChecked(true);}
  }, []);
  useEffect(() => {void getMe();}, [getMe]);
  async function logout() {
    setLogoutBusy(true);
    try { await api('/auth/logout', 'POST'); } finally { setMe(null); setCsrf(''); setLogoutBusy(false); }
  }
  if (!checked) return <div className="splash"><div className="splash-logo">✦</div>Loading GroundReply…</div>;
  if (!me) return <Auth onSuccess={() => void getMe()}/>;
  const safeMenu = menu.filter(item => !(item.key === 'audit' && me.role !== 'owner'));
  return <div className="layout"><aside className="sidebar"><div className="brand"><span className="brand-icon">✦</span><div><strong>KTNS <span>GroundReply</span></strong><small>AI OPERATIONS</small></div></div>
    <div className="workspace-switch"><div className="workspace-letter">{me.organization_name[0]?.toUpperCase()}</div><div><b>{me.organization_name}</b><small>{me.plan.toUpperCase()} WORKSPACE</small></div><span className="tiny-chevron">⌄</span></div>
    <div className="nav-section-label">WORKSPACE</div><nav>{safeMenu.map(item => <button key={item.key} className={`nav-item ${page === item.key ? 'selected' : ''}`} onClick={() => setPage(item.key)}><span>{item.glyph}</span>{item.label}{item.key === 'inbox' && <span className="nav-dot"/>}</button>)}</nav>
    <div className="sidebar-bottom"><div className="trust-tag"><span>◉</span><div><b>Grounded AI</b><small>Human approval required</small></div></div><div className="profile"><div className="profile-avatar">{me.email[0]?.toUpperCase()}</div><div className="profile-details"><b>{me.email}</b><small>{me.role} access</small></div><button title="Sign out" className="logout" disabled={logoutBusy} onClick={() => void logout()}>⇥</button></div></div></aside>
    <div className="main"><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <b>{safeMenu.find(item => item.key === page)?.label}</b></div><div className="topbar-right"><span className="online"><span/> Human approval on</span><span className="top-avatar">{me.email[0]?.toUpperCase()}</span></div></header>
      <main className="content">{page === 'overview' && <OverviewPage go={setPage}/>}{page === 'inbox' && <TicketsPage role={me.role}/>}{page === 'knowledge' && <KnowledgePage role={me.role}/>}{page === 'evaluations' && <EvaluationsPage role={me.role}/>}{page === 'team' && <TeamPage me={me}/>}{page === 'billing' && <BillingPage me={me}/>}{page === 'audit' && <AuditPage/>}</main>
      <footer className="footer"><span>KTNS GroundReply</span><span>Built for trustworthy AI operations · v0.1</span></footer>
    </div>
  </div>;
}
