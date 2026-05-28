import { useTsfStore } from '@/store/useTsfStore';
import { GlassCard } from './GlassCard';
import { StatusPill } from '@/components/ui/StatusPill';
import {
  Crown,
  Search,
  Hammer,
  TrendingUp,
  Shield,
  Briefcase,
  AlertCircle,
} from 'lucide-react';

const iconMap: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  Crown,
  Search,
  Hammer,
  TrendingUp,
  Shield,
};

export function AgentInspector() {
  const agents = useTsfStore((s) => s.agents);
  const selectedAgentId = useTsfStore((s) => s.selectedAgentId);
  const selectAgent = useTsfStore((s) => s.selectAgent);
  const tasks = useTsfStore((s) => s.tasks);
  const budget = useTsfStore((s) => s.budget);

  if (selectedAgentId) {
    const agent = agents[selectedAgentId];
    const agentTasks = tasks.filter((t) => t.assignedTo === agent.id);
    const activeTask = agentTasks.find((t) => t.status === 'in_progress');
    const completedTasks = agentTasks.filter((t) => t.status === 'completed');
    const agentBudget = budget.perAgentUsage[agent.id];
    const IconComponent = iconMap[agent.avatar] || Crown;

    return (
      <div className="space-y-2.5">
        <button
          onClick={() => selectAgent(null)}
          className="text-[10px] uppercase tracking-wider text-[#475569] transition-colors hover:text-[#e2e8f0]"
        >
          ← Back to all agents
        </button>

        <GlassCard borderColor={agent.color}>
          <div className="flex items-center gap-3">
            <div
              className="flex h-11 w-11 items-center justify-center rounded-lg"
              style={{ backgroundColor: `${agent.color}15`, border: `1.5px solid ${agent.color}40` }}
            >
              <IconComponent className="h-5 w-5" style={{ color: agent.color }} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-[#e2e8f0]">{agent.name}</h3>
              <p className="text-[10px] text-[#475569]">{agent.role}</p>
            </div>
          </div>
          <div className="mt-2">
            <StatusPill status={agent.state} />
          </div>
          {activeTask && (
            <div className="mt-2.5 rounded bg-[#020617]/50 p-2">
              <div className="flex items-center gap-1.5">
                <Briefcase className="h-3 w-3 text-[#06B6D4]" />
                <span className="text-[9px] uppercase tracking-wider text-[#475569]">Active Task</span>
              </div>
              <p className="mt-1 text-[11px] text-[#e2e8f0]">{activeTask.title}</p>
            </div>
          )}
          {agent.state === 'blocked' && (
            <div className="mt-2 flex items-center gap-1.5 rounded bg-[#EF4444]/10 p-2">
              <AlertCircle className="h-3 w-3 text-[#EF4444]" />
              <span className="text-[10px] text-[#EF4444]">Agent blocked — needs intervention</span>
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <h4 className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Stats</h4>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded bg-[#020617]/50 p-2">
              <p className="text-[8px] uppercase tracking-wider text-[#475569]">Completed</p>
              <p className="mt-0.5 font-mono text-base font-semibold text-[#10B981]">{completedTasks.length}</p>
            </div>
            <div className="rounded bg-[#020617]/50 p-2">
              <p className="text-[8px] uppercase tracking-wider text-[#475569]">Active</p>
              <p className="mt-0.5 font-mono text-base font-semibold text-[#3B82F6]">
                {agentTasks.filter((t) => t.status === 'in_progress').length}
              </p>
            </div>
            <div className="rounded bg-[#020617]/50 p-2">
              <p className="text-[8px] uppercase tracking-wider text-[#475569]">Budget Used</p>
              <p className="mt-0.5 font-mono text-base font-semibold" style={{ color: agentBudget > 200 ? '#F59E0B' : '#e2e8f0' }}>
                ${agentBudget}
              </p>
            </div>
            <div className="rounded bg-[#020617]/50 p-2">
              <p className="text-[8px] uppercase tracking-wider text-[#475569]">Total Tasks</p>
              <p className="mt-0.5 font-mono text-base font-semibold text-[#e2e8f0]">{agentTasks.length}</p>
            </div>
          </div>
        </GlassCard>

        {agentTasks.length > 0 && (
          <GlassCard>
            <h4 className="mb-2 text-[9px] font-semibold uppercase tracking-wider text-[#475569]">Task History</h4>
            <div className="max-h-40 space-y-1 overflow-y-auto">
              {agentTasks.map((task) => (
                <div key={task.id} className="flex items-center justify-between rounded bg-[#020617]/50 px-2 py-1.5">
                  <span className="truncate text-[10px] text-[#e2e8f0]">{task.title}</span>
                  <StatusPill status={task.status} size="sm" />
                </div>
              ))}
            </div>
          </GlassCard>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <h3 className="text-[9px] font-semibold uppercase tracking-wider text-[#475569]">All Agents</h3>
      {Object.values(agents).map((agent) => {
        const IconComponent = iconMap[agent.avatar] || Crown;
        const isSelected = selectedAgentId === agent.id;
        const agentTaskCount = tasks.filter((t) => t.assignedTo === agent.id).length;

        return (
          <button key={agent.id} onClick={() => selectAgent(agent.id)} className="w-full text-left">
            <GlassCard hover className={isSelected ? 'border-[#06B6D4]/40' : ''}>
              <div className="flex items-center gap-2.5">
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${agent.color}12`, border: `1px solid ${agent.color}35` }}
                >
                  <IconComponent className="h-4 w-4" style={{ color: agent.color }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-[#e2e8f0]">{agent.name}</span>
                    <StatusPill status={agent.state} size="sm" />
                  </div>
                  <p className="truncate text-[9px] text-[#475569]">{agent.role}</p>
                  {agentTaskCount > 0 && (
                    <p className="text-[8px] text-[#475569]">{agentTaskCount} tasks</p>
                  )}
                </div>
              </div>
            </GlassCard>
          </button>
        );
      })}
    </div>
  );
}
