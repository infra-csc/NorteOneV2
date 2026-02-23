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
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L39,40 L41,38
   M41,30 L44,46 Q46,52,48,54 L42,68 L36,82 Q34,88,36,90 L40,90 Q42,88,44,84 L52,66
   M44,46 Q50,52,54,54 L60,70 L66,84 Q68,88,66,90 L62,90 Q60,88,58,84 L50,66
   M41,30 L30,24 Q26,22,24,24 L26,28 Q28,30,32,30 L40,34
   M43,28 L62,22 Q66,20,68,22 L66,26 Q64,28,60,28 L44,32`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L43,46 Q44,52,44,56 L38,72 L34,86 Q32,90,34,92 L38,92 Q40,90,42,86 L48,68
   M43,46 Q50,50,56,50 L64,66 L70,80 Q72,84,70,86 L66,86 Q64,84,62,80 L54,64
   M41,30 L28,28 Q24,26,22,28 L24,32 Q26,34,30,32 L40,34
   M43,28 L64,18 Q68,16,70,18 L68,22 Q66,24,62,24 L44,30`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L42,46 Q42,54,40,58 L34,76 L32,88 Q30,92,32,94 L36,94 Q38,92,40,88 L46,72
   M42,46 Q48,48,54,46 L66,58 L74,72 Q76,76,74,78 L70,78 Q68,76,66,72 L56,58
   M41,30 L26,32 Q22,32,20,34 L22,38 Q24,38,28,36 L40,34
   M43,28 L66,14 Q70,12,72,14 L70,18 Q68,20,64,20 L44,28`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L42,46 Q42,54,42,58 L38,78 L36,90 Q34,94,36,94 L40,94 Q42,92,42,88 L46,72
   M42,46 Q46,48,50,48 L58,56 L66,68 Q68,72,66,74 L62,74 Q60,72,58,68 L50,56
   M41,30 L26,36 Q22,36,20,38 L22,42 Q24,42,28,40 L40,36
   M43,28 L64,16 Q68,14,70,16 L68,20 Q66,22,62,22 L44,28`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L44,46 Q46,52,48,54 L46,70 L44,84 Q42,90,44,92 L48,92 Q50,90,50,86 L50,68
   M44,46 Q48,50,52,50 L56,62 L60,76 Q62,82,60,84 L56,84 Q54,82,54,78 L50,64
   M41,30 L28,38 Q24,40,22,42 L24,44 Q26,44,30,42 L40,36
   M43,28 L60,18 Q64,16,66,18 L64,22 Q62,24,58,24 L44,28`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L46,46 Q50,50,52,50 L54,66 L54,82 Q54,88,52,90 L48,90 Q46,88,46,84 L48,68
   M46,46 Q44,50,42,52 L36,66 L32,80 Q30,86,32,88 L36,88 Q38,86,38,82 L42,66
   M41,30 L32,38 Q28,40,26,42 L28,44 Q30,44,34,42 L42,36
   M43,28 L56,20 Q60,18,62,20 L60,24 Q58,26,54,26 L44,28`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L48,46 Q52,48,56,46 L62,62 L66,78 Q68,84,66,86 L62,86 Q60,84,58,78 L52,62
   M48,46 Q44,50,40,54 L32,70 L28,84 Q26,90,28,92 L32,92 Q34,90,36,86 L42,70
   M41,30 L34,36 Q30,38,28,40 L30,42 Q32,42,36,40 L42,34
   M43,28 L54,22 Q58,20,60,22 L58,26 Q56,28,52,28 L44,28`,
  `M50,12 a7,7,0,1,1,0.1,0 Z
   M47,20 C44,20,42,24,41,30 L40,40 L42,38
   M41,30 L46,46 Q48,52,50,56 L46,72 L40,86 Q38,90,40,92 L44,92 Q46,90,46,86 L50,70
   M46,46 Q50,50,54,48 L62,62 L68,76 Q70,80,68,82 L64,82 Q62,80,60,76 L54,62
   M41,30 L30,28 Q26,28,24,30 L26,34 Q28,34,32,32 L40,32
   M43,28 L60,20 Q64,18,66,20 L64,24 Q62,26,58,26 L44,28`,
];

const swimmerFrames = [
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,40,50,38 Q66,36,78,38 Q86,40,90,42
   M50,38 L48,28 Q46,22,42,18 L44,16 Q48,14,50,18 L52,24 L54,32
   M50,38 L48,50 Q46,56,42,60 L40,62 Q44,58,46,54 L48,46
   M78,38 L82,30 Q84,26,88,24 L90,22 Q88,26,86,30 L82,36
   M78,38 L80,46 Q82,50,86,52 L88,54 Q84,52,82,48 L80,42`,
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,41,50,40 Q66,38,78,40 Q86,42,90,44
   M50,40 L44,32 Q40,26,36,24 L34,22 Q38,22,40,26 L46,34
   M50,40 L52,50 Q54,54,56,56 L58,56 Q56,54,54,50 L52,44
   M78,40 L84,34 Q88,30,90,28 L92,28 Q90,32,86,36 L82,40
   M78,40 L76,48 Q74,54,72,58 L70,60 Q72,56,74,52 L76,46`,
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,42,50,42 Q66,42,78,42 Q86,42,90,44
   M50,42 L40,36 Q34,32,30,32 L28,32 Q32,30,36,32 L44,38
   M50,42 L56,50 Q60,54,64,54 L66,52 Q62,54,58,52 L52,46
   M78,42 L86,38 Q90,36,92,36 L94,36 Q90,38,86,40 L80,42
   M78,42 L72,50 Q68,56,64,60 L62,62 Q66,58,70,52 L76,46`,
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,42,50,44 Q66,44,78,42 Q86,42,90,42
   M50,44 L38,40 Q32,38,28,40 L26,42 Q30,38,34,38 L44,42
   M50,44 L58,48 Q62,50,66,48 L68,46 Q64,50,60,50 L52,46
   M78,42 L86,42 Q90,42,92,44 L92,46 Q90,44,86,44 L80,44
   M78,42 L70,48 Q66,54,62,58 L60,60 Q64,56,68,50 L76,44`,
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,44,50,46 Q66,46,78,44 Q86,42,90,42
   M50,46 L40,46 Q34,46,30,48 L28,50 Q32,46,36,46 L46,46
   M50,46 L56,44 Q60,42,64,42 L66,42 Q62,44,58,46 L52,46
   M78,44 L84,46 Q88,48,90,50 L90,52 Q88,48,84,46 L80,44
   M78,44 L72,44 Q68,46,64,50 L62,52 Q66,48,70,44 L76,44`,
  `M14,48 a5.5,5.5,0,1,1,0.1,0 Z
   M22,44 Q34,44,50,44 Q66,44,78,44 Q86,44,90,44
   M50,44 L46,52 Q44,58,42,62 L40,64 Q42,60,44,56 L48,48
   M50,44 L52,36 Q54,30,56,26 L58,24 Q56,28,54,34 L52,40
   M78,44 L80,50 Q82,54,84,56 L86,56 Q84,54,82,50 L80,46
   M78,44 L80,38 Q82,32,84,28 L86,26 Q84,30,82,36 L80,42`,
];

