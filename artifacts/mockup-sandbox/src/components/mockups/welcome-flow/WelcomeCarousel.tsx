import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CalendarPlus,
  TrendingUp,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  Check,
  Sun,
  Moon,
  PartyPopper,
  Mic,
  ListChecks,
  Target,
  Users,
  MapPin,
} from "lucide-react";

type Slide = {
  id: string;
  kind: "welcome" | "feature" | "nori";
  badge?: string;
  title: string;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
  glow: string;
};

const slides: Slide[] = [
  {
    id: "welcome",
    kind: "welcome",
    title: "Bem-vindo ao DW Financeiro",
    subtitle:
      "Sua central única de dados para eventos. Em poucos passos, vamos te mostrar as ferramentas que vão facilitar o seu dia a dia.",
    icon: PartyPopper,
    accent: "from-indigo-600 to-purple-600",
    glow: "from-indigo-500/30 to-purple-500/30",
  },
  {
    id: "cadastro",
    kind: "feature",
    badge: "Passo 1",
    title: "Cadastro do Evento",
    subtitle:
      "Registre e gerencie todos os seus eventos em um só lugar. Defina datas, locais, metas e configurações que alimentam toda a plataforma.",
    icon: CalendarPlus,
    accent: "from-blue-600 to-indigo-600",
    glow: "from-blue-500/30 to-indigo-500/30",
  },
  {
    id: "projecao",
    kind: "feature",
    badge: "Passo 2",
    title: "Projeção de Inscritos",
    subtitle:
      "Planeje metas de inscrições por evento e por área. Acompanhe a evolução, registre cortes e visualize o consolidado da operação.",
    icon: TrendingUp,
    accent: "from-emerald-600 to-teal-600",
    glow: "from-emerald-500/30 to-teal-500/30",
  },
  {
    id: "nori",
    kind: "nori",
    badge: "Passo 3",
    title: "Conheça a Nori",
    subtitle:
      "Sua assistente virtual inteligente. Faça perguntas por texto ou voz e receba respostas instantâneas sobre os seus dados — quando quiser.",
    icon: Sparkles,
    accent: "from-indigo-500 via-purple-500 to-pink-500",
    glow: "from-purple-500/30 to-pink-500/30",
  },
];

const featurePoints: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string }[]> = {
  cadastro: [
    { icon: CalendarPlus, label: "Datas e local do evento" },
    { icon: Target, label: "Metas de inscrição" },
    { icon: MapPin, label: "Circuito e regional" },
  ],
  projecao: [
    { icon: Target, label: "Metas por área" },
    { icon: ListChecks, label: "Cortes e ajustes" },
    { icon: Users, label: "Consolidado por kit e cliente" },
  ],
  nori: [
    { icon: Mic, label: "Pergunte por voz ou texto" },
    { icon: Sparkles, label: "Respostas com IA" },
    { icon: TrendingUp, label: "Insights sobre seus dados" },
  ],
};

