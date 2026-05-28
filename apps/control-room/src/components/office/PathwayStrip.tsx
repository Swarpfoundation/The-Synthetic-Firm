import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface PathwayStripProps {
  start: [number, number, number];
  end: [number, number, number];
  color: string;
}

export function PathwayStrip({ start, end, color }: PathwayStripProps) {
  const meshRef = useRef<THREE.Mesh>(null);

  const direction = new THREE.Vector3(end[0] - start[0], 0, end[2] - start[2]);
  const length = direction.length();
  const midX = (start[0] + end[0]) / 2;
  const midZ = (start[2] + end[2]) / 2;

  // Calculate rotation to align with direction
  const angle = Math.atan2(direction.x, direction.z);

  useFrame((state) => {
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = 0.15 + Math.sin(state.clock.elapsedTime * 1.5) * 0.08;
  });

  return (
    <mesh
      ref={meshRef}
      position={[midX, start[1], midZ]}
      rotation={[0, angle, 0]}
    >
      <boxGeometry args={[0.15, 0.03, length]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={0.15}
        roughness={0.4}
        metalness={0.6}
        transparent
        opacity={0.5}
      />
    </mesh>
  );
}
