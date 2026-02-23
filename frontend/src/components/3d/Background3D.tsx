import { useRef, useMemo, useState, useEffect, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, MeshDistortMaterial, MeshWobbleMaterial, Stars } from '@react-three/drei';
import * as THREE from 'three';

function FloatingSphere({ position, color, speed, distort, size }: {
  position: [number, number, number];
  color: string;
  speed: number;
  distort: number;
  size: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * speed * 0.3) * 0.3;
      meshRef.current.rotation.y = Math.cos(state.clock.elapsedTime * speed * 0.2) * 0.3;
    }
  });

  return (
    <Float speed={speed} rotationIntensity={0.5} floatIntensity={2} floatingRange={[-0.5, 0.5]}>
      <mesh ref={meshRef} position={position}>
        <sphereGeometry args={[size, 64, 64]} />
        <MeshDistortMaterial
          color={color}
          transparent
          opacity={0.6}
          distort={distort}
          speed={speed * 0.5}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
    </Float>
  );
}

function FloatingTorus({ position, color, speed, size }: {
  position: [number, number, number];
  color: string;
  speed: number;
  size: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = state.clock.elapsedTime * speed * 0.2;
      meshRef.current.rotation.z = Math.sin(state.clock.elapsedTime * speed * 0.15) * 0.5;
    }
  });

  return (
    <Float speed={speed * 0.7} rotationIntensity={1} floatIntensity={1.5}>
      <mesh ref={meshRef} position={position}>
        <torusGeometry args={[size, size * 0.3, 32, 64]} />
        <MeshWobbleMaterial
          color={color}
          transparent
          opacity={0.5}
          factor={0.3}
          speed={speed}
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>
    </Float>
  );
}

function FloatingOctahedron({ position, color, speed, size }: {
  position: [number, number, number];
  color: string;
  speed: number;
  size: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.y = state.clock.elapsedTime * speed * 0.3;
      meshRef.current.rotation.x = Math.cos(state.clock.elapsedTime * speed * 0.2) * 0.4;
    }
  });

  return (
    <Float speed={speed * 0.5} rotationIntensity={1.5} floatIntensity={2}>
      <mesh ref={meshRef} position={position}>
        <octahedronGeometry args={[size, 0]} />
        <MeshDistortMaterial
          color={color}
          transparent
          opacity={0.45}
          distort={0.2}
          speed={speed * 0.3}
          roughness={0.15}
          metalness={0.85}
          wireframe
        />
      </mesh>
    </Float>
  );
}

function Particles() {
  const count = 200;
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 20;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 20;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 20;
    }
    return pos;
  }, []);

  const pointsRef = useRef<THREE.Points>(null!);

  useFrame((state) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y = state.clock.elapsedTime * 0.02;
      pointsRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.01) * 0.1;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.03}
        color="#6699ff"
        transparent
        opacity={0.8}
        sizeAttenuation
      />
    </points>
  );
}

function GlowRing({ position, color, size }: {
  position: [number, number, number];
  color: string;
  size: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = Math.PI / 2 + Math.sin(state.clock.elapsedTime * 0.5) * 0.3;
      meshRef.current.rotation.z = state.clock.elapsedTime * 0.15;
    }
  });

  return (
    <Float speed={1} floatIntensity={1}>
      <mesh ref={meshRef} position={position}>
        <torusGeometry args={[size, 0.02, 16, 100]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={2}
          transparent
          opacity={0.6}
        />
      </mesh>
    </Float>
  );
}

function Scene() {
  return (
    <>
      <ambientLight intensity={0.3} />
      <directionalLight position={[5, 5, 5]} intensity={0.8} color="#4488ff" />
      <pointLight position={[-5, -3, 3]} intensity={0.6} color="#ff4400" />
      <pointLight position={[3, 4, -2]} intensity={0.4} color="#2244ff" />

      <FloatingSphere position={[-3.5, 1.5, -2]} color="#1a4fff" speed={1.5} distort={0.4} size={1.2} />
      <FloatingSphere position={[3.5, -1.5, -3]} color="#ff4400" speed={1.2} distort={0.3} size={0.8} />
      <FloatingSphere position={[2, 2.5, -4]} color="#2255ff" speed={1} distort={0.5} size={0.6} />

      <FloatingTorus position={[-2.5, -2, -1.5]} color="#3366ff" speed={1.3} size={0.7} />
      <FloatingTorus position={[4, 1, -3]} color="#ff5511" speed={0.8} size={0.5} />

      <FloatingOctahedron position={[0, 3, -3]} color="#4488ff" speed={1} size={0.6} />
      <FloatingOctahedron position={[-4, -1, -4]} color="#ff6622" speed={0.7} size={0.8} />

      <GlowRing position={[0, 0, -5]} color="#1a4fff" size={3} />
      <GlowRing position={[2, -1, -6]} color="#ff4400" size={2} />

      <Particles />
      <Stars radius={50} depth={50} count={1000} factor={3} saturation={0.5} fade speed={0.5} />
    </>
  );
}

