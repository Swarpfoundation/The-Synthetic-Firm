import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { RoundedBox } from '@react-three/drei';
import * as THREE from 'three';

interface RoomPlatformProps {
  position: [number, number, number];
  size: [number, number];
  color: string;
  name: string;
  isSelected: boolean;
  isMeetingRoom: boolean;
  isMeetingActive: boolean;
  hasPendingApprovals: boolean;
  onClick: () => void;
}

export function RoomPlatform({
  position,
  size,
  color,
  name,
  isSelected,
  isMeetingRoom,
  isMeetingActive,
  hasPendingApprovals,
  onClick,
}: RoomPlatformProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const borderRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const [w, d] = size;
  const height = isMeetingRoom ? 0.4 : 0.35;

  useFrame((state) => {
    if (!borderRef.current) return;

    // Pulsing glow effect
    const pulse = Math.sin(state.clock.elapsedTime * 2) * 0.15 + 0.5;

    if (isMeetingActive) {
      (borderRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity =
        0.6 + Math.sin(state.clock.elapsedTime * 3) * 0.3;
    } else if (hasPendingApprovals) {
      (borderRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity =
        0.4 + Math.sin(state.clock.elapsedTime * 5) * 0.3;
    } else if (isSelected || hovered) {
      (borderRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.7;
    } else {
      (borderRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = pulse;
    }
  });

  // Meeting room table
  const renderMeetingTable = () => {
    if (!isMeetingRoom) return null;
    return (
      <group position={[0, height / 2 + 0.01, 0]}>
        {/* Table */}
        <RoundedBox args={[3.5, 0.15, 2]} radius={0.05} position={[0, 0.075, 0]}>
          <meshStandardMaterial color="#1e293b" roughness={0.4} metalness={0.6} />
        </RoundedBox>
        {/* Chairs */}
        {[-1.5, 0, 1.5].map((x, i) => (
          <mesh key={`c-front-${i}`} position={[x, 0, 1.4]} castShadow>
            <cylinderGeometry args={[0.25, 0.25, 0.4, 16]} />
            <meshStandardMaterial color="#334155" roughness={0.5} metalness={0.4} />
          </mesh>
        ))}
        {[-1, 1].map((x, i) => (
          <mesh key={`c-back-${i}`} position={[x, 0, -1.4]} castShadow>
            <cylinderGeometry args={[0.25, 0.25, 0.4, 16]} />
            <meshStandardMaterial color="#334155" roughness={0.5} metalness={0.4} />
          </mesh>
        ))}
      </group>
    );
  };

  // Server racks for core room
  const renderServerRacks = () => {
    if (name !== 'CORE') return null;
    return (
      <group position={[0, height / 2 + 0.01, 0]}>
        {[-1.5, -0.5, 0.5, 1.5].map((x, i) => (
          <group key={i} position={[x, 0.6, 0]}>
            <RoundedBox args={[0.6, 1.2, 0.8]} radius={0.02} castShadow>
              <meshStandardMaterial color="#0f172a" roughness={0.3} metalness={0.8} />
            </RoundedBox>
            {/* LED rows */}
            {[0, 1, 2, 3].map((row) => (
              <group key={row}>
                <mesh position={[-0.15, -0.3 + row * 0.2, 0.41]}>
                  <circleGeometry args={[0.035, 8]} />
                  <meshStandardMaterial
                    color={row % 2 === 0 ? '#06B6D4' : '#8B5CF6'}
                    emissive={row % 2 === 0 ? '#06B6D4' : '#8B5CF6'}
                    emissiveIntensity={0.8}
                  />
                </mesh>
                <mesh position={[0.15, -0.3 + row * 0.2, 0.41]}>
                  <circleGeometry args={[0.035, 8]} />
                  <meshStandardMaterial
                    color={row % 3 === 0 ? '#10B981' : '#06B6D4'}
                    emissive={row % 3 === 0 ? '#10B981' : '#06B6D4'}
                    emissiveIntensity={0.6}
                  />
                </mesh>
              </group>
            ))}
          </group>
        ))}
      </group>
    );
  };

  // Approval desk
  const renderApprovalDesk = () => {
    if (name !== 'APPROVALS') return null;
    return (
      <group position={[0, height / 2 + 0.01, 0]}>
        <RoundedBox args={[2.5, 0.15, 1.2]} radius={0.03} position={[0, 0.075, 0]} castShadow>
          <meshStandardMaterial color="#1e293b" roughness={0.4} metalness={0.6} />
        </RoundedBox>
        {/* Screen on desk */}
        <RoundedBox args={[1, 0.6, 0.05]} radius={0.01} position={[0, 0.5, -0.4]} castShadow>
          <meshStandardMaterial
            color="#020617"
            emissive="#F59E0B"
            emissiveIntensity={0.15}
            roughness={0.2}
          />
        </RoundedBox>
      </group>
    );
  };

  // Shield wall for Sentinel
  const renderShieldWall = () => {
    if (name !== 'SECURITY') return null;
    return (
      <group position={[0, height / 2 + 0.01, 0]}>
        {/* Shield display wall */}
        <RoundedBox args={[3, 1.8, 0.1]} radius={0.02} position={[0, 1, -1.5]} castShadow>
          <meshStandardMaterial
            color="#0f172a"
            emissive="#EF4444"
            emissiveIntensity={0.08}
            roughness={0.2}
            metalness={0.5}
          />
        </RoundedBox>
        {/* Radar rings */}
        {[0.4, 0.8, 1.2].map((r, i) => (
          <mesh key={i} position={[0, 1, -1.44]} rotation={[0, 0, 0]}>
            <ringGeometry args={[r - 0.02, r, 32]} />
            <meshStandardMaterial
              color="#EF4444"
              emissive="#EF4444"
              emissiveIntensity={0.2}
              transparent
              opacity={0.3 - i * 0.08}
            />
          </mesh>
        ))}
      </group>
    );
  };

  const borderColor = isMeetingActive ? '#F9FAFB' : hasPendingApprovals ? '#F59E0B' : color;
  const intensity = isMeetingActive ? 0.5 : isSelected ? 0.4 : hovered ? 0.3 : 0.15;

  return (
    <group position={position}>
      {/* Floor platform */}
      <mesh
        ref={meshRef}
        position={[0, height / 2, 0]}
        receiveShadow
        castShadow
        onClick={(e) => {
          e.stopPropagation();
          onClick();
        }}
        onPointerOver={() => {
          setHovered(true);
          document.body.style.cursor = 'pointer';
        }}
        onPointerOut={() => {
          setHovered(false);
          document.body.style.cursor = 'auto';
        }}
      >
        <boxGeometry args={[w, height, d]} />
        <meshStandardMaterial
          color="#0D1117"
          roughness={0.7}
          metalness={0.3}
          transparent
          opacity={0.9}
        />
      </mesh>

      {/* Surface grid */}
      <mesh position={[0, height + 0.001, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[w - 0.2, d - 0.2]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.03}
          roughness={0.8}
          transparent
          opacity={0.15}
        />
      </mesh>

      {/* Glowing border */}
      <mesh ref={borderRef} position={[0, height / 2, 0]}>
        <boxGeometry args={[w + 0.1, height + 0.05, d + 0.1]} />
        <meshStandardMaterial
          color={borderColor}
          emissive={borderColor}
          emissiveIntensity={intensity}
          roughness={0.2}
          metalness={0.8}
          transparent
          opacity={0.15}
          wireframe={false}
        />
      </mesh>

      {/* Border lines (wireframe edges) */}
      <lineSegments position={[0, height / 2, 0]}>
        <edgesGeometry args={[new THREE.BoxGeometry(w + 0.12, height + 0.08, d + 0.12)]} />
        <lineBasicMaterial color={borderColor} transparent opacity={0.4} />
      </lineSegments>

      {/* Interior props */}
      {renderMeetingTable()}
      {renderServerRacks()}
      {renderApprovalDesk()}
      {renderShieldWall()}
    </group>
  );
}
