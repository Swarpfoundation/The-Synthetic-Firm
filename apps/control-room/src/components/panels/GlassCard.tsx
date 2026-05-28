import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  borderColor?: string;
  hover?: boolean;
}

export function GlassCard({ children, className, borderColor, hover }: GlassCardProps) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-lg border border-[#1e293b]/50 bg-[#0f172a]/60 p-3 backdrop-blur-sm',
        hover && 'transition-all hover:border-[#334155] hover:bg-[#1e293b]/60',
        className
      )}
      style={borderColor ? { borderLeftColor: borderColor, borderLeftWidth: '2px' } : undefined}
    >
      {/* Subtle scan line effect */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.02]"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, #06B6D4 2px, #06B6D4 4px)',
          backgroundSize: '100% 4px',
        }}
      />
      {children}
    </div>
  );
}
