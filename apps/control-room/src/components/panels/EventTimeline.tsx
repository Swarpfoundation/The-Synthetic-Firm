import { motion } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { formatTimestamp } from '@/utils/formatters';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  MessageSquare,
  Users,
  Play,
  Pause,
  Square,
  FileText,
  Activity,
  ShieldAlert,
} from 'lucide-react';

const eventIcons: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  'task.created': FileText, 'task.assigned': FileText, 'task.started': Play, 'task.blocked': AlertTriangle,
  'task.review_required': ShieldAlert, 'task.completed': CheckCircle, 'approval.requested': ShieldAlert,
  'approval.approved': CheckCircle, 'approval.denied': XCircle, 'message.sent': MessageSquare,
  'meeting.started': Users, 'meeting.ended': Users, 'budget.warning': AlertTriangle,
  'budget.exceeded': AlertTriangle, 'runtime.paused': Pause, 'runtime.resumed': Play,
  'runtime.killed': Square, 'daily_report.generated': FileText, 'agent.state_changed': Activity,
};

const eventColors: Record<string, string> = {
  'task.created': '#06B6D4', 'task.assigned': '#06B6D4', 'task.started': '#3B82F6', 'task.blocked': '#EF4444',
  'task.review_required': '#EC4899', 'task.completed': '#10B981', 'approval.requested': '#F59E0B',
  'approval.approved': '#10B981', 'approval.denied': '#EF4444', 'message.sent': '#8B5CF6',
  'meeting.started': '#e2e8f0', 'meeting.ended': '#475569', 'budget.warning': '#F59E0B',
  'budget.exceeded': '#EF4444', 'runtime.paused': '#F59E0B', 'runtime.resumed': '#10B981',
  'runtime.killed': '#EF4444', 'daily_report.generated': '#06B6D4', 'agent.state_changed': '#8B5CF6',
};

export function EventTimeline() {
  const timeline = useTsfStore((s) => s.timeline);

  if (timeline.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-[#475569]">
        <Activity className="h-7 w-7 text-[#1e293b]" />
        <p className="mt-2 text-[11px]">No events yet</p>
        <p className="text-[9px] text-[#334155]">Events appear as simulation runs</p>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Live Feed</span>
        <span className="font-mono text-[9px] text-[#475569]">{timeline.length} events</span>
      </div>
      <div className="relative space-y-0">
        <div className="absolute left-[13px] top-0 bottom-0 w-px bg-[#1e293b]" />
        {timeline.map((event, index) => {
          const Icon = eventIcons[event.type] || Activity;
          const color = eventColors[event.type] || '#475569';
          const isRecent = index < 3;
          return (
            <motion.div key={event.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.2, delay: index * 0.01 }} className={`relative flex gap-2.5 py-1 ${isRecent ? '' : 'opacity-55'}`}>
              <div className="relative z-10 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-md" style={{ backgroundColor: `${color}12`, border: `1px solid ${color}25` }}>
                <Icon className="h-2.5 w-2.5" style={{ color } as React.CSSProperties} />
              </div>
              <div className="min-w-0 flex-1 pt-0.5">
                <p className="truncate text-[10px] leading-tight text-[#e2e8f0]">{event.message}</p>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="font-mono text-[8px] text-[#475569]">{formatTimestamp(event.timestamp)}</span>
                  <span className="rounded px-1 py-[1px] text-[7px] font-medium uppercase tracking-wider" style={{ backgroundColor: `${color}12`, color }}>{event.type.split('.')[0]}</span>
                  {event.agentId && <span className="text-[8px] text-[#475569]">{event.agentId}</span>}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
