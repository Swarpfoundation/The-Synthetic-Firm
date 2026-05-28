import { motion, AnimatePresence } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { AgentInspector } from './AgentInspector';
import { TaskBoard } from './TaskBoard';
import { ApprovalInbox } from './ApprovalInbox';
import { BudgetPanel } from './BudgetPanel';
import { DailyReportPanel } from './DailyReportPanel';
import { EventTimeline } from './EventTimeline';
import { ReadOnlyStatusPanel } from './ReadOnlyStatusPanel';
import {
  Users,
  ClipboardList,
  ShieldAlert,
  Wallet,
  FileBarChart,
  ScrollText,
} from 'lucide-react';

const tabs = [
  { id: 'agents', label: 'Agents', icon: Users },
  { id: 'tasks', label: 'Tasks', icon: ClipboardList },
  { id: 'approvals', label: 'Approvals', icon: ShieldAlert },
  { id: 'budget', label: 'Budget', icon: Wallet },
  { id: 'reports', label: 'Reports', icon: FileBarChart },
  { id: 'events', label: 'Events', icon: ScrollText },
];

export function FounderControlPanel() {
  const activePanelTab = useTsfStore((s) => s.activePanelTab);
  const setActivePanelTab = useTsfStore((s) => s.setActivePanelTab);
  const approvals = useTsfStore((s) => s.approvals);
  const pendingCount = approvals.filter((a) => a.status === 'pending').length;

  return (
    <motion.div
      initial={{ x: 400, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.6, delay: 0.3, ease: 'easeOut' }}
      className="pointer-events-auto absolute right-0 top-[56px] z-30 flex h-[calc(100vh-56px)] w-[360px] shrink-0 flex-col border-l border-[#1e293b]/60 bg-[#0a0e17]/80 backdrop-blur-xl"
    >
      {/* Tabs */}
      <div className="flex border-b border-[#1e293b]/60">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activePanelTab === tab.id;
          const showBadge = tab.id === 'approvals' && pendingCount > 0;

          return (
            <button
              key={tab.id}
              onClick={() => setActivePanelTab(tab.id)}
              className="relative flex flex-1 flex-col items-center gap-0.5 py-2 transition-all"
            >
              <div className="relative">
                <Icon
                  className="h-3.5 w-3.5"
                  style={{ color: isActive ? '#06B6D4' : '#475569' }}
                />
                {showBadge && (
                  <span className="absolute -right-2 -top-1 flex h-3 w-3 items-center justify-center rounded-full bg-[#EF4444] text-[7px] font-bold text-white">
                    {pendingCount}
                  </span>
                )}
              </div>
              <span
                className="text-[8px] font-medium uppercase tracking-wider"
                style={{ color: isActive ? '#06B6D4' : '#475569' }}
              >
                {tab.label}
              </span>
              {isActive && (
                <motion.div
                  layoutId="activeTab3d"
                  className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#06B6D4]"
                  transition={{ duration: 0.2 }}
                />
              )}
            </button>
          );
        })}
      </div>

      <ReadOnlyStatusPanel />

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3">
        <AnimatePresence mode="wait">
          <motion.div
            key={activePanelTab}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.15 }}
          >
            {activePanelTab === 'agents' && <AgentInspector />}
            {activePanelTab === 'tasks' && <TaskBoard />}
            {activePanelTab === 'approvals' && <ApprovalInbox />}
            {activePanelTab === 'budget' && <BudgetPanel />}
            {activePanelTab === 'reports' && <DailyReportPanel />}
            {activePanelTab === 'events' && <EventTimeline />}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
