import type { AgentId, ApprovalStatus, RiskLevel, RuntimeState, WorkdayPhase } from './tsf';

export interface ControlRoomSnapshot {
  schemaVersion: 'control-room.v1';
  audience?: 'public' | 'founder';
  dataMode?: 'real_snapshot';
  truthfulness?: 'real_runtime_data_only';
  generatedAt: string;
  source?: {
    label: string;
    mode: 'read_only';
  };
  runtime: {
    status: RuntimeState;
    summary: string;
  };
  workday: {
    timezone: 'Europe/Paris';
    insideWorkday: boolean;
    phase: WorkdayPhase;
    summary?: string;
  };
  autonomousWorkday?: {
    status: 'not_started' | 'active' | 'paused' | 'closing' | 'closed' | 'failed';
    summary: string;
    cycleCount: number;
    workdayId: string | null;
    atlasPlanId: string | null;
    publicReportId: string | null;
    privateReportId: string | null;
    lastCycleAt?: string | null;
  };
  scheduler?: {
    status: 'not_started' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped';
    lastCheckpointAt: string | null;
    lastCheckpointType: string | null;
    nextCheckpoint: string | null;
    workdayWindow: string;
    summary: string;
  };
  storage?: {
    storeBackendPublicStatus: 'sqlite_preview' | 'postgres_ready' | 'postgres_unavailable';
    backend?: string;
    repositoryMode?: string | null;
    connected?: boolean;
    schemaVersion?: number | null;
    summary: string;
  };
  storeBackendPublicStatus?: 'sqlite_preview' | 'postgres_ready' | 'postgres_unavailable';
  schedulerPublicStatus?: string;
  lastSchedulerCheckpoint?: string | null;
  lastAtlasReportAt?: string | null;
  publicEmptyStateReason?: string | null;
  deploymentSummary?: {
    latestState: string;
    latestTarget: string | null;
    latestEnvironment: string | null;
    latestPreviewUrl: string | null;
    backendHealthPublicStatus: string;
    deploymentBlockedReason: string | null;
    lastCheckedAt?: string | null;
    credentialStatus?: Record<
      string,
      {
        provider: string;
        enabled: boolean;
        cliAvailable: boolean;
        credentialPresent: boolean;
        credentialSource: string;
        projectLinked: boolean;
        targetConfigured: boolean;
        safeSummary: string;
        missingRequirements: string[];
        humanTaskRequired: boolean;
        lastCheckedAt: string;
      }
    >;
    summary: string;
    history: Array<{
      deploymentId: string;
      target: string;
      environment: string;
      state: string;
      previewUrl: string | null;
      publicSummary: string;
      blockedReason: string | null;
      createdAt: string;
      updatedAt: string;
    }>;
  };
  agents: SnapshotAgent[];
  tasks: SnapshotTask[];
  messages: {
    count: number;
    recent: SnapshotMessage[];
  };
  approvals: SnapshotApproval[];
  executionQueue: SnapshotExecutionQueueItem[];
  budget: SnapshotBudget;
  reports: SnapshotReport[];
  publicDailyReport?: SnapshotPublicDailyReport;
  privateFounderReport?: Record<string, unknown> | null;
  humanTasks?: SnapshotHumanTask[];
  humanTaskSummary?: {
    pendingCount: number;
    blockedCount: number;
    doneCount: number;
    publicSummaries: Array<{
      humanTaskId: string;
      status: string;
      publicSummary: string;
    }>;
    summary: string;
  };
  agentProgressSummary?: Array<{
    agentId: AgentId;
    name: string;
    completedCount: number;
    inProgressCount: number;
    blockedCount: number;
    summary: string;
  }>;
  audit: {
    verified: boolean;
    lastSequence: number;
    summary: string;
  };
  events: SnapshotEvent[];
}

export interface SnapshotPublicDailyReport {
  type: 'public_daily_report';
  title: string;
  date: string;
  runtime: RuntimeState;
  workdayPhase: WorkdayPhase;
  whatHappenedToday: string[];
  completed: string[];
  inProgress: string[];
  blocked: string[];
  humanTasks: Array<{
    status: string;
    publicSummary: string;
  }>;
  notes: string[];
  risksAndLessons: string[];
  nextLikelyWork: string[];
  truthfulness: string;
  emptyState?: {
    completed?: string;
    humanTasks?: string;
  };
}

export interface SnapshotHumanTask {
  humanTaskId: string;
  requestedByAgentId: AgentId;
  relatedTaskId: string | null;
  priority: string;
  riskLevel: RiskLevel;
  publicSummary: string;
  status: 'pending' | 'done' | 'blocked' | 'cancelled';
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

export interface SnapshotAgent {
  id: AgentId;
  name: string;
  role: string;
  status: string;
  currentTaskId: string | null;
  currentTaskTitle: string | null;
  attentionLevel: 'normal' | 'warning' | 'blocked' | 'approval_required';
}

export interface SnapshotTask {
  id: string;
  title: string;
  objective: string;
  assignedAgentId: AgentId | null;
  createdByAgentId: AgentId;
  riskLevel: RiskLevel;
  status: string;
  externalEffect: boolean;
  budgetLimit: number | null;
  maxSteps: number | null;
  createdAt: string;
  updatedAt: string;
  plainEnglishSummary: string;
}

export interface SnapshotApproval {
  id: string;
  taskId: string;
  agentId: AgentId;
  requestedAction: string;
  riskLevel: RiskLevel;
  externalEffect: boolean;
  plainEnglishRequest: string;
  sentinelReview: string;
  status: ApprovalStatus;
  createdAt: string;
  decidedAt: string | null;
}

export interface SnapshotMessage {
  id: string;
  senderAgentId: AgentId;
  recipientAgentId: AgentId | null;
  channel: string | null;
  taskId: string | null;
  messageType: string;
  summary: string;
  createdAt: string;
}

export interface SnapshotExecutionQueueItem {
  id: string;
  taskId: string;
  agentId: AgentId;
  action: string;
  externalEffect: boolean;
  approvalId: string | null;
  status: string;
  resultSummary: string;
  createdAt: string;
  updatedAt: string;
}

export interface SnapshotBudget {
  companyDailyLimit: number;
  companyUsage: number;
  loopSteps: number;
  toolCalls: number;
  warningThresholds: number[];
  perAgent: Array<{
    agentId: AgentId;
    dailyLimit: number;
    usage: number;
    loopSteps: number;
    toolCalls: number;
  }>;
}

export interface SnapshotReport {
  id: string;
  date: string;
  summary: string;
  createdAt: string;
}

export interface SnapshotEvent {
  id: string;
  type: string;
  agentId: AgentId | null;
  message: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}
