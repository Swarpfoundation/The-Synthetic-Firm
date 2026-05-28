import { cn } from '@/lib/utils';
import { getRiskColor } from '@/utils/formatters';
import { Shield, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react';

interface RiskBadgeProps {
  level: string;
  className?: string;
  showIcon?: boolean;
}

const riskIcons: Record<string, React.ReactNode> = {
  low: <ShieldCheck className="h-3 w-3" />,
  medium: <Shield className="h-3 w-3" />,
  high: <ShieldAlert className="h-3 w-3" />,
  critical: <ShieldX className="h-3 w-3" />,
};

export function RiskBadge({ level, className, showIcon = true }: RiskBadgeProps) {
  const color = getRiskColor(level);

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
        className
      )}
      style={{
        backgroundColor: `${color}20`,
        color: color,
        border: `1px solid ${color}40`,
      }}
    >
      {showIcon && riskIcons[level] || <Shield className="h-3 w-3" />}
      {level}
    </span>
  );
}
