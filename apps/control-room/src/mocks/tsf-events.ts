import type { AgentId, EventType, RiskLevel, TimelineEvent } from '@/types/tsf';

// ============================================
// TSF Mock Event Stream Generator
// ============================================

let eventCounter = 0;
let taskCounter = 0;

function generateId(prefix: string): string {
  eventCounter++;
  return `${prefix}-${Date.now()}-${eventCounter}`;
}

function generateTaskId(): string {
  taskCounter++;
  return `task-${Date.now()}-${taskCounter}`;
}

const AGENTS: AgentId[] = ['atlas', 'scout', 'forge', 'pulse', 'sentinel'];

const TASK_TEMPLATES: Record<AgentId, string[]> = {
  atlas: [
    'Review daily priorities',
    'Coordinate team standup',
    'Assess project risks',
    'Approve strategic initiatives',
    'Review Sentinel audit report',
  ],
  scout: [
    'Analyze market trends',
    'Research competitor landscape',
    'Identify partnership opportunities',
    'Gather user feedback data',
    'Evaluate emerging technologies',
  ],
  forge: [
    'Implement dashboard feature',
    'Fix API integration bug',
    'Deploy staging build',
    'Refactor authentication module',
    'Write unit tests for core logic',
  ],
  pulse: [
    'Draft outreach campaign',
    'Analyze conversion metrics',
    'Update pricing page',
    'Schedule demo calls',
    'Optimize onboarding flow',
  ],
  sentinel: [
    'Review security policies',
    'Audit access permissions',
    'Run compliance check',
    'Scan for vulnerabilities',
    'Document risk assessment',
  ],
};

const MEETING_TOPICS = [
  'Sprint Planning Review',
  'Security Incident Response',
  'Product Roadmap Alignment',
  'Budget Allocation Discussion',
  'Client Demo Preparation',
  'Team Retrospective',
];

const RISK_LEVELS: RiskLevel[] = ['low', 'medium', 'high', 'critical'];

function randomAgent(): AgentId {
  return AGENTS[Math.floor(Math.random() * AGENTS.length)];
}

function randomItem<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomRisk(): RiskLevel {
  const weights = [0.4, 0.35, 0.2, 0.05];
  const rand = Math.random();
  let cum = 0;
  for (let i = 0; i < weights.length; i++) {
    cum += weights[i];
    if (rand < cum) return RISK_LEVELS[i];
  }
  return 'low';
}

// ---- Event Generators ----

export interface GeneratedEvent {
  type: EventType;
  timeline: TimelineEvent;
  task?: {
    id: string;
    title: string;
    description: string;
    assignedTo: AgentId;
    priority: 'low' | 'medium' | 'high';
    estimatedCost: number;
  };
  approval?: {
    id: string;
    taskId: string;
    requesterId: AgentId;
    action: string;
    description: string;
    riskLevel: RiskLevel;
    hasExternalEffect: boolean;
    sentinelReview: string;
  };
  meeting?: {
    id: string;
    topic: string;
    participantIds: AgentId[];
  };
  agentUpdate?: {
    agentId: AgentId;
    newState: string;
  };
  budgetWarning?: {
    threshold: number;
    message: string;
  };
}

export function generateTaskCreatedEvent(): GeneratedEvent {
  const agent = randomAgent();
  const title = randomItem(TASK_TEMPLATES[agent]);
  const taskId = generateTaskId();

  return {
    type: 'task.created',
    timeline: {
      id: generateId('evt'),
      type: 'task.created',
      agentId: agent,
      message: `${agent} created task: "${title}"`,
      timestamp: Date.now(),
    },
    task: {
      id: taskId,
      title,
      description: `Task initiated by ${agent} for operational execution.`,
      assignedTo: agent,
      priority: randomItem(['low', 'medium', 'high']),
      estimatedCost: Math.floor(Math.random() * 100) + 20,
    },
  };
}

export function generateTaskAssignedEvent(taskId: string, agentId: AgentId): GeneratedEvent {
  return {
    type: 'task.assigned',
    timeline: {
      id: generateId('evt'),
      type: 'task.assigned',
      agentId,
      message: `Task ${taskId} assigned to ${agentId}`,
      timestamp: Date.now(),
    },
  };
}

