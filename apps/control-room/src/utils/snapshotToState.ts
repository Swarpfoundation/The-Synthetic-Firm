import { initialAgents, initialState } from '@/mocks/tsf-state';
import type { ControlRoomSnapshot, SnapshotTask } from '@/types/controlRoomSnapshot';
import type { AgentState, ApprovalStatus, RiskLevel, TaskStatus, TsfState } from '@/types/tsf';
import { snapshotToTimelineEvents } from './snapshotToEvents';

export function snapshotToState(snapshot: ControlRoomSnapshot): Partial<TsfState> {
  const tasks = snapshot.tasks.map(snapshotTaskToTask);
  const approvals = snapshot.approvals.map((approval) => ({
    id: approval.id,
    taskId: approval.taskId,
    requesterId: approval.agentId,
    action: approval.requestedAction,
    description: approval.plainEnglishRequest,
    status: normalizeApprovalStatus(approval.status),
    riskLevel: approval.riskLevel,
    hasExternalEffect: approval.externalEffect,
    sentinelReview: approval.sentinelReview || 'No Sentinel review recorded.',
    requestedAt: Date.parse(approval.createdAt) || Date.now(),
    resolvedAt: approval.decidedAt ? Date.parse(approval.decidedAt) : null,
  }));
  const perAgentUsage = { ...initialState.budget.perAgentUsage };
  for (const usage of snapshot.budget.perAgent) {
    perAgentUsage[usage.agentId] = usage.usage;
  }
  const agents = { ...initialAgents };
  for (const agent of snapshot.agents) {
    const known = agents[agent.id];
    agents[agent.id] = {
      ...known,
      name: agent.name,
      role: agent.role,
      state: normalizeAgentState(agent.status),
      activeTaskId: agent.currentTaskId,
    };
  }
  return {
    runtimeState: snapshot.runtime.status,
    workdayClock: {
      ...initialState.workdayClock,
      isWithinWorkHours: snapshot.workday.insideWorkday,
      phase: snapshot.workday.phase,
    },
    agents,
    tasks,
    approvals,
    activeMeeting: null,
    budget: {
      dailyLimit: snapshot.budget.companyDailyLimit || initialState.budget.dailyLimit,
      currentUsage: snapshot.budget.companyUsage || 0,
      perAgentUsage,
      warningThreshold: 0.5,
    },
    dailyReport: snapshot.publicDailyReport
      ? {
          day: initialState.workdayClock.day,
          date: snapshot.publicDailyReport.date,
          completedTasks: snapshot.publicDailyReport.completed.length,
          blockedTasks: snapshot.publicDailyReport.blocked.length,
          pendingApprovals: approvals.filter((approval) => approval.status === 'pending').length,
          budgetUsage: snapshot.budget.companyUsage || 0,
          budgetLimit: snapshot.budget.companyDailyLimit || initialState.budget.dailyLimit,
          sentinelRisks: snapshot.publicDailyReport.risksAndLessons,
          founderQuestions: snapshot.publicDailyReport.humanTasks.length > 0
            ? snapshot.publicDailyReport.humanTasks.map((task) => task.publicSummary)
            : [snapshot.publicDailyReport.emptyState?.humanTasks || 'No public human tasks pending.'],
          nextActions: snapshot.publicDailyReport.nextLikelyWork,
          efficiency: tasks.length > 0 ? Math.round((tasks.filter((task) => task.status === 'completed').length / tasks.length) * 100) : 100,
        }
      : snapshot.reports[0]
      ? {
          day: initialState.workdayClock.day,
          date: snapshot.reports[0].date,
          completedTasks: tasks.filter((task) => task.status === 'completed').length,
          blockedTasks: tasks.filter((task) => task.status === 'blocked').length,
          pendingApprovals: approvals.filter((approval) => approval.status === 'pending').length,
          budgetUsage: snapshot.budget.companyUsage || 0,
          budgetLimit: snapshot.budget.companyDailyLimit || initialState.budget.dailyLimit,
          sentinelRisks: approvals
            .filter((approval) => approval.riskLevel === 'high' || approval.riskLevel === 'critical')
            .map((approval) => `${approval.requesterId}: ${approval.action} (${approval.riskLevel})`),
          founderQuestions: [snapshot.reports[0].summary],
          nextActions: ['Atlas will route founder actions through Telegram when real-world blockers appear.'],
          efficiency: tasks.length > 0 ? Math.round((tasks.filter((task) => task.status === 'completed').length / tasks.length) * 100) : 100,
        }
      : null,
    timeline: snapshotToTimelineEvents(snapshot),
    dataSourceMode: 'snapshot',
    dataSourceStatus: 'ready',
    dataSourceLabel: snapshot.audience === 'founder' ? 'Founder snapshot' : 'Public Observer Mode',
    dataSourceError: null,
    snapshotMetadata: {
      schemaVersion: snapshot.schemaVersion,
      generatedAt: snapshot.generatedAt,
      sourceLabel: snapshot.source?.label || 'TSF snapshot',
      auditVerified: snapshot.audit.verified,
      lastAuditSequence: snapshot.audit.lastSequence,
      queueBlockedMissingAdapter: snapshot.executionQueue.filter((item) => item.status === 'blocked_missing_adapter').length,
      autonomousWorkdayStatus: snapshot.autonomousWorkday?.status || 'not_started',
      autonomousWorkdaySummary: snapshot.autonomousWorkday?.summary || 'No autonomous workday started today.',
      schedulerStatus: snapshot.scheduler?.status || 'not_started',
      lastCheckpointAt: snapshot.scheduler?.lastCheckpointAt || null,
      nextCheckpoint: snapshot.scheduler?.nextCheckpoint || null,
      workdayWindow: snapshot.scheduler?.workdayWindow || '10:00-16:00 Europe/Paris',
      deploymentState: snapshot.deploymentSummary?.latestState || 'not_started',
      deploymentSummary: snapshot.deploymentSummary
        ? `${snapshot.deploymentSummary.summary} Health: ${snapshot.deploymentSummary.backendHealthPublicStatus}.`
        : 'No public deployment activity yet.',
    },
  };
}

