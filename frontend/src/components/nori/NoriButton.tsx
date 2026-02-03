import React, { useState } from 'react';
import NoriChat from './NoriChat';
import noriAvatar from '@assets/Nori_1768273889454.png';

const NoriButton: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-110"
        title="Falar com Nori"
      >
        <img src={noriAvatar} alt="Nori" className="w-20 h-20 drop-shadow-lg" />
        <span className="absolute top-0 right-0 w-4 h-4 bg-green-500 rounded-full border-2 border-white animate-pulse" />
      </button>
      
      <NoriChat isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default NoriButton;
