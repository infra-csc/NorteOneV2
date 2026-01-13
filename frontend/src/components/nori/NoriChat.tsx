import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  MessageCircle, 
  X, 
  Send, 
  Mic, 
  MicOff, 
  Volume2, 
  VolumeX,
  Sparkles,
  BarChart3,
  Loader2,
  ListTodo,
  Plus
} from 'lucide-react';
import { noriService, ChatMessage, tarefasService, TarefaCreate } from '../../services/api';
import { mockEvents } from '../../data/mockMarketingData';

interface NoriChatProps {
  isOpen: boolean;
  onClose: () => void;
}

const NoriChat: React.FC<NoriChatProps> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeechEnabled, setIsSpeechEnabled] = useState(true);
  const [greeting, setGreeting] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && messages.length === 0) {
      fetchGreeting();
    }
  }, [isOpen]);

  const fetchGreeting = async () => {
    try {
      const response = await noriService.getGreeting();
      setGreeting(response.greeting);
      if (isSpeechEnabled) {
        speak(response.greeting);
      }
    } catch (error) {
      setGreeting('Olá! Eu sou o Nori, seu assistente virtual. Como posso ajudar?');
    }
  };

  const speak = (text: string) => {
    if (!isSpeechEnabled || !('speechSynthesis' in window)) return;
    
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'pt-BR';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    
    const voices = window.speechSynthesis.getVoices();
    const ptVoice = voices.find(v => v.lang.startsWith('pt'));
    if (ptVoice) {
      utterance.voice = ptVoice;
    }
    
    window.speechSynthesis.speak(utterance);
  };

  const startListening = useCallback(() => {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      alert('Seu navegador não suporta reconhecimento de voz');
      return;
    }

    const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    recognitionRef.current = new SpeechRecognition();
    recognitionRef.current.continuous = false;
    recognitionRef.current.interimResults = false;
    recognitionRef.current.lang = 'pt-BR';

    recognitionRef.current.onstart = () => {
      setIsListening(true);
    };

    recognitionRef.current.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInputValue(transcript);
      setIsListening(false);
    };

    recognitionRef.current.onerror = () => {
      setIsListening(false);
    };

    recognitionRef.current.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current.start();
  }, []);

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  };

  const sendMessage = async (messageText?: string) => {
    const text = messageText || inputValue.trim();
    if (!text || isLoading) return;

    const userMessage: ChatMessage = { role: 'user', content: text };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const eventsData = mockEvents.map(e => ({
        name: e.name,
        location: e.location,
        category: e.category,
        dMinus: e.dMinus,
        currentSales: e.currentSales,
        salesGoal: e.salesGoal,
        isc: e.isc,
        iscStatus: e.iscStatus,
        iscComponents: e.iscComponents,
        suggestedAction: e.suggestedAction
      }));

      const response = await noriService.chat(text, messages, eventsData);
      
      const assistantMessage: ChatMessage = { role: 'assistant', content: response.response };
      setMessages(prev => [...prev, assistantMessage]);
      
      if (isSpeechEnabled) {
        speak(response.response);
      }
    } catch (error) {
      const errorMessage: ChatMessage = { 
        role: 'assistant', 
        content: 'Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente.' 
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const analyzeEvents = async () => {
    setIsLoading(true);
    const analysisMessage: ChatMessage = { 
      role: 'user', 
      content: 'Analise o cenário atual dos eventos de marketing' 
    };
    setMessages(prev => [...prev, analysisMessage]);

    try {
      const eventsData = mockEvents.map(e => ({
        name: e.name,
        location: e.location,
        category: e.category,
        dMinus: e.dMinus,
        currentSales: e.currentSales,
        salesGoal: e.salesGoal,
        isc: e.isc,
        iscStatus: e.iscStatus,
        iscComponents: e.iscComponents,
        suggestedAction: e.suggestedAction
      }));

      const response = await noriService.analyze(eventsData);
      
      const assistantMessage: ChatMessage = { role: 'assistant', content: response.response };
      setMessages(prev => [...prev, assistantMessage]);
      
      if (isSpeechEnabled) {
        speak(response.response);
      }
    } catch (error) {
      const errorMessage: ChatMessage = { 
        role: 'assistant', 
        content: 'Desculpe, ocorreu um erro ao analisar os dados. Tente novamente.' 
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl h-[80vh] flex flex-col overflow-hidden border border-gray-200 dark:border-gray-700">
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">Nori</h2>
              <p className="text-white/80 text-sm">Assistente Virtual</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsSpeechEnabled(!isSpeechEnabled)}
              className="p-2 rounded-full hover:bg-white/20 transition-colors"
              title={isSpeechEnabled ? 'Desativar voz' : 'Ativar voz'}
            >
              {isSpeechEnabled ? (
                <Volume2 className="w-5 h-5 text-white" />
              ) : (
                <VolumeX className="w-5 h-5 text-white/60" />
              )}
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-full hover:bg-white/20 transition-colors"
            >
              <X className="w-5 h-5 text-white" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {greeting && messages.length === 0 && (
            <div className="flex gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl rounded-tl-sm p-4 max-w-[80%]">
                <p className="text-gray-800 dark:text-gray-200">{greeting}</p>
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              {message.role === 'assistant' && (
                <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full flex items-center justify-center flex-shrink-0">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
              )}
              <div
                className={`rounded-2xl p-4 max-w-[80%] ${
                  message.role === 'user'
                    ? 'bg-indigo-600 text-white rounded-tr-sm'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-tl-sm'
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl rounded-tl-sm p-4">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
                  <span className="text-gray-600 dark:text-gray-400">Pensando...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex gap-2 mb-3 flex-wrap">
            <button
              onClick={analyzeEvents}
              disabled={isLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-full text-sm font-medium hover:from-green-600 hover:to-emerald-600 transition-colors disabled:opacity-50"
            >
              <BarChart3 className="w-4 h-4" />
              Analisar Eventos
            </button>
            <button
              onClick={() => sendMessage('Quais são minhas tarefas pendentes?')}
              disabled={isLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-full text-sm font-medium hover:from-amber-600 hover:to-orange-600 transition-colors disabled:opacity-50"
            >
              <ListTodo className="w-4 h-4" />
              Minhas Tarefas
            </button>
          </div>
          
          <div className="flex gap-2">
            <button
              onClick={isListening ? stopListening : startListening}
              className={`p-3 rounded-full transition-colors ${
                isListening 
                  ? 'bg-red-500 text-white animate-pulse' 
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
              }`}
              title={isListening ? 'Parar de ouvir' : 'Falar com Nori'}
            >
              {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>
            
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Digite sua mensagem ou clique no microfone..."
              className="flex-1 px-4 py-3 bg-gray-100 dark:bg-gray-700 border-0 rounded-full text-gray-800 dark:text-white placeholder-gray-500 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              disabled={isLoading}
            />
            
            <button
              onClick={() => sendMessage()}
              disabled={!inputValue.trim() || isLoading}
              className="p-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-full hover:from-indigo-700 hover:to-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NoriChat;
