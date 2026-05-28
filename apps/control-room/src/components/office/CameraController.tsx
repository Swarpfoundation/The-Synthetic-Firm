import { useRef, useEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useTsfStore } from '@/store/useTsfStore';

// Room camera targets
const ROOM_TARGETS: Record<string, { pos: [number, number, number]; lookAt: [number, number, number] }> = {
  'atlas-office': { pos: [-6, 10, -2], lookAt: [-8, 0, -8] },
  'scout-intel': { pos: [2, 10, -2], lookAt: [0, 0, -8] },
  'forge-lab': { pos: [10, 10, -2], lookAt: [8, 0, -8] },
  'meeting-room': { pos: [5, 12, 5], lookAt: [0, 0, 0] },
  'pulse-desk': { pos: [-6, 10, 4], lookAt: [-10, 0, 0] },
  'task-board': { pos: [14, 10, 4], lookAt: [10, 0, 0] },
  'sentinel-sec': { pos: [-6, 10, 14], lookAt: [-8, 0, 8] },
  'server-core': { pos: [4, 10, 14], lookAt: [0, 0, 8] },
  'approval-chamber': { pos: [10, 10, 14], lookAt: [8, 0, 8] },
};

const AGENT_OFFSETS: Record<string, [number, number, number]> = {
  atlas: [-8, 0, -8],
  scout: [0, 0, -8],
  forge: [8, 0, -8],
  pulse: [-10, 0, 0],
  sentinel: [-8, 0, 8],
};

export function CameraController() {
  const { camera } = useThree();
  const selectedRoomId = useTsfStore((s) => s.selectedRoomId);
  const selectedAgentId = useTsfStore((s) => s.selectedAgentId);
  const runtimeState = useTsfStore((s) => s.runtimeState);

  const targetPos = useRef(new THREE.Vector3(20, 25, 25));
  const targetLook = useRef(new THREE.Vector3(0, 0, 0));
  const currentLook = useRef(new THREE.Vector3(0, 0, 0));

  // Reset camera when runtime is killed
  useEffect(() => {
    if (runtimeState === 'killed') {
      targetPos.current.set(25, 30, 30);
      targetLook.current.set(0, 0, 0);
    }
  }, [runtimeState]);

  // Update target when selection changes
  useEffect(() => {
    if (selectedRoomId && ROOM_TARGETS[selectedRoomId]) {
      const t = ROOM_TARGETS[selectedRoomId];
      targetPos.current.set(...t.pos);
      targetLook.current.set(...t.lookAt);
    } else if (selectedAgentId && AGENT_OFFSETS[selectedAgentId]) {
      const offset = AGENT_OFFSETS[selectedAgentId];
      targetPos.current.set(offset[0] + 4, 8, offset[2] + 4);
      targetLook.current.set(offset[0], 1, offset[2]);
    } else {
      // Default overview
      targetPos.current.set(20, 25, 25);
      targetLook.current.set(0, 0, 0);
    }
  }, [selectedRoomId, selectedAgentId]);

  useFrame((_, delta) => {
    const lerpFactor = 1 - Math.pow(0.02, delta);

    // Smooth camera position
    camera.position.lerp(targetPos.current, lerpFactor * 0.5);

    // Smooth look-at target
    currentLook.current.lerp(targetLook.current, lerpFactor * 0.5);
    camera.lookAt(currentLook.current);
  });

  return null;
}
