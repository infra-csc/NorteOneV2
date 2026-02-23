import { useRef, useMemo, useState, useEffect, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float, MeshDistortMaterial } from '@react-three/drei';
import * as THREE from 'three';

function GlowOrb({ position, color, speed, size }: {
  position: [number, number, number];
  color: string;
  speed: number;
  size: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (meshRef.current) {
      meshRef.current.rotation.x = Math.sin(state.clock.elapsedTime * speed * 0.2) * 0.2;
      meshRef.current.rotation.y = state.clock.elapsedTime * speed * 0.08;
    }
  });

  return (
    <Float speed={speed * 0.6} rotationIntensity={0.3} floatIntensity={1.5} floatingRange={[-0.3, 0.3]}>
      <mesh ref={meshRef} position={position}>
        <sphereGeometry args={[size, 64, 64]} />
        <MeshDistortMaterial
          color={color}
          transparent
          opacity={0.35}
          distort={0.35}
          speed={speed * 0.4}
          roughness={0.1}
          metalness={0.9}
        />
      </mesh>
    </Float>
  );
}

function Particles() {
  const count = 80;
  const positions = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 18;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 14;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 10 - 3;
    }
    return pos;
  }, []);

  const pointsRef = useRef<THREE.Points>(null!);

  useFrame((state) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y = state.clock.elapsedTime * 0.015;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.025}
        color="#5588dd"
        transparent
        opacity={0.6}
        sizeAttenuation
      />
    </points>
  );
}

function Scene() {
  return (
    <>
      <ambientLight intensity={0.2} />
      <directionalLight position={[5, 5, 5]} intensity={0.5} color="#4488ff" />
      <pointLight position={[-4, -2, 2]} intensity={0.4} color="#ff4400" />

      <GlowOrb position={[-4, 2, -4]} color="#1a4fff" speed={1.2} size={1.8} />
      <GlowOrb position={[4.5, -2, -5]} color="#ff4400" speed={0.9} size={1.3} />

      <Particles />
    </>
  );
}

function RunnerSilhouette({ style, flip }: { style: React.CSSProperties; flip?: boolean }) {
  return (
    <svg
      viewBox="0 0 120 160"
      style={{ ...style, transform: `${style.transform || ''} ${flip ? 'scaleX(-1)' : ''}`.trim() }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <g fill="currentColor">
        <circle cx="62" cy="18" r="10" />
        <path d="M55 28 C50 28, 42 35, 40 48 L38 60 L28 72 L36 74 L46 62 L48 56 L52 68 L38 95 L30 120 L40 122 L54 96 L60 80 L66 96 L62 122 L72 124 L80 96 L72 68 L68 48 C66 35, 62 28, 55 28Z" />
        <path d="M40 48 L24 58 L20 70 L28 72" />
        <path d="M68 48 L85 42 L95 48 L88 54 L72 52" />
        <path d="M30 120 L22 130 L18 140 L28 138 L36 128 L40 122" />
        <path d="M62 122 L58 135 L60 148 L70 146 L72 132 L72 124" />
      </g>
    </svg>
  );
}

function FinishLine({ style }: { style: React.CSSProperties }) {
  const squares = [];
  const cols = 4;
  const rows = 20;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if ((r + c) % 2 === 0) {
        squares.push(
          <rect key={`${r}-${c}`} x={c * 6} y={r * 6} width="6" height="6" fill="currentColor" />
        );
      }
    }
  }
  return (
    <svg viewBox={`0 0 ${cols * 6} ${rows * 6}`} style={style} xmlns="http://www.w3.org/2000/svg">
      {squares}
    </svg>
  );
}

