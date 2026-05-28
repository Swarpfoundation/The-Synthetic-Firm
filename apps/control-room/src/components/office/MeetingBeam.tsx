import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface MeetingBeamProps {
  position: [number, number, number];
  participants: string[];
}

export function MeetingBeam({ position }: MeetingBeamProps) {
  const beamRef = useRef<THREE.Mesh>(null);
  const particlesRef = useRef<THREE.Points>(null);

  // Particle positions for spiral
  const particleCount = 50;
  const positions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    const angle = (i / particleCount) * Math.PI * 8;
    const radius = 0.5 + (i / particleCount) * 1.5;
    const y = (i / particleCount) * 6;
    positions[i * 3] = Math.cos(angle) * radius;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = Math.sin(angle) * radius;
  }

  useFrame((state) => {
    if (beamRef.current) {
      const mat = beamRef.current.material as THREE.MeshStandardMaterial;
      mat.emissiveIntensity = 0.3 + Math.sin(state.clock.elapsedTime * 2) * 0.15;
    }

    if (particlesRef.current) {
      particlesRef.current.rotation.y += 0.005;
      const positions = particlesRef.current.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < particleCount; i++) {
        positions[i * 3 + 1] += 0.01;
        if (positions[i * 3 + 1] > 6) {
          positions[i * 3 + 1] = 0;
        }
      }
      particlesRef.current.geometry.attributes.position.needsUpdate = true;
    }
  });

  return (
    <group position={position}>
      {/* Main beam cylinder */}
      <mesh ref={beamRef} position={[0, 3, 0]}>
        <cylinderGeometry args={[2.5, 2, 6, 16, 1, true]} />
        <meshStandardMaterial
          color="#F9FAFB"
          emissive="#F9FAFB"
          emissiveIntensity={0.25}
          transparent
          opacity={0.08}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Inner glow */}
      <mesh position={[0, 3, 0]}>
        <cylinderGeometry args={[1.5, 1.2, 6, 16, 1, true]} />
        <meshStandardMaterial
          color="#06B6D4"
          emissive="#06B6D4"
          emissiveIntensity={0.2}
          transparent
          opacity={0.06}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Spiral particles */}
      <points ref={particlesRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#F9FAFB"
          size={0.08}
          transparent
          opacity={0.6}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>

      {/* Top glow cap */}
      <mesh position={[0, 6.2, 0]}>
        <sphereGeometry args={[1.5, 16, 16]} />
        <meshStandardMaterial
          color="#F9FAFB"
          emissive="#06B6D4"
          emissiveIntensity={0.4}
          transparent
          opacity={0.1}
          depthWrite={false}
        />
      </mesh>

      {/* Light source */}
      <pointLight
        position={[0, 4, 0]}
        color="#06B6D4"
        intensity={2}
        distance={8}
        decay={2}
      />
    </group>
  );
}
