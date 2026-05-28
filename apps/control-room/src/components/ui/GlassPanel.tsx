import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface GlassPanelProps {
  children: ReactNode;
  className?: string;
  noPadding?: boolean;
  borderColor?: string;
}

export function GlassPanel({ children, className, noPadding, borderColor }: GlassPanelProps) {
  return (
    <div
      className={cn(
        'rounded-lg backdrop-blur-md',
        'bg-[#111827]/80 border',
        noPadding ? '' : 'p-4',
        className
      )}
      style={{
        borderColor: borderColor || '#1F2937',
      }}
    >
      {children}
    </div>
  );
}