export function generateTaskStartedEvent(taskId: string, agentId: AgentId): GeneratedEvent {
  return {
    type: 'task.started',
    timeline: {
      id: generateId('evt'),
      type: 'task.started',
      agentId,
      message: `${agentId} started working on ${taskId}`,
      timestamp: Date.now(),
    },
    agentUpdate: {
      agentId,
      newState: agentId === 'forge' ? 'building' : agentId === 'scout' ? 'researching' : agentId === 'sentinel' ? 'reviewing' : 'planning',
    },
  };
}

export function generateTaskBlockedEvent(taskId: string, agentId: AgentId): GeneratedEvent {
  return {
    type: 'task.blocked',
    timeline: {
      id: generateId('evt'),
      type: 'task.blocked',
      agentId,
      message: `${agentId} blocked on ${taskId}: dependency missing`,
      timestamp: Date.now(),
    },
    agentUpdate: {
      agentId,
      newState: 'blocked',
    },
  };
}

export function generateTaskCompletedEvent(taskId: string, agentId: AgentId): GeneratedEvent {
  return {
    type: 'task.completed',
    timeline: {
      id: generateId('evt'),
      type: 'task.completed',
      agentId,
      message: `${agentId} completed ${taskId}`,
      timestamp: Date.now(),
    },
    agentUpdate: {
      agentId,
      newState: 'idle',
    },
  };
}

export function generateApprovalRequestedEvent(taskId: string, agentId: AgentId): GeneratedEvent {
  const risk = randomRisk();
  const actions = [
    'Queue production deployment review',
    'Draft client message for founder review',
    'Request external API access review',
    'Propose database migration plan',
    'Draft public statement for founder review',
    'Request budget exception review',
  ];
  const action = randomItem(actions);

  return {
    type: 'approval.requested',
    timeline: {
      id: generateId('evt'),
      type: 'approval.requested',
      agentId,
      message: `${agentId} requests approval: ${action}`,
      timestamp: Date.now(),
    },
    approval: {
      id: generateId('apr'),
      taskId,
      requesterId: agentId,
      action,
      description: `${agentId} needs authorization to execute: "${action}". This action has external visibility and requires founder oversight.`,
      riskLevel: risk,
      hasExternalEffect: risk === 'high' || risk === 'critical',
      sentinelReview: `Sentinel analysis: Risk level ${risk.toUpperCase()}. ${risk === 'high' || risk === 'critical' ? 'External impact detected. Recommend careful review.' : 'Standard operational risk. Proceed with caution.'}`,
    },
  };
}

export function generateMeetingStartedEvent(): GeneratedEvent {
  const topic = randomItem(MEETING_TOPICS);
  const numParticipants = Math.floor(Math.random() * 3) + 2;
  const participants: AgentId[] = [];
  const shuffled = [...AGENTS].sort(() => Math.random() - 0.5);
  for (let i = 0; i < numParticipants; i++) {
    participants.push(shuffled[i]);
  }

  return {
    type: 'meeting.started',
    timeline: {
      id: generateId('evt'),
      type: 'meeting.started',
      agentId: null,
      message: `Meeting started: "${topic}" with ${participants.join(', ')}`,
      timestamp: Date.now(),
    },
    meeting: {
      id: generateId('mtg'),
      topic,
      participantIds: participants,
    },
  };
}

export function generateMeetingEndedEvent(meetingId: string): GeneratedEvent {
  return {
    type: 'meeting.ended',
    timeline: {
      id: generateId('evt'),
      type: 'meeting.ended',
      agentId: null,
      message: `Meeting ${meetingId} concluded`,
      timestamp: Date.now(),
    },
  };
}

export function generateBudgetWarningEvent(threshold: number): GeneratedEvent {
  const messages: Record<number, string> = {
    0.5: 'Budget at 50% - monitoring usage',
    0.8: 'Budget at 80% - consider cost reduction',
    0.95: 'Budget at 95% - critical threshold reached',
    1.0: 'Budget exhausted - operations halted',
  };

  return {
    type: 'budget.warning',
    timeline: {
      id: generateId('evt'),
      type: 'budget.warning',
      agentId: null,
      message: messages[threshold] || `Budget warning at ${Math.round(threshold * 100)}%`,
      timestamp: Date.now(),
    },
    budgetWarning: {
      threshold,
      message: messages[threshold] || `Budget warning at ${Math.round(threshold * 100)}%`,
    },
  };
}

