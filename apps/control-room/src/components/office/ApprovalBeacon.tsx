import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface ApprovalBeaconProps {
  position: [number, number, number];
}

export function ApprovalBeacon({ position }: ApprovalBeaconProps) {
  const beaconRef = useRef<THREE.Mesh>(null);
  const lightRef = useRef<THREE.PointLight>(null);

  useFrame((state) => {
    if (!beaconRef.current || !lightRef.current) return;

    const t = state.clock.elapsedTime;
    const flash = Math.sin(t * 4) * 0.5 + 0.5;

    // Rotate beacon
    beaconRef.current.rotation.y += 0.05;

    // Flash intensity
    const intensity = 0.5 + flash * 1.5;
    lightRef.current.intensity = intensity;

    const mat = beaconRef.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = intensity;
  });

  return (
    <group position={position}>
      {/* Beacon cylinder */}
      <mesh ref={beaconRef} position={[0, 0.5, 0]} castShadow>
        <cylinderGeometry args={[0.15, 0.2, 0.6, 8]} />
        <meshStandardMaterial
          color="#F59E0B"
          emissive="#F59E0B"
          emissiveIntensity={1.0}
          roughness={0.3}
          metalness={0.5}
        />
      </mesh>

      {/* Beacon light */}
      <pointLight
        ref={lightRef}
        position={[0, 0.8, 0]}
        color="#F59E0B"
        intensity={1.5}
        distance={5}
        decay={2}
      />

      {/* Glow sphere */}
      <mesh position={[0, 0.8, 0]}>
        <sphereGeometry args={[0.25, 8, 8]} />
        <meshStandardMaterial
          color="#F59E0B"
          emissive="#F59E0B"
          emissiveIntensity={0.8}
          transparent
          opacity={0.3}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}