function SpeedLines() {
  return (
    <svg
      style={{
        position: 'absolute',
        bottom: '18%',
        left: 0,
        width: '100%',
        height: '120px',
        opacity: 0.06,
        pointerEvents: 'none',
      }}
      viewBox="0 0 1200 120"
      preserveAspectRatio="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <style>{`
        @keyframes dashFlow {
          from { stroke-dashoffset: 0; }
          to { stroke-dashoffset: -200; }
        }
      `}</style>
      <line x1="0" y1="30" x2="1200" y2="30" stroke="#1a4fff" strokeWidth="1" strokeDasharray="40 60" style={{ animation: 'dashFlow 4s linear infinite' }} />
      <line x1="0" y1="55" x2="1200" y2="55" stroke="#ff4400" strokeWidth="1.5" strokeDasharray="60 40" style={{ animation: 'dashFlow 3s linear infinite' }} />
      <line x1="0" y1="80" x2="1200" y2="80" stroke="#1a4fff" strokeWidth="0.8" strokeDasharray="30 70" style={{ animation: 'dashFlow 5s linear infinite' }} />
      <line x1="0" y1="100" x2="1200" y2="100" stroke="#ff4400" strokeWidth="0.6" strokeDasharray="20 80" style={{ animation: 'dashFlow 6s linear infinite' }} />
    </svg>
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
        @keyframes driftOrb1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(40px, -50px) scale(1.08); }
        }
        @keyframes driftOrb2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(-30px, 40px) scale(1.05); }
        }
        @keyframes twinkle {
          0%, 100% { opacity: 0; }
          50% { opacity: 0.8; }
        }
        @keyframes runnerGlide {
          0% { transform: translateX(-100px); opacity: 0; }
          15% { opacity: 1; }
          85% { opacity: 1; }
          100% { transform: translateX(calc(100vw + 100px)); opacity: 0; }
        }
        @keyframes runnerGlideReverse {
          0% { transform: translateX(100vw) scaleX(-1); opacity: 0; }
          15% { opacity: 1; }
          85% { opacity: 1; }
          100% { transform: translateX(-200px) scaleX(-1); opacity: 0; }
        }
        @keyframes pulseTrack {
          0%, 100% { opacity: 0.03; }
          50% { opacity: 0.07; }
        }
      `}</style>

      <div style={{
        position: 'absolute',
        top: '10%',
        left: '5%',
        width: '400px',
        height: '400px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(26, 79, 255, 0.2) 0%, transparent 70%)',
        filter: 'blur(60px)',
        animation: 'driftOrb1 16s ease-in-out infinite',
      }} />

      <div style={{
        position: 'absolute',
        bottom: '10%',
        right: '5%',
        width: '350px',
        height: '350px',
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255, 68, 0, 0.15) 0%, transparent 70%)',
        filter: 'blur(60px)',
        animation: 'driftOrb2 20s ease-in-out infinite',
      }} />

      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: `${10 + Math.random() * 80}%`,
            left: `${10 + Math.random() * 80}%`,
            width: '2px',
            height: '2px',
            borderRadius: '50%',
            background: i % 4 === 0 ? 'rgba(255, 100, 50, 0.7)' : 'rgba(100, 150, 255, 0.7)',
            animation: `twinkle ${4 + Math.random() * 6}s ease-in-out ${Math.random() * 6}s infinite`,
          }}
        />
      ))}

      <RunnerSilhouette
        style={{
          position: 'absolute',
          bottom: '8%',
          left: 0,
          width: '45px',
          height: '60px',
          color: 'rgba(26, 79, 255, 0.08)',
          animation: 'runnerGlide 18s linear infinite',
        }}
      />

      <RunnerSilhouette
        style={{
          position: 'absolute',
          bottom: '12%',
          left: 0,
          width: '35px',
          height: '48px',
          color: 'rgba(255, 68, 0, 0.06)',
          animation: 'runnerGlide 24s linear 6s infinite',
        }}
      />

      <RunnerSilhouette
        flip
        style={{
          position: 'absolute',
          top: '10%',
          right: 0,
          width: '30px',
          height: '40px',
          color: 'rgba(26, 79, 255, 0.05)',
          animation: 'runnerGlideReverse 22s linear 3s infinite',
        }}
      />

      <SpeedLines />

      <FinishLine style={{
        position: 'absolute',
        right: '6%',
        bottom: '5%',
        width: '18px',
        height: '90px',
        color: 'rgba(255, 255, 255, 0.04)',
        animation: 'pulseTrack 6s ease-in-out infinite',
      }} />

      <svg
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          width: '100%',
          height: '80px',
          opacity: 0.04,
          pointerEvents: 'none',
        }}
        viewBox="0 0 1200 80"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <ellipse cx="600" cy="70" rx="600" ry="15" fill="none" stroke="#1a4fff" strokeWidth="1" strokeDasharray="8 12" />
        <ellipse cx="600" cy="60" rx="550" ry="12" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="0.5" strokeDasharray="4 16" />
      </svg>
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
