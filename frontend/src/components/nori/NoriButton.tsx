import React, { useState } from 'react';
import { Sparkles } from 'lucide-react';
import NoriChat from './NoriChat';

const NoriButton: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 w-14 h-14 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center group hover:scale-110"
        title="Falar com Nori"
      >
        <Sparkles className="w-7 h-7 text-white group-hover:animate-pulse" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white animate-pulse" />
      </button>
      
      <NoriChat isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default NoriButton;
