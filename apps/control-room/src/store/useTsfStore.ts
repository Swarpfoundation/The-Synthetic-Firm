import { create } from 'zustand';
import type { AgentId, RuntimeState, TsfState } from '@/types/tsf';
import { initialState } from '@/mocks/tsf-state';
import { createEventStream, type GeneratedEvent } from '@/mocks/tsf-events';
import { loadControlRoomDataSource } from '@/adapters/controlRoomDataSource';
import { subscribeToPublicControlRoomEvents, type ControlRoomSseSubscription } from '@/adapters/controlRoomSseClient';
import {
  processEvent,
  approveApproval,
  denyApproval,
  setRuntimeState,
  advanceClock,
  startNewDay,
} from '@/utils/eventReducer';
import { snapshotToState } from '@/utils/snapshotToState';

// ============================================
// Zustand Store for TSF State Management
// ============================================

interface TsfActions {
  initializeDataSource: () => Promise<void>;

  // Event simulation
  startEventSimulation: () => void;
  stopEventSimulation: () => void;
  processGeneratedEvent: (event: GeneratedEvent) => void;

  // Runtime controls
  setRuntimeState: (state: RuntimeState) => void;
  pauseRuntime: () => void;
  resumeRuntime: () => void;
  killRuntime: () => void;

  // Clock
  advanceClock: () => void;
  startNewDay: () => void;

  // Selection
  selectAgent: (agentId: AgentId | null) => void;
  selectRoom: (roomId: string | null) => void;
  setActivePanelTab: (tab: string) => void;

  // Approvals
  approveRequest: (approvalId: string) => void;
  denyRequest: (approvalId: string) => void;

  // Report
  openReportModal: () => void;
  closeReportModal: () => void;

  // Reset
  resetStore: () => void;
}

let eventStreamInstance: ReturnType<typeof createEventStream> | null = null;
let sseSubscription: ControlRoomSseSubscription | null = null;

function isReadOnlyMode(mode: string): boolean {
  return mode !== 'mock';
}

export const useTsfStore = create<TsfState & TsfActions>((set, get) => ({
  ...initialState,

  initializeDataSource: async () => {
    set({ dataSourceStatus: 'loading' });
    try {
      const dataSource = await loadControlRoomDataSource();
      if (dataSource.snapshot) {
        if (eventStreamInstance) {
          eventStreamInstance.stop();
          eventStreamInstance = null;
        }
        if (sseSubscription) {
          sseSubscription.close();
          sseSubscription = null;
        }
        set({
          ...snapshotToState(dataSource.snapshot),
          dataSourceMode: dataSource.mode,
          dataSourceStatus: 'ready',
          dataSourceLabel: dataSource.label,
          eventSimulationActive: false,
        });
        if (dataSource.mode === 'sse' && dataSource.sseUrl) {
          sseSubscription = subscribeToPublicControlRoomEvents(
            (snapshot) => {
              set({
                ...snapshotToState(snapshot),
                dataSourceMode: 'sse',
                dataSourceStatus: 'ready',
                dataSourceLabel: 'Public Observer Mode',
              });
            },
            (message) => {
              set({
                dataSourceStatus: 'error',
                dataSourceError: message,
              });
            },
          );
        }
        return;
      }
      set({
        ...initialState,
        dataSourceMode: 'mock',
        dataSourceStatus: 'ready',
        dataSourceLabel: dataSource.label,
        dataSourceError: null,
      });
      get().startEventSimulation();
    } catch (error) {
      const configuredMode = import.meta.env.VITE_TSF_CONTROL_ROOM_DATA_SOURCE;
      set({
        dataSourceStatus: 'error',
        dataSourceError: error instanceof Error ? error.message : 'Snapshot load failed',
        dataSourceMode: configuredMode === 'sse' ? 'sse' : configuredMode === 'snapshot' ? 'snapshot' : 'api',
        dataSourceLabel: 'Public Observer Mode',
      });
    }
  },

  // Event simulation
  startEventSimulation: () => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    if (eventStreamInstance) {
      eventStreamInstance.stop();
    }
    if (sseSubscription) {
      sseSubscription.close();
      sseSubscription = null;
    }
    eventStreamInstance = createEventStream((event) => {
      const state = get();
      if (state.runtimeState !== 'active') return;
      get().processGeneratedEvent(event);
    });
    eventStreamInstance.start(4000);
    set({ eventSimulationActive: true });
  },

  stopEventSimulation: () => {
    if (eventStreamInstance) {
      eventStreamInstance.stop();
    }
    set({ eventSimulationActive: false });
  },

  processGeneratedEvent: (event) => {
    const state = get();
    if (state.runtimeState !== 'active' || isReadOnlyMode(state.dataSourceMode)) return;
    const updates = processEvent(state, event);
    set(updates);
  },

  // Runtime controls
  setRuntimeState: (newState) => {
    const state = get();
    const updates = setRuntimeState(state, newState);
    set(updates);
  },

  pauseRuntime: () => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    const state = get();
    const updates = setRuntimeState(state, 'paused');
    set(updates);
    if (eventStreamInstance) eventStreamInstance.stop();
  },

  resumeRuntime: () => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    const state = get();
    const updates = setRuntimeState(state, 'active');
    set(updates);
    if (eventStreamInstance) eventStreamInstance.start(4000);
  },

  killRuntime: () => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    const state = get();
    const updates = setRuntimeState(state, 'killed');
    set(updates);
    if (eventStreamInstance) eventStreamInstance.stop();
  },

  // Clock
  advanceClock: () => {
    const state = get();
    const updates = advanceClock(state);
    set(updates);
  },

  startNewDay: () => {
    const state = get();
    const updates = startNewDay(state);
    set(updates);
  },

  // Selection
  selectAgent: (agentId) => {
    set({ selectedAgentId: agentId, selectedRoomId: null });
    if (agentId) {
      set({ activePanelTab: 'agents' });
    }
  },

  selectRoom: (roomId) => {
    set({ selectedRoomId: roomId, selectedAgentId: null });
    if (roomId) {
      set({ activePanelTab: 'agents' });
    }
  },

  setActivePanelTab: (tab) => set({ activePanelTab: tab }),

  // Approvals
  approveRequest: (approvalId) => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    const state = get();
    const updates = approveApproval(state, approvalId);
    set(updates);
  },

  denyRequest: (approvalId) => {
    if (isReadOnlyMode(get().dataSourceMode)) return;
    const state = get();
    const updates = denyApproval(state, approvalId);
    set(updates);
  },

  // Report
  openReportModal: () => set({ isReportModalOpen: true }),
  closeReportModal: () => set({ isReportModalOpen: false }),

  // Reset
  resetStore: () => {
    if (eventStreamInstance) {
      eventStreamInstance.stop();
      eventStreamInstance = null;
    }
    if (sseSubscription) {
      sseSubscription.close();
      sseSubscription = null;
    }
    set(initialState);
  },
}));
