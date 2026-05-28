// ============================================
// Workday Clock Utilities
// ============================================

export const TSF_WORKDAY_TIMEZONE = 'Europe/Paris';

export function addMinutes(time: string, minutes: number): string {
  const [h, m] = time.split(':').map(Number);
  const totalMinutes = h * 60 + m + minutes;
  const newH = Math.floor(totalMinutes / 60);
  const newM = totalMinutes % 60;
  return `${String(newH).padStart(2, '0')}:${String(newM).padStart(2, '0')}`;
}

export function isWithinWorkHours(time: string): boolean {
  return time >= '10:00' && time < '16:00';
}

export function getWorkdayPhase(time: string): 'planning' | 'execution' | 'review' | 'report' | 'closed' {
  if (time < '10:00') return 'closed';
  if (time < '11:00') return 'planning';
  if (time < '15:00') return 'execution';
  if (time < '16:00') return 'review';
  return 'report';
}

export function getPhaseLabel(phase: string): string {
  const labels: Record<string, string> = {
    planning: 'PLANNING',
    execution: 'EXECUTION',
    review: 'REVIEW',
    report: 'REPORT',
    closed: 'CLOSED',
  };
  return labels[phase] || phase.toUpperCase();
}

export function getParisClockLabel(): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: TSF_WORKDAY_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date());
}

export function formatTimeUntilEnd(time: string): string {
  const [h, m] = time.split(':').map(Number);
  const endH = 16;
  const endM = 0;
  const currentMinutes = h * 60 + m;
  const endMinutes = endH * 60 + endM;
  const diff = Math.max(0, endMinutes - currentMinutes);
  const diffH = Math.floor(diff / 60);
  const diffM = diff % 60;
  return `${diffH}h ${diffM}m remaining`;
}
