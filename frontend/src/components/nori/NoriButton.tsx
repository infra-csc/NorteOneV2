import React, { useState } from 'react';
import NoriChat from './NoriChat';
import noriAvatar from '@assets/Nori_1768273889454.png';

const NoriButton: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 transition-all duration-300 hover:scale-110"
        title="Falar com Nori"
      >
        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-1 shadow-xl shadow-indigo-500/40 hover:shadow-indigo-500/60">
          <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
            <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
          </div>
        </div>
        <span className="absolute bottom-0 right-0 w-4 h-4 bg-green-500 rounded-full border-2 border-white animate-pulse" />
      </button>
      
      <NoriChat isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default NoriButton;
