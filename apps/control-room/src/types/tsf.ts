// ============================================
// TSF Core Type Definitions
// ============================================

export type AgentId = 'atlas' | 'scout' | 'forge' | 'pulse' | 'sentinel';

export type AgentState =
  | 'idle'
  | 'planning'
  | 'researching'
  | 'building'
  | 'reviewing'
  | 'drafting'
  | 'meeting'
  | 'blocked'
  | 'approval_required'
  | 'reporting'
  | 'paused';

export type RuntimeState = 'active' | 'paused' | 'killed';

export type TaskStatus =
  | 'proposed'
  | 'accepted'
  | 'assigned'
  | 'in_progress'
  | 'review_required'
  | 'approval_required'
  | 'completed'
  | 'blocked'
  | 'cancelled'
  | 'failed';

export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'expired' | 'cancelled' | 'executed' | 'failed';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type WorkdayPhase = 'planning' | 'execution' | 'review' | 'report' | 'closed';

export type EventType =
  | 'task.created'
  | 'task.assigned'
  | 'task.started'
  | 'task.blocked'
  | 'task.review_required'
  | 'task.completed'
  | 'approval.requested'
  | 'approval.approved'
  | 'approval.denied'
  | 'message.sent'
  | 'meeting.started'
  | 'meeting.ended'
  | 'budget.warning'
  | 'budget.exceeded'
  | 'runtime.paused'
  | 'runtime.resumed'
  | 'runtime.killed'
  | 'daily_report.generated'
  | 'agent.state_changed';

export interface Agent {
  id: AgentId;
  name: string;
  role: string;
  state: AgentState;
  activeTaskId: string | null;
  avatar: string; // Lucide icon name
  color: string; // accent color
  position: { x: number; y: number };
  defaultPosition: { x: number; y: number };
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  assignedTo: AgentId | null;
  createdAt: number; // timestamp
  startedAt: number | null;
  completedAt: number | null;
  priority: 'low' | 'medium' | 'high';
  estimatedCost: number;
  actualCost: number;
}

export interface Approval {
  id: string;
  taskId: string;
  requesterId: AgentId;
  action: string;
  description: string;
  status: ApprovalStatus;
  riskLevel: RiskLevel;
  hasExternalEffect: boolean;
  sentinelReview: string;
  requestedAt: number;
  resolvedAt: number | null;
}

export interface Meeting {
  id: string;
  topic: string;
  participantIds: AgentId[];
  startedAt: number | null;
  endedAt: number | null;
  isActive: boolean;
}

export interface Budget {
  dailyLimit: number;
  currentUsage: number;
  perAgentUsage: Record<AgentId, number>;
  warningThreshold: number; // 0.5, 0.8, 0.95
}

export interface DailyReport {
  day: number;
  date: string;
  completedTasks: number;
  blockedTasks: number;
  pendingApprovals: number;
  budgetUsage: number;
  budgetLimit: number;
  sentinelRisks: string[];
  founderQuestions: string[];
  nextActions: string[];
  efficiency: number;
}

export interface TimelineEvent {
  id: string;
  type: EventType;
  agentId: AgentId | null;
  message: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface WorkdayClock {
  currentTime: string; // "HH:MM"
  isWithinWorkHours: boolean;
  phase: WorkdayPhase;
  day: number;
}

export interface OfficeRoom {
  id: string;
  name: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  agentId?: AgentId;
}

export interface TsfState {
  // Runtime
  runtimeState: RuntimeState;
  workdayClock: WorkdayClock;

  // Agents
  agents: Record<AgentId, Agent>;

  // Tasks
  tasks: Task[];

  // Approvals
  approvals: Approval[];

  // Meetings
  activeMeeting: Meeting | null;

  // Budget
  budget: Budget;

  // Daily Report
  dailyReport: DailyReport | null;

  // Event Timeline
  timeline: TimelineEvent[];

  // UI State
  selectedAgentId: AgentId | null;
  selectedRoomId: string | null;
  activePanelTab: string;
  isReportModalOpen: boolean;
  eventSimulationActive: boolean;
  dataSourceMode: 'mock' | 'snapshot' | 'api' | 'sse';
  dataSourceStatus: 'idle' | 'loading' | 'ready' | 'error';
  dataSourceLabel: string;
  dataSourceError: string | null;
  snapshotMetadata: {
    schemaVersion: string | null;
    generatedAt: string | null;
    sourceLabel: string | null;
    auditVerified: boolean | null;
    lastAuditSequence: number | null;
    queueBlockedMissingAdapter: number;
    autonomousWorkdayStatus: string | null;
    autonomousWorkdaySummary: string | null;
    schedulerStatus: string | null;
    lastCheckpointAt: string | null;
    nextCheckpoint: string | null;
    workdayWindow: string | null;
    deploymentState: string | null;
    deploymentSummary: string | null;
  };
}
