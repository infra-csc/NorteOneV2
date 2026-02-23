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

const runnerFrames = [
  "M50,15 a8,8,0,1,1,0.1,0 Z M46,24 L42,40 L30,52 L36,55 L48,44 L50,38 L52,50 L36,72 L28,92 L38,93 L52,74 L56,58 L64,78 L68,92 L78,90 L70,70 L62,50 L58,38 C56,28,50,24,46,24 Z M42,34 L26,30 L22,36 L30,38 Z M58,32 L74,26 L80,30 L72,36 Z",
  "M50,15 a8,8,0,1,1,0.1,0 Z M46,24 L44,40 L50,56 L40,78 L32,94 L42,95 L52,78 L54,60 L56,78 L60,94 L70,93 L64,74 L58,52 L56,38 C54,28,48,24,46,24 Z M44,34 L28,38 L24,44 L32,44 Z M56,34 L72,38 L76,44 L68,44 Z",
  "M50,15 a8,8,0,1,1,0.1,0 Z M46,24 L40,40 L26,48 L30,54 L44,46 L48,38 L50,54 L42,76 L48,94 L56,92 L54,74 L56,56 L60,72 L72,88 L78,84 L68,68 L58,48 L56,36 C54,28,48,24,46,24 Z M40,32 L24,26 L20,32 L28,36 Z M56,30 L76,28 L82,34 L74,38 Z",
  "M50,15 a8,8,0,1,1,0.1,0 Z M46,24 L44,40 L50,56 L40,78 L32,94 L42,95 L52,78 L54,60 L56,78 L60,94 L70,93 L64,74 L58,52 L56,38 C54,28,48,24,46,24 Z M44,34 L28,38 L24,44 L32,44 Z M56,34 L72,38 L76,44 L68,44 Z",
];

const swimmerFrames = [
  "M18,50 a6,6,0,1,1,0.1,0 Z M26,46 L50,42 L68,38 L80,40 L90,44 L80,42 L68,42 L50,46 L34,50 Z M50,42 L48,54 L44,60 L50,58 L54,50 Z M50,46 L48,34 L44,28 L50,30 L54,38 Z M80,40 L84,48 L88,54 L84,50 L80,44 Z M80,42 L84,34 L88,28 L84,32 L80,40 Z",
  "M18,50 a6,6,0,1,1,0.1,0 Z M26,46 L50,44 L68,42 L80,44 L90,46 L80,44 L68,44 L50,46 L34,48 Z M50,44 L46,50 L42,52 L48,52 L52,48 Z M50,46 L46,42 L42,40 L48,40 L52,44 Z M80,44 L82,50 L86,52 L84,48 L80,46 Z M80,44 L82,38 L86,36 L84,40 L80,44 Z",
  "M18,50 a6,6,0,1,1,0.1,0 Z M26,48 L50,46 L68,44 L80,42 L90,44 L80,44 L68,46 L50,48 L34,50 Z M50,46 L54,56 L58,60 L54,56 L50,50 Z M50,48 L54,38 L58,34 L54,38 L50,44 Z M80,42 L78,50 L76,56 L78,52 L80,46 Z M80,44 L78,36 L76,30 L78,34 L80,40 Z",
];

const cyclistFrames = [
  "M50,20 a6,6,0,1,1,0.1,0 Z M48,28 L44,44 L40,44 L46,48 L48,44 Z M36,56 a12,12,0,1,1,0.1,0 Z M64,56 a12,12,0,1,1,0.1,0 Z M44,44 L38,56 L32,64 Z M44,44 L46,56 L50,64 Z M48,44 L56,48 L64,48 L64,44 L56,42 Z M48,28 L56,26 L60,28 L56,30 Z M36,56 L64,56",
  "M50,20 a6,6,0,1,1,0.1,0 Z M48,28 L44,44 L40,44 L46,48 L48,44 Z M36,56 a12,12,0,1,1,0.1,0 Z M64,56 a12,12,0,1,1,0.1,0 Z M44,44 L32,58 L28,54 Z M44,44 L50,58 L54,54 Z M48,44 L56,48 L64,48 L64,44 L56,42 Z M48,28 L56,26 L60,28 L56,30 Z M36,56 L64,56",
  "M50,20 a6,6,0,1,1,0.1,0 Z M48,28 L44,44 L40,44 L46,48 L48,44 Z M36,56 a12,12,0,1,1,0.1,0 Z M64,56 a12,12,0,1,1,0.1,0 Z M44,44 L42,64 L38,68 Z M44,44 L46,64 L50,68 Z M48,44 L56,48 L64,48 L64,44 L56,42 Z M48,28 L56,26 L60,28 L56,30 Z M36,56 L64,56",
];

