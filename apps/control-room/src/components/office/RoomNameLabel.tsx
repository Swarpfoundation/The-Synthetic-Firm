import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text } from '@react-three/drei';
import * as THREE from 'three';

interface RoomNameLabelProps {
  position: [number, number, number];
  text: string;
  color: string;
}

export function RoomNameLabel({ position, text, color }: RoomNameLabelProps) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (groupRef.current) {
      // Gentle floating
      groupRef.current.position.y = position[1] + Math.sin(state.clock.elapsedTime * 0.8) * 0.08;
    }
  });

  return (
    <group ref={groupRef} position={position}>
      <Text
        fontSize={0.45}
        color={color}
        anchorX="center"
        anchorY="middle"
        font={undefined}
        letterSpacing={0.15}
      >
        {text}
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.4}
          transparent
          opacity={0.85}
        />
      </Text>
      {/* Subtle glow plane behind text */}
      <mesh position={[0, 0, -0.05]}>
        <planeGeometry args={[text.length * 0.3, 0.6]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.1}
          transparent
          opacity={0.05}
        />
      </mesh>
    </group>
  );
}