export function WelcomeCarousel() {
  const [dark, setDark] = useState(true);
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [done, setDone] = useState(false);

  const slide = slides[index];
  const isLast = index === slides.length - 1;

  const go = (dir: number) => {
    const next = index + dir;
    if (next < 0 || next >= slides.length) return;
    setDirection(dir);
    setIndex(next);
  };

  const finish = () => setDone(true);

  return (
    <div className={dark ? "dark" : ""}>
      <div className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-slate-50 via-indigo-50/40 to-purple-50/40 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950/40 flex items-center justify-center p-6 transition-colors duration-500">
        {/* Animated background blobs */}
        <motion.div
          aria-hidden
          className={`pointer-events-none absolute -top-40 -left-40 h-[28rem] w-[28rem] rounded-full bg-gradient-to-br ${slide.glow} blur-3xl`}
          animate={{ scale: [1, 1.15, 1], x: [0, 30, 0], y: [0, 20, 0] }}
          transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          aria-hidden
          className={`pointer-events-none absolute -bottom-40 -right-40 h-[32rem] w-[32rem] rounded-full bg-gradient-to-br ${slide.glow} blur-3xl`}
          animate={{ scale: [1.1, 1, 1.1], x: [0, -30, 0], y: [0, -20, 0] }}
          transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
        />

        {/* Theme toggle */}
        <button
          onClick={() => setDark((d) => !d)}
          className="absolute top-6 right-6 z-20 inline-flex items-center justify-center h-11 w-11 rounded-xl border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm text-gray-600 dark:text-gray-300 shadow-sm hover:scale-105 transition-transform"
          aria-label="Alternar tema"
        >
          {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        {/* Card */}
        <div className="relative z-10 w-full max-w-3xl">
          <div className="rounded-3xl border border-gray-200/70 dark:border-gray-700/60 bg-white/90 dark:bg-gray-800/90 backdrop-blur-xl shadow-2xl shadow-indigo-500/10 overflow-hidden">
            {/* Top gradient bar */}
            <div className={`h-2 w-full bg-gradient-to-r ${slide.accent}`} />

            {/* Live region for assistive tech */}
            <div aria-live="polite" className="sr-only">
              {done
                ? "Tour concluído"
                : `Passo ${index + 1} de ${slides.length}: ${slide.title}`}
            </div>

            <AnimatePresence mode="wait" custom={direction}>
              {!done ? (
                <motion.div
                  key={slide.id}
                  custom={direction}
                  initial={{ opacity: 0, x: direction * 60 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: direction * -60 }}
                  transition={{ duration: 0.35, ease: "easeInOut" }}
                  className="px-10 py-12 sm:px-14 sm:py-16"
                >
                  {slide.badge && (
                    <span className={`inline-block mb-5 rounded-full bg-gradient-to-r ${slide.accent} px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-white shadow-sm`}>
                      {slide.badge}
                    </span>
                  )}

                  <div className="flex flex-col items-center text-center">
                    {/* Icon / Avatar */}
                    {slide.kind === "nori" ? (
                      <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: 0.1, type: "spring", stiffness: 200 }}
                        className="relative mb-7"
                      >
                        <div className={`absolute inset-0 rounded-full bg-gradient-to-br ${slide.accent} blur-xl opacity-50`} />
                        <img
                          src="/__mockup/images/nori.png"
                          alt="Nori"
                          className="relative h-28 w-28 rounded-full object-cover ring-4 ring-white/80 dark:ring-gray-700 shadow-xl"
                        />
                      </motion.div>
                    ) : (
                      <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: 0.1, type: "spring", stiffness: 200 }}
                        className={`mb-7 flex h-24 w-24 items-center justify-center rounded-3xl bg-gradient-to-br ${slide.accent} shadow-xl shadow-indigo-500/30`}
                      >
                        <slide.icon className="h-12 w-12 text-white" />
                      </motion.div>
                    )}

                    <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
                      {slide.title}
                    </h1>
                    <p className="mt-4 max-w-xl text-base sm:text-lg leading-relaxed text-gray-500 dark:text-gray-400">
                      {slide.subtitle}
                    </p>

                    {/* Feature chips */}
                    {slide.kind !== "welcome" && featurePoints[slide.id] && (
                      <div className="mt-8 grid w-full max-w-lg grid-cols-1 sm:grid-cols-3 gap-3">
                        {featurePoints[slide.id].map((point, i) => (
                          <motion.div
                            key={point.label}
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2 + i * 0.08 }}
                            className="flex items-center gap-2.5 rounded-xl border border-gray-100 dark:border-gray-700/70 bg-gray-50/80 dark:bg-gray-900/50 px-3.5 py-3 text-left"
                          >
                            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br ${slide.accent} text-white`}>
                              <point.icon className="h-4 w-4" />
                            </span>
                            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                              {point.label}
                            </span>
                          </motion.div>
                        ))}
                      </div>
                    )}

                    {/* Welcome feature preview */}
                    {slide.kind === "welcome" && (
                      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                        {[
                          { icon: CalendarPlus, label: "Cadastro" },
                          { icon: TrendingUp, label: "Projeção" },
                          { icon: Sparkles, label: "Nori" },
                        ].map((f, i) => (
                          <motion.div
                            key={f.label}
                            initial={{ opacity: 0, scale: 0.85 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.25 + i * 0.1 }}
                            className="flex items-center gap-2 rounded-full border border-indigo-100 dark:border-indigo-900/50 bg-indigo-50/70 dark:bg-indigo-950/40 px-4 py-2"
                          >
                            <f.icon className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                            <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
                              {f.label}
                            </span>
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              ) : (
                <motion.div
                  key="done"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="px-10 py-20 sm:px-14 flex flex-col items-center text-center"
                >
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 200, delay: 0.05 }}
                    className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 shadow-xl shadow-emerald-500/30"
                  >
                    <Check className="h-12 w-12 text-white" strokeWidth={3} />
                  </motion.div>
                  <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
                    Tudo pronto!
                  </h1>
                  <p className="mt-4 max-w-md text-base sm:text-lg text-gray-500 dark:text-gray-400">
                    Você já conhece o essencial. Explore o sistema no seu ritmo — a Nori está sempre por perto se precisar de ajuda.
                  </p>
                  <button
                    onClick={() => {
                      setDone(false);
                      setIndex(0);
                      setDirection(1);
                    }}
                    className="mt-8 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 hover:opacity-95 transition"
                  >
                    Rever o tour
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Footer controls */}
            {!done && (
              <div className="flex items-center justify-between gap-4 border-t border-gray-100 dark:border-gray-700/60 px-10 py-6 sm:px-14">
                {/* Skip / Back */}
                <div className="flex-1">
                  {index === 0 ? (
                    <button
                      onClick={finish}
                      className="text-sm font-medium text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
                    >
                      Pular
                    </button>
                  ) : (
                    <button
                      onClick={() => go(-1)}
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Voltar
                    </button>
                  )}
                </div>

                {/* Progress dots */}
                <div className="flex items-center gap-2">
                  {slides.map((s, i) => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setDirection(i > index ? 1 : -1);
                        setIndex(i);
                      }}
                      aria-label={`Ir para o passo ${i + 1}`}
                      aria-current={i === index ? "step" : undefined}
                      className="group"
                    >
                      <span
                        className={`block h-2 rounded-full transition-all duration-300 ${
                          i === index
                            ? "w-8 bg-gradient-to-r from-indigo-600 to-purple-600"
                            : "w-2 bg-gray-300 dark:bg-gray-600 group-hover:bg-gray-400"
                        }`}
                      />
                    </button>
                  ))}
                </div>

                {/* Next / Finish */}
                <div className="flex flex-1 justify-end">
                  {isLast ? (
                    <button
                      onClick={finish}
                      className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 hover:opacity-95 transition"
                    >
                      Começar
                      <Check className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => go(1)}
                      className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/30 hover:opacity-95 transition"
                    >
                      Avançar
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
