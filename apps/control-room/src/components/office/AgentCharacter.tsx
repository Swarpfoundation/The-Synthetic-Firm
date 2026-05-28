import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, Sparkles } from '@react-three/drei';
import * as THREE from 'three';
import type { Agent, AgentId } from '@/types/tsf';

interface AgentCharacterProps {
  agent: Agent;
  roomPosition: [number, number, number];
  isSelected: boolean;
  isPaused: boolean;
  isKilled: boolean;
  onClick: () => void;
}

const AGENT_CONFIG: Record<AgentId, {
  shape: 'crystal' | 'orb' | 'cube' | 'spike' | 'shield';
  scale: number;
  rotationSpeed: number;
  bobSpeed: number;
  bobAmount: number;
}> = {
  atlas: { shape: 'crystal', scale: 1.1, rotationSpeed: 0.3, bobSpeed: 0.8, bobAmount: 0.12 },
  scout: { shape: 'orb', scale: 1.0, rotationSpeed: 0.8, bobSpeed: 1.2, bobAmount: 0.08 },
  forge: { shape: 'cube', scale: 0.9, rotationSpeed: 0.2, bobSpeed: 0.6, bobAmount: 0.06 },
  pulse: { shape: 'spike', scale: 1.0, rotationSpeed: 0.5, bobSpeed: 1.5, bobAmount: 0.15 },
  sentinel: { shape: 'shield', scale: 1.1, rotationSpeed: 0.4, bobSpeed: 0.5, bobAmount: 0.05 },
};

