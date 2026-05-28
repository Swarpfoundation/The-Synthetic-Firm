import { cn } from '@/lib/utils';
import { getStatusColor } from '@/utils/formatters';

interface StatusPillProps {
  status: string;
  className?: string;
  size?: 'sm' | 'md';
}

export function StatusPill({ status, className, size = 'sm' }: StatusPillProps) {
  const color = getStatusColor(status);

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium uppercase tracking-wider',
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1 text-xs',
        className
      )}
      style={{
        backgroundColor: `${color}20`,
        color: color,
        border: `1px solid ${color}40`,
      }}
    >
      <span
        className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full animate-pulse"
        style={{ backgroundColor: color }}
      />
      {status.replace(/_/g, ' ')}
    </span>
  );
}
