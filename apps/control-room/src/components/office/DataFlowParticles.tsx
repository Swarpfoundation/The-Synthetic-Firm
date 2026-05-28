import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Data packet flowing between rooms
interface DataPacket {
  start: THREE.Vector3;
  end: THREE.Vector3;
  progress: number;
  speed: number;
  color: string;
  size: number;
}

interface PathDef {
  from: [number, number, number];
  to: [number, number, number];
  color: string;
}

const PATHS: PathDef[] = [
  { from: [-8, 0.4, -8], to: [0, 0.4, -8], color: '#8B5CF6' },
  { from: [0, 0.4, -8], to: [8, 0.4, -8], color: '#F59E0B' },
  { from: [-8, 0.4, -8], to: [-10, 0.4, 0], color: '#10B981' },
  { from: [0, 0.4, -8], to: [0, 0.4, 0], color: '#06B6D4' },
  { from: [8, 0.4, -8], to: [0, 0.4, 0], color: '#F59E0B' },
  { from: [-10, 0.4, 0], to: [0, 0.4, 0], color: '#10B981' },
  { from: [0, 0.4, 0], to: [-8, 0.4, 8], color: '#EF4444' },
  { from: [0, 0.4, 0], to: [0, 0.4, 8], color: '#06B6D4' },
  { from: [0, 0.4, 0], to: [8, 0.4, 8], color: '#F59E0B' },
  { from: [-8, 0.4, 8], to: [0, 0.4, 8], color: '#06B6D4' },
  { from: [0, 0.4, 8], to: [8, 0.4, 8], color: '#F59E0B' },
];

export function DataFlowParticles() {
  const groupRef = useRef<THREE.Group>(null);
  const packetsRef = useRef<DataPacket[]>([]);
  const meshRefs = useRef<THREE.Mesh[]>([]);

  // Initialize packets
  useMemo(() => {
    packetsRef.current = PATHS.map((path) => ({
      start: new THREE.Vector3(...path.from),
      end: new THREE.Vector3(...path.to),
      progress: Math.random(),
      speed: 0.1 + Math.random() * 0.15,
      color: path.color,
      size: 0.06 + Math.random() * 0.04,
    }));
  }, []);

  useFrame((state, delta) => {
    if (!groupRef.current) return;

    packetsRef.current.forEach((packet, i) => {
      packet.progress += packet.speed * delta;
      if (packet.progress > 1) {
        packet.progress = 0;
        packet.speed = 0.1 + Math.random() * 0.15;
      }

      const mesh = meshRefs.current[i];
      if (mesh) {
        mesh.position.lerpVectors(packet.start, packet.end, packet.progress);
        // Slight arc
        const arcHeight = Math.sin(packet.progress * Math.PI) * 0.3;
        mesh.position.y = packet.start.y + arcHeight;

        // Pulse opacity based on progress
        const mat = mesh.material as THREE.MeshStandardMaterial;
        const fadeIn = Math.min(packet.progress * 10, 1);
        const fadeOut = Math.min((1 - packet.progress) * 10, 1);
        mat.opacity = Math.min(fadeIn, fadeOut) * 0.8;

        // Emissive pulse
        mat.emissiveIntensity = 0.5 + Math.sin(state.clock.elapsedTime * 5 + i) * 0.3;
      }
    });
  });

  return (
    <group ref={groupRef}>
      {PATHS.map((path, i) => (
        <mesh
          key={i}
          ref={(el) => {
            if (el) meshRefs.current[i] = el;
          }}
          position={path.from}
        >
          <boxGeometry args={[0.08, 0.08, 0.08]} />
          <meshStandardMaterial
            color={path.color}
            emissive={path.color}
            emissiveIntensity={0.6}
            transparent
            opacity={0.8}
          />
        </mesh>
      ))}
    </group>
  );
}
