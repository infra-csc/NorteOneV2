import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { projetosService } from '../../services/api';
import { 
  Plus, Pencil, X, Check, Calendar, MapPin, Users, 
  Trophy, Zap, Target, Sparkles, Clock, Package,
  Image as ImageIcon, Search, Filter, Eye,
  ChevronDown, RotateCcw, DollarSign, Timer,
  Hash, Award, Ticket, Droplets, Gift, Layers,
  UserPlus, Building2, ShoppingBag, Ruler, Palette,
  TrendingUp, TrendingDown, AlertCircle, Globe, UsersRound,
  Box, Flag, Activity
} from 'lucide-react';

interface Projeto {
  id: number;
  evento: string;
  codigo: string;
  imagem_kv?: string;
}

interface HidratacaoDistancia {
  distancia: string;
  postos: number;
  doses_atleta: number;
  atletas: number;
  total: number;
}

interface HidratacaoData {
  copos_por_caixa: number;
  distancias: HidratacaoDistancia[];
  chegada: { postos: number; doses_atleta: number; atletas: number; total: number };
  ativacoes: { postos: number; doses_atleta: number; atletas: number; total: number };
}

interface CadastroEvento {
  id: number;
  projeto_id: number | null;
  nome: string;
  imagem_kv: string;
  status: string;
  modalidade: string;
  info_geral: {
    data: string;
    horario_largada: string;
    local: string;
    distancias: string[];
  };
  atletas: {
    site: { pago: number; cortesia: number; tkt_medio: number };
    grupos: { pago: number; cortesia: number; tkt_medio: number };
  };
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  pelotoes: Array<{ pelotao: string; atletas: number }>;
  cronometragem: Array<{
    distancia: string;
    pelotoes: Array<{ pelotao: string; num_inicio: number; num_fim: number; cor: string }>;
  }>;
  kit_produto: Array<{ kit: string; produtos: string[] }>;
  trofeus: number;
  hidratacao: HidratacaoData;
  faixas_preco_site: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
  faixas_preco_grupos: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
}

interface FormData {
  projeto_id: number | null;
  nome: string;
  imagem_kv: string;
  info_geral: {
    data: string;
    horario_largada: string;
    local: string;
    distancias: string[];
  };
  atletas: {
    site: { pago: number; cortesia: number; tkt_medio: number };
    grupos: { pago: number; cortesia: number; tkt_medio: number };
  };
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  pelotoes: Array<{ pelotao: string; atletas: number }>;
  cronometragem: Array<{
    distancia: string;
    pelotoes: Array<{ pelotao: string; num_inicio: number; num_fim: number; cor: string }>;
  }>;
  kit_produto: Array<{ kit: string; produtos: string[] }>;
  trofeus: number;
  hidratacao: HidratacaoData;
  faixas_preco_site: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
  faixas_preco_grupos: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
}

const distanciasOptions = ['3k', '5k', '10k', '15k', '21k', '42k'];
const pelotoesOptions = ['Quênia', 'Azul', 'Verde', 'Branco'];
const kitOptions = ['Kit Participação', 'Kit Básico', 'Kit Vip', 'Kit Plus', 'Kit Super'];
const faixaOptions = ['1', '2', '3', '4', '5'];
const coresPeitoOptions = ['Branco', 'Amarelo', 'Laranja', 'Verde', 'Azul', 'Vermelho', 'Rosa', 'Roxo', 'Preto'];

const produtosDisponiveis = [
  'Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola',
  'Moletom', 'Jaqueta', 'Boné', 'Viseira', 'Toalha', 'Squeeze', 'Munhequeira'
];

const produtosPadraoPorKit: Record<string, string[]> = {
  'Kit Participação': ['Medalha'],
  'Kit Básico': ['Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola'],
  'Kit Vip': ['Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola', 'Moletom', 'Jaqueta'],
  'Kit Plus': ['Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola', 'Boné', 'Viseira'],
  'Kit Super': ['Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola']
};

const createDefaultHidratacao = (): HidratacaoData => ({
  copos_por_caixa: 48,
  distancias: [],
  chegada: { postos: 0, doses_atleta: 0, atletas: 0, total: 0 },
  ativacoes: { postos: 0, doses_atleta: 0, atletas: 0, total: 0 }
});

const createDefaultCadastro = (): Omit<CadastroEvento, 'id'> => ({
  projeto_id: null,
  nome: '',
  imagem_kv: '',
  status: 'Em andamento',
  modalidade: 'Corrida',
  info_geral: { data: '', horario_largada: '', local: '', distancias: [] },
  atletas: {
    site: { pago: 0, cortesia: 0, tkt_medio: 0 },
    grupos: { pago: 0, cortesia: 0, tkt_medio: 0 }
  },
  retirada_kit: { local: '', data_horario: '' },
  pelotoes: [{ pelotao: '', atletas: 0 }],
  cronometragem: [],
  kit_produto: [{ kit: '', produtos: [] }],
  trofeus: 0,
  hidratacao: createDefaultHidratacao(),
  faixas_preco_site: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }],
  faixas_preco_grupos: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
});

const mockCadastros: CadastroEvento[] = [
  {
    id: 1,
    projeto_id: 1,
    nome: 'Maratona de São Paulo 2026',
    imagem_kv: 'https://images.unsplash.com/photo-1513593771513-7b58b6c4af38?w=800',
    status: 'Em andamento',
    modalidade: 'Corrida',
    info_geral: { data: '2026-04-12', horario_largada: '06:30', local: 'Ibirapuera, São Paulo - SP', distancias: ['10k', '21k', '42k'] },
    atletas: {
      site: { pago: 10000, cortesia: 2000, tkt_medio: 199.90 },
      grupos: { pago: 2500, cortesia: 500, tkt_medio: 159.90 }
    },
    retirada_kit: { local: 'Pavilhão do Ibirapuera', data_horario: '2026-04-11T10:00' },
    pelotoes: [{ pelotao: 'Quênia', atletas: 50 }, { pelotao: 'Azul', atletas: 2000 }, { pelotao: 'Verde', atletas: 5000 }],
    cronometragem: [
      { distancia: '10k', pelotoes: [{ pelotao: 'Quênia', num_inicio: 1, num_fim: 50, cor: 'Amarelo' }, { pelotao: 'Azul', num_inicio: 51, num_fim: 2000, cor: 'Azul' }] },
      { distancia: '21k', pelotoes: [{ pelotao: 'Verde', num_inicio: 2001, num_fim: 5000, cor: 'Verde' }] }
    ],
    kit_produto: [
      { kit: 'Kit Básico', produtos: ['Camiseta', 'Medalha', 'Garrafa', 'Sacochila'] },
      { kit: 'Kit Vip', produtos: ['Camiseta', 'Medalha', 'Moletom'] }
    ],
    trofeus: 50,
    hidratacao: {
      copos_por_caixa: 48,
      distancias: [
        { distancia: '10k', postos: 2, doses_atleta: 1.5, atletas: 3000, total: 9000 },
        { distancia: '21k', postos: 4, doses_atleta: 2, atletas: 5000, total: 40000 },
        { distancia: '42k', postos: 6, doses_atleta: 3, atletas: 2000, total: 36000 }
      ],
      chegada: { postos: 1, doses_atleta: 1, atletas: 10000, total: 10000 },
      ativacoes: { postos: 2, doses_atleta: 0.5, atletas: 1000, total: 1000 }
    },
    faixas_preco_site: [{ faixa: '1', qtd: 4000, tkt_medio: 149.90, total: 599600 }, { faixa: '2', qtd: 4000, tkt_medio: 199.90, total: 799600 }, { faixa: '3', qtd: 4000, tkt_medio: 249.90, total: 999600 }],
    faixas_preco_grupos: [{ faixa: '1', qtd: 1500, tkt_medio: 129.90, total: 194850 }, { faixa: '2', qtd: 1500, tkt_medio: 169.90, total: 254850 }]
  },
  {
    id: 2,
    projeto_id: 2,
    nome: 'Night Run Rio 2026',
    imagem_kv: 'https://images.unsplash.com/photo-1552674605-db6ffd4facb5?w=800',
    status: 'Em andamento',
    modalidade: 'Corrida',
    info_geral: { data: '2026-06-20', horario_largada: '20:00', local: 'Aterro do Flamengo, Rio de Janeiro - RJ', distancias: ['5k', '10k'] },
    atletas: {
      site: { pago: 5500, cortesia: 600, tkt_medio: 139.90 },
      grupos: { pago: 1700, cortesia: 200, tkt_medio: 109.90 }
    },
    retirada_kit: { local: 'Marina da Glória', data_horario: '2026-06-19T14:00' },
    pelotoes: [{ pelotao: 'Azul', atletas: 3000 }, { pelotao: 'Verde', atletas: 5000 }],
    cronometragem: [
      { distancia: '5k', pelotoes: [{ pelotao: 'Azul', num_inicio: 1, num_fim: 3000, cor: 'Azul' }] },
      { distancia: '10k', pelotoes: [{ pelotao: 'Verde', num_inicio: 3001, num_fim: 8000, cor: 'Verde' }] }
    ],
    kit_produto: [{ kit: 'Kit Básico', produtos: ['Camiseta', 'Medalha'] }],
    trofeus: 30,
    hidratacao: {
      copos_por_caixa: 48,
      distancias: [
        { distancia: '5k', postos: 1, doses_atleta: 1, atletas: 3000, total: 3000 },
        { distancia: '10k', postos: 2, doses_atleta: 1.5, atletas: 5000, total: 15000 }
      ],
      chegada: { postos: 1, doses_atleta: 1, atletas: 8000, total: 8000 },
      ativacoes: { postos: 1, doses_atleta: 0.5, atletas: 500, total: 250 }
    },
    faixas_preco_site: [{ faixa: '1', qtd: 3000, tkt_medio: 99.90, total: 299700 }, { faixa: '2', qtd: 3100, tkt_medio: 159.90, total: 495690 }],
    faixas_preco_grupos: [{ faixa: '1', qtd: 1900, tkt_medio: 89.90, total: 170810 }]
  }
];