function AnimatedRunner({ bottom, duration, delay, color, size, opacity }: {
  bottom: string;
  duration: number;
  delay: number;
  color: string;
  size: number;
  opacity: number;
}) {
  const [frame, setFrame] = useState(0);
  const animId = useMemo(() => `runner-${Math.random().toString(36).slice(2, 8)}`, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % runnerFrames.length);
    }, 150);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <style>{`
        @keyframes ${animId} {
          0% { transform: translateX(-${size + 20}px); }
          100% { transform: translateX(calc(100vw + ${size + 20}px)); }
        }
      `}</style>
      <svg
        viewBox="0 0 100 100"
        style={{
          position: 'absolute',
          bottom,
          left: 0,
          width: `${size}px`,
          height: `${size}px`,
          color,
          opacity,
          animation: `${animId} ${duration}s linear ${delay}s infinite`,
          pointerEvents: 'none',
          filter: `drop-shadow(0 0 ${size * 0.15}px ${color})`,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d={runnerFrames[frame]} fill="currentColor" />
      </svg>
    </>
  );
}

function AnimatedSwimmer({ top, duration, delay, color, size, opacity }: {
  top: string;
  duration: number;
  delay: number;
  color: string;
  size: number;
  opacity: number;
}) {
  const [frame, setFrame] = useState(0);
  const animId = useMemo(() => `swimmer-${Math.random().toString(36).slice(2, 8)}`, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % swimmerFrames.length);
    }, 250);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <style>{`
        @keyframes ${animId} {
          0% { transform: translateX(calc(100vw + ${size + 20}px)); }
          100% { transform: translateX(-${size + 20}px); }
        }
      `}</style>
      <svg
        viewBox="0 0 100 100"
        style={{
          position: 'absolute',
          top,
          right: 0,
          width: `${size * 1.4}px`,
          height: `${size * 0.7}px`,
          color,
          opacity,
          animation: `${animId} ${duration}s linear ${delay}s infinite`,
          pointerEvents: 'none',
          filter: `drop-shadow(0 0 ${size * 0.12}px ${color})`,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d={swimmerFrames[frame]} fill="currentColor" />
      </svg>
    </>
  );
}

function AnimatedCyclist({ bottom, duration, delay, color, size, opacity }: {
  bottom: string;
  duration: number;
  delay: number;
  color: string;
  size: number;
  opacity: number;
}) {
  const [frame, setFrame] = useState(0);
  const animId = useMemo(() => `cyclist-${Math.random().toString(36).slice(2, 8)}`, []);
  const wheelAnim = useMemo(() => `wheel-${Math.random().toString(36).slice(2, 8)}`, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % cyclistFrames.length);
    }, 200);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <style>{`
        @keyframes ${animId} {
          0% { transform: translateX(-${size + 20}px); }
          100% { transform: translateX(calc(100vw + ${size + 20}px)); }
        }
        @keyframes ${wheelAnim} {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
      <svg
        viewBox="0 0 100 80"
        style={{
          position: 'absolute',
          bottom,
          left: 0,
          width: `${size * 1.2}px`,
          height: `${size}px`,
          color,
          opacity,
          animation: `${animId} ${duration}s linear ${delay}s infinite`,
          pointerEvents: 'none',
          filter: `drop-shadow(0 0 ${size * 0.12}px ${color})`,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d={cyclistFrames[frame]} fill="currentColor" />
      </svg>
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
  return (
    <svg
      style={{
        position: 'absolute',
        bottom: '3%',
        left: '5%',
        width: '90%',
        height: '40px',
        opacity: 0.12,
        pointerEvents: 'none',
      }}
      viewBox="0 0 800 40"
      preserveAspectRatio="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <style>{`
        @keyframes heartbeatDash {
          from { stroke-dashoffset: 800; }
          to { stroke-dashoffset: 0; }
        }
      `}</style>
      <path
        d="M0,20 L120,20 L140,20 L155,5 L170,35 L185,10 L200,30 L215,15 L230,20 L350,20 L370,20 L385,8 L400,32 L415,12 L430,28 L445,18 L460,20 L580,20 L600,20 L615,5 L630,35 L645,10 L660,30 L675,15 L690,20 L800,20"
        fill="none"
        stroke="#ff4400"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="800"
        style={{ animation: 'heartbeatDash 4s linear infinite' }}
      />
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

      <AnimatedRunner bottom="6%" duration={12} delay={0} color="#1a4fff" size={80} opacity={0.2} />
      <AnimatedRunner bottom="10%" duration={15} delay={4} color="#ff4400" size={60} opacity={0.15} />

      <AnimatedSwimmer top="8%" duration={16} delay={2} color="#1a4fff" size={55} opacity={0.12} />

      <AnimatedCyclist bottom="14%" duration={9} delay={6} color="#ff4400" size={65} opacity={0.15} />

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
