import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stars } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette, ToneMapping } from '@react-three/postprocessing';
import * as THREE from 'three';
import { useTsfStore } from '@/store/useTsfStore';
import { OfficeFloor } from './OfficeFloor';
import { RoomPlatform } from './RoomPlatform';
import { AgentCharacter } from './AgentCharacter';
import { PathwayStrip } from './PathwayStrip';
import { DataFlowParticles } from './DataFlowParticles';
import { MeetingBeam } from './MeetingBeam';
import { ServerRackLights } from './ServerRackLights';
import { ApprovalBeacon } from './ApprovalBeacon';
import { RoomNameLabel } from './RoomNameLabel';
import { CameraController } from './CameraController';

// Room definitions for 3D scene
interface RoomDef {
  id: string;
  name: string;
  agentId?: string;
  pos: [number, number, number];
  size: [number, number];
  color: string;
  labelPos: [number, number, number];
}

const ROOMS: RoomDef[] = [
  { id: 'atlas-office', name: 'ATLAS COMMAND', agentId: 'atlas', pos: [-8, 0, -8], size: [6, 6], color: '#06B6D4', labelPos: [-8, 3.5, -8] },
  { id: 'scout-intel', name: 'SCOUT INTEL', agentId: 'scout', pos: [0, 0, -8], size: [6, 6], color: '#8B5CF6', labelPos: [0, 3.5, -8] },
  { id: 'forge-lab', name: 'FORGE LAB', agentId: 'forge', pos: [8, 0, -8], size: [6, 6], color: '#F59E0B', labelPos: [8, 3.5, -8] },
  { id: 'meeting-room', name: 'MEETING ROOM', pos: [0, 0, 0], size: [8, 8], color: '#E2E8F0', labelPos: [0, 4.5, 0] },
  { id: 'pulse-desk', name: 'PULSE GROWTH', agentId: 'pulse', pos: [-10, 0, 0], size: [5, 5], color: '#10B981', labelPos: [-10, 3, 0] },
  { id: 'task-board', name: 'TASK BOARD', pos: [10, 0, 0], size: [5, 5], color: '#A78BFA', labelPos: [10, 3, 0] },
  { id: 'sentinel-sec', name: 'SENTINEL SECURITY', agentId: 'sentinel', pos: [-8, 0, 8], size: [6, 6], color: '#EF4444', labelPos: [-8, 3.5, 8] },
  { id: 'server-core', name: 'SERVER CORE', pos: [0, 0, 8], size: [6, 6], color: '#06B6D4', labelPos: [0, 3.5, 8] },
  { id: 'approval-chamber', name: 'APPROVAL CHAMBER', pos: [8, 0, 8], size: [5, 5], color: '#F59E0B', labelPos: [8, 3, 8] },
];

interface PathDef {
  from: [number, number, number];
  to: [number, number, number];
  color: string;
}

const PATHWAYS: PathDef[] = [
  { from: [-5, 0.15, -8], to: [-3, 0.15, -8], color: '#374151' },
  { from: [3, 0.15, -8], to: [5, 0.15, -8], color: '#374151' },
  { from: [-8, 0.15, -5], to: [-10, 0.15, -2], color: '#374151' },
  { from: [0, 0.15, -5], to: [0, 0.15, -4], color: '#374151' },
  { from: [8, 0.15, -5], to: [4, 0.15, -4], color: '#374151' },
  { from: [-7.5, 0.15, 0], to: [-4, 0.15, 0], color: '#374151' },
  { from: [-8, 0.15, 5], to: [-8, 0.15, 5], color: '#374151' },
  { from: [0, 0.15, 5], to: [0, 0.15, 4], color: '#374151' },
  { from: [5.5, 0.15, 8], to: [4, 0.15, 4], color: '#374151' },
  { from: [-5, 0.15, 8], to: [-3, 0.15, 8], color: '#374151' },
  { from: [3, 0.15, 8], to: [5.5, 0.15, 8], color: '#374151' },
  { from: [-8, 0.15, 5], to: [-8, 0.15, 5], color: '#374151' },
];