const getStatusStyle = (status: string) => {
  switch (status) {
    case 'Em andamento':
      return { bg: 'bg-emerald-500/20', text: 'text-emerald-400', border: 'border-emerald-500/50', icon: <Zap className="w-3 h-3" /> };
    case 'Concluído':
      return { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/50', icon: <Check className="w-3 h-3" /> };
    case 'Cancelado':
      return { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50', icon: <X className="w-3 h-3" /> };
    default:
      return { bg: 'bg-gray-500/20', text: 'text-gray-400', border: 'border-gray-500/50', icon: null };
  }
};

const formatDateDisplay = (dateString: string): string => {
  if (!dateString) return '-';
  const parts = dateString.split('T')[0].split('-');
  if (parts.length === 3) {
    const [year, month, day] = parts;
    const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit' });
  }
  return dateString;
};

const formatCurrency = (value: number): string => {
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
};

const tabs = [
  { id: 'info_geral', label: 'Info Geral', icon: Calendar },
  { id: 'atletas', label: 'Atletas', icon: Users },
  { id: 'faixas_preco_site', label: 'Faixa Preço - Site', icon: Globe },
  { id: 'faixas_preco_grupos', label: 'Faixa Preço - Grupos', icon: UsersRound },
  { id: 'retirada_kit', label: 'Retirada Kit', icon: Package },
  { id: 'pelotoes', label: 'Pelotões', icon: Layers },
  { id: 'cronometragem', label: 'Cronometragem', icon: Timer },
  { id: 'kit_produto', label: 'Kit Produto', icon: Gift },
  { id: 'hidratacao', label: 'Hidratação', icon: Droplets },
];

const Cadastro: React.FC = () => {
  const { isDark } = useTheme();
  const [cadastros, setCadastros] = useState<CadastroEvento[]>(mockCadastros);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedCadastro, setSelectedCadastro] = useState<CadastroEvento | null>(null);
  const [editItem, setEditItem] = useState<CadastroEvento | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [activeTab, setActiveTab] = useState('info_geral');
  const [busca, setBusca] = useState('');
  
  const [projetos, setProjetos] = useState<Projeto[]>([]);
  const [projetoBusca, setProjetoBusca] = useState('');
  const [showProjetoDropdown, setShowProjetoDropdown] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 });
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadProjetos();
  }, []);

  const loadProjetos = async () => {
    try {
      const data = await projetosService.list();
      setProjetos(data);
    } catch (error) {
      console.error('Erro ao carregar projetos:', error);
    }
  };

  const filteredProjetos = useMemo(() => {
    if (!projetoBusca) return projetos;
    return projetos.filter(p => 
      p.evento.toLowerCase().includes(projetoBusca.toLowerCase()) ||
      p.codigo.toLowerCase().includes(projetoBusca.toLowerCase())
    );
  }, [projetos, projetoBusca]);

  const initialFormData: FormData = {
    projeto_id: null,
    nome: '',
    imagem_kv: '',
    info_geral: {
      data: '',
      horario_largada: '',
      local: '',
      distancias: []
    },
    atletas: {
      site: { pago: 0, cortesia: 0, tkt_medio: 0 },
      grupos: { pago: 0, cortesia: 0, tkt_medio: 0 }
    },
    retirada_kit: {
      local: '',
      data_horario: ''
    },
    pelotoes: [{ pelotao: '', atletas: 0 }],
    cronometragem: [],
    kit_produto: [{ kit: '', produtos: [] }],
    trofeus: 0,
    hidratacao: createDefaultHidratacao(),
    faixas_preco_site: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }],
    faixas_preco_grupos: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
  };

  const [form, setForm] = useState<FormData>(initialFormData);

  const formatNumber = (value: number | string): string => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(num) || num === 0) return '';
    return num.toLocaleString('pt-BR');
  };

  const parseFormattedNumber = (value: string): number => {
    const cleaned = value.replace(/\./g, '').replace(',', '.');
    return parseFloat(cleaned) || 0;
  };

  const FormattedInput = ({ 
    value, 
    onChange, 
    label,
    placeholder,
    className = '',
    icon,
    allowDecimal = false,
    readOnly = false
  }: { 
    value: number; 
    onChange: (val: number) => void;
    label?: string;
    placeholder?: string;
    className?: string;
    icon?: React.ReactNode;
    allowDecimal?: boolean;
    readOnly?: boolean;
  }) => {
    const [isFocused, setIsFocused] = useState(false);
    const [inputValue, setInputValue] = useState('');
    
    const formatForDisplay = (num: number): string => {
      if (num === 0 || num === null || num === undefined || isNaN(num)) return '';
      if (allowDecimal) {
        return num.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
      }
      return num.toLocaleString('pt-BR');
    };
    
    const parseToNumber = (str: string): number => {
      if (!str) return 0;
      const cleaned = str.replace(/\./g, '').replace(',', '.');
      return parseFloat(cleaned) || 0;
    };
    
    const handleFocus = () => {
      setIsFocused(true);
      if (allowDecimal) {
        setInputValue(value ? String(value).replace('.', ',') : '');
      } else {
        setInputValue(value ? String(value) : '');
      }
    };
    
    const handleBlur = () => {
      setIsFocused(false);
      const numValue = parseToNumber(inputValue);
      onChange(numValue);
    };
    
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      let newValue = e.target.value;
      if (allowDecimal) {
        newValue = newValue.replace(/[^\d,]/g, '');
        const parts = newValue.split(',');
        if (parts.length > 2) {
          newValue = parts[0] + ',' + parts.slice(1).join('');
        }
        if (parts[1] && parts[1].length > 2) {
          newValue = parts[0] + ',' + parts[1].slice(0, 2);
        }
      } else {
        newValue = newValue.replace(/\D/g, '');
      }
      setInputValue(newValue);
    };
    
    const hasValue = value > 0;
    const displayValue = isFocused ? inputValue : formatForDisplay(value);
    
    return (
      <div className="relative">
        {hasValue && !isFocused && label && (
          <label className={`absolute -top-2 left-2 px-1 text-[10px] font-medium z-10 ${isDark ? 'text-gray-400 bg-gray-800' : 'text-gray-500 bg-white'}`}>
            {icon}{label}
          </label>
        )}
        <input
          type="text"
          inputMode={allowDecimal ? "decimal" : "numeric"}
          value={displayValue}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          placeholder={placeholder || label}
          className={className}
          readOnly={readOnly}
        />
      </div>
    );
  };

  const getTotalAtletas = () => {
    const sitePago = form.atletas.site.pago || 0;
    const siteCortesia = form.atletas.site.cortesia || 0;
    const gruposPago = form.atletas.grupos.pago || 0;
    const gruposCortesia = form.atletas.grupos.cortesia || 0;
    return sitePago + siteCortesia + gruposPago + gruposCortesia;
  };

  const getTotalAtletasCadastro = (cadastro: CadastroEvento) => {
    return (cadastro.atletas.site.pago || 0) + 
           (cadastro.atletas.site.cortesia || 0) + 
           (cadastro.atletas.grupos.pago || 0) + 
           (cadastro.atletas.grupos.cortesia || 0);
  };

  const filteredCadastros = useMemo(() => {
    if (!busca) return cadastros;
    return cadastros.filter(c => 
      c.nome.toLowerCase().includes(busca.toLowerCase()) ||
      c.info_geral.local.toLowerCase().includes(busca.toLowerCase())
    );
  }, [cadastros, busca]);

  const totalEventos = cadastros.length;
  const emAndamento = cadastros.filter(c => c.status === 'Em andamento').length;
  const concluidos = cadastros.filter(c => c.status === 'Concluído').length;
  const totalAtletas = cadastros.reduce((acc, c) => acc + getTotalAtletasCadastro(c), 0);

  const openNewModal = () => {
    setEditItem(null);
    setForm(initialFormData);
    setProjetoBusca('');
    setActiveTab('info_geral');
    setShowModal(true);
  };

  const handleViewDetails = (cadastro: CadastroEvento) => {
    setSelectedCadastro(cadastro);
    setShowDetailsModal(true);
  };

  const handleEdit = (item: CadastroEvento) => {
    setEditItem(item);
    setForm({
      projeto_id: item.projeto_id,
      nome: item.nome,
      imagem_kv: item.imagem_kv,
      info_geral: { ...item.info_geral },
      atletas: { 
        site: { ...item.atletas.site },
        grupos: { ...item.atletas.grupos }
      },
      retirada_kit: { ...item.retirada_kit },
      pelotoes: item.pelotoes.length > 0 ? [...item.pelotoes] : [{ pelotao: '', atletas: 0 }],
      cronometragem: item.cronometragem.length > 0 ? item.cronometragem.map(c => ({
        distancia: c.distancia,
        pelotoes: c.pelotoes.map(p => ({ ...p }))
      })) : [],
      kit_produto: item.kit_produto.length > 0 ? item.kit_produto.map(k => ({ kit: k.kit, produtos: [...k.produtos] })) : [{ kit: '', produtos: [] }],
      trofeus: item.trofeus || 0,
      hidratacao: item.hidratacao?.copos_por_caixa !== undefined ? {
        copos_por_caixa: item.hidratacao.copos_por_caixa,
        distancias: item.hidratacao.distancias.map(d => ({ ...d })),
        chegada: { ...item.hidratacao.chegada },
        ativacoes: { ...item.hidratacao.ativacoes }
      } : createDefaultHidratacao(),
      faixas_preco_site: item.faixas_preco_site?.length > 0 ? [...item.faixas_preco_site] : [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }],
      faixas_preco_grupos: item.faixas_preco_grupos?.length > 0 ? [...item.faixas_preco_grupos] : [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
    });
    setProjetoBusca(item.nome);
    setActiveTab('info_geral');
    setShowModal(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editItem) {
      setCadastros(prev => prev.map(c => 
        c.id === editItem.id 
          ? {
              ...c,
              projeto_id: form.projeto_id,
              nome: form.nome,
              imagem_kv: form.imagem_kv,
              info_geral: form.info_geral,
              atletas: form.atletas,
              retirada_kit: form.retirada_kit,
              pelotoes: form.pelotoes,
              cronometragem: form.cronometragem,
              kit_produto: form.kit_produto,
              trofeus: form.trofeus,
              hidratacao: form.hidratacao,
              faixas_preco_site: form.faixas_preco_site,
              faixas_preco_grupos: form.faixas_preco_grupos
            }
          : c
      ));
    } else {
      const newCadastro: CadastroEvento = {
        id: Date.now(),
        projeto_id: form.projeto_id,
        nome: form.nome,
        imagem_kv: form.imagem_kv,
        status: 'Em andamento',
        modalidade: 'Corrida',
        info_geral: form.info_geral,
        atletas: form.atletas,
        retirada_kit: form.retirada_kit,
        pelotoes: form.pelotoes,
        cronometragem: form.cronometragem,
        kit_produto: form.kit_produto,
        trofeus: form.trofeus,
        hidratacao: form.hidratacao,
        faixas_preco_site: form.faixas_preco_site,
        faixas_preco_grupos: form.faixas_preco_grupos
      };
      setCadastros(prev => [...prev, newCadastro]);
    }
    setShowModal(false);
    setEditItem(null);
  };

  const addArrayField = (field: 'pelotoes' | 'cronometragem' | 'kit_produto' | 'faixas_preco_site' | 'faixas_preco_grupos') => {
    const defaults: Record<string, any> = {
      pelotoes: { pelotao: '', atletas: 0 },
      cronometragem: { distancia: '', pelotoes: [{ pelotao: '', num_inicio: 0, num_fim: 0, cor: '' }] },
      kit_produto: { kit: '', produtos: [] },
      faixas_preco_site: { faixa: '', qtd: 0, tkt_medio: 0, total: 0 },
      faixas_preco_grupos: { faixa: '', qtd: 0, tkt_medio: 0, total: 0 }
    };
    setForm(prev => ({
      ...prev,
      [field]: [...(prev as any)[field], defaults[field]]
    }));
  };

  const removeArrayField = (field: 'pelotoes' | 'cronometragem' | 'kit_produto' | 'faixas_preco_site' | 'faixas_preco_grupos', index: number) => {
    setForm(prev => ({
      ...prev,
      [field]: (prev as any)[field].filter((_: any, i: number) => i !== index)
    }));
  };

  const updateArrayField = (field: string, index: number, key: string, value: any) => {
    setForm(prev => ({
      ...prev,
      [field]: (prev as any)[field].map((item: any, i: number) => 
        i === index ? { ...item, [key]: value } : item
      )
    }));
  };

  useEffect(() => {
    if (form.info_geral.distancias.length > 0) {
      const existingDistancias = form.cronometragem.map(c => c.distancia);
      const newDistancias = form.info_geral.distancias.filter(d => !existingDistancias.includes(d));
      const removedDistancias = existingDistancias.filter(d => !form.info_geral.distancias.includes(d));
      
      if (newDistancias.length > 0 || removedDistancias.length > 0) {
        setForm(prev => ({
          ...prev,
          cronometragem: [
            ...prev.cronometragem.filter(c => form.info_geral.distancias.includes(c.distancia)),
            ...newDistancias.map(d => ({
              distancia: d,
              pelotoes: [{ pelotao: '', num_inicio: 0, num_fim: 0, cor: '' }]
            }))
          ]
        }));
      }
    }
  }, [form.info_geral.distancias]);

  useEffect(() => {
    const existingDistancias = form.hidratacao.distancias.map(h => h.distancia);
    const newDistancias = form.info_geral.distancias.filter(d => !existingDistancias.includes(d));
    const removedDistancias = existingDistancias.filter(d => !form.info_geral.distancias.includes(d));
    
    if (newDistancias.length > 0 || removedDistancias.length > 0) {
      setForm(prev => ({
        ...prev,
        hidratacao: {
          ...prev.hidratacao,
          distancias: [
            ...prev.hidratacao.distancias.filter(h => form.info_geral.distancias.includes(h.distancia)),
            ...newDistancias.map(d => ({
              distancia: d,
              postos: 0,
              doses_atleta: 0,
              atletas: 0,
              total: 0
            }))
          ]
        }
      }));
    }
  }, [form.info_geral.distancias]);

  const calcularTotalizadorFaixa = (faixas: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>) => {
    const totalQtd = faixas.reduce((acc, f) => acc + (f.qtd || 0), 0);
    const totalValor = faixas.reduce((acc, f) => acc + (f.total || 0), 0);
    const ticketMedioReal = totalQtd > 0 ? totalValor / totalQtd : 0;
    return { totalQtd, totalValor, ticketMedioReal };
  };

  const renderFaixaPrecoContent = (tipo: 'site' | 'grupos') => {
    const field = tipo === 'site' ? 'faixas_preco_site' : 'faixas_preco_grupos';
    const faixas = tipo === 'site' ? form.faixas_preco_site : form.faixas_preco_grupos;
    const { totalQtd, totalValor, ticketMedioReal } = calcularTotalizadorFaixa(faixas);
    
    const atletasOrcado = tipo === 'site' 
      ? (form.atletas.site.pago || 0) + (form.atletas.site.cortesia || 0)
      : (form.atletas.grupos.pago || 0) + (form.atletas.grupos.cortesia || 0);
    const tktMedioOrcado = tipo === 'site' 
      ? (form.atletas.site.tkt_medio || 0) 
      : (form.atletas.grupos.tkt_medio || 0);
    const valorTotalOrcado = atletasOrcado * tktMedioOrcado;
    
    const canAddMore = faixas.length < 5;
    
    const diferencaQtd = totalQtd - atletasOrcado;
    const diferencaTktMedio = ticketMedioReal - tktMedioOrcado;
    const diferencaValor = totalValor - valorTotalOrcado;
    const percentualPreenchido = atletasOrcado > 0 ? (totalQtd / atletasOrcado) * 100 : 0;

    return (
      <div className="space-y-4">
        {faixas.map((faixa, index) => (
          <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
            <div className="flex justify-between items-center mb-3">
              <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Faixa de Preço {index + 1}</span>
              {faixas.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeArrayField(field, index)}
                  className="p-1 text-red-400 hover:text-red-300 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <div className="grid grid-cols-4 gap-3">
              <select
                value={faixa.faixa}
                onChange={(e) => updateArrayField(field, index, 'faixa', e.target.value)}
                className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              >
                <option value="">Faixa</option>
                {faixaOptions.filter(f => !faixas.some((ff, i) => i !== index && ff.faixa === f)).map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
              <FormattedInput
                value={faixa.qtd || 0}
                onChange={(qtd) => {
                  const total = qtd * (faixa.tkt_medio || 0);
                  setForm(prev => ({
                    ...prev,
                    [field]: (prev as any)[field].map((item: any, i: number) => 
                      i === index ? { ...item, qtd, total } : item
                    )
                  }));
                }}
                label="Qtd"
                placeholder="Qtd"
                className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.tkt_medio || 0}
                onChange={(tkt_medio) => {
                  const total = (faixa.qtd || 0) * tkt_medio;
                  setForm(prev => ({
                    ...prev,
                    [field]: (prev as any)[field].map((item: any, i: number) => 
                      i === index ? { ...item, tkt_medio, total } : item
                    )
                  }));
                }}
                label="Tkt Médio"
                placeholder="Tkt Médio"
                allowDecimal={true}
                className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.total || 0}
                onChange={() => {}}
                label="Total"
                placeholder="Total"
                allowDecimal={true}
                readOnly={true}
                className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-600 border-gray-500 text-gray-400' : 'bg-gray-100 border-gray-300 text-gray-500'} cursor-not-allowed`}
              />
            </div>
          </div>
        ))}
        
        {canAddMore && (
          <button
            type="button"
            onClick={() => addArrayField(field)}
            className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
          >
            <Plus className="w-5 h-5" />
            Adicionar Faixa de Preço ({faixas.length}/5)
          </button>
        )}

        {faixas.length > 0 && faixas.some(f => f.qtd > 0 || f.tkt_medio > 0) && (
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gradient-to-r from-purple-900/50 to-pink-900/50' : 'bg-gradient-to-r from-purple-50 to-pink-50'} border ${isDark ? 'border-purple-500/30' : 'border-purple-200'}`}>
            <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>
              Totalizador
            </h4>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="text-center">
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Qtd</p>
                <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalQtd) || '0'}</p>
              </div>
              <div className="text-center">
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ticket Médio Real</p>
                <p className={`text-lg font-bold text-purple-400`}>{formatCurrency(ticketMedioReal)}</p>
              </div>
              <div className="text-center">
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Valor</p>
                <p className={`text-lg font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
              </div>
            </div>
            
            <div className={`p-4 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-white/50'} space-y-4`}>
              <h5 className={`text-sm font-bold ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                Comparativo com Orçado ({tipo === 'site' ? 'Site' : 'Grupos'})
              </h5>
              
              <div className="grid grid-cols-1 gap-4">
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd Atletas</p>
                      <p className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalQtd) || '0'}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatNumber(atletasOrcado) || '0'}</p>
                      <span className={`text-lg font-bold flex items-center justify-end gap-1 ${
                        diferencaQtd === 0 ? 'text-green-400' : diferencaQtd > 0 ? 'text-blue-400' : 'text-orange-400'
                      }`}>
                        {diferencaQtd === 0 ? (
                          <><Check className="w-4 h-4" /> Exato</>
                        ) : diferencaQtd > 0 ? (
                          <><TrendingUp className="w-4 h-4" /> +{formatNumber(diferencaQtd)}</>
                        ) : (
                          <><TrendingDown className="w-4 h-4" /> {formatNumber(diferencaQtd)}</>
                        )}
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-600 rounded-full h-2.5">
                    <div 
                      className={`h-2.5 rounded-full transition-all ${
                        percentualPreenchido >= 100 ? 'bg-green-500' : percentualPreenchido >= 80 ? 'bg-blue-500' : 'bg-orange-500'
                      }`}
                      style={{ width: `${Math.min(percentualPreenchido, 100)}%` }}
                    />
                  </div>
                  <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{percentualPreenchido.toFixed(1)}%</p>
                </div>
                
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ticket Médio</p>
                      <p className={`text-xl font-bold text-purple-400`}>{formatCurrency(ticketMedioReal)}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatCurrency(tktMedioOrcado)}</p>
                      <span className={`text-lg font-bold flex items-center justify-end gap-1 ${
                        Math.abs(diferencaTktMedio) < 0.01 ? 'text-green-400' : diferencaTktMedio > 0 ? 'text-blue-400' : 'text-orange-400'
                      }`}>
                        {Math.abs(diferencaTktMedio) < 0.01 ? (
                          <><Check className="w-4 h-4" /> Exato</>
                        ) : diferencaTktMedio > 0 ? (
                          <><TrendingUp className="w-4 h-4" /> +{formatCurrency(diferencaTktMedio)}</>
                        ) : (
                          <><TrendingDown className="w-4 h-4" /> {formatCurrency(diferencaTktMedio)}</>
                        )}
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-600 rounded-full h-2.5">
                    <div 
                      className={`h-2.5 rounded-full transition-all ${
                        tktMedioOrcado > 0 && ticketMedioReal >= tktMedioOrcado ? 'bg-green-500' : tktMedioOrcado > 0 && ticketMedioReal >= tktMedioOrcado * 0.8 ? 'bg-blue-500' : 'bg-orange-500'
                      }`}
                      style={{ width: `${tktMedioOrcado > 0 ? Math.min((ticketMedioReal / tktMedioOrcado) * 100, 100) : 0}%` }}
                    />
                  </div>
                  <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{tktMedioOrcado > 0 ? ((ticketMedioReal / tktMedioOrcado) * 100).toFixed(1) : 0}%</p>
                </div>
                
                <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-100'}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Valor Total</p>
                      <p className={`text-xl font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatCurrency(valorTotalOrcado)}</p>
                      <span className={`text-lg font-bold flex items-center justify-end gap-1 ${
                        Math.abs(diferencaValor) < 0.01 ? 'text-green-400' : diferencaValor > 0 ? 'text-blue-400' : 'text-orange-400'
                      }`}>
                        {Math.abs(diferencaValor) < 0.01 ? (
                          <><Check className="w-4 h-4" /> Exato</>
                        ) : diferencaValor > 0 ? (
                          <><TrendingUp className="w-4 h-4" /> +{formatCurrency(diferencaValor)}</>
                        ) : (
                          <><TrendingDown className="w-4 h-4" /> {formatCurrency(diferencaValor)}</>
                        )}
                      </span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-600 rounded-full h-2.5">
                    <div 
                      className={`h-2.5 rounded-full transition-all ${
                        valorTotalOrcado > 0 && totalValor >= valorTotalOrcado ? 'bg-green-500' : valorTotalOrcado > 0 && totalValor >= valorTotalOrcado * 0.8 ? 'bg-blue-500' : 'bg-orange-500'
                      }`}
                      style={{ width: `${valorTotalOrcado > 0 ? Math.min((totalValor / valorTotalOrcado) * 100, 100) : 0}%` }}
                    />
                  </div>
                  <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>{valorTotalOrcado > 0 ? ((totalValor / valorTotalOrcado) * 100).toFixed(1) : 0}%</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'info_geral':
        return (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  <Calendar className="w-4 h-4 inline mr-2 text-purple-500" />
                  Data
                </label>
                <input
                  type="date"
                  value={form.info_geral.data}
                  onChange={(e) => setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, data: e.target.value } }))}
                  className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                />
              </div>
              <div>
                <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  <Clock className="w-4 h-4 inline mr-2 text-purple-500" />
                  Horário Largada
                </label>
                <input
                  type="time"
                  value={form.info_geral.horario_largada}
                  onChange={(e) => setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, horario_largada: e.target.value } }))}
                  className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                />
              </div>
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <MapPin className="w-4 h-4 inline mr-2 text-purple-500" />
                Local
              </label>
              <textarea
                value={form.info_geral.local}
                onChange={(e) => setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, local: e.target.value } }))}
                placeholder="Endereço completo do evento"
                rows={2}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 resize-none`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Ruler className="w-4 h-4 inline mr-2 text-purple-500" />
                Distâncias
              </label>
              <div className="flex flex-wrap gap-2">
                {distanciasOptions.map(d => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => {
                      const distancias = form.info_geral.distancias.includes(d)
                        ? form.info_geral.distancias.filter(dist => dist !== d)
                        : [...form.info_geral.distancias, d];
                      setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, distancias } }));
                    }}
                    className={`px-4 py-2 rounded-xl font-medium transition-all ${
                      form.info_geral.distancias.includes(d)
                        ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg'
                        : isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          </div>
        );

      case 'atletas':
        const siteTotal = (form.atletas.site.pago || 0) + (form.atletas.site.cortesia || 0);
        const gruposTotal = (form.atletas.grupos.pago || 0) + (form.atletas.grupos.cortesia || 0);
        const totalGeral = siteTotal + gruposTotal;

        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <div className={`p-4 rounded-xl ${isDark ? 'bg-blue-900/20 border-blue-500/30' : 'bg-blue-50 border-blue-200'} border`}>
                <div className="flex items-center gap-2 mb-4">
                  <Globe className="w-5 h-5 text-blue-400" />
                  <h3 className={`font-bold ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>Site</h3>
                </div>
                <div className="space-y-3">
                  <FormattedInput
                    value={form.atletas.site.pago || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, site: { ...prev.atletas.site, pago: val } } }))}
                    label="Pago"
                    placeholder="Pago"
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                  />
                  <FormattedInput
                    value={form.atletas.site.cortesia || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, site: { ...prev.atletas.site, cortesia: val } } }))}
                    label="Cortesia"
                    placeholder="Cortesia"
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                  />
                  <div className={`p-2 rounded-lg ${isDark ? 'bg-blue-800/30' : 'bg-blue-100'}`}>
                    <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>Total Site</label>
                    <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(siteTotal) || '0'}</p>
                  </div>
                  <FormattedInput
                    value={form.atletas.site.tkt_medio || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, site: { ...prev.atletas.site, tkt_medio: val } } }))}
                    label="Ticket Médio"
                    placeholder="Ticket Médio"
                    allowDecimal={true}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                  />
                </div>
              </div>

              <div className={`p-4 rounded-xl ${isDark ? 'bg-orange-900/20 border-orange-500/30' : 'bg-orange-50 border-orange-200'} border`}>
                <div className="flex items-center gap-2 mb-4">
                  <UsersRound className="w-5 h-5 text-orange-400" />
                  <h3 className={`font-bold ${isDark ? 'text-orange-300' : 'text-orange-700'}`}>Grupos</h3>
                </div>
                <div className="space-y-3">
                  <FormattedInput
                    value={form.atletas.grupos.pago || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, grupos: { ...prev.atletas.grupos, pago: val } } }))}
                    label="Pago"
                    placeholder="Pago"
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                  />
                  <FormattedInput
                    value={form.atletas.grupos.cortesia || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, grupos: { ...prev.atletas.grupos, cortesia: val } } }))}
                    label="Cortesia"
                    placeholder="Cortesia"
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                  />
                  <div className={`p-2 rounded-lg ${isDark ? 'bg-orange-800/30' : 'bg-orange-100'}`}>
                    <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-orange-300' : 'text-orange-700'}`}>Total Grupos</label>
                    <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(gruposTotal) || '0'}</p>
                  </div>
                  <FormattedInput
                    value={form.atletas.grupos.tkt_medio || 0}
                    onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, grupos: { ...prev.atletas.grupos, tkt_medio: val } } }))}
                    label="Ticket Médio"
                    placeholder="Ticket Médio"
                    allowDecimal={true}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                  />
                </div>
              </div>
            </div>

            <div className={`p-5 rounded-xl ${isDark ? 'bg-gradient-to-r from-purple-900/50 to-pink-900/50 border-purple-500/30' : 'bg-gradient-to-r from-purple-50 to-pink-50 border-purple-200'} border`}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Users className="w-6 h-6 text-purple-400" />
                  <span className={`text-lg font-bold ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>Total Atletas</span>
                </div>
                <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalGeral) || '0'}</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className={`p-3 rounded-lg ${isDark ? 'bg-green-900/30' : 'bg-green-50'} border ${isDark ? 'border-green-500/30' : 'border-green-200'}`}>
                  <span className={`block text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Pagos</span>
                  <span className="text-2xl font-bold text-green-400">{formatNumber((form.atletas.site.pago || 0) + (form.atletas.grupos.pago || 0)) || '0'}</span>
                </div>
                <div className={`p-3 rounded-lg ${isDark ? 'bg-orange-900/30' : 'bg-orange-50'} border ${isDark ? 'border-orange-500/30' : 'border-orange-200'}`}>
                  <span className={`block text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Cortesias</span>
                  <span className="text-2xl font-bold text-orange-400">{formatNumber((form.atletas.site.cortesia || 0) + (form.atletas.grupos.cortesia || 0)) || '0'}</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'faixas_preco_site':
        return renderFaixaPrecoContent('site');

      case 'faixas_preco_grupos':
        return renderFaixaPrecoContent('grupos');

      case 'retirada_kit':
        return (
          <div className="space-y-4">
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <MapPin className="w-4 h-4 inline mr-2 text-purple-500" />
                Local
              </label>
              <textarea
                value={form.retirada_kit.local}
                onChange={(e) => setForm(prev => ({ ...prev, retirada_kit: { ...prev.retirada_kit, local: e.target.value } }))}
                placeholder="Endereço para retirada do kit"
                rows={2}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 resize-none`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Calendar className="w-4 h-4 inline mr-2 text-purple-500" />
                Data e Horário
              </label>
              <input
                type="datetime-local"
                value={form.retirada_kit.data_horario}
                onChange={(e) => setForm(prev => ({ ...prev, retirada_kit: { ...prev.retirada_kit, data_horario: e.target.value } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
          </div>
        );

      case 'pelotoes':
        return (
          <div className="space-y-4">
            {form.pelotoes.map((pelotao, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Pelotão {index + 1}</span>
                  {form.pelotoes.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('pelotoes', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <select
                    value={pelotao.pelotao}
                    onChange={(e) => updateArrayField('pelotoes', index, 'pelotao', e.target.value)}
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Selecione</option>
                    {pelotoesOptions.filter(p => !form.pelotoes.some((fp, i) => i !== index && fp.pelotao === p)).map(p => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                  <FormattedInput
                    value={pelotao.atletas || 0}
                    onChange={(val) => updateArrayField('pelotoes', index, 'atletas', val)}
                    label="Qtd Atletas"
                    placeholder="Qtd Atletas"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addArrayField('pelotoes')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Pelotão
            </button>
          </div>
        );

      case 'cronometragem':
        return (
          <div className="space-y-4">
            {form.info_geral.distancias.length === 0 ? (
              <div className={`p-6 rounded-xl text-center ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'}`}>
                <AlertCircle className="w-12 h-12 mx-auto mb-3 text-orange-400" />
                <p className={`font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Defina as distâncias na aba "Info Geral" primeiro
                </p>
                <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                  Os campos de cronometragem serão gerados automaticamente
                </p>
              </div>
            ) : (
              form.cronometragem.map((crono, cronoIndex) => (
                <div key={cronoIndex} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="px-3 py-1 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 text-white text-sm font-bold">
                      {crono.distancia}
                    </div>
                  </div>
                  
                  {crono.pelotoes.map((pel, pelIndex) => (
                    <div key={pelIndex} className={`p-3 rounded-lg mb-3 ${isDark ? 'bg-gray-800/50' : 'bg-white'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                      <div className="flex justify-between items-center mb-2">
                        <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Pelotão {pelIndex + 1}</span>
                        {crono.pelotoes.length > 1 && (
                          <button
                            type="button"
                            onClick={() => {
                              setForm(prev => ({
                                ...prev,
                                cronometragem: prev.cronometragem.map((c, i) => 
                                  i === cronoIndex 
                                    ? { ...c, pelotoes: c.pelotoes.filter((_, pi) => pi !== pelIndex) }
                                    : c
                                )
                              }));
                            }}
                            className="p-1 text-red-400 hover:text-red-300 transition-colors"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-4 gap-2">
                        <select
                          value={pel.pelotao}
                          onChange={(e) => {
                            setForm(prev => ({
                              ...prev,
                              cronometragem: prev.cronometragem.map((c, i) => 
                                i === cronoIndex 
                                  ? { ...c, pelotoes: c.pelotoes.map((p, pi) => pi === pelIndex ? { ...p, pelotao: e.target.value } : p) }
                                  : c
                              )
                            }));
                          }}
                          className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                        >
                          <option value="">Pelotão</option>
                          {pelotoesOptions.filter(p => 
                            p === pel.pelotao || !crono.pelotoes.some((other, otherIdx) => otherIdx !== pelIndex && other.pelotao === p)
                          ).map(p => (
                            <option key={p} value={p}>{p}</option>
                          ))}
                        </select>
                        <FormattedInput
                          value={pel.num_inicio || 0}
                          onChange={(value) => {
                            const safeValue = Math.max(1, value);
                            setForm(prev => ({
                              ...prev,
                              cronometragem: prev.cronometragem.map((c, i) => 
                                i === cronoIndex 
                                  ? { ...c, pelotoes: c.pelotoes.map((p, pi) => pi === pelIndex ? { ...p, num_inicio: safeValue } : p) }
                                  : c
                              )
                            }));
                          }}
                          label="Início"
                          placeholder="Início"
                          className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                        />
                        <FormattedInput
                          value={pel.num_fim || 0}
                          onChange={(value) => {
                            const safeValue = Math.max(1, value);
                            setForm(prev => {
                              const newCronometragem = prev.cronometragem.map((c, i) => 
                                i === cronoIndex 
                                  ? { ...c, pelotoes: c.pelotoes.map((p, pi) => pi === pelIndex ? { ...p, num_fim: safeValue } : p) }
                                  : c
                              );
                              
                              const currentCrono = newCronometragem[cronoIndex];
                              if (pelIndex < currentCrono.pelotoes.length - 1) {
                                currentCrono.pelotoes[pelIndex + 1] = {
                                  ...currentCrono.pelotoes[pelIndex + 1],
                                  num_inicio: safeValue + 1
                                };
                              } else if (cronoIndex < newCronometragem.length - 1) {
                                const nextCrono = newCronometragem[cronoIndex + 1];
                                if (nextCrono.pelotoes.length > 0) {
                                  nextCrono.pelotoes[0] = {
                                    ...nextCrono.pelotoes[0],
                                    num_inicio: safeValue + 1
                                  };
                                }
                              }
                              
                              return { ...prev, cronometragem: newCronometragem };
                            });
                          }}
                          label="Fim"
                          placeholder="Fim"
                          className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                        />
                        <select
                          value={pel.cor}
                          onChange={(e) => {
                            setForm(prev => ({
                              ...prev,
                              cronometragem: prev.cronometragem.map((c, i) => 
                                i === cronoIndex 
                                  ? { ...c, pelotoes: c.pelotoes.map((p, pi) => pi === pelIndex ? { ...p, cor: e.target.value } : p) }
                                  : c
                              )
                            }));
                          }}
                          className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                        >
                          <option value="">Cor</option>
                          {coresPeitoOptions.map(c => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))}
                  
                  <button
                    type="button"
                    onClick={() => {
                      setForm(prev => {
                        const currentCrono = prev.cronometragem[cronoIndex];
                        const lastPelotao = currentCrono.pelotoes[currentCrono.pelotoes.length - 1];
                        const nextNumInicio = lastPelotao && lastPelotao.num_fim > 0 ? lastPelotao.num_fim + 1 : 1;
                        
                        return {
                          ...prev,
                          cronometragem: prev.cronometragem.map((c, i) => 
                            i === cronoIndex 
                              ? { ...c, pelotoes: [...c.pelotoes, { pelotao: '', num_inicio: nextNumInicio, num_fim: 0, cor: '' }] }
                              : c
                          )
                        };
                      });
                    }}
                    className="w-full py-2 rounded-lg border border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors text-sm flex items-center justify-center gap-2"
                  >
                    <Plus className="w-4 h-4" />
                    Adicionar Pelotão
                  </button>
                </div>
              ))
            )}
          </div>
        );

      case 'kit_produto':
        return (
          <div className="space-y-4">
            {form.kit_produto.map((kit, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Kit {index + 1}</span>
                  {form.kit_produto.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('kit_produto', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="mb-4">
                  <select
                    value={kit.kit}
                    onChange={(e) => {
                      const selectedKit = e.target.value;
                      const defaultProdutos = produtosPadraoPorKit[selectedKit] || [];
                      setForm(prev => ({
                        ...prev,
                        kit_produto: prev.kit_produto.map((k, i) => 
                          i === index ? { ...k, kit: selectedKit, produtos: defaultProdutos } : k
                        )
                      }));
                    }}
                    className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Selecione o Kit</option>
                    {kitOptions.filter(k => !form.kit_produto.some((fk, i) => i !== index && fk.kit === k)).map(k => (
                      <option key={k} value={k}>{k}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <label className={`block text-xs font-medium mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Produtos do Kit (clique para adicionar/remover)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {produtosDisponiveis.map(produto => {
                      const isSelected = kit.produtos.includes(produto);
                      return (
                        <button
                          key={produto}
                          type="button"
                          onClick={() => {
                            const produtos = isSelected
                              ? kit.produtos.filter(p => p !== produto)
                              : [...kit.produtos, produto];
                            setForm(prev => ({
                              ...prev,
                              kit_produto: prev.kit_produto.map((k, i) => 
                                i === index ? { ...k, produtos } : k
                              )
                            }));
                          }}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                            isSelected
                              ? 'bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-md'
                              : isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                          }`}
                        >
                          {produto}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addArrayField('kit_produto')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Kit
            </button>

            <div className={`p-4 rounded-xl ${isDark ? 'bg-amber-900/20 border-amber-500/30' : 'bg-amber-50 border-amber-200'} border`}>
              <div className="flex items-center gap-2 mb-3">
                <Trophy className="w-5 h-5 text-amber-400" />
                <span className={`font-bold ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>Troféus (Evento)</span>
              </div>
              <FormattedInput
                value={form.trofeus || 0}
                onChange={(val) => setForm(prev => ({ ...prev, trofeus: val }))}
                label="Quantidade de troféus"
                placeholder="Quantidade de troféus para o evento"
                className={`w-full px-4 py-3 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-amber-500`}
              />
            </div>
          </div>
        );

      case 'hidratacao': {
        const updateHidratacaoDistancia = (index: number, field: string, value: number) => {
          setForm(prev => {
            const newDistancias = [...prev.hidratacao.distancias];
            newDistancias[index] = { ...newDistancias[index], [field]: value };
            if (field === 'postos' || field === 'doses_atleta' || field === 'atletas') {
              const postos = field === 'postos' ? value : newDistancias[index].postos;
              const doses = field === 'doses_atleta' ? value : newDistancias[index].doses_atleta;
              const atletas = field === 'atletas' ? value : newDistancias[index].atletas;
              newDistancias[index].total = Math.round(atletas * doses * postos);
            }
            const newTotalAtletas = newDistancias.reduce((acc, d) => acc + (d.atletas || 0), 0);
            const newChegada = { 
              ...prev.hidratacao.chegada, 
              atletas: newTotalAtletas,
              total: Math.round(newTotalAtletas * (prev.hidratacao.chegada.doses_atleta || 0) * (prev.hidratacao.chegada.postos || 0))
            };
            return { ...prev, hidratacao: { ...prev.hidratacao, distancias: newDistancias, chegada: newChegada } };
          });
        };

        const updateHidratacaoSection = (section: 'chegada' | 'ativacoes', field: string, value: number) => {
          setForm(prev => {
            const newSection = { ...prev.hidratacao[section], [field]: value };
            if (field === 'postos' || field === 'doses_atleta' || field === 'atletas') {
              const postos = field === 'postos' ? value : newSection.postos;
              const doses = field === 'doses_atleta' ? value : newSection.doses_atleta;
              if (section === 'chegada') {
                const totalAtletasFromDistancias = prev.hidratacao.distancias.reduce((acc, d) => acc + (d.atletas || 0), 0);
                newSection.atletas = totalAtletasFromDistancias;
                newSection.total = Math.round(totalAtletasFromDistancias * doses * postos);
              } else {
                const atletas = field === 'atletas' ? value : newSection.atletas;
                newSection.total = Math.round(atletas * doses * postos);
              }
            }
            return { ...prev, hidratacao: { ...prev.hidratacao, [section]: newSection } };
          });
        };

        const totalAtletasDistancias = form.hidratacao.distancias.reduce((acc, d) => acc + (d.atletas || 0), 0);
        const totalCoposDistancias = form.hidratacao.distancias.reduce((acc, d) => acc + (d.total || 0), 0);
        const chegadaTotalCalculado = Math.round(totalAtletasDistancias * (form.hidratacao.chegada.doses_atleta || 0) * (form.hidratacao.chegada.postos || 0));
        const totalCoposAtivacoes = form.hidratacao.ativacoes.total || 0;
        const totalCoposGeral = totalCoposDistancias + chegadaTotalCalculado + totalCoposAtivacoes;
        const coposPorCaixa = form.hidratacao.copos_por_caixa || 48;
        const totalCaixas = coposPorCaixa > 0 ? Math.ceil(totalCoposGeral / coposPorCaixa) : 0;

        const renderHidratacaoCard = (
          title: string,
          icon: React.ReactNode,
          gradientFrom: string,
          gradientTo: string,
          postos: number,
          dosesAtleta: number,
          atletas: number,
          total: number,
          onUpdate: (field: string, value: number) => void,
          isAtletasReadOnly: boolean = false
        ) => (
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
            <div className="flex items-center gap-2 mb-4">
              <div className={`p-2 rounded-lg bg-gradient-to-r ${gradientFrom} ${gradientTo}`}>
                {icon}
              </div>
              <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{title}</span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <FormattedInput
                value={postos}
                onChange={(val) => onUpdate('postos', Math.max(0, val))}
                label="Postos"
                placeholder="Postos"
                className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
              />
              <FormattedInput
                value={dosesAtleta}
                onChange={(val) => onUpdate('doses_atleta', Math.max(0, val))}
                label="Doses/Atleta"
                placeholder="Doses/Atleta"
                allowDecimal
                className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-cyan-500`}
              />
              <FormattedInput
                value={atletas}
                onChange={(val) => onUpdate('atletas', Math.max(0, val))}
                label="Atletas"
                placeholder="Atletas"
                readOnly={isAtletasReadOnly}
                className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 ${isAtletasReadOnly ? 'opacity-70 cursor-not-allowed' : ''}`}
              />
              <FormattedInput
                value={total}
                onChange={() => {}}
                label="Total"
                placeholder="Total"
                readOnly
                className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-600 border-gray-500 text-white' : 'bg-gray-100 border-gray-300 text-gray-700'} opacity-70 cursor-not-allowed`}
              />
            </div>
          </div>
        );

        return (
          <div className="space-y-4">
            {form.info_geral.distancias.length === 0 ? (
              <div className={`p-6 rounded-xl text-center ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'}`}>
                <AlertCircle className="w-12 h-12 mx-auto mb-3 text-orange-400" />
                <p className={`font-medium ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  Defina as distâncias na aba "Info Geral" primeiro
                </p>
                <p className={`text-sm ${isDark ? 'text-gray-500' : 'text-gray-500'}`}>
                  Os campos de hidratação serão gerados automaticamente
                </p>
              </div>
            ) : (
              <>
                <div className={`p-4 rounded-xl ${isDark ? 'bg-blue-900/20 border-blue-500/30' : 'bg-blue-50 border-blue-200'} border`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-gradient-to-r from-blue-500 to-cyan-500">
                        <Box className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <span className={`text-sm font-bold ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>Copos por Caixa</span>
                        <p className={`text-xs ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>Base de cálculo para todas as distâncias</p>
                      </div>
                    </div>
                    <div className="w-32">
                      <FormattedInput
                        value={coposPorCaixa}
                        onChange={(val) => setForm(prev => ({ 
                          ...prev, 
                          hidratacao: { ...prev.hidratacao, copos_por_caixa: Math.max(1, val) }
                        }))}
                        label="Qtd"
                        placeholder="48"
                        className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500 text-center font-bold`}
                      />
                    </div>
                  </div>
                </div>

                {form.hidratacao.distancias.map((h, index) => (
                  <div key={h.distancia} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                    <div className="flex items-center gap-2 mb-4">
                      <div className="px-3 py-1 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 text-white text-sm font-bold">
                        {h.distancia}
                      </div>
                    </div>
                    <div className="grid grid-cols-4 gap-3">
                      <FormattedInput
                        value={h.postos || 0}
                        onChange={(val) => updateHidratacaoDistancia(index, 'postos', Math.max(0, val))}
                        label="Postos"
                        placeholder="Postos"
                        className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                      />
                      <FormattedInput
                        value={h.doses_atleta || 0}
                        onChange={(val) => updateHidratacaoDistancia(index, 'doses_atleta', Math.max(0, val))}
                        label="Doses/Atleta"
                        placeholder="Doses/Atleta"
                        allowDecimal
                        className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-cyan-500`}
                      />
                      <FormattedInput
                        value={h.atletas || 0}
                        onChange={(val) => updateHidratacaoDistancia(index, 'atletas', Math.max(0, val))}
                        label="Atletas"
                        placeholder="Atletas"
                        className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                      />
                      <FormattedInput
                        value={h.total || 0}
                        onChange={() => {}}
                        label="Total"
                        placeholder="Total"
                        readOnly
                        className={`w-full px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-600 border-gray-500 text-white' : 'bg-gray-100 border-gray-300 text-gray-700'} opacity-70 cursor-not-allowed`}
                      />
                    </div>
                  </div>
                ))}

                {renderHidratacaoCard(
                  'Chegada',
                  <Flag className="w-4 h-4 text-white" />,
                  'from-emerald-500',
                  'to-green-500',
                  form.hidratacao.chegada.postos,
                  form.hidratacao.chegada.doses_atleta,
                  totalAtletasDistancias,
                  chegadaTotalCalculado,
                  (field, value) => {
                    if (field === 'atletas') return;
                    setForm(prev => ({ 
                      ...prev, 
                      hidratacao: { 
                        ...prev.hidratacao, 
                        chegada: { ...prev.hidratacao.chegada, [field]: value } 
                      } 
                    }));
                  },
                  true
                )}

                {renderHidratacaoCard(
                  'Ativações',
                  <Activity className="w-4 h-4 text-white" />,
                  'from-orange-500',
                  'to-amber-500',
                  form.hidratacao.ativacoes.postos,
                  form.hidratacao.ativacoes.doses_atleta,
                  form.hidratacao.ativacoes.atletas,
                  form.hidratacao.ativacoes.total,
                  (field, value) => updateHidratacaoSection('ativacoes', field, value),
                  false
                )}

                <div className={`p-5 rounded-2xl ${isDark ? 'bg-gradient-to-br from-purple-900/40 to-pink-900/40 border-purple-500/30' : 'bg-gradient-to-br from-purple-50 to-pink-50 border-purple-200'} border`}>
                  <div className="flex items-center gap-2 mb-4">
                    <Droplets className="w-5 h-5 text-purple-400" />
                    <span className={`font-bold ${isDark ? 'text-white' : 'text-gray-800'}`}>Resumo de Hidratação</span>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/50' : 'bg-white'} text-center`}>
                      <div className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total de Copos</div>
                      <div className={`text-2xl font-black ${isDark ? 'text-cyan-400' : 'text-cyan-600'}`}>
                        {formatNumber(totalCoposGeral) || '0'}
                      </div>
                      <div className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'} mt-1`}>
                        Dist: {formatNumber(totalCoposDistancias)} | Cheg: {formatNumber(chegadaTotalCalculado)} | Ativ: {formatNumber(totalCoposAtivacoes)}
                      </div>
                    </div>
                    <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/50' : 'bg-white'} text-center`}>
                      <div className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Copos por Caixa</div>
                      <div className={`text-2xl font-black ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
                        {formatNumber(coposPorCaixa)}
                      </div>
                    </div>
                    <div className={`p-4 rounded-xl ${isDark ? 'bg-gray-800/50' : 'bg-white'} text-center`}>
                      <div className={`text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total de Caixas</div>
                      <div className={`text-2xl font-black bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent`}>
                        {formatNumber(totalCaixas)}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        <div className="absolute top-1/2 left-1/2 w-64 h-64 bg-orange-500/5 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      <div className="relative z-10 space-y-8 p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 shadow-lg shadow-purple-500/30">
                <Trophy className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className={`text-3xl font-black tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  Cadastro
                  <span className="bg-gradient-to-r from-purple-400 via-pink-500 to-orange-500 bg-clip-text text-transparent"> de Eventos</span>
                </h1>
                <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                  Gerencie seus cadastros de eventos esportivos
                </p>
              </div>
            </div>
          </div>

          <button 
            onClick={openNewModal} 
            className="group relative px-6 py-3 bg-gradient-to-r from-purple-600 via-pink-600 to-orange-500 text-white rounded-2xl font-semibold shadow-xl shadow-purple-500/30 hover:shadow-purple-500/50 transition-all duration-300 hover:scale-105 overflow-hidden"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-purple-400 via-pink-400 to-orange-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <span className="relative flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Novo Cadastro
              <Sparkles className="w-4 h-4" />
            </span>
          </button>
        </div>

        <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
              <input
                type="text"
                placeholder="Buscar por nome do evento ou local..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className={`w-full pl-10 pr-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 placeholder-gray-500'} focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all`}
              />
            </div>

            {busca && (
              <button
                onClick={() => setBusca('')}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-700 hover:bg-gray-50'} transition-all`}
              >
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium">Limpar</span>
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-purple-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-purple-500/20">
                  <Target className="w-4 h-4 text-purple-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Eventos</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{totalEventos}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-emerald-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-emerald-500/20">
                  <Zap className="w-4 h-4 text-emerald-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Em Andamento</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{emAndamento}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-blue-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-blue-500/20">
                  <Check className="w-4 h-4 text-blue-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Concluídos</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{concluidos}</p>
            </div>
          </div>

          <div className={`relative overflow-hidden rounded-2xl p-4 ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
            <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-orange-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center gap-2 mb-2">
                <div className="p-1.5 rounded-lg bg-orange-500/20">
                  <Users className="w-4 h-4 text-orange-400" />
                </div>
                <span className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Total Atletas</span>
              </div>
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalAtletas) || '0'}</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {loading ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-purple-500/30 rounded-full" />
                <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-purple-500 rounded-full animate-spin" />
              </div>
              <p className={`mt-4 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Carregando cadastros...</p>
            </div>
          ) : filteredCadastros.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20">
              <div className="p-4 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 mb-4">
                <Trophy className="w-12 h-12 text-purple-400" />
              </div>
              <p className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                {busca ? 'Nenhum cadastro encontrado' : 'Nenhum cadastro encontrado'}
              </p>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                {busca ? 'Tente ajustar a busca' : 'Crie seu primeiro cadastro clicando no botão acima'}
              </p>
            </div>
          ) : filteredCadastros.map((cadastro, index) => {
            const statusStyle = getStatusStyle(cadastro.status);
            const totalAtletasCad = getTotalAtletasCadastro(cadastro);
            const tktMedioGeral = ((cadastro.atletas.site.tkt_medio || 0) + (cadastro.atletas.grupos.tkt_medio || 0)) / 2;

            return (
              <div 
                key={cadastro.id} 
                className={`group relative overflow-hidden rounded-3xl ${isDark ? 'bg-gray-800/80 backdrop-blur-xl' : 'bg-white/90 backdrop-blur-xl'} border ${isDark ? 'border-gray-700/50' : 'border-gray-200'} shadow-xl hover:shadow-2xl transition-all duration-500 hover:-translate-y-2`}
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <div className="relative h-48 overflow-hidden">
                  {cadastro.imagem_kv ? (
                    <img 
                      src={cadastro.imagem_kv} 
                      alt={cadastro.nome}
                      className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-700"
                    />
                  ) : (
                    <div className={`w-full h-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center`}>
                      <ImageIcon className="w-12 h-12 text-white/30" />
                    </div>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                  
                  <div className="absolute top-3 left-3 flex gap-2">
                    <div className={`px-3 py-1.5 rounded-full ${statusStyle.bg} ${statusStyle.border} border backdrop-blur-md`}>
                      <span className={`flex items-center gap-1.5 text-xs font-bold ${statusStyle.text}`}>
                        {statusStyle.icon}
                        {cadastro.status}
                      </span>
                    </div>
                  </div>

                  <div className="absolute bottom-3 left-3 right-3">
                    <h3 className="text-xl font-black text-white mb-1 line-clamp-1">{cadastro.nome}</h3>
                    <div className="flex items-center gap-2 text-white/80 text-sm">
                      <Calendar className="w-4 h-4" />
                      <span>{formatDateDisplay(cadastro.info_geral.data)}</span>
                      <span className="text-white/50">•</span>
                      <Clock className="w-4 h-4" />
                      <span>{cadastro.info_geral.horario_largada}</span>
                    </div>
                  </div>
                </div>

                <div className="p-4 space-y-4">
                  <div className="flex items-center gap-2 text-sm">
                    <MapPin className={`w-4 h-4 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                    <span className={`${isDark ? 'text-gray-300' : 'text-gray-700'} line-clamp-1`}>{cadastro.info_geral.local}</span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {cadastro.info_geral.distancias.map(d => (
                      <span 
                        key={d}
                        className="px-3 py-1 rounded-full bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-purple-400 text-xs font-bold"
                      >
                        {d}
                      </span>
                    ))}
                  </div>

                  <div className="grid grid-cols-3 gap-2 py-3 border-t border-gray-700/50">
                    <div className="text-center">
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total</p>
                      <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalAtletasCad) || '0'}</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Site</p>
                      <p className={`text-lg font-bold text-blue-400`}>{formatNumber((cadastro.atletas.site.pago || 0) + (cadastro.atletas.site.cortesia || 0)) || '0'}</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Grupos</p>
                      <p className={`text-lg font-bold text-orange-400`}>{formatNumber((cadastro.atletas.grupos.pago || 0) + (cadastro.atletas.grupos.cortesia || 0)) || '0'}</p>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => handleViewDetails(cadastro)}
                      className={`flex-1 py-2.5 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 ${isDark ? 'bg-gray-700/50 text-gray-300 hover:bg-gray-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
                    >
                      <Eye className="w-4 h-4" />
                      Detalhes
                    </button>
                    <button
                      onClick={() => handleEdit(cadastro)}
                      className="flex-1 py-2.5 rounded-xl font-semibold bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all flex items-center justify-center gap-2"
                    >
                      <Pencil className="w-4 h-4" />
                      Editar
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showDetailsModal && selectedCadastro && (
        <div 
          className="fixed inset-0 bg-black/70 backdrop-blur-md flex items-center justify-center z-50 overflow-y-auto p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowDetailsModal(false);
              setSelectedCadastro(null);
            }
          }}
        >
          <div 
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl w-[90%] max-w-7xl my-4 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden max-h-[90vh] flex flex-col`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative h-64 overflow-hidden flex-shrink-0">
              {selectedCadastro.imagem_kv ? (
                <img 
                  src={selectedCadastro.imagem_kv} 
                  alt={selectedCadastro.nome}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className={`w-full h-full bg-gradient-to-br from-purple-600 to-pink-600 flex items-center justify-center`}>
                  <ImageIcon className="w-20 h-20 text-white/30" />
                </div>
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent" />
              
              <button 
                onClick={() => {
                  setShowDetailsModal(false);
                  setSelectedCadastro(null);
                }}
                className="absolute top-4 right-4 p-2 rounded-full bg-black/40 backdrop-blur-md border border-white/20 text-white hover:bg-black/60 transition-colors"
              >
                <X className="w-6 h-6" />
              </button>

              <div className="absolute bottom-4 left-4 right-4">
                <h2 className="text-3xl font-black text-white mb-2">{selectedCadastro.nome}</h2>
                <div className="flex items-center gap-4 text-white/80">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-5 h-5" />
                    <span>{formatDateDisplay(selectedCadastro.info_geral.data)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-5 h-5" />
                    <span>{selectedCadastro.info_geral.horario_largada}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MapPin className="w-5 h-5" />
                    <span>{selectedCadastro.info_geral.local}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div className="grid grid-cols-4 gap-4">
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Atletas</p>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(getTotalAtletasCadastro(selectedCadastro)) || '0'}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Site</p>
                  <p className="text-2xl font-bold text-blue-400">{formatNumber((selectedCadastro.atletas.site.pago || 0) + (selectedCadastro.atletas.site.cortesia || 0)) || '0'}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Grupos</p>
                  <p className="text-2xl font-bold text-orange-400">{formatNumber((selectedCadastro.atletas.grupos.pago || 0) + (selectedCadastro.atletas.grupos.cortesia || 0)) || '0'}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Troféus</p>
                  <p className="text-2xl font-bold text-amber-400">{selectedCadastro.trofeus || 0}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <span className={`text-sm font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Distâncias:</span>
                {selectedCadastro.info_geral.distancias.map(d => (
                  <span 
                    key={d}
                    className="px-4 py-1.5 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 text-white text-sm font-bold"
                  >
                    {d}
                  </span>
                ))}
              </div>

              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowDetailsModal(false);
                    setSelectedCadastro(null);
                  }}
                  className={`px-6 py-3 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'} transition-colors`}
                >
                  Fechar
                </button>
                <button
                  onClick={() => {
                    setShowDetailsModal(false);
                    handleEdit(selectedCadastro);
                  }}
                  className="px-6 py-3 rounded-xl font-semibold bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all flex items-center gap-2"
                >
                  <Pencil className="w-5 h-5" />
                  Editar Cadastro
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 overflow-y-auto p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowModal(false);
              setEditItem(null);
            }
          }}
        >
          <div 
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl w-[90%] max-w-7xl my-4 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden max-h-[90vh] flex flex-col`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`relative h-48 overflow-hidden flex-shrink-0 ${isDark ? 'bg-gray-800' : 'bg-gray-100'}`}>
              {form.imagem_kv ? (
                <img 
                  src={form.imagem_kv} 
                  alt="Preview"
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-purple-600/50 to-pink-600/50 flex items-center justify-center">
                  <div className="text-center">
                    <ImageIcon className="w-16 h-16 text-white/30 mx-auto mb-2" />
                    <p className="text-white/50">Adicione uma imagem do evento</p>
                  </div>
                </div>
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              
              <button 
                type="button"
                onClick={() => {
                  setShowModal(false);
                  setEditItem(null);
                }}
                className="absolute top-4 right-4 p-2 rounded-full bg-black/40 backdrop-blur-md border border-white/20 text-white hover:bg-black/60 transition-colors"
              >
                <X className="w-6 h-6" />
              </button>

              <div className="absolute bottom-4 left-4 right-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/50" />
                  <input
                    ref={searchInputRef}
                    type="text"
                    value={projetoBusca}
                    onChange={(e) => {
                      setProjetoBusca(e.target.value);
                      setShowProjetoDropdown(true);
                    }}
                    onClick={() => {
                      if (searchInputRef.current) {
                        const rect = searchInputRef.current.getBoundingClientRect();
                        setDropdownPosition({ top: rect.bottom + 8, left: rect.left, width: rect.width });
                      }
                      setShowProjetoDropdown(true);
                    }}
                    onFocus={() => {
                      if (searchInputRef.current) {
                        const rect = searchInputRef.current.getBoundingClientRect();
                        setDropdownPosition({ top: rect.bottom + 8, left: rect.left, width: rect.width });
                      }
                      setShowProjetoDropdown(true);
                    }}
                    placeholder="Clique para selecionar o evento..."
                    className="w-full pl-10 pr-16 py-3 text-xl font-bold bg-black/30 backdrop-blur-md text-white placeholder-white/50 border border-white/20 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 cursor-pointer"
                  />
                  {form.projeto_id ? (
                    <button
                      type="button"
                      onClick={() => {
                        setForm(prev => ({ ...prev, projeto_id: null, nome: '', imagem_kv: '' }));
                        setProjetoBusca('');
                      }}
                      className="absolute right-10 top-1/2 -translate-y-1/2 p-1 rounded-full bg-red-500/80 hover:bg-red-500 text-white transition-colors"
                      title="Remover seleção"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  ) : null}
                  <ChevronDown className={`absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/50 transition-transform ${showProjetoDropdown ? 'rotate-180' : ''}`} />
                  {showProjetoDropdown && (
                    <>
                      <div 
                        className="fixed inset-0 z-[100]" 
                        onClick={() => setShowProjetoDropdown(false)}
                      />
                      <div 
                        className={`fixed max-h-64 overflow-y-auto rounded-xl ${isDark ? 'bg-gray-800' : 'bg-white'} border ${isDark ? 'border-gray-700' : 'border-gray-200'} shadow-2xl z-[101]`}
                        style={{ top: dropdownPosition.top, left: dropdownPosition.left, width: dropdownPosition.width }}
                      >
                        <div className={`sticky top-0 px-4 py-2 border-b ${isDark ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
                          <p className={`text-xs font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            {filteredProjetos.length} evento{filteredProjetos.length !== 1 ? 's' : ''} disponível{filteredProjetos.length !== 1 ? 'is' : ''}
                          </p>
                        </div>
                        {filteredProjetos.length > 0 ? (
                          filteredProjetos.map(projeto => (
                            <button
                              key={projeto.id}
                              type="button"
                              onClick={() => {
                                setForm(prev => ({ ...prev, projeto_id: projeto.id, nome: projeto.evento, imagem_kv: projeto.imagem_kv || '' }));
                                setProjetoBusca(projeto.evento);
                                setShowProjetoDropdown(false);
                              }}
                              className={`w-full px-4 py-3 text-left hover:bg-purple-500/20 transition-colors flex items-center gap-3 ${
                                form.projeto_id === projeto.id ? (isDark ? 'bg-purple-500/30' : 'bg-purple-100') : ''
                              } ${isDark ? 'text-white' : 'text-gray-900'}`}
                            >
                              {projeto.imagem_kv ? (
                                <img src={projeto.imagem_kv} alt="" className="w-10 h-10 rounded-lg object-cover" />
                              ) : (
                                <div className={`w-10 h-10 rounded-lg ${isDark ? 'bg-gray-700' : 'bg-gray-200'} flex items-center justify-center`}>
                                  <Calendar className="w-5 h-5 text-gray-400" />
                                </div>
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="font-semibold truncate">{projeto.evento}</div>
                                <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{projeto.codigo}</div>
                              </div>
                              {form.projeto_id === projeto.id && (
                                <Check className="w-5 h-5 text-purple-500 flex-shrink-0" />
                              )}
                            </button>
                          ))
                        ) : (
                          <div className={`px-4 py-6 text-center ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                            <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                            <p>Nenhum evento encontrado</p>
                            <p className="text-xs mt-1">Tente outro termo de busca</p>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>


            <div className="flex overflow-x-auto scrollbar-hide border-b border-gray-700/50">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-5 py-4 font-medium whitespace-nowrap transition-all relative ${
                      isActive
                        ? isDark ? 'text-purple-400' : 'text-purple-600'
                        : isDark ? 'text-gray-400 hover:text-gray-300' : 'text-gray-600 hover:text-gray-800'
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? 'text-purple-500' : ''}`} />
                    <span className="text-sm">{tab.label}</span>
                    {isActive && (
                      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
                    )}
                  </button>
                );
              })}
            </div>

            <form onSubmit={handleSubmit} className="flex-1 flex flex-col min-h-0">
              <div className="p-6 flex-1 overflow-y-auto scrollbar-thin-custom">
                {renderTabContent()}
              </div>

              <div className={`p-4 border-t flex-shrink-0 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'} flex justify-end gap-3`}>
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditItem(null);
                  }}
                  className={`px-6 py-3 rounded-xl font-semibold ${isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'} transition-colors`}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-8 py-3 rounded-xl font-semibold bg-gradient-to-r from-purple-500 via-pink-500 to-orange-500 text-white shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all flex items-center gap-2"
                >
                  <Check className="w-5 h-5" />
                  {editItem ? 'Salvar Alterações' : 'Criar Cadastro'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <style>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-hide {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default Cadastro;
