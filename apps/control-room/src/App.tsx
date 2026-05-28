import { Component, lazy, useEffect, useRef, Suspense, type ReactNode } from 'react';
import { useTsfStore } from '@/store/useTsfStore';
import { RuntimeHeader } from '@/components/panels/RuntimeHeader';
import { FounderControlPanel } from '@/components/panels/FounderControlPanel';
import { ReportModal } from '@/components/panels/ReportModal';
import './App.css';

const Scene3D = lazy(() => import('@/components/office/Scene').then((module) => ({ default: module.Scene3D })));

class SceneErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  override render() {
    if (this.state.failed) return <SceneFallback />;
    return this.props.children;
  }
}

// Loading fallback for 3D scene
function SceneLoader() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#05080F]">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-[#06B6D4] border-t-transparent" />
        <p className="text-xs tracking-[0.2em] text-[#475569]">INITIALIZING 3D SCENE</p>
      </div>
    </div>
  );
}

function SceneFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#05080F]">
      <div className="grid w-[min(760px,70vw)] grid-cols-3 gap-3 opacity-90">
        {['Atlas', 'Scout', 'Forge', 'Pulse', 'Sentinel', 'Core'].map((label) => (
          <div key={label} className="h-28 border border-[#1e293b] bg-[#0a0e17]/80 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[#06B6D4]">{label}</p>
            <div className="mt-4 h-1 w-full bg-[#1e293b]">
              <div className="h-1 w-1/2 bg-[#06B6D4]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function App() {
  const runtimeState = useTsfStore((s) => s.runtimeState);
  const dataSourceMode = useTsfStore((s) => s.dataSourceMode);
  const initializeDataSource = useTsfStore((s) => s.initializeDataSource);
  const stopEventSimulation = useTsfStore((s) => s.stopEventSimulation);
  const advanceClock = useTsfStore((s) => s.advanceClock);

  const clockIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load configured data source
  useEffect(() => {
    void initializeDataSource();
    return () => stopEventSimulation();
  }, [initializeDataSource, stopEventSimulation]);

  // Clock ticker
  useEffect(() => {
    if (runtimeState === 'active' && dataSourceMode === 'mock') {
      clockIntervalRef.current = setInterval(() => advanceClock(), 600);
    } else {
      if (clockIntervalRef.current) clearInterval(clockIntervalRef.current);
    }
    return () => {
      if (clockIntervalRef.current) clearInterval(clockIntervalRef.current);
    };
  }, [runtimeState, dataSourceMode, advanceClock]);

  return (
    <div
      className="relative h-screen w-screen overflow-hidden bg-[#05080F]"
      data-tsf-public-progress-window="true"
      data-tsf-read-only="true"
    >
      {/* 3D Scene — fills the background */}
      <div className="absolute inset-0 z-0">
        <SceneErrorBoundary>
          <Suspense fallback={<SceneLoader />}>
            <Scene3D />
          </Suspense>
        </SceneErrorBoundary>
      </div>

      {/* HUD Overlay */}
      <div className="pointer-events-none absolute inset-0 z-10">
        <div className="pointer-events-none absolute left-4 top-[62px] z-20 rounded border border-[#06B6D4]/20 bg-[#05080F]/75 px-3 py-2 text-[9px] uppercase tracking-[0.16em] text-[#94A3B8] backdrop-blur">
          <span className="font-semibold text-[#06B6D4]">Public Progress Window</span>
          <span className="mx-2 text-[#334155]">/</span>
          <span>Read-only public view</span>
          <span className="mx-2 text-[#334155]">/</span>
          <span>Real TSF runtime data only</span>
        </div>

        {/* Runtime Header — top bar */}
        <RuntimeHeader />

        {/* Public progress panel — right sidebar */}
        <FounderControlPanel />

        {/* Bottom-left corner info */}
        <div className="pointer-events-auto absolute bottom-3 left-3">
          <p className="text-[9px] tracking-[0.15em] text-[#1e293b]">
            TSF PROGRESS WINDOW v2.0 — THREE.JS RENDERER
          </p>
        </div>
      </div>

      {/* Report Modal */}
      <ReportModal />
    </div>
  );
}

export default App;
