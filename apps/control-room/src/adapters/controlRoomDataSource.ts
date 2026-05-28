import type { ControlRoomSnapshot } from '@/types/controlRoomSnapshot';
import { fetchPublicControlRoomSnapshot, getConfiguredApiBaseUrl } from './controlRoomApiClient';
import { getPublicSseUrl } from './controlRoomSseClient';

export type ControlRoomDataSourceMode = 'mock' | 'snapshot' | 'api' | 'sse';

export interface ControlRoomDataSourceResult {
  mode: ControlRoomDataSourceMode;
  label: string;
  snapshot: ControlRoomSnapshot | null;
  sseUrl: string | null;
}

const DEFAULT_SNAPSHOT_URL = '/control-room-snapshot.json';

export function getConfiguredDataSourceMode(): ControlRoomDataSourceMode {
  const raw = import.meta.env.VITE_TSF_CONTROL_ROOM_DATA_SOURCE;
  if (raw === 'snapshot' || raw === 'api' || raw === 'sse') return raw;
  return 'mock';
}

export function getConfiguredSnapshotUrl(): string {
  return import.meta.env.VITE_TSF_CONTROL_ROOM_SNAPSHOT_URL || DEFAULT_SNAPSHOT_URL;
}

export async function loadControlRoomDataSource(): Promise<ControlRoomDataSourceResult> {
  const mode = getConfiguredDataSourceMode();
  if (mode === 'mock') {
    return { mode, label: 'Development Mock Mode', snapshot: null, sseUrl: null };
  }
  if (mode === 'api' || mode === 'sse') {
    const snapshot = await fetchPublicControlRoomSnapshot();
    return {
      mode,
      label: mode === 'sse' ? 'Public Observer Mode' : 'Public API Mode',
      snapshot,
      sseUrl: mode === 'sse' ? getPublicSseUrl(getConfiguredApiBaseUrl()) : null,
    };
  }
  const url = getConfiguredSnapshotUrl();
  const response = await fetch(url, {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Snapshot load failed with HTTP ${response.status}`);
  }
  const snapshot = (await response.json()) as ControlRoomSnapshot;
  if (snapshot.schemaVersion !== 'control-room.v1') {
    throw new Error('Unsupported public progress snapshot schema');
  }
  return {
    mode,
    label: 'Real Snapshot Mode',
    snapshot,
    sseUrl: null,
  };
}
