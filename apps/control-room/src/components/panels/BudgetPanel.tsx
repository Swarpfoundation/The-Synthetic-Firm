import { motion } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import { Wallet, AlertTriangle, PiggyBank } from 'lucide-react';

const AGENT_NAMES: Record<string, string> = {
  atlas: 'Atlas', scout: 'Scout', forge: 'Forge', pulse: 'Pulse', sentinel: 'Sentinel',
};
const AGENT_COLORS: Record<string, string> = {
  atlas: '#06B6D4', scout: '#8B5CF6', forge: '#F59E0B', pulse: '#10B981', sentinel: '#EF4444',
};

export function BudgetPanel() {
  const budget = useTsfStore((s) => s.budget);
  const pct = Math.min((budget.currentUsage / budget.dailyLimit) * 100, 100);
  const remaining = budget.dailyLimit - budget.currentUsage;

  const threshold = pct >= 100 ? { text: 'EXHAUSTED', color: '#EF4444' }
    : pct >= 95 ? { text: 'CRITICAL', color: '#EF4444' }
    : pct >= 80 ? { text: 'WARNING', color: '#F59E0B' }
    : pct >= 50 ? { text: 'CAUTION', color: '#F59E0B' }
    : { text: 'HEALTHY', color: '#10B981' };

  return (
    <div className="space-y-2">
      <GlassCard>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-[#06B6D4]" />
            <span className="text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Daily Budget</span>
          </div>
          <span className="rounded border px-1.5 py-[1px] text-[9px] font-semibold uppercase tracking-wider" style={{ backgroundColor: `${threshold.color}15`, color: threshold.color, borderColor: `${threshold.color}30` }}>
            {threshold.text}
          </span>
        </div>
        <div className="mt-3">
          <div className="flex items-end justify-between">
            <div>
              <p className="font-mono text-xl font-semibold text-[#e2e8f0]">${budget.currentUsage.toFixed(0)}</p>
              <p className="text-[9px] text-[#475569]">of ${budget.dailyLimit.toFixed(0)}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-base font-semibold" style={{ color: remaining < 100 ? '#EF4444' : '#10B981' }}>${remaining.toFixed(0)}</p>
              <p className="text-[9px] text-[#475569]">remaining</p>
            </div>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[#1e293b]">
            <motion.div className="h-full rounded-full" style={{ background: `linear-gradient(90deg, #10B981, #F59E0B ${Math.min(pct, 80)}%, #EF4444)` }} initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8 }} />
          </div>
          <div className="mt-1 flex justify-between text-[8px] text-[#475569]">
            <span>0%</span><span>50%</span><span>80%</span><span>95%</span><span>100%</span>
          </div>
        </div>
        {pct >= 80 && (
          <div className="mt-2 flex items-center gap-1.5 rounded bg-[#F59E0B]/10 p-1.5">
            <AlertTriangle className="h-3 w-3 text-[#F59E0B]" />
            <span className="text-[9px] text-[#F59E0B]">Approaching limit — deny non-critical approvals</span>
          </div>
        )}
      </GlassCard>

      <GlassCard>
        <h4 className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Per-Agent</h4>
        <div className="space-y-2">
          {Object.entries(budget.perAgentUsage).map(([agentId, usage]) => {
            const agentPct = (usage / Math.max(budget.currentUsage, 1)) * 100;
            return (
              <div key={agentId}>
                <div className="mb-0.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full" style={{ backgroundColor: AGENT_COLORS[agentId] }} />
                    <span className="text-[10px] text-[#e2e8f0]">{AGENT_NAMES[agentId]}</span>
                  </div>
                  <span className="font-mono text-[9px] text-[#475569]">${usage.toFixed(0)}</span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-[#020617]/50">
                  <motion.div className="h-full rounded-full" style={{ backgroundColor: AGENT_COLORS[agentId] }} initial={{ width: 0 }} animate={{ width: `${agentPct}%` }} transition={{ duration: 0.5 }} />
                </div>
              </div>
            );
          })}
        </div>
      </GlassCard>

      <GlassCard>
        <div className="flex items-start gap-2">
          <PiggyBank className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#10B981]" />
          <div>
            <p className="text-[9px] font-semibold text-[#10B981]">Tip</p>
            <p className="mt-0.5 text-[9px] leading-relaxed text-[#475569]">Deny high-risk external actions to preserve budget for critical ops.</p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