export function generateMessageSentEvent(): GeneratedEvent {
  const agent = randomAgent();
  const messages = [
    'Update received from external partner',
    'Client feedback processed',
    'New data available for analysis',
    'Deployment pipeline ready',
    'Security scan completed',
  ];

  return {
    type: 'message.sent',
    timeline: {
      id: generateId('evt'),
      type: 'message.sent',
      agentId: agent,
      message: `${agent}: ${randomItem(messages)}`,
      timestamp: Date.now(),
    },
  };
}

export function generateAgentStateChangeEvent(agentId: AgentId, newState: string): GeneratedEvent {
  return {
    type: 'agent.state_changed',
    timeline: {
      id: generateId('evt'),
      type: 'agent.state_changed',
      agentId,
      message: `${agentId} state changed to ${newState}`,
      timestamp: Date.now(),
    },
    agentUpdate: {
      agentId,
      newState,
    },
  };
}

// ---- Event Stream Orchestrator ----

export type EventCallback = (event: GeneratedEvent) => void;

export class EventStream {
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private callback: EventCallback;
  private active: boolean = false;
  private eventFrequency: number = 3000; // ms between events
  private pendingTasks: string[] = [];
  private activeMeetings: string[] = [];

  constructor(callback: EventCallback) {
    this.callback = callback;
  }

  start(frequency: number = 3000) {
    if (this.active) return;
    this.active = true;
    this.eventFrequency = frequency;

    // Immediate first event
    this.tick();

    this.intervalId = setInterval(() => {
      if (this.active) this.tick();
    }, this.eventFrequency);
  }

  stop() {
    this.active = false;
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  setFrequency(frequency: number) {
    this.eventFrequency = frequency;
    if (this.active) {
      this.stop();
      this.start(frequency);
    }
  }

  private tick() {
    const rand = Math.random();

    if (rand < 0.25) {
      // Create a new task
      const evt = generateTaskCreatedEvent();
      this.callback(evt);
      if (evt.task) {
        this.pendingTasks.push(evt.task.id);
        // Auto-assign after short delay
        setTimeout(() => {
          if (evt.task) {
            this.callback(generateTaskAssignedEvent(evt.task.id, evt.task.assignedTo));
            // Start the task
            setTimeout(() => {
              if (evt.task) {
                this.callback(generateTaskStartedEvent(evt.task.id, evt.task.assignedTo));
              }
            }, 1000);
          }
        }, 500);
      }
    } else if (rand < 0.4) {
      // Complete a pending task if any
      if (this.pendingTasks.length > 0) {
        const taskId = this.pendingTasks.shift()!;
        const agent = randomAgent();
        // 30% chance task needs approval
        if (Math.random() < 0.3) {
          this.callback(generateApprovalRequestedEvent(taskId, agent));
        } else {
          this.callback(generateTaskCompletedEvent(taskId, agent));
        }
      } else {
        // Send a message instead
        this.callback(generateMessageSentEvent());
      }
    } else if (rand < 0.55) {
      // Start a meeting
      if (this.activeMeetings.length === 0) {
        const evt = generateMeetingStartedEvent();
        this.callback(evt);
        if (evt.meeting) {
          this.activeMeetings.push(evt.meeting.id);
          // Auto-end meeting after 8 seconds
          setTimeout(() => {
            this.callback(generateMeetingEndedEvent(evt.meeting!.id));
            this.activeMeetings = this.activeMeetings.filter((id) => id !== evt.meeting!.id);
          }, 8000);
        }
      } else {
        this.callback(generateMessageSentEvent());
      }
    } else if (rand < 0.7) {
      // Block a task
      if (this.pendingTasks.length > 0) {
        const taskId = this.pendingTasks[Math.floor(Math.random() * this.pendingTasks.length)];
        const agent = randomAgent();
        this.callback(generateTaskBlockedEvent(taskId, agent));
      } else {
        this.callback(generateMessageSentEvent());
      }
    } else {
      // Generic message
      this.callback(generateMessageSentEvent());
    }
  }

  reset() {
    this.stop();
    this.pendingTasks = [];
    this.activeMeetings = [];
    eventCounter = 0;
    taskCounter = 0;
  }
}

// Factory for creating event streams
export function createEventStream(callback: EventCallback): EventStream {
  return new EventStream(callback);
}
