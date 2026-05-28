import type { ControlRoomSnapshot } from '@/types/controlRoomSnapshot';
import { getConfiguredApiBaseUrl, validatePublicSnapshot } from './controlRoomApiClient';

export interface ControlRoomSseSubscription {
  close: () => void;
}

export function getPublicSseUrl(baseUrl = getConfiguredApiBaseUrl()): string {
  return `${baseUrl}/api/public/control-room/events`;
}

export function subscribeToPublicControlRoomEvents(
  onSnapshot: (snapshot: ControlRoomSnapshot) => void,
  onError: (message: string) => void,
  baseUrl = getConfiguredApiBaseUrl(),
): ControlRoomSseSubscription {
  const source = new EventSource(getPublicSseUrl(baseUrl));
  source.addEventListener('snapshot', (event) => {
    try {
      const snapshot = JSON.parse((event as MessageEvent).data) as ControlRoomSnapshot;
      validatePublicSnapshot(snapshot);
      onSnapshot(snapshot);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'SSE snapshot parse failed');
    }
  });
  source.onerror = () => {
    onError('Public progress SSE connection interrupted');
  };
  return {
    close: () => source.close(),
  };
}