function CSSFallbackBackground() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #0a1628 60%, #050a18 100%)',
        overflow: 'hidden',
      }}
    >
      <style>{`
        @keyframes floatOrb1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          25% { transform: translate(30px, -40px) scale(1.1); }
          50% { transform: translate(-20px, -80px) scale(0.95); }
          75% { transform: translate(40px, -30px) scale(1.05); }
        }
        @keyframes floatOrb2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          25% { transform: translate(-40px, 30px) scale(1.05); }
          50% { transform: translate(30px, 60px) scale(0.9); }
          75% { transform: translate(-20px, 20px) scale(1.1); }
        }
        @keyframes floatOrb3 {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          33% { transform: translate(50px, -50px) rotate(120deg); }
          66% { transform: translate(-30px, 30px) rotate(240deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.6; }
        }
        @keyframes rotateRing {
          from { transform: translate(-50%, -50%) rotate(0deg); }
          to { transform: translate(-50%, -50%) rotate(360deg); }
        }
        @keyframes sparkle {
          0%, 100% { opacity: 0; transform: scale(0); }
          50% { opacity: 1; transform: scale(1); }
        }
      `}</style>

      <div style={{
        position: 'absolute',
        top: '15%',
        left: '10%',
        width: '300px',
        height: '300px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(26, 79, 255, 0.25) 0%, transparent 70%)',
        filter: 'blur(40px)',
        animation: 'floatOrb1 12s ease-in-out infinite',
      }} />

      <div style={{
        position: 'absolute',
        bottom: '20%',
        right: '15%',
        width: '250px',
        height: '250px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255, 68, 0, 0.2) 0%, transparent 70%)',
        filter: 'blur(40px)',
        animation: 'floatOrb2 15s ease-in-out infinite',
      }} />

      <div style={{
        position: 'absolute',
        top: '50%',
        left: '60%',
        width: '200px',
        height: '200px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(34, 85, 255, 0.15) 0%, transparent 70%)',
        filter: 'blur(30px)',
        animation: 'floatOrb1 18s ease-in-out infinite reverse',
      }} />

      <div style={{
        position: 'absolute',
        top: '30%',
        right: '20%',
        width: '180px',
        height: '180px',
        border: '1px solid rgba(26, 79, 255, 0.15)',
        borderRadius: '50%',
        animation: 'rotateRing 20s linear infinite',
        transformOrigin: 'center center',
      }}>
        <div style={{
          position: 'absolute',
          top: '-3px',
          left: '50%',
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: '#1a4fff',
          boxShadow: '0 0 10px #1a4fff, 0 0 20px #1a4fff',
        }} />
      </div>

      <div style={{
        position: 'absolute',
        bottom: '30%',
        left: '15%',
        width: '120px',
        height: '120px',
        border: '1px solid rgba(255, 68, 0, 0.12)',
        borderRadius: '50%',
        animation: 'rotateRing 15s linear infinite reverse',
        transformOrigin: 'center center',
      }}>
        <div style={{
          position: 'absolute',
          top: '-3px',
          left: '50%',
          width: '5px',
          height: '5px',
          borderRadius: '50%',
          background: '#ff4400',
          boxShadow: '0 0 8px #ff4400, 0 0 16px #ff4400',
        }} />
      </div>

      {Array.from({ length: 30 }).map((_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: `${Math.random() * 100}%`,
            left: `${Math.random() * 100}%`,
            width: `${1 + Math.random() * 3}px`,
            height: `${1 + Math.random() * 3}px`,
            borderRadius: '50%',
            background: i % 3 === 0 ? '#ff4400' : '#4488ff',
            animation: `sparkle ${3 + Math.random() * 5}s ease-in-out ${Math.random() * 5}s infinite`,
          }}
        />
      ))}

      <div style={{
        position: 'absolute',
        top: '60%',
        left: '40%',
        width: '60px',
        height: '60px',
        border: '1px solid rgba(26, 79, 255, 0.1)',
        animation: 'floatOrb3 10s ease-in-out infinite',
        transform: 'rotate(45deg)',
      }} />

      <div style={{
        position: 'absolute',
        top: '20%',
        left: '70%',
        width: '40px',
        height: '40px',
        border: '1px solid rgba(255, 68, 0, 0.1)',
        animation: 'floatOrb3 8s ease-in-out infinite reverse',
        transform: 'rotate(30deg)',
      }} />
    </div>
  );
}

function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}

export default function Background3D() {
  const [webglAvailable, setWebglAvailable] = useState(true);

  useEffect(() => {
    setWebglAvailable(isWebGLAvailable());
  }, []);

  if (!webglAvailable) {
    return <CSSFallbackBackground />;
  }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0 }}>
      <CSSFallbackBackground />
      <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
        <Canvas
          camera={{ position: [0, 0, 6], fov: 60 }}
          gl={{ antialias: true, alpha: true }}
          onCreated={({ gl }) => {
            gl.setClearColor(0x000000, 0);
          }}
        >
          <Suspense fallback={null}>
            <Scene />
          </Suspense>
        </Canvas>
      </div>
    </div>
  );
}
