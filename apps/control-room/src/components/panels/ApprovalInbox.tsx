import { motion, AnimatePresence } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import { RiskBadge } from '@/components/ui/RiskBadge';
import { StatusPill } from '@/components/ui/StatusPill';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  ExternalLink,
  Shield,
} from 'lucide-react';

export function ApprovalInbox() {
  const approvals = useTsfStore((s) => s.approvals);
  const approveRequest = useTsfStore((s) => s.approveRequest);
  const denyRequest = useTsfStore((s) => s.denyRequest);
  const runtimeState = useTsfStore((s) => s.runtimeState);
  const dataSourceMode = useTsfStore((s) => s.dataSourceMode);
  const readOnly = dataSourceMode !== 'mock';

  const pending = approvals.filter((a) => a.status === 'pending');
  const resolved = approvals.filter((a) => a.status !== 'pending');

  if (approvals.length === 0) {
    return (
      <GlassCard className="flex flex-col items-center justify-center py-10">
        <ShieldAlert className="h-7 w-7 text-[#1e293b]" />
        <p className="mt-2 text-[11px] text-[#475569]">No approvals yet</p>
        <p className="text-[9px] text-[#334155]">External actions appear here</p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-1.5">
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#F59E0B]">{pending.length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Pending</p>
        </div>
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#10B981]">{approvals.filter((a) => a.status === 'approved').length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Approved</p>
        </div>
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#EF4444]">{approvals.filter((a) => a.status === 'denied').length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Denied</p>
        </div>
      </div>

      {pending.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#F59E0B]">Pending</h4>
          {readOnly && (
            <div className="mb-2 rounded border border-[#06B6D4]/20 bg-[#06B6D4]/10 p-2 text-[9px] leading-relaxed text-[#06B6D4]">
              This public observer view is read-only. Approval handling is private and founder-only.
            </div>
          )}
          <div className="space-y-1.5">
            <AnimatePresence>
              {pending.map((approval) => (
                <motion.div key={approval.id} layout initial={{ opacity: 0, y: -16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }} transition={{ type: 'spring', stiffness: 400, damping: 28 }}>
                  <GlassCard borderColor={approval.riskLevel === 'critical' ? '#EF4444' : approval.riskLevel === 'high' ? '#F59E0B' : undefined}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-semibold text-[#06B6D4]">{approval.requesterId}</span>
                          {approval.hasExternalEffect && <span className="flex items-center gap-0.5 rounded bg-[#EF4444]/10 px-1 py-[1px] text-[7px] text-[#EF4444]"><ExternalLink className="h-2 w-2" /> EXT</span>}
                        </div>
                        <p className="mt-0.5 text-[11px] text-[#e2e8f0]">{approval.action}</p>
                      </div>
                      <RiskBadge level={approval.riskLevel} />
                    </div>
                    <p className="mt-1.5 text-[9px] leading-relaxed text-[#475569]">{approval.description}</p>
                    <div className="mt-1.5 flex items-start gap-1.5 rounded bg-[#020617]/50 p-1.5">
                      <Shield className="mt-0.5 h-3 w-3 shrink-0 text-[#8B5CF6]" />
                      <p className="text-[8px] leading-relaxed text-[#8B5CF6]">{approval.sentinelReview}</p>
                    </div>
                    {!readOnly && runtimeState !== 'killed' && (
                      <div className="mt-2 flex gap-1.5">
                        <button onClick={() => approveRequest(approval.id)} className="flex flex-1 items-center justify-center gap-1 rounded border border-[#10B981]/20 bg-[#10B981]/10 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#10B981] transition-all hover:bg-[#10B981]/20">
                          <CheckCircle className="h-3 w-3" /> Approve
                        </button>
                        <button onClick={() => denyRequest(approval.id)} className="flex flex-1 items-center justify-center gap-1 rounded border border-[#334155]/50 bg-[#1e293b]/50 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#475569] transition-all hover:bg-[#334155]/50">
                          <XCircle className="h-3 w-3" /> Deny
                        </button>
                      </div>
                    )}
                  </GlassCard>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {resolved.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Resolved</h4>
          <div className="space-y-1 opacity-50">
            {resolved.map((approval) => (
              <GlassCard key={approval.id} className="py-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-[#475569]">{approval.requesterId}</span>
                    <span className="truncate text-[10px] text-[#e2e8f0]">{approval.action}</span>
                  </div>
                  <StatusPill status={approval.status} size="sm" />
                </div>
              </GlassCard>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
