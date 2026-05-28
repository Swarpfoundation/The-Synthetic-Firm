import { motion } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import {
  CheckCircle,
  AlertTriangle,
  ShieldAlert,
  Lightbulb,
  ArrowRight,
  Play,
} from 'lucide-react';

export function DailyReportPanel() {
  const dailyReport = useTsfStore((s) => s.dailyReport);
  const isReportModalOpen = useTsfStore((s) => s.isReportModalOpen);
  const closeReportModal = useTsfStore((s) => s.closeReportModal);
  const startNewDay = useTsfStore((s) => s.startNewDay);
  const workdayClock = useTsfStore((s) => s.workdayClock);
  const tasks = useTsfStore((s) => s.tasks);
  const approvals = useTsfStore((s) => s.approvals);
  const budget = useTsfStore((s) => s.budget);
  const dataSourceMode = useTsfStore((s) => s.dataSourceMode);
  const readOnly = dataSourceMode !== 'mock';

  const report = dailyReport || {
    day: workdayClock.day,
    date: new Date().toISOString().split('T')[0],
    completedTasks: tasks.filter((t) => t.status === 'completed').length,
    blockedTasks: tasks.filter((t) => t.status === 'blocked').length,
    pendingApprovals: approvals.filter((a) => a.status === 'pending').length,
    budgetUsage: budget.currentUsage,
    budgetLimit: budget.dailyLimit,
    sentinelRisks: approvals.filter((a) => a.riskLevel === 'high' || a.riskLevel === 'critical').map((a) => `${a.requesterId}: ${a.action} (${a.riskLevel})`),
    founderQuestions: readOnly ? ['No public human tasks pending.'] : [`Review ${tasks.filter((t) => t.status === 'completed').length} completed tasks`, `Address ${tasks.filter((t) => t.status === 'blocked').length} blocked tasks`],
    nextActions: readOnly ? ['No public next steps recorded yet.'] : ['Continue monitoring', 'Review pending approvals'],
    efficiency: tasks.length > 0 ? Math.round((tasks.filter((t) => t.status === 'completed').length / tasks.length) * 100) : 100,
  };

  const efficiencyColor = report.efficiency >= 80 ? '#10B981' : report.efficiency >= 60 ? '#F59E0B' : '#EF4444';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Day {report.day} Report</span>
        </div>
        <span className="font-mono text-[9px] text-[#475569]">{report.date}</span>
      </div>

      <GlassCard className="text-center">
        <p className="text-[9px] uppercase tracking-wider text-[#475569]">Efficiency</p>
        <motion.p className="mt-1 font-mono text-3xl font-bold" style={{ color: efficiencyColor }} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200 }}>
          {report.efficiency}%
        </motion.p>
        <div className="mx-auto mt-1.5 h-1 w-24 overflow-hidden rounded-full bg-[#1e293b]">
          <motion.div className="h-full rounded-full" style={{ backgroundColor: efficiencyColor }} initial={{ width: 0 }} animate={{ width: `${report.efficiency}%` }} transition={{ duration: 0.8 }} />
        </div>
      </GlassCard>

      <div className="grid grid-cols-2 gap-1.5">
        <GlassCard className="text-center"><CheckCircle className="mx-auto h-4 w-4 text-[#10B981]" /><p className="mt-1 font-mono text-lg font-semibold text-[#e2e8f0]">{report.completedTasks}</p><p className="text-[8px] uppercase tracking-wider text-[#475569]">Completed</p></GlassCard>
        <GlassCard className="text-center"><AlertTriangle className="mx-auto h-4 w-4 text-[#F59E0B]" /><p className="mt-1 font-mono text-lg font-semibold text-[#e2e8f0]">{report.blockedTasks}</p><p className="text-[8px] uppercase tracking-wider text-[#475569]">Blocked</p></GlassCard>
        <GlassCard className="text-center"><ShieldAlert className="mx-auto h-4 w-4 text-[#F59E0B]" /><p className="mt-1 font-mono text-lg font-semibold text-[#e2e8f0]">{report.pendingApprovals}</p><p className="text-[8px] uppercase tracking-wider text-[#475569]">Pending</p></GlassCard>
        <GlassCard className="text-center"><p className="mx-auto font-mono text-sm text-[#06B6D4]">$</p><p className="mt-1 font-mono text-lg font-semibold text-[#e2e8f0]">${report.budgetUsage.toFixed(0)}</p><p className="text-[8px] uppercase tracking-wider text-[#475569]">of ${report.budgetLimit}</p></GlassCard>
      </div>

      {report.sentinelRisks.length > 0 && (
        <GlassCard>
          <h4 className="mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#EF4444]"><ShieldAlert className="h-3 w-3" /> Sentinel Flags</h4>
          {report.sentinelRisks.map((risk, i) => <div key={i} className="rounded bg-[#EF4444]/5 p-1.5 text-[9px] text-[#e2e8f0]">{risk}</div>)}
        </GlassCard>
      )}

      <GlassCard>
        <h4 className="mb-1.5 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-wider text-[#F59E0B]"><Lightbulb className="h-3 w-3" /> Action Items</h4>
        {report.founderQuestions.map((q, i) => <div key={i} className="flex items-start gap-1.5"><ArrowRight className="mt-0.5 h-2 w-2 shrink-0 text-[#475569]" /><span className="text-[9px] text-[#475569]">{q}</span></div>)}
      </GlassCard>

      {isReportModalOpen && (
        <motion.button initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} disabled={readOnly} onClick={() => { closeReportModal(); if (!readOnly) startNewDay(); }} className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#06B6D4] py-2.5 text-[11px] font-semibold uppercase tracking-wider text-white transition-all hover:bg-[#06B6D4]/90 disabled:cursor-not-allowed disabled:opacity-40">
          <Play className="h-3.5 w-3.5" /> {readOnly ? 'Read-only snapshot' : `Start Day ${report.day + 1}`}
        </motion.button>
      )}
    </div>
  );
}
