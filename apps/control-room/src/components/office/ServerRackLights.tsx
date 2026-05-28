import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface ServerRackLightsProps {
  position: [number, number, number];
}

export function ServerRackLights({ position }: ServerRackLightsProps) {
  const lightsRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!lightsRef.current) return;
    const t = state.clock.elapsedTime;

    lightsRef.current.children.forEach((child, i) => {
      const mat = (child as THREE.Mesh).material as THREE.MeshStandardMaterial;
      if (mat && mat.emissive) {
        // Different blink patterns per LED
        const speed = 2 + (i % 3) * 1.5;
        const phase = i * 0.7;
        const intensity = 0.5 + Math.sin(t * speed + phase) * 0.4;
        mat.emissiveIntensity = Math.max(0.1, intensity);
      }
    });
  });

  // Generate LED positions for 4 racks x 4 rows x 2 columns
  const leds: { pos: [number, number, number]; color: string }[] = [];
  const colors = ['#06B6D4', '#8B5CF6', '#10B981', '#06B6D4'];

  for (let rack = 0; rack < 4; rack++) {
    const rackX = -1.5 + rack * 1.0;
    for (let row = 0; row < 4; row++) {
      const y = -0.3 + row * 0.2;
      for (let col = 0; col < 2; col++) {
        const x = rackX + (col === 0 ? -0.15 : 0.15);
        const colorIdx = (rack + row + col) % colors.length;
        leds.push({ pos: [x, y, 0.42], color: colors[colorIdx] });
      }
    }
  }

  return (
    <group ref={lightsRef} position={position}>
      {leds.map((led, i) => (
        <mesh key={i} position={led.pos}>
          <circleGeometry args={[0.035, 8]} />
          <meshStandardMaterial
            color={led.color}
            emissive={led.color}
            emissiveIntensity={0.6}
          />
        </mesh>
      ))}
    </group>
  );
}