function snapshotTaskToTask(task: SnapshotTask) {
  return {
    id: task.id,
    title: task.title,
    description: task.plainEnglishSummary || task.objective,
    status: normalizeTaskStatus(task.status),
    assignedTo: task.assignedAgentId,
    createdAt: Date.parse(task.createdAt) || Date.now(),
    startedAt: null,
    completedAt: task.status === 'completed' ? Date.parse(task.updatedAt) || null : null,
    priority: normalizePriority(task.riskLevel),
    estimatedCost: task.budgetLimit || 0,
    actualCost: 0,
  };
}

function normalizeTaskStatus(status: string): TaskStatus {
  if (status === 'accepted' || status === 'assigned') return 'assigned';
  if (status === 'cancelled' || status === 'failed') return status;
  if (
    status === 'proposed' ||
    status === 'in_progress' ||
    status === 'review_required' ||
    status === 'approval_required' ||
    status === 'completed' ||
    status === 'blocked'
  ) {
    return status;
  }
  return 'proposed';
}

function normalizeApprovalStatus(status: string): ApprovalStatus {
  if (
    status === 'pending' ||
    status === 'approved' ||
    status === 'denied' ||
    status === 'expired' ||
    status === 'cancelled' ||
    status === 'executed' ||
    status === 'failed'
  ) {
    return status;
  }
  return 'pending';
}

function normalizeAgentState(status: string): AgentState {
  if (
    status === 'idle' ||
    status === 'planning' ||
    status === 'researching' ||
    status === 'building' ||
    status === 'reviewing' ||
    status === 'drafting' ||
    status === 'meeting' ||
    status === 'blocked' ||
    status === 'approval_required' ||
    status === 'reporting' ||
    status === 'paused'
  ) {
    return status;
  }
  return 'idle';
}

function normalizePriority(risk: RiskLevel): 'low' | 'medium' | 'high' {
  if (risk === 'critical' || risk === 'high') return 'high';
  if (risk === 'medium') return 'medium';
  return 'low';
}
