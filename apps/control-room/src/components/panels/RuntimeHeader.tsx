import { motion } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { getPhaseLabel, formatTimeUntilEnd, getParisClockLabel } from '@/utils/workday';
import {
  Play,
  Pause,
  Square,
  Activity,
  Clock,
  Zap,
} from 'lucide-react';

export function RuntimeHeader() {
  const runtimeState = useTsfStore((s) => s.runtimeState);
  const dataSourceMode = useTsfStore((s) => s.dataSourceMode);
  const dataSourceLabel = useTsfStore((s) => s.dataSourceLabel);
  const dataSourceStatus = useTsfStore((s) => s.dataSourceStatus);
  const snapshotMetadata = useTsfStore((s) => s.snapshotMetadata);
  const workdayClock = useTsfStore((s) => s.workdayClock);
  const budget = useTsfStore((s) => s.budget);
  const pauseRuntime = useTsfStore((s) => s.pauseRuntime);
  const resumeRuntime = useTsfStore((s) => s.resumeRuntime);
  const killRuntime = useTsfStore((s) => s.killRuntime);
  const parisTime = getParisClockLabel();
  const readOnly = dataSourceMode !== 'mock';

  const budgetPct = (budget.currentUsage / budget.dailyLimit) * 100;
  const budgetColor = budgetPct >= 95 ? '#EF4444' : budgetPct >= 80 ? '#F59E0B' : budgetPct >= 50 ? '#F59E0B' : '#10B981';

  return (
    <motion.header
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className="pointer-events-auto absolute left-0 right-0 top-0 z-30 flex h-[56px] items-center justify-between border-b border-[#1e293b]/60 bg-[#0a0e17]/70 px-4 backdrop-blur-xl"
    >
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <motion.div
          className="flex h-8 w-8 items-center justify-center rounded bg-[#06B6D4]/10 ring-1 ring-[#06B6D4]/20"
          whileHover={{ scale: 1.1 }}
        >
          <Activity className="h-4 w-4 text-[#06B6D4]" />
        </motion.div>
        <div>
          <h1 className="text-[13px] font-bold tracking-[0.15em] text-[#e2e8f0]">
            Public Progress Window
          </h1>
          <p className="text-[9px] tracking-wider text-[#475569]">
            Read-only public view — Real TSF runtime data only
          </p>
        </div>
      </div>

      {/* Center: Clock & Phase */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 text-[#06B6D4]" />
          <span className="font-mono text-[15px] font-semibold text-[#e2e8f0]">
            {workdayClock.currentTime}
          </span>
          <span className="text-[9px] text-[#475569]">Europe/Paris {parisTime}</span>
        </div>

        <div className="h-5 w-px bg-[#1e293b]" />

        <div className="flex items-center gap-2">
          <motion.div
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: workdayClock.isWithinWorkHours ? '#10B981' : '#475569' }}
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span
            className="rounded border px-2 py-[2px] text-[9px] font-semibold uppercase tracking-wider"
            style={{
              backgroundColor: `${getStatusColor(workdayClock.phase)}15`,
              color: getStatusColor(workdayClock.phase),
              borderColor: `${getStatusColor(workdayClock.phase)}30`,
            }}
          >
            {getPhaseLabel(workdayClock.phase)}
          </span>
        </div>

        <div className="h-5 w-px bg-[#1e293b]" />

        <div className="rounded border border-[#06B6D4]/20 bg-[#06B6D4]/10 px-2 py-[2px]">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-[#06B6D4]">
            {dataSourceLabel}
          </span>
          {readOnly && (
            <span className="ml-1 text-[8px] uppercase tracking-wider text-[#8B5CF6]">
              Read-only
            </span>
          )}
        </div>

        {dataSourceStatus === 'error' && (
          <span className="text-[9px] text-[#EF4444]">snapshot unavailable</span>
        )}

        {readOnly && snapshotMetadata.auditVerified !== null && (
          <span className="text-[9px] text-[#475569]">
            audit {snapshotMetadata.auditVerified ? 'verified' : 'failed'} #{snapshotMetadata.lastAuditSequence ?? 0}
          </span>
        )}

        <div className="h-5 w-px bg-[#1e293b]" />

        <span className="text-[10px] text-[#475569]">
          {formatTimeUntilEnd(workdayClock.currentTime)}
        </span>
      </div>

      {/* Right: Budget + Controls */}
      <div className="flex items-center gap-4">
        {/* Budget */}
        <div className="flex items-center gap-2">
          <Zap className="h-3 w-3" style={{ color: budgetColor }} />
          <div className="w-20">
            <div className="mb-0.5 flex justify-between">
              <span className="text-[8px] uppercase tracking-wider text-[#475569]">Budget</span>
              <span className="font-mono text-[8px]" style={{ color: budgetColor }}>
                {Math.round(budgetPct)}%
              </span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-[#1e293b]">
              <motion.div
                className="h-full rounded-full"
                style={{
                  background: `linear-gradient(90deg, #10B981, #F59E0B ${Math.min(budgetPct, 80)}%, #EF4444)`,
                }}
                animate={{ width: `${Math.min(budgetPct, 100)}%` }}
                transition={{ duration: 0.8 }}
              />
            </div>
          </div>
        </div>

        <div className="h-5 w-px bg-[#1e293b]" />

        {/* Controls */}
        <div className="flex items-center gap-1.5">
          <motion.div
            className="flex h-7 items-center gap-1.5 rounded border px-2.5 text-[10px] font-semibold uppercase tracking-wider"
            style={{
              backgroundColor: runtimeState === 'active' ? '#10B98115' : runtimeState === 'paused' ? '#F59E0B15' : '#EF444415',
              color: runtimeState === 'active' ? '#10B981' : runtimeState === 'paused' ? '#F59E0B' : '#EF4444',
              borderColor: runtimeState === 'active' ? '#10B98130' : runtimeState === 'paused' ? '#F59E0B30' : '#EF444430',
            }}
          >
            <div
              className="h-1.5 w-1.5 rounded-full"
              style={{
                backgroundColor: runtimeState === 'active' ? '#10B981' : runtimeState === 'paused' ? '#F59E0B' : '#EF4444',
              }}
            />
            {runtimeState}
          </motion.div>

          {readOnly ? (
            <span className="rounded border border-[#8B5CF6]/20 bg-[#8B5CF6]/10 px-2 py-1 text-[8px] uppercase tracking-wider text-[#8B5CF6]">
              Public observer
            </span>
          ) : runtimeState === 'active' ? (
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                onClick={pauseRuntime}
                className="flex h-7 w-7 items-center justify-center rounded border border-[#F59E0B]/20 bg-[#F59E0B]/10 text-[#F59E0B] transition-colors hover:bg-[#F59E0B]/20"
                title="Pause"
              >
                <Pause className="h-3.5 w-3.5" />
              </motion.button>
            ) : runtimeState === 'paused' ? (
              <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                onClick={resumeRuntime}
                className="flex h-7 w-7 items-center justify-center rounded border border-[#10B981]/20 bg-[#10B981]/10 text-[#10B981] transition-colors hover:bg-[#10B981]/20"
                title="Resume"
              >
                <Play className="h-3.5 w-3.5" />
              </motion.button>
            ) : null}

          {!readOnly && (
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.95 }}
              onClick={killRuntime}
              disabled={runtimeState === 'killed'}
              className="flex h-7 w-7 items-center justify-center rounded border border-[#EF4444]/20 bg-[#EF4444]/10 text-[#EF4444] transition-colors hover:bg-[#EF4444]/20 disabled:opacity-30"
              title="Kill"
            >
              <Square className="h-3.5 w-3.5" />
            </motion.button>
          )}
        </div>
      </div>
    </motion.header>
  );
}

function getStatusColor(phase: string): string {
  const colors: Record<string, string> = {
    planning: '#06B6D4',
    execution: '#10B981',
    review: '#8B5CF6',
    report: '#F59E0B',
    closed: '#475569',
  };
  return colors[phase] || '#475569';
}