function SceneContent() {
  const agents = useTsfStore((s) => s.agents);
  const runtimeState = useTsfStore((s) => s.runtimeState);
  const activeMeeting = useTsfStore((s) => s.activeMeeting);
  const approvals = useTsfStore((s) => s.approvals);
  const selectedRoomId = useTsfStore((s) => s.selectedRoomId);
  const selectedAgentId = useTsfStore((s) => s.selectedAgentId);
  const selectRoom = useTsfStore((s) => s.selectRoom);
  const selectAgent = useTsfStore((s) => s.selectAgent);

  const hasPendingApprovals = approvals.some((a) => a.status === 'pending');
  const isPaused = runtimeState === 'paused';
  const isKilled = runtimeState === 'killed';

  return (
    <>
      <CameraController />
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.05}
        minDistance={12}
        maxDistance={50}
        maxPolarAngle={Math.PI / 2.1}
        minPolarAngle={0.2}
        target={[0, 0, 0]}
      />

      {/* Environment */}
      <fog attach="fog" args={['#05080F', 20, 70]} />
      <color attach="background" args={['#05080F']} />

      {/* Lighting */}
      <ambientLight intensity={0.04} color="#1e293b" />
      <directionalLight
        position={[-15, 30, -10]}
        intensity={0.15}
        color="#334155"
        castShadow
      />
      <hemisphereLight args={['#0c4a6e', '#05080F', 0.1]} />

      <Stars radius={80} depth={60} count={800} factor={3} saturation={0} fade speed={0.5} />

      <OfficeFloor />

      {PATHWAYS.map((path, i) => (
        <PathwayStrip key={i} start={path.from} end={path.to} color={path.color} />
      ))}

      {ROOMS.map((room) => (
        <group key={room.id}>
          <RoomPlatform
            position={room.pos}
            size={room.size}
            color={room.color}
            name={room.name}
            isSelected={selectedRoomId === room.id}
            isMeetingRoom={room.id === 'meeting-room'}
            isMeetingActive={!!activeMeeting?.isActive && room.id === 'meeting-room'}
            hasPendingApprovals={hasPendingApprovals && room.id === 'approval-chamber'}
            onClick={() => selectRoom(selectedRoomId === room.id ? null : room.id)}
          />
          <RoomNameLabel position={room.labelPos} text={room.name} color={room.color} />
        </group>
      ))}

      <ServerRackLights position={[0, 0.5, 8]} />

      {hasPendingApprovals && <ApprovalBeacon position={[8, 1, 8]} />}

      {activeMeeting?.isActive && (
        <MeetingBeam position={[0, 0.5, 0]} participants={activeMeeting.participantIds} />
      )}

      {Object.values(agents).map((agent) => {
        const room = ROOMS.find((r) => r.agentId === agent.id);
        if (!room) return null;
        return (
          <AgentCharacter
            key={agent.id}
            agent={agent}
            roomPosition={room.pos}
            isSelected={selectedAgentId === agent.id}
            isPaused={isPaused}
            isKilled={isKilled}
            onClick={() => selectAgent(selectedAgentId === agent.id ? null : agent.id)}
          />
        );
      })}

      <DataFlowParticles />

      <EffectComposer>
        <Bloom intensity={0.8} luminanceThreshold={0.2} luminanceSmoothing={0.9} mipmapBlur />
        <Vignette eskil={false} offset={0.1} darkness={0.7} />
        <ToneMapping mode={THREE.ACESFilmicToneMapping} />
      </EffectComposer>
    </>
  );
}

export function Scene3D() {
  return (
    <Canvas
      shadows
      camera={{ position: [20, 25, 25], fov: 50, near: 0.1, far: 500 }}
      gl={{
        antialias: true,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 0.9,
      }}
      style={{ background: '#05080F' }}
    >
      <SceneContent />
    </Canvas>
  );
}
