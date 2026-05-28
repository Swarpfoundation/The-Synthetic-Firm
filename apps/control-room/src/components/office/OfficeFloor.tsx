import { useMemo } from 'react';
import * as THREE from 'three';

export function OfficeFloor() {

  // Grid texture
  const gridTexture = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#05080F';
    ctx.fillRect(0, 0, 512, 512);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    // Draw grid
    for (let i = 0; i <= 512; i += 32) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, 512);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(512, i);
      ctx.stroke();
    }
    // Draw larger grid
    ctx.strokeStyle = '#1e3a5f';
    ctx.lineWidth = 1.5;
    for (let i = 0; i <= 512; i += 128) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, 512);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(512, i);
      ctx.stroke();
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(8, 8);
    return tex;
  }, []);

  return (
    <group>
      {/* Main floor plane */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.1, 0]}
        receiveShadow
      >
        <planeGeometry args={[120, 120]} />
        <meshStandardMaterial
          map={gridTexture}
          color="#080c14"
          roughness={0.9}
          metalness={0.1}
          transparent
          opacity={0.6}
        />
      </mesh>

      {/* Reflective surface beneath rooms */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, -0.05, 0]}
      >
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial
          color="#060a10"
          roughness={0.3}
          metalness={0.8}
          transparent
          opacity={0.4}
        />
      </mesh>

      {/* World border ring */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.08, 0]}>
        <ringGeometry args={[28, 29, 64]} />
        <meshStandardMaterial
          color="#06B6D4"
          emissive="#06B6D4"
          emissiveIntensity={0.3}
          transparent
          opacity={0.3}
        />
      </mesh>
    </group>
  );
}
