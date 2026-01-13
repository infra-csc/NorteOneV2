import React, { useState } from 'react';
import NoriChat from './NoriChat';
import noriAvatar from '@assets/Nori_1768273889454.png';

const NoriButton: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 w-16 h-16 rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center group hover:scale-110 overflow-hidden border-2 border-indigo-500/50 bg-gray-900"
        title="Falar com Nori"
      >
        <img src={noriAvatar} alt="Nori" className="w-[140%] h-[140%] object-cover object-center scale-110" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-white animate-pulse" />
      </button>
      
      <NoriChat isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default NoriButton;
