import { motion, AnimatePresence } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import { StatusPill } from '@/components/ui/StatusPill';
import { ClipboardList, AlertTriangle } from 'lucide-react';

const columns = [
  { id: 'proposed', label: 'Proposed', color: '#475569' },
  { id: 'in_progress', label: 'In Progress', color: '#3B82F6' },
  { id: 'review_required', label: 'Review', color: '#EC4899' },
  { id: 'approval_required', label: 'Approval', color: '#F59E0B' },
  { id: 'completed', label: 'Completed', color: '#10B981' },
  { id: 'blocked', label: 'Blocked', color: '#EF4444' },
];

export function TaskBoard() {
  const tasks = useTsfStore((s) => s.tasks);

  if (tasks.length === 0) {
    return (
      <GlassCard className="flex flex-col items-center justify-center py-10">
        <ClipboardList className="h-7 w-7 text-[#1e293b]" />
        <p className="mt-2 text-[11px] text-[#475569]">No tasks yet</p>
        <p className="text-[9px] text-[#334155]">Waiting for events...</p>
      </GlassCard>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-1.5">
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#e2e8f0]">{tasks.length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Total</p>
        </div>
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#10B981]">{tasks.filter((t) => t.status === 'completed').length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Done</p>
        </div>
        <div className="rounded bg-[#020617]/50 p-1.5 text-center">
          <p className="font-mono text-sm font-semibold text-[#EF4444]">{tasks.filter((t) => t.status === 'blocked').length}</p>
          <p className="text-[8px] uppercase tracking-wider text-[#475569]">Blocked</p>
        </div>
      </div>

      {columns.map((col) => {
        const colTasks = tasks.filter((t) => t.status === col.id);
        if (colTasks.length === 0) return null;
        return (
          <div key={col.id}>
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: col.color }} />
                <span className="text-[9px] font-semibold uppercase tracking-wider" style={{ color: col.color }}>{col.label}</span>
              </div>
              <span className="font-mono text-[9px] text-[#475569]">{colTasks.length}</span>
            </div>
            <div className="space-y-1">
              <AnimatePresence>
                {colTasks.map((task) => (
                  <motion.div key={task.id} layout initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 16 }} transition={{ duration: 0.2 }}>
                    <GlassCard className="py-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[10px] text-[#e2e8f0]">{task.title}</p>
                          <div className="mt-0.5 flex items-center gap-2">
                            <span className="text-[8px] text-[#475569]">{task.assignedTo || 'unassigned'}</span>
                            {task.priority === 'high' && <span className="flex items-center gap-0.5 text-[8px] text-[#EF4444]"><AlertTriangle className="h-2 w-2" /> High</span>}
                          </div>
                        </div>
                        <StatusPill status={task.status} size="sm" />
                      </div>
                    </GlassCard>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>
        );
      })}
    </div>
  );
}
