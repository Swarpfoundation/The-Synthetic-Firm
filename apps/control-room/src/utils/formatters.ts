// ============================================
// Formatting Utilities
// ============================================

export function formatCurrency(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function formatPercentage(value: number, total: number): string {
  if (total === 0) return '0%';
  return `${Math.round((value / total) * 100)}%`;
}

export function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatTimeShort(time: string): string {
  return time;
}

export function truncateText(text: string, maxLength: number = 50): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

export function capitalizeFirst(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function getRiskColor(risk: string): string {
  const colors: Record<string, string> = {
    low: '#10B981',
    medium: '#F59E0B',
    high: '#EF4444',
    critical: '#DC2626',
  };
  return colors[risk] || '#9CA3AF';
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    active: '#10B981',
    paused: '#F59E0B',
    killed: '#EF4444',
    idle: '#6B7280',
    planning: '#06B6D4',
    researching: '#8B5CF6',
    building: '#F59E0B',
    reviewing: '#EC4899',
    drafting: '#3B82F6',
    meeting: '#F9FAFB',
    blocked: '#EF4444',
    approval_required: '#F59E0B',
    reporting: '#10B981',
    pending: '#F59E0B',
    approved: '#10B981',
    denied: '#EF4444',
    proposed: '#6B7280',
    in_progress: '#3B82F6',
    review_required: '#EC4899',
    completed: '#10B981',
  };
  return colors[status] || '#9CA3AF';
}
