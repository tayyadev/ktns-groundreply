export type Page = 'overview' | 'inbox' | 'knowledge' | 'evaluations' | 'team' | 'billing' | 'audit';
export interface Me {
  user_id: string; email: string; role: string; organization_id: string;
  organization_name: string; plan: string; csrf_token: string;
}
export interface Overview {
  total_tickets: number; this_month: number; needs_action: number; approved: number;
  ready_documents: number; monthly_limit: number; input_tokens: number; output_tokens: number;
}
export interface DocumentItem {
  id: string; title: string; status: string; chunk_count: number; error: string | null; created_at: string;
}
export interface Citation { ref: string; title: string; excerpt: string; document_id: string; similarity: number; }
export interface Ticket {
  id: string; subject: string; status: string; category: string | null; priority: string | null;
  requester_email: string | null; created_at: string; approved_at: string | null;
  question?: string; draft?: string | null; citations?: Citation[];
  review_flags?: string[]; trace?: {step: string; [key: string]: unknown}[]; error?: string | null;
}
export interface EvalCase { id: string; question: string; must_include: string | null; expect_abstain: boolean; }
export interface EvalResult { case_id: string; question: string; passed: boolean; abstained: boolean; citations: number; preview: string; }
export interface EvalRun { id: string; status: string; passed: number; total: number; results: EvalResult[]; error: string | null; created_at: string; }