const cyclistFrames = [
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L36,52 L28,62 Q26,66,28,66 L32,64
   M42,42 L48,54 L52,64 Q54,68,52,68 L48,66`,
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L32,50 L24,56 Q22,60,24,62 L28,60
   M42,42 L50,50 L56,60 Q58,64,56,64 L52,62`,
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L30,46 L22,48 Q20,50,22,52 L26,52
   M42,42 L52,46 L58,52 Q60,56,58,58 L54,56`,
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L32,44 L24,42 Q22,42,22,44 L24,48
   M42,42 L52,42 L60,46 Q62,48,60,50 L56,50`,
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L36,40 L28,38 Q24,38,24,40 L26,44
   M42,42 L50,40 L58,42 Q62,44,60,46 L56,46`,
  `M30,58 a10,10,0,1,1,0.1,0 Z M30,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M70,58 a10,10,0,1,1,0.1,0 Z M70,58 m-4,0 a4,4,0,1,1,8,0 a4,4,0,1,1,-8,0
   M30,58 L42,42 L48,36 L46,28
   M46,18 a5,5,0,1,1,0.1,0 Z
   M42,42 L56,46 L70,58
   M42,42 L54,40 L62,44
   M48,36 L56,34 Q60,33,62,34
   M42,42 L38,46 L30,50 Q26,52,28,54 L32,54
   M42,42 L50,46 L56,54 Q58,58,56,60 L52,58`,
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
    }, 100);
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
        {runnerFrames.map((d, i) => (
          <path
            key={i}
            d={d}
            fill="currentColor"
            style={{
              opacity: i === frame ? 1 : 0,
              transition: 'opacity 80ms ease',
            }}
          />
        ))}
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
    }, 180);
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
        viewBox="0 0 100 80"
        style={{
          position: 'absolute',
          top,
          right: 0,
          width: `${size * 1.6}px`,
          height: `${size * 0.9}px`,
          color,
          opacity,
          animation: `${animId} ${duration}s linear ${delay}s infinite`,
          pointerEvents: 'none',
          filter: `drop-shadow(0 0 ${size * 0.12}px ${color})`,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {swimmerFrames.map((d, i) => (
          <path
            key={i}
            d={d}
            fill="currentColor"
            style={{
              opacity: i === frame ? 1 : 0,
              transition: 'opacity 140ms ease',
            }}
          />
        ))}
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

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % cyclistFrames.length);
    }, 120);
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
        viewBox="0 0 100 80"
        style={{
          position: 'absolute',
          bottom,
          left: 0,
          width: `${size * 1.3}px`,
          height: `${size}px`,
          color,
          opacity,
          animation: `${animId} ${duration}s linear ${delay}s infinite`,
          pointerEvents: 'none',
          filter: `drop-shadow(0 0 ${size * 0.12}px ${color})`,
        }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {cyclistFrames.map((d, i) => (
          <path
            key={i}
            d={d}
            fill="currentColor"
            style={{
              opacity: i === frame ? 1 : 0,
              transition: 'opacity 100ms ease',
            }}
          />
        ))}
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

      <AnimatedRunner bottom="4%" duration={10} delay={0} color="#3a6fff" size={90} opacity={0.25} />
      <AnimatedRunner bottom="12%" duration={14} delay={5} color="#ff6633" size={70} opacity={0.18} />

      <AnimatedSwimmer top="6%" duration={14} delay={1} color="#3a6fff" size={70} opacity={0.2} />
      <AnimatedSwimmer top="14%" duration={18} delay={8} color="#ff6633" size={55} opacity={0.15} />

      <AnimatedCyclist bottom="16%" duration={8} delay={3} color="#ff6633" size={80} opacity={0.22} />
      <AnimatedCyclist bottom="22%" duration={12} delay={9} color="#3a6fff" size={60} opacity={0.15} />

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
