import type { ControlRoomSnapshot } from '@/types/controlRoomSnapshot';
import type { EventType, TimelineEvent } from '@/types/tsf';

const KNOWN_EVENTS = new Set<EventType>([
  'task.created',
  'task.assigned',
  'task.started',
  'task.blocked',
  'task.review_required',
  'task.completed',
  'approval.requested',
  'approval.approved',
  'approval.denied',
  'message.sent',
  'meeting.started',
  'meeting.ended',
  'budget.warning',
  'budget.exceeded',
  'runtime.paused',
  'runtime.resumed',
  'runtime.killed',
  'daily_report.generated',
  'agent.state_changed',
]);

export function snapshotToTimelineEvents(snapshot: ControlRoomSnapshot): TimelineEvent[] {
  return snapshot.events.map((event) => ({
    id: event.id,
    type: normalizeEventType(event.type),
    agentId: event.agentId,
    message: event.message,
    timestamp: Date.parse(event.timestamp) || Date.now(),
    metadata: event.metadata,
  }));
}

function normalizeEventType(type: string): EventType {
  if (type === 'runtime.active') return 'runtime.resumed';
  if (KNOWN_EVENTS.has(type as EventType)) return type as EventType;
  return 'message.sent';
}
