import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
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
  Square,
  TrendingUp,
  TrendingDown,
  Minus
} from 'lucide-react';
import { noriService, ChatMessage, tarefasService, TarefaCreate, marketingService, MarketingEvent } from '../../services/api';
import noriAvatar from '@assets/Nori.png';

const MiniISCGauge: React.FC<{ value: number; status: string }> = ({ value, status }) => {
  const color = status === 'accelerating' ? '#22c55e' : status === 'stable' ? '#eab308' : '#ef4444';
  const percentage = Math.min(Math.max((value / 2) * 100, 0), 100);
  
  return (
    <div className="inline-flex items-center gap-2 bg-gray-50 dark:bg-gray-600 rounded-lg px-3 py-1.5">
      <div className="relative w-12 h-6">
        <svg viewBox="0 0 48 24" className="w-full h-full">
          <path
            d="M4 20 A 20 20 0 0 1 44 20"
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path
            d="M4 20 A 20 20 0 0 1 44 20"
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={`${percentage * 0.63} 100`}
          />
        </svg>
      </div>
      <span className="font-bold text-sm" style={{ color }}>{value.toFixed(2)}</span>
    </div>
  );
};

const EventMiniCard: React.FC<{ event: MarketingEvent }> = ({ event }) => {
  const statusColors: Record<string, string> = {
    accelerating: 'border-green-500 bg-green-50 dark:bg-green-900/20',
    stable: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
    decelerating: 'border-red-500 bg-red-50 dark:bg-red-900/20'
  };
  
  const StatusIcon = event.iscStatus === 'accelerating' ? TrendingUp : 
                     event.iscStatus === 'stable' ? Minus : TrendingDown;
  const iconColor = event.iscStatus === 'accelerating' ? 'text-green-500' : 
                    event.iscStatus === 'stable' ? 'text-yellow-500' : 'text-red-500';
  
  const progress = (event.currentSales / event.salesGoal) * 100;
  
  return (
    <div className={`border-l-4 rounded-lg p-3 my-2 ${statusColors[event.iscStatus]}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <StatusIcon className={`w-4 h-4 ${iconColor}`} />
          <span className="font-semibold text-sm dark:text-gray-200">{event.name}</span>
        </div>
        <MiniISCGauge value={event.isc} status={event.iscStatus} />
      </div>
      <div className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400">
        <span>D-{event.dMinus}</span>
        <div className="flex-1">
          <div className="h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
            <div 
              className={`h-full rounded-full ${
                event.iscStatus === 'accelerating' ? 'bg-green-500' : 
                event.iscStatus === 'stable' ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${Math.min(progress, 100)}%` }}
            />
          </div>
        </div>
        <span>{event.currentSales.toLocaleString()}/{event.salesGoal.toLocaleString()}</span>
      </div>
    </div>
  );
};

interface UserOption {
  id: number;
  nome: string;
  email: string;
}

interface NoriChatProps {
  isOpen: boolean;
  onClose: () => void;
  onTaskCreated?: () => void;
}

const NoriChat: React.FC<NoriChatProps> = ({ isOpen, onClose, onTaskCreated }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeechEnabled, setIsSpeechEnabled] = useState(true);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [greeting, setGreeting] = useState('');
  const [users, setUsers] = useState<UserOption[]>([]);
  const [showUserMention, setShowUserMention] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [selectedUser, setSelectedUser] = useState<UserOption | null>(null);
  const [realEvents, setRealEvents] = useState<MarketingEvent[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const cleanTextForSpeech = (text: string): string => {
    return text
      .replace(/#{1,6}\s?/g, '')
      .replace(/\*{1,2}([^*]+)\*{1,2}/g, '$1')
      .replace(/_{1,2}([^_]+)_{1,2}/g, '$1')
      .replace(/`{1,3}[^`]*`{1,3}/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[🟢🟡🔴📊📈📉✅❌⚠️💡🎯🚀💪🔥⭐️📌🎉]/g, '')
      .replace(/[-•]\s/g, '')
      .replace(/\n{2,}/g, '. ')
      .replace(/\n/g, ', ')
      .replace(/\s{2,}/g, ' ')
      .replace(/:\s*,/g, ': ')
      .trim();
  };

  const renderFormattedMessage = (content: string) => {
    const parts = content.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-bold">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  const detectMentionedEvents = (content: string): MarketingEvent[] => {
    const mentioned: MarketingEvent[] = [];
    realEvents.forEach(event => {
      if (content.toLowerCase().includes(event.name.toLowerCase())) {
        mentioned.push(event);
      }
    });
    return mentioned.slice(0, 4);
  };

  const [showEventCards, setShowEventCards] = useState(false);
  const [lastAnalysisData, setLastAnalysisData] = useState<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && messages.length === 0) {
      fetchGreeting();
      fetchUsers();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const controller = new AbortController();
    marketingService.getEventos(undefined, controller.signal)
      .then(data => {
        if (!controller.signal.aborted) {
          setRealEvents(data.eventos);
        }
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          console.error('Erro ao carregar eventos:', err);
        }
      });
    return () => controller.abort();
  }, [isOpen]);

  const fetchUsers = async () => {
    try {
      const token = localStorage.getItem('token');
      if (token) {
        const response = await fetch('/api/users/', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setUsers(data);
        }
      }
    } catch (error) {
      console.error('Erro ao carregar usuários:', error);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    
    const lastAtIndex = value.lastIndexOf('@');
    if (lastAtIndex !== -1 && lastAtIndex === value.length - 1) {
      setShowUserMention(true);
      setMentionFilter('');
    } else if (lastAtIndex !== -1 && value.slice(lastAtIndex + 1).indexOf(' ') === -1) {
      setShowUserMention(true);
      setMentionFilter(value.slice(lastAtIndex + 1).toLowerCase());
    } else {
      setShowUserMention(false);
    }
  };

  const handleSelectUser = (user: UserOption) => {
    setSelectedUser(user);
    const lastAtIndex = inputValue.lastIndexOf('@');
    const newValue = inputValue.slice(0, lastAtIndex) + `@${user.nome} `;
    setInputValue(newValue);
    setShowUserMention(false);
    inputRef.current?.focus();
  };

  const filteredUsers = users.filter(u => 
    u.nome.toLowerCase().includes(mentionFilter) || 
    u.email.toLowerCase().includes(mentionFilter)
  );

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
    
    const cleanText = cleanTextForSpeech(text);
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'pt-BR';
    utterance.rate = 0.9;
    utterance.pitch = 0.95;
    utterance.volume = 1.0;
    
    const voices = window.speechSynthesis.getVoices();
    const maleVoices = voices.filter(v => 
      v.lang.startsWith('pt-BR') && 
      (v.name.toLowerCase().includes('google português do brasil') ||
       v.name.toLowerCase().includes('ricardo') ||
       v.name.toLowerCase().includes('daniel') ||
       v.name.toLowerCase().includes('male') ||
       (!v.name.toLowerCase().includes('female') && 
        !v.name.toLowerCase().includes('luciana') && 
        !v.name.toLowerCase().includes('francisca')))
    );
    
    const selectedVoice = maleVoices[0] || voices.find(v => v.lang.startsWith('pt-BR')) || voices.find(v => v.lang.startsWith('pt'));
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
    
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    
    window.speechSynthesis.speak(utterance);
  };

  const stopSpeaking = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
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

  const detectTaskCreation = (text: string): { isTask: boolean; taskTitle: string } => {
    const taskPatterns = [
      /^(?:criar?|crie|adicionar?|adicione|nova?)\s+(?:uma?\s+)?tarefa\s*[:\-]?\s*(.+)/i,
      /^(?:lembrar?|lembre|me\s+lembr[ea]r?)\s+(?:de\s+)?(.+)/i,
      /^(?:agendar?|agende|marcar?|marque)\s+(.+)/i,
      /^tarefa\s*[:\-]\s*(.+)/i,
      /^(?:preciso|tenho\s+que|devo)\s+(.+)/i,
    ];

    for (const pattern of taskPatterns) {
      const match = text.match(pattern);
      if (match && match[1]) {
        let taskTitle = match[1].trim();
        taskTitle = taskTitle.replace(/^(para\s+|de\s+)/i, '');
        if (taskTitle.length > 3) {
          return { isTask: true, taskTitle };
        }
      }
    }

    return { isTask: false, taskTitle: '' };
  };

  const sendMessage = async (messageText?: string) => {
    const text = messageText || inputValue.trim();
    if (!text || isLoading) return;

    const userMessage: ChatMessage = { role: 'user', content: text };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const taskDetection = detectTaskCreation(text);
      
      if (taskDetection.isTask) {
        await createQuickTask(taskDetection.taskTitle);
        setIsLoading(false);
        return;
      }

      const eventsData = realEvents.map(e => ({
        name: e.name,
        location: e.location,
        category: e.category,
        dMinus: e.dMinus,
        dMinusInscricoes: e.dMinusInscricoes,
        currentSales: e.currentSales,
        salesGoal: e.salesGoal,
        averageTicket: e.averageTicket,
        budgetTicket: e.budgetTicket,
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
      const eventsData = realEvents.map(e => ({
        name: e.name,
        location: e.location,
        category: e.category,
        dMinus: e.dMinus,
        dMinusInscricoes: e.dMinusInscricoes,
        currentSales: e.currentSales,
        salesGoal: e.salesGoal,
        averageTicket: e.averageTicket,
        budgetTicket: e.budgetTicket,
        isc: e.isc,
        iscStatus: e.iscStatus,
        iscComponents: e.iscComponents,
        suggestedAction: e.suggestedAction
      }));

      const response = await noriService.analyze(eventsData);
      
      const analysisSnapshot = {
        timestamp: new Date().toISOString(),
        events: eventsData,
        analysis: response.response
      };
      setLastAnalysisData(JSON.stringify(analysisSnapshot));
      
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
    if (e.key === 'Escape' && showUserMention) {
      setShowUserMention(false);
    }
  };

  const isEventRelatedTask = (titulo: string): boolean => {
    const keywords = ['evento', 'eventos', 'análise', 'analise', 'isc', 'marketing', 'vendas', 'crítico', 'critico', 'desacelerando', 'acelerando'];
    const lowerTitulo = titulo.toLowerCase();
    return keywords.some(kw => lowerTitulo.includes(kw));
  };

  const createQuickTask = async (titulo: string) => {
    try {
      const shouldIncludeAnalysis = isEventRelatedTask(titulo) && lastAnalysisData;
      
      const taskData: TarefaCreate = {
        titulo,
        criado_por_nori: true,
        responsavel_id: selectedUser?.id,
        dados_analise: shouldIncludeAnalysis ? lastAnalysisData : undefined
      };
      
      await tarefasService.create(taskData);
      
      const responsavelInfo = selectedUser ? ` para @${selectedUser.nome}` : '';
      const analysisInfo = shouldIncludeAnalysis ? '\n\n📊 *Dados da análise anexados à tarefa*' : '';
      const confirmMessage: ChatMessage = {
        role: 'assistant',
        content: `✅ Tarefa criada com sucesso${responsavelInfo}!\n\n**"${titulo}"**${analysisInfo}\n\nVocê pode ver suas tarefas na tela principal do Nori.`
      };
      setMessages(prev => [...prev, confirmMessage]);
      
      if (isSpeechEnabled) {
        speak(`Tarefa criada com sucesso${responsavelInfo ? ` ${responsavelInfo}` : ''}!`);
      }
      
      setSelectedUser(null);
      
      if (onTaskCreated) {
        onTaskCreated();
      }
    } catch (error) {
      console.error('Erro ao criar tarefa:', error);
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: '❌ Desculpe, não consegui criar a tarefa. Tente novamente.'
      };
      setMessages(prev => [...prev, errorMsg]);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl h-[80vh] flex flex-col overflow-hidden border border-gray-200 dark:border-gray-700">
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-indigo-400 via-purple-400 to-pink-400 p-0.5 shadow-lg">
              <div className="w-full h-full rounded-full overflow-hidden bg-white">
                <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
              </div>
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">Nori</h2>
              <p className="text-white/80 text-sm">Assistente Virtual</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isSpeaking && (
              <button
                onClick={stopSpeaking}
                className="p-2 rounded-full bg-red-500/80 hover:bg-red-500 transition-colors animate-pulse"
                title="Parar de falar"
              >
                <Square className="w-4 h-4 text-white" />
              </button>
            )}
            <button
              onClick={() => {
                if (isSpeaking) stopSpeaking();
                setIsSpeechEnabled(!isSpeechEnabled);
              }}
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
              onClick={() => {
                stopSpeaking();
                onClose();
              }}
              className="p-2 rounded-full hover:bg-white/20 transition-colors"
            >
              <X className="w-5 h-5 text-white" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {greeting && messages.length === 0 && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-0.5 flex-shrink-0">
                <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
                  <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
                </div>
              </div>
              <div className="bg-gray-100 dark:bg-gray-700 rounded-2xl rounded-tl-sm p-4 max-w-[80%]">
                <p className="text-gray-800 dark:text-gray-200">{greeting}</p>
              </div>
            </div>
          )}

          {messages.map((message, index) => {
            const mentionedEvents = message.role === 'assistant' ? detectMentionedEvents(message.content) : [];
            const isAnalysis = message.content.includes('ISC') || message.content.includes('evento') || mentionedEvents.length > 0;
            
            return (
              <div
                key={index}
                className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                {message.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-0.5 flex-shrink-0">
                <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
                  <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
                </div>
              </div>
                )}
                <div className={`max-w-[85%] ${message.role === 'user' ? '' : ''}`}>
                  <div
                    className={`rounded-2xl p-4 ${
                      message.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-sm'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-tl-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {renderFormattedMessage(message.content)}
                    </p>
                  </div>
                  
                  {message.role === 'assistant' && mentionedEvents.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 px-2">
                        <BarChart3 className="w-3 h-3" />
                        <span>Eventos mencionados</span>
                      </div>
                      {mentionedEvents.map(event => (
                        <EventMiniCard key={event.id} event={event} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {isLoading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-0.5 flex-shrink-0">
                <div className="w-full h-full rounded-full overflow-hidden bg-white dark:bg-gray-800">
                  <img src={noriAvatar} alt="Nori" className="w-full h-full object-cover scale-125" />
                </div>
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
          
          {selectedUser && (
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Responsável:</span>
              <span className="px-2 py-1 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-full text-xs font-medium flex items-center gap-1">
                @{selectedUser.nome}
                <button 
                  onClick={() => setSelectedUser(null)}
                  className="hover:text-red-500 ml-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            </div>
          )}

          <div className="flex gap-2 relative">
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
            
            <div className="flex-1 relative">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={handleInputChange}
                onKeyPress={handleKeyPress}
                placeholder="Digite sua mensagem... Use @ para mencionar"
                className="w-full px-4 py-3 bg-gray-100 dark:bg-gray-700 border-0 rounded-full text-gray-800 dark:text-white placeholder-gray-500 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                disabled={isLoading}
              />
              
              {showUserMention && filteredUsers.length > 0 && (
                <div className="absolute bottom-full left-0 right-0 mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 max-h-48 overflow-y-auto z-50">
                  <div className="p-2 border-b border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
                    Selecione um usuário para atribuir a tarefa
                  </div>
                  {filteredUsers.map(user => (
                    <button
                      key={user.id}
                      onClick={() => handleSelectUser(user)}
                      className="w-full px-4 py-2 text-left hover:bg-indigo-50 dark:hover:bg-indigo-900/20 flex items-center gap-3 transition-colors"
                    >
                      <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full flex items-center justify-center text-white text-sm font-medium">
                        {user.nome.charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-900 dark:text-white text-sm truncate">{user.nome}</p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user.email}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            <button
              onClick={() => sendMessage()}
              disabled={!inputValue.trim() || isLoading}
              className="p-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-full hover:from-indigo-700 hover:to-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
          
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
            Use @ para mencionar usuários ao criar tarefas
          </p>
        </div>
      </div>
    </div>
  );
};

export default NoriChat;
