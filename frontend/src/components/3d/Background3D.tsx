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

function SpeedTrails() {
  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' }}>
      <style>{`
        @keyframes trailSweep {
          0% { transform: translateX(-100%); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateX(200vw); opacity: 0; }
        }
      `}</style>
      {[
        { top: '82%', h: '2px', color: '#1a4fff', dur: 3, delay: 0, opacity: 0.25 },
        { top: '85%', h: '1px', color: '#ff4400', dur: 2.5, delay: 1, opacity: 0.2 },
        { top: '78%', h: '1px', color: '#1a4fff', dur: 4, delay: 2, opacity: 0.15 },
        { top: '15%', h: '1px', color: '#ff4400', dur: 3.5, delay: 0.5, opacity: 0.12 },
        { top: '88%', h: '3px', color: '#1a4fff', dur: 2, delay: 3, opacity: 0.2 },
      ].map((trail, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: trail.top,
            left: 0,
            width: '30%',
            height: trail.h,
            background: `linear-gradient(90deg, transparent, ${trail.color}, transparent)`,
            opacity: trail.opacity,
            borderRadius: '2px',
            animation: `trailSweep ${trail.dur}s linear ${trail.delay}s infinite`,
          }}
        />
      ))}
    </div>
  );
}

function HeartbeatLine() {
  const heartPath = "M0,25 L80,25 L100,25 L108,25 L114,8 L120,42 L126,4 L132,38 L138,14 L144,25 L160,25 L240,25 L260,25 L268,25 L274,10 L280,40 L286,6 L292,36 L298,16 L304,25 L320,25 L400,25 L420,25 L428,25 L434,8 L440,42 L446,4 L452,38 L458,14 L464,25 L480,25 L560,25 L580,25 L588,25 L594,10 L600,40 L606,6 L612,36 L618,16 L624,25 L640,25 L720,25 L740,25 L748,25 L754,8 L760,42 L766,4 L772,38 L778,14 L784,25 L800,25";

  return (
    <div style={{
      position: 'absolute',
      bottom: '2%',
      left: '0',
      width: '100%',
      height: '60px',
      pointerEvents: 'none',
    }}>
      <style>{`
        @keyframes heartbeatDash {
          from { stroke-dashoffset: 1600; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes heartbeatGlow {
          0%, 100% { opacity: 0.15; filter: drop-shadow(0 0 3px rgba(255, 68, 0, 0.3)); }
          50% { opacity: 0.35; filter: drop-shadow(0 0 8px rgba(255, 68, 0, 0.6)); }
        }
        @keyframes heartbeatPulse {
          0%, 100% { opacity: 0.08; }
          50% { opacity: 0.2; }
        }
      `}</style>

      <svg
        style={{
          position: 'absolute',
          bottom: 0,
          left: '2%',
          width: '96%',
          height: '60px',
          animation: 'heartbeatPulse 2s ease-in-out infinite',
        }}
        viewBox="0 0 800 50"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d={heartPath}
          fill="none"
          stroke="#ff4400"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.15"
          style={{ filter: 'blur(6px)' }}
        />
      </svg>

      <svg
        style={{
          position: 'absolute',
          bottom: 0,
          left: '2%',
          width: '96%',
          height: '60px',
          animation: 'heartbeatGlow 2s ease-in-out infinite',
        }}
        viewBox="0 0 800 50"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="heartGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ff4400" stopOpacity="0.3" />
            <stop offset="25%" stopColor="#ff6633" stopOpacity="0.8" />
            <stop offset="50%" stopColor="#ff4400" stopOpacity="1" />
            <stop offset="75%" stopColor="#ff6633" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#ff4400" stopOpacity="0.3" />
          </linearGradient>
        </defs>
        <path
          d={heartPath}
          fill="none"
          stroke="url(#heartGrad)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="1600"
          style={{ animation: 'heartbeatDash 6s linear infinite' }}
        />
      </svg>

      <svg
        style={{
          position: 'absolute',
          bottom: 0,
          left: '2%',
          width: '96%',
          height: '60px',
          opacity: 0.6,
        }}
        viewBox="0 0 800 50"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d={heartPath}
          fill="none"
          stroke="#ff4400"
          strokeWidth="0.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.15"
        />
      </svg>
    </div>
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

      <SpeedTrails />
      <HeartbeatLine />
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