function AgentGeometry({ shape, color, isActive, isBlocked }: {
  shape: string; color: string; isActive: boolean; isBlocked: boolean;
}) {
  const meshColor = isBlocked ? '#EF4444' : color;
  const emissiveIntensity = isActive ? 0.6 : isBlocked ? 0.4 : 0.25;

  switch (shape) {
    case 'crystal':
      return (
        <group>
          {/* Diamond crystal body */}
          <mesh castShadow>
            <octahedronGeometry args={[0.5, 0]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity}
              roughness={0.1}
              metalness={0.9}
              transparent
              opacity={0.9}
            />
          </mesh>
          {/* Inner core glow */}
          <mesh scale={0.4}>
            <octahedronGeometry args={[0.5, 0]} />
            <meshStandardMaterial
              color="#ffffff"
              emissive={meshColor}
              emissiveIntensity={1.2}
              transparent
              opacity={0.4}
            />
          </mesh>
        </group>
      );

    case 'orb':
      return (
        <group>
          {/* Main orb */}
          <mesh castShadow>
            <icosahedronGeometry args={[0.45, 2]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity}
              roughness={0.05}
              metalness={0.1}
              transparent
              opacity={0.85}
            />
          </mesh>
          {/* Outer ring 1 */}
          <mesh rotation={[Math.PI / 3, 0, 0]}>
            <torusGeometry args={[0.65, 0.02, 8, 32]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity * 0.8}
              transparent
              opacity={0.5}
            />
          </mesh>
          {/* Outer ring 2 */}
          <mesh rotation={[0, Math.PI / 4, Math.PI / 6]}>
            <torusGeometry args={[0.8, 0.015, 8, 32]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity * 0.5}
              transparent
              opacity={0.35}
            />
          </mesh>
        </group>
      );

    case 'cube':
      return (
        <group>
          {/* Main cube */}
          <mesh castShadow>
            <boxGeometry args={[0.7, 0.7, 0.7]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity}
              roughness={0.3}
              metalness={0.7}
            />
          </mesh>
          {/* Edge glow */}
          <lineSegments>
            <edgesGeometry args={[new THREE.BoxGeometry(0.72, 0.72, 0.72)]} />
            <lineBasicMaterial color={meshColor} transparent opacity={0.6} />
          </lineSegments>
          {/* Forge fire glow inside */}
          <mesh position={[0, -0.1, 0]} scale={0.5}>
            <sphereGeometry args={[0.3, 8, 8]} />
            <meshStandardMaterial
              color="#F59E0B"
              emissive="#F59E0B"
              emissiveIntensity={1.0}
              transparent
              opacity={0.3}
            />
          </mesh>
        </group>
      );

    case 'spike':
      return (
        <group>
          {/* Main spike */}
          <mesh castShadow>
            <coneGeometry args={[0.35, 1.2, 6]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity}
              roughness={0.15}
              metalness={0.8}
              transparent
              opacity={0.9}
            />
          </mesh>
          {/* Pulse rings at base */}
          {[0.5, 0.7, 0.9].map((r, i) => (
            <mesh key={i} position={[0, -0.5 + i * 0.05, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <ringGeometry args={[r - 0.02, r, 16]} />
              <meshStandardMaterial
                color={meshColor}
                emissive={meshColor}
                emissiveIntensity={emissiveIntensity * (0.3 - i * 0.08)}
                transparent
                opacity={0.25 - i * 0.06}
                side={THREE.DoubleSide}
              />
            </mesh>
          ))}
        </group>
      );

    case 'shield':
      return (
        <group>
          {/* Shield body */}
          <mesh castShadow>
            <cylinderGeometry args={[0.5, 0.35, 0.9, 6]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity}
              roughness={0.25}
              metalness={0.85}
              transparent
              opacity={0.9}
            />
          </mesh>
          {/* Shield border ring */}
          <mesh position={[0, 0.4, 0]}>
            <torusGeometry args={[0.38, 0.03, 8, 24]} />
            <meshStandardMaterial
              color={meshColor}
              emissive={meshColor}
              emissiveIntensity={emissiveIntensity * 1.2}
            />
          </mesh>
          {/* Scanning beam */}
          <mesh position={[0, 0.1, 0.42]} rotation={[0.1, 0, 0]}>
            <planeGeometry args={[0.6, 0.02]} />
            <meshStandardMaterial
              color="#EF4444"
              emissive="#EF4444"
              emissiveIntensity={1.5}
              transparent
              opacity={0.6}
              side={THREE.DoubleSide}
            />
          </mesh>
        </group>
      );

    default:
      return (
        <mesh castShadow>
          <sphereGeometry args={[0.4, 16, 16]} />
          <meshStandardMaterial color={meshColor} emissive={meshColor} emissiveIntensity={emissiveIntensity} />
        </mesh>
      );
  }
}

export function AgentCharacter({
  agent,
  roomPosition,
  isSelected,
  isPaused,
  isKilled,
  onClick,
}: AgentCharacterProps) {
  const groupRef = useRef<THREE.Group>(null);
  const characterRef = useRef<THREE.Group>(null);
  const [hovered, setHovered] = useState(false);

  const config = AGENT_CONFIG[agent.id];
  const isActive = agent.state !== 'idle' && agent.state !== 'paused' && agent.state !== 'blocked';
  const isBlocked = agent.state === 'blocked';
  const isMeeting = agent.state === 'meeting';

  // Target position from agent state, or default room position
  const targetX = agent.position.x !== roomPosition[0] ? agent.position.x / 20 : roomPosition[0];
  const targetZ = agent.position.y !== roomPosition[2] ? agent.position.y / 20 : roomPosition[2];
  const targetY = isMeeting ? 1.2 : 0.5;

  useFrame((state, delta) => {
    if (!groupRef.current || !characterRef.current) return;

    if (isPaused || isKilled) return;

    const t = state.clock.elapsedTime;

    // Smooth position lerp
    groupRef.current.position.x = THREE.MathUtils.lerp(groupRef.current.position.x, targetX, delta * 3);
    groupRef.current.position.z = THREE.MathUtils.lerp(groupRef.current.position.z, targetZ, delta * 3);

    // Bobbing animation
    const bobOffset = isPaused ? 0 : Math.sin(t * config.bobSpeed) * config.bobAmount;
    groupRef.current.position.y = THREE.MathUtils.lerp(
      groupRef.current.position.y,
      targetY + bobOffset,
      delta * 4
    );

    // Rotation
    const rotSpeed = isMeeting ? config.rotationSpeed * 3 : config.rotationSpeed;
    characterRef.current.rotation.y += rotSpeed * delta;

    // Blocked shake
    if (isBlocked && !isPaused) {
      groupRef.current.position.x += Math.sin(t * 15) * 0.005;
      groupRef.current.position.z += Math.cos(t * 12) * 0.005;
    }
  });

  // Scale down if killed
  const scale = isKilled ? 0.3 : config.scale;
  const opacity = isKilled ? 0.3 : 1;

  return (
    <group
      ref={groupRef}
      position={[roomPosition[0], 0.5, roomPosition[2]]}
    >
      {/* Pedestal */}
      <mesh position={[0, -0.35, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.4, 0.5, 0.15, 16]} />
        <meshStandardMaterial
          color="#1e293b"
          roughness={0.5}
          metalness={0.6}
          emissive={agent.color}
          emissiveIntensity={0.05}
        />
      </mesh>

      {/* Selection ring */}
      {isSelected && (
        <mesh position={[0, -0.25, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.7, 0.75, 32]} />
          <meshStandardMaterial
            color={agent.color}
            emissive={agent.color}
            emissiveIntensity={0.8}
            transparent
            opacity={0.6}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Character body */}
      <group
        ref={characterRef}
        scale={scale}
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
        <AgentGeometry
          shape={config.shape}
          color={agent.color}
          isActive={isActive}
          isBlocked={isBlocked}
        />
      </group>

      {/* Sparkle particles when active */}
      {isActive && !isPaused && !isKilled && (
        <Sparkles
          count={8}
          scale={1.5}
          size={1.5}
          speed={0.4}
          color={agent.color}
          opacity={0.4}
        />
      )}

      {/* Hover glow */}
      {hovered && !isKilled && (
        <pointLight
          position={[0, 0.5, 0]}
          color={agent.color}
          intensity={1.5}
          distance={3}
        />
      )}

      {/* Name label (billboarded) */}
      <Text
        position={[0, 1.0, 0]}
        fontSize={0.25}
        color="#E2E8F0"
        anchorX="center"
        anchorY="middle"
        letterSpacing={0.1}
      >
        {agent.name}
        <meshStandardMaterial
          color="#E2E8F0"
          emissive="#E2E8F0"
          emissiveIntensity={0.2}
          transparent
          opacity={opacity}
        />
      </Text>

      {/* State label */}
      <Text
        position={[0, 0.7, 0]}
        fontSize={0.15}
        color={isBlocked ? '#EF4444' : isActive ? agent.color : '#475569'}
        anchorX="center"
        anchorY="middle"
        letterSpacing={0.05}
      >
        {agent.state.replace(/_/g, ' ')}
        <meshStandardMaterial
          color={isBlocked ? '#EF4444' : isActive ? agent.color : '#475569'}
          emissive={isBlocked ? '#EF4444' : isActive ? agent.color : '#475569'}
          emissiveIntensity={0.3}
          transparent
          opacity={opacity * 0.8}
        />
      </Text>
    </group>
  );
}
