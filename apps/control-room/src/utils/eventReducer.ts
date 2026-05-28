import type { AgentId, AgentState, Approval, Budget, DailyReport, Meeting, RuntimeState, Task, TaskStatus, TimelineEvent, TsfState, WorkdayPhase } from '@/types/tsf';
import type { GeneratedEvent } from '@/mocks/tsf-events';
import { addMinutes, getWorkdayPhase, isWithinWorkHours } from './workday';

// ============================================
// Event Reducer - Processes events and updates state
// ============================================

export function processEvent(state: TsfState, event: GeneratedEvent): Partial<TsfState> {
  const updates: Partial<TsfState> = {};

  // Always add to timeline
  const timelineEntry: TimelineEvent = {
    ...event.timeline,
    id: `tl-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  };
  updates.timeline = [timelineEntry, ...state.timeline].slice(0, 100);

  // Process specific event types
  switch (event.type) {
    case 'task.created':
      if (event.task) {
        const newTask: Task = {
          ...event.task,
          status: 'proposed',
          assignedTo: null,
          createdAt: Date.now(),
          startedAt: null,
          completedAt: null,
          actualCost: 0,
        };
        updates.tasks = [...state.tasks, newTask];
      }
      break;

    case 'task.assigned':
      if (event.timeline.metadata?.taskId || event.task) {
        const taskId = (event.timeline.metadata?.taskId as string) || event.task?.id;
        if (taskId) {
          updates.tasks = state.tasks.map((t) =>
            t.id === taskId
              ? { ...t, assignedTo: event.timeline.agentId as AgentId, status: 'in_progress' as TaskStatus }
              : t
          );
        }
      }
      break;

    case 'task.started':
      if (event.agentUpdate) {
        const agentId = event.agentUpdate.agentId as AgentId;
        const newState = event.agentUpdate.newState as AgentState;
        updates.agents = {
          ...state.agents,
          [agentId]: {
            ...state.agents[agentId],
            state: newState,
          },
        };
      }
      break;

    case 'task.blocked':
      if (event.agentUpdate) {
        const agentId = event.agentUpdate.agentId as AgentId;
        updates.agents = {
          ...state.agents,
          [agentId]: {
            ...state.agents[agentId],
            state: 'blocked' as AgentState,
          },
        };
      }
      break;

    case 'task.completed':
      if (event.agentUpdate) {
        const agentId = event.agentUpdate.agentId as AgentId;
        const cost = Math.floor(Math.random() * 80) + 20;
        updates.agents = {
          ...state.agents,
          [agentId]: {
            ...state.agents[agentId],
            state: 'idle' as AgentState,
            activeTaskId: null,
          },
        };
        updates.budget = {
          ...state.budget,
          currentUsage: state.budget.currentUsage + cost,
          perAgentUsage: {
            ...state.budget.perAgentUsage,
            [agentId]: state.budget.perAgentUsage[agentId] + cost,
          },
        };
      }
      break;

    case 'approval.requested':
      if (event.approval) {
        const newApproval: Approval = {
          ...event.approval,
          status: 'pending',
          requestedAt: Date.now(),
          resolvedAt: null,
        };
        updates.approvals = [...state.approvals, newApproval];
        // Update requester agent state
        if (event.approval.requesterId) {
          updates.agents = {
            ...(updates.agents || state.agents),
            [event.approval.requesterId]: {
              ...state.agents[event.approval.requesterId],
              state: 'approval_required',
            },
          };
        }
      }
      break;

    case 'meeting.started':
      if (event.meeting) {
        const newMeeting: Meeting = {
          ...event.meeting,
          startedAt: Date.now(),
          endedAt: null,
          isActive: true,
        };
        updates.activeMeeting = newMeeting;
        // Move participating agents to meeting room center
        const meetingCenter = { x: 500, y: 450 };
        const updatedAgents = { ...(updates.agents || state.agents) };
        event.meeting.participantIds.forEach((pid, idx) => {
          const offset = idx * 30;
          updatedAgents[pid] = {
            ...state.agents[pid],
            state: 'meeting',
            position: {
              x: meetingCenter.x + offset - (event.meeting!.participantIds.length * 15),
              y: meetingCenter.y,
            },
          };
        });
        updates.agents = updatedAgents;
      }
      break;

    case 'meeting.ended':
      if (state.activeMeeting) {
        updates.activeMeeting = {
          ...state.activeMeeting,
          endedAt: Date.now(),
          isActive: false,
        };
        // Return agents to default positions
        const updatedAgents = { ...(updates.agents || state.agents) };
        state.activeMeeting.participantIds.forEach((pid) => {
          updatedAgents[pid] = {
            ...updatedAgents[pid],
            state: 'idle',
            position: state.agents[pid].defaultPosition,
          };
        });
        updates.agents = updatedAgents;
      }
      break;

    case 'budget.warning':
      // Budget warnings are logged to timeline only
      break;

    case 'message.sent':
      // Messages are logged to timeline only
      break;

    case 'agent.state_changed':
      if (event.agentUpdate) {
        const agentId = event.agentUpdate.agentId as AgentId;
        const newState = event.agentUpdate.newState as AgentState;
        updates.agents = {
          ...state.agents,
          [agentId]: {
            ...state.agents[agentId],
            state: newState,
          },
        };
      }
      break;

    default:
      break;
  }

  return updates;
}

// ---- Direct Actions (user-triggered) ----

export function approveApproval(state: TsfState, approvalId: string): Partial<TsfState> {
  const approval = state.approvals.find((a) => a.id === approvalId);
  if (!approval || approval.status !== 'pending') return {};

  const updatedApprovals = state.approvals.map((a) =>
    a.id === approvalId
      ? { ...a, status: 'approved' as const, resolvedAt: Date.now() }
      : a
  );

  // Update requester agent state back to idle
  const updatedAgents = {
    ...state.agents,
    [approval.requesterId]: {
      ...state.agents[approval.requesterId],
      state: 'idle' as AgentState,
    },
  };

  // Deduct budget
  const cost = Math.floor(Math.random() * 100) + 30;
  const updatedBudget: Budget = {
    ...state.budget,
    currentUsage: state.budget.currentUsage + cost,
    perAgentUsage: {
      ...state.budget.perAgentUsage,
      [approval.requesterId]: state.budget.perAgentUsage[approval.requesterId] + cost,
    },
  };

  const timelineEntry: TimelineEvent = {
    id: `tl-${Date.now()}`,
    type: 'approval.approved',
    agentId: approval.requesterId,
    message: `Approval ${approvalId} approved: ${approval.action}`,
    timestamp: Date.now(),
  };

  return {
    approvals: updatedApprovals,
    agents: updatedAgents,
    budget: updatedBudget,
    timeline: [timelineEntry, ...state.timeline].slice(0, 100),
  };
}

export function denyApproval(state: TsfState, approvalId: string): Partial<TsfState> {
  const approval = state.approvals.find((a) => a.id === approvalId);
  if (!approval || approval.status !== 'pending') return {};

  const updatedApprovals = state.approvals.map((a) =>
    a.id === approvalId
      ? { ...a, status: 'denied' as const, resolvedAt: Date.now() }
      : a
  );

  // Update requester agent state back to idle
  const updatedAgents = {
    ...state.agents,
    [approval.requesterId]: {
      ...state.agents[approval.requesterId],
      state: 'idle' as AgentState,
    },
  };

  const timelineEntry: TimelineEvent = {
    id: `tl-${Date.now()}`,
    type: 'approval.denied',
    agentId: approval.requesterId,
    message: `Approval ${approvalId} denied: ${approval.action}`,
    timestamp: Date.now(),
  };

  return {
    approvals: updatedApprovals,
    agents: updatedAgents,
    timeline: [timelineEntry, ...state.timeline].slice(0, 100),
  };
}

export function setRuntimeState(state: TsfState, newState: RuntimeState): Partial<TsfState> {
  const updates: Partial<TsfState> = {
    runtimeState: newState,
  };

  if (newState === 'paused') {
    // Set all agents to paused state
    const pausedAgents = { ...state.agents };
    Object.keys(pausedAgents).forEach((key) => {
      const id = key as AgentId;
      pausedAgents[id] = { ...pausedAgents[id], state: 'paused' as AgentState };
    });
    updates.agents = pausedAgents;
    updates.eventSimulationActive = false;
  } else if (newState === 'killed') {
    const killedAgents = { ...state.agents };
    Object.keys(killedAgents).forEach((key) => {
      const id = key as AgentId;
      killedAgents[id] = { ...killedAgents[id], state: 'idle' as AgentState };
    });
    updates.agents = killedAgents;
    updates.eventSimulationActive = false;
  } else if (newState === 'active') {
    // Resume agents to idle
    const resumedAgents = { ...state.agents };
    Object.keys(resumedAgents).forEach((key) => {
      const id = key as AgentId;
      if (resumedAgents[id].state === 'paused') {
        resumedAgents[id] = { ...resumedAgents[id], state: 'idle' as AgentState };
      }
    });
    updates.agents = resumedAgents;
    updates.eventSimulationActive = true;
  }

  const timelineEntry: TimelineEvent = {
    id: `tl-${Date.now()}`,
    type: newState === 'paused' ? 'runtime.paused' : newState === 'killed' ? 'runtime.killed' : 'runtime.resumed',
    agentId: null,
    message: `Runtime ${newState}`,
    timestamp: Date.now(),
  };
  updates.timeline = [timelineEntry, ...state.timeline].slice(0, 100);

  return updates;
}

export function advanceClock(state: TsfState): Partial<TsfState> {
  const newTime = addMinutes(state.workdayClock.currentTime, 1); // 1 simulated minute per tick
  const phase = getWorkdayPhase(newTime);
  const isWithinHours = isWithinWorkHours(newTime);

  const updates: Partial<TsfState> = {
    workdayClock: {
      ...state.workdayClock,
      currentTime: newTime,
      isWithinWorkHours: isWithinHours,
      phase: phase as WorkdayPhase,
    },
  };

  // Check budget thresholds
  const budgetPct = state.budget.currentUsage / state.budget.dailyLimit;
  if (budgetPct >= 1.0 && state.budget.warningThreshold < 1.0) {
    updates.budget = { ...state.budget, warningThreshold: 1.0 };
  } else if (budgetPct >= 0.95 && state.budget.warningThreshold < 0.95) {
    updates.budget = { ...state.budget, warningThreshold: 0.95 };
  } else if (budgetPct >= 0.8 && state.budget.warningThreshold < 0.8) {
    updates.budget = { ...state.budget, warningThreshold: 0.8 };
  } else if (budgetPct >= 0.5 && state.budget.warningThreshold < 0.5) {
    updates.budget = { ...state.budget, warningThreshold: 0.5 };
  }

  // End of day
  if (newTime >= '16:00' && state.workdayClock.currentTime < '16:00') {
    // Generate daily report
    const completedTasks = state.tasks.filter((t) => t.status === 'completed').length;
    const blockedTasks = state.tasks.filter((t) => t.status === 'blocked').length;
    const pendingApprovals = state.approvals.filter((a) => a.status === 'pending').length;

    const report: DailyReport = {
      day: state.workdayClock.day,
      date: new Date().toISOString().split('T')[0],
      completedTasks,
      blockedTasks,
      pendingApprovals,
      budgetUsage: state.budget.currentUsage,
      budgetLimit: state.budget.dailyLimit,
      sentinelRisks: state.approvals
        .filter((a) => a.riskLevel === 'high' || a.riskLevel === 'critical')
        .map((a) => `${a.requesterId}: ${a.action} (${a.riskLevel})`),
      founderQuestions: [
        `Review ${completedTasks} completed tasks for quality`,
        `Address ${blockedTasks} blocked tasks`,
        pendingApprovals > 0 ? `Resolve ${pendingApprovals} pending approvals` : 'All approvals resolved',
      ],
      nextActions: [
        'Start next workday planning',
        'Review budget allocation',
        'Check Sentinel audit logs',
      ],
      efficiency: state.tasks.length > 0 ? Math.round((completedTasks / state.tasks.length) * 100) : 100,
    };

    updates.dailyReport = report;
    updates.isReportModalOpen = true;
  }

  return updates;
}

export function startNewDay(state: TsfState): Partial<TsfState> {
  return {
    workdayClock: {
      currentTime: '10:00',
      isWithinWorkHours: true,
      phase: 'planning',
      day: state.workdayClock.day + 1,
    },
    tasks: [],
    approvals: state.approvals.filter((a) => a.status === 'pending'),
    dailyReport: null,
    isReportModalOpen: false,
    budget: {
      ...state.budget,
      currentUsage: 0,
      perAgentUsage: {
        atlas: 0,
        scout: 0,
        forge: 0,
        pulse: 0,
        sentinel: 0,
      },
      warningThreshold: 0,
    },
    agents: Object.fromEntries(
      Object.entries(state.agents).map(([id, agent]) => [
        id,
        { ...agent, state: 'idle' as AgentState, activeTaskId: null, position: agent.defaultPosition },
      ])
    ) as Record<AgentId, typeof state.agents.atlas>,
  };
}
