import type { ControlRoomSnapshot } from '@/types/controlRoomSnapshot';

const DEFAULT_API_BASE_URL = 'http://localhost:8787';

export function getConfiguredApiBaseUrl(): string {
  return (import.meta.env.VITE_TSF_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, '');
}

export function getConfiguredAudience(): 'public' {
  return 'public';
}

export async function fetchPublicControlRoomSnapshot(baseUrl = getConfiguredApiBaseUrl()): Promise<ControlRoomSnapshot> {
  const response = await fetch(`${baseUrl}/api/public/control-room/snapshot`, {
    method: 'GET',
    credentials: 'omit',
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`Public progress API returned HTTP ${response.status}`);
  }
  const snapshot = (await response.json()) as ControlRoomSnapshot;
  validatePublicSnapshot(snapshot);
  return snapshot;
}

export function validatePublicSnapshot(snapshot: ControlRoomSnapshot): void {
  if (snapshot.schemaVersion !== 'control-room.v1') {
    throw new Error('Unsupported public progress snapshot schema');
  }
  if (snapshot.audience && snapshot.audience !== 'public') {
    throw new Error('Public progress API returned a non-public snapshot');
  }
  if (snapshot.truthfulness && snapshot.truthfulness !== 'real_runtime_data_only') {
    throw new Error('Public progress API returned an unsupported truthfulness mode');
  }
}
