import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import { Lock, ShieldCheck, ShieldX } from 'lucide-react';

export function ReadOnlyStatusPanel() {
  const dataSourceMode = useTsfStore((s) => s.dataSourceMode);
  const dataSourceStatus = useTsfStore((s) => s.dataSourceStatus);
  const dataSourceError = useTsfStore((s) => s.dataSourceError);
  const metadata = useTsfStore((s) => s.snapshotMetadata);
  const runtimeState = useTsfStore((s) => s.runtimeState);
  const approvals = useTsfStore((s) => s.approvals);
  const tasks = useTsfStore((s) => s.tasks);

  if (dataSourceMode === 'mock') return null;

  const pendingApprovals = approvals.filter((approval) => approval.status === 'pending').length;
  const blockedTasks = tasks.filter((task) => task.status === 'blocked').length;
  const AuditIcon = metadata.auditVerified ? ShieldCheck : ShieldX;

  return (
    <div className="border-b border-[#1e293b]/60 p-3">
      <GlassCard borderColor={metadata.auditVerified === false ? '#EF4444' : '#06B6D4'}>
        <div className="flex items-start gap-2">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#06B6D4]" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[9px] font-semibold uppercase tracking-wider text-[#06B6D4]">Public Observer Mode</p>
              <span className="text-[8px] uppercase tracking-wider text-[#475569]">{dataSourceStatus}</span>
            </div>
            <p className="mt-1 text-[9px] leading-relaxed text-[#64748b]">
              Read-only public progress window. Agents decide their own work; the founder only handles real-world blockers.
            </p>
            <div className="mt-2 grid grid-cols-2 gap-1 text-[8px] text-[#94a3b8]">
              <span>schema: {metadata.schemaVersion || 'unknown'}</span>
              <span>runtime: {runtimeState}</span>
              <span>generated: {metadata.generatedAt ? new Date(metadata.generatedAt).toLocaleTimeString() : 'unknown'}</span>
              <span>source: {metadata.sourceLabel || 'TSF snapshot'}</span>
              <span>pending approvals: {pendingApprovals}</span>
              <span>blocked tasks: {blockedTasks}</span>
              <span>workday: {metadata.autonomousWorkdayStatus || 'not_started'}</span>
              <span>blocked adapters: {metadata.queueBlockedMissingAdapter}</span>
              <span>scheduler: {metadata.schedulerStatus || 'not_started'}</span>
              <span>window: {metadata.workdayWindow || '10:00-16:00 Europe/Paris'}</span>
              <span>last checkpoint: {metadata.lastCheckpointAt ? new Date(metadata.lastCheckpointAt).toLocaleTimeString() : 'none'}</span>
              <span>next checkpoint: {metadata.nextCheckpoint || 'next workday'}</span>
              <span>deployment: {metadata.deploymentState || 'not_started'}</span>
              <span>storage: {metadata.storeBackendPublicStatus || 'sqlite_preview'}</span>
              <span>repository: {metadata.repositoryMode || 'sqlite_active'}</span>
              <span>Atlas report: {metadata.lastAtlasReportAt ? new Date(metadata.lastAtlasReportAt).toLocaleTimeString() : 'none'}</span>
              <span className="flex items-center gap-1">
                <AuditIcon className="h-3 w-3" />
                audit #{metadata.lastAuditSequence ?? 0}
              </span>
            </div>
            <p className="mt-2 text-[9px] font-semibold uppercase tracking-wider text-[#94a3b8]">
              Autonomous Scheduler Status
            </p>
            <p className="mt-1 text-[9px] leading-relaxed text-[#64748b]">
              Agents work 10:00-16:00 Europe/Paris. Scheduler updates are read-only here.
            </p>
            {metadata.autonomousWorkdaySummary && (
              <p className="mt-2 text-[9px] leading-relaxed text-[#94a3b8]">{metadata.autonomousWorkdaySummary}</p>
            )}
            {metadata.deploymentSummary && (
              <p className="mt-2 text-[9px] leading-relaxed text-[#94a3b8]">{metadata.deploymentSummary}</p>
            )}
            {metadata.storageSummary && (
              <p className="mt-2 text-[9px] leading-relaxed text-[#94a3b8]">{metadata.storageSummary}</p>
            )}
            {metadata.publicEmptyStateReason && (
              <p className="mt-2 text-[9px] leading-relaxed text-[#94a3b8]">{metadata.publicEmptyStateReason}</p>
            )}
            {dataSourceError && <p className="mt-2 text-[9px] text-[#EF4444]">{dataSourceError}</p>}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
