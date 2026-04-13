import React, { useState, useMemo, useEffect } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { usePermissions } from '../../context/PermissionContext';
import { cadastrosService } from '../../services/api';
import api from '../../services/api';
import { 
  Plus, Pencil, X, Check, Calendar, MapPin, Users, 
  Trophy, Zap, Target, Sparkles, Clock, Package,
  Image as ImageIcon, Search, Filter, Eye,
  RotateCcw, DollarSign, Timer,
  Hash, Award, Ticket, Droplets, Gift, Layers,
  UserPlus, Building2, ShoppingBag, Ruler, Palette,
  TrendingUp, TrendingDown, AlertCircle, Globe, UsersRound,
  Box, Flag, Activity, Scale, Download, Trash2, RefreshCw, Percent,
  ChevronDown, ChevronUp
} from 'lucide-react';

interface CortesiaItem {
  cliente: string;
  quantidade: number;
}

interface TaxaItem {
  valor_unitario: number;
  percentual_inscricao: number;
  tipo_calculo: 'unitario' | 'percentual';
  validado: boolean;
  data_validacao: string;
}

interface FaixaPrecoItem {
  faixa: string;
  qtd: number;
  tkt_medio: number;
  total: number;
}

interface FaixasPrecoSiteByKit {
  kit_basico: FaixaPrecoItem[];
  kit_participacao: FaixaPrecoItem[];
  kit_sem_bike: FaixaPrecoItem[];
  kit_com_bike: FaixaPrecoItem[];
}

interface CiclismoCenariosData {
  participacao_pago: number;
  sem_bike_pago: number;
  sem_bike_tkt_medio: number;
  com_bike_pago: number;
  com_bike_tkt_medio: number;
}

interface CadastroEvento {
  id: number;
  projeto_id: number | null;
  nome: string;
  circuito_produto: string;
  localizacao_evento: string;
  ano_evento: number | null;
  imagem_kv: string;
  status: string;
  modalidade: string;
  sku: string;
  produto: string;
  tipo_evento: string;
  lei: string;
  capacidade_maxima: number | null;
  cidade: string;
  estado: string;
  info_geral: {
    data: string;
    horario_largada: string;
    local: string;
    distancias: any[];
    dias_encerramento_inscricao: number;
  };
  atletas: {
    site: { pago: number; tkt_medio: number };
    grupos: { pago: number; tkt_medio: number };
    cortesia: number;
    appai: { pago: number; tkt_medio: number };
    ciclismo?: CiclismoCenariosData;
  };
  cortesias: CortesiaItem[];
  taxas: TaxaItem[];
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  kit_produto: Array<{ kit: string; ativo_categoria?: string; produtos: Array<{ nome: string; valor_unitario: number }> }>;
  merchan: Array<{ kit: string; itens: Array<{ nome: string; valor_venda: number }> }>;
  faixas_preco_site: FaixasPrecoSiteByKit;
  faixas_preco_grupos: FaixasPrecoSiteByKit;
}

interface FormData {
  projeto_id: number | null;
  nome: string;
  circuito_produto: string;
  localizacao_evento: string;
  ano_evento: number;
  imagem_kv: string;
  status: string;
  modalidade: string;
  sku: string;
  produto: string;
  tipo_evento: string;
  lei: string;
  capacidade_maxima: number | null;
  cidade: string;
  estado: string;
  info_geral: {
    data: string;
    horario_largada: string;
    local: string;
    distancias: any[];
    dias_encerramento_inscricao: number;
  };
  atletas: {
    site: { pago: number; tkt_medio: number };
    grupos: { pago: number; tkt_medio: number };
    cortesia: number;
    appai: { pago: number; tkt_medio: number };
    ciclismo?: CiclismoCenariosData;
  };
  cortesias: CortesiaItem[];
  taxas: TaxaItem[];
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  kit_produto: Array<{ kit: string; ativo_categoria?: string; produtos: Array<{ nome: string; valor_unitario: number }> }>;
  merchan: Array<{ kit: string; itens: Array<{ nome: string; valor_venda: number }> }>;
  faixas_preco_site: FaixasPrecoSiteByKit;
  faixas_preco_grupos: FaixasPrecoSiteByKit;
}

const distanciasOptionsFallback = ['3k', '5k', '10k', '13k', '15k', '21k', '42k'];
const pelotoesOptions = ['Quênia', 'Azul', 'Verde', 'Branco'];
const kitOptions = ['Kit Básico', 'Kit Participação', 'Kit Vip', 'Kit Plus', 'Kit Super'];
const faixaOptions = ['1', '2', '3', '4', '5'];
const coresPeitoOptions = ['Branco', 'Amarelo', 'Laranja', 'Verde', 'Azul', 'Vermelho', 'Rosa', 'Roxo', 'Preto'];
const modalidadesOptions = ['Beach', 'Ciclismo', 'Corrida', 'Cultura', 'Educação', 'E-Sports', 'Família', 'Natação', 'Obstáculo', 'Saúde', 'Triathlon'];

const mesesOptions = [
  { value: '01', label: 'Janeiro' }, { value: '02', label: 'Fevereiro' },
  { value: '03', label: 'Março' },   { value: '04', label: 'Abril' },
  { value: '05', label: 'Maio' },    { value: '06', label: 'Junho' },
  { value: '07', label: 'Julho' },   { value: '08', label: 'Agosto' },
  { value: '09', label: 'Setembro' },{ value: '10', label: 'Outubro' },
  { value: '11', label: 'Novembro' },{ value: '12', label: 'Dezembro' },
];
const tiposEventoOptions = ['Próprio', 'Incentivado', 'Organização', 'Licenciado'];
const leisOptions = ['', 'LIE', 'PIE', 'FIA', 'ICMS RJ', 'PROAC', 'PRONAC', 'ROUANET', 'ISS RJ'];
const statusOptions = ['Em andamento', 'Concluído', 'Cancelado'];

const produtosDisponiveis = [
  'Camiseta', 'Medalha', 'Garrafa', 'Sacochila', 'Mochila', 'Sacola',
  'Moletom', 'Jaqueta', 'Boné', 'Viseira', 'Toalha', 'Touca', 'Squeeze', 'Munhequeira'
];

const produtosPadraoPorKit: Record<string, Array<{ nome: string; valor_unitario: number }>> = {
  'Kit Participação': [{ nome: 'Medalha', valor_unitario: 0 }],
  'Kit Básico': [{ nome: 'Camiseta', valor_unitario: 0 }, { nome: 'Medalha', valor_unitario: 0 }, { nome: 'Garrafa', valor_unitario: 0 }, { nome: 'Sacochila', valor_unitario: 0 }, { nome: 'Mochila', valor_unitario: 0 }, { nome: 'Sacola', valor_unitario: 0 }],
  'Kit Vip': [{ nome: 'Camiseta', valor_unitario: 0 }, { nome: 'Medalha', valor_unitario: 0 }, { nome: 'Garrafa', valor_unitario: 0 }, { nome: 'Sacochila', valor_unitario: 0 }, { nome: 'Mochila', valor_unitario: 0 }, { nome: 'Sacola', valor_unitario: 0 }, { nome: 'Moletom', valor_unitario: 0 }, { nome: 'Jaqueta', valor_unitario: 0 }],
  'Kit Plus': [{ nome: 'Camiseta', valor_unitario: 0 }, { nome: 'Medalha', valor_unitario: 0 }, { nome: 'Garrafa', valor_unitario: 0 }, { nome: 'Sacochila', valor_unitario: 0 }, { nome: 'Mochila', valor_unitario: 0 }, { nome: 'Sacola', valor_unitario: 0 }, { nome: 'Boné', valor_unitario: 0 }, { nome: 'Viseira', valor_unitario: 0 }],
  'Kit Super': [{ nome: 'Camiseta', valor_unitario: 0 }, { nome: 'Medalha', valor_unitario: 0 }, { nome: 'Garrafa', valor_unitario: 0 }, { nome: 'Sacochila', valor_unitario: 0 }, { nome: 'Mochila', valor_unitario: 0 }, { nome: 'Sacola', valor_unitario: 0 }]
};

const produtosExtrasPorKit: Record<string, string[]> = {
  'Kit Vip': ['Moletom', 'Jaqueta'],
  'Kit Plus': ['Boné', 'Viseira'],
  'Kit Super': [],
};

const defaultCiclismoData: CiclismoCenariosData = {
  participacao_pago: 0,
  sem_bike_pago: 0,
  sem_bike_tkt_medio: 0,
  com_bike_pago: 0,
  com_bike_tkt_medio: 0,
};

const defaultFaixaRow: FaixaPrecoItem = { faixa: '1', qtd: 0, tkt_medio: 0, total: 0 };

const createDefaultCadastro = (): Omit<CadastroEvento, 'id'> => ({
  projeto_id: null,
  nome: '',
  circuito_produto: '',
  localizacao_evento: '',
  ano_evento: new Date().getFullYear(),
  imagem_kv: '',
  status: 'Em andamento',
  modalidade: 'Corrida',
  sku: '',
  produto: '',
  tipo_evento: 'Próprio',
  lei: '',
  capacidade_maxima: null,
  cidade: '',
  estado: '',
  info_geral: { data: '', horario_largada: '', local: '', distancias: [], dias_encerramento_inscricao: 2 },
  atletas: {
    site: { pago: 0, tkt_medio: 0 },
    grupos: { pago: 0, tkt_medio: 0 },
    cortesia: 0,
    appai: { pago: 0, tkt_medio: 0 },
    ciclismo: { ...defaultCiclismoData }
  },
  cortesias: [],
  taxas: [],
  retirada_kit: { local: '', data_horario: '' },
  kit_produto: [{ kit: '', produtos: [] }],
  merchan: [],
  faixas_preco_site: {
    kit_basico: [{ ...defaultFaixaRow }],
    kit_participacao: [{ ...defaultFaixaRow }],
    kit_sem_bike: [{ ...defaultFaixaRow }],
    kit_com_bike: [{ ...defaultFaixaRow }]
  },
  faixas_preco_grupos: {
    kit_basico: [{ ...defaultFaixaRow }],
    kit_participacao: [{ ...defaultFaixaRow }],
    kit_sem_bike: [{ ...defaultFaixaRow }],
    kit_com_bike: [{ ...defaultFaixaRow }]
  }
});


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
  { id: 'retirada_kit', label: 'Retirada Kit', icon: Package },
  { id: 'atletas', label: 'Atletas', icon: Users },
  { id: 'cortesias', label: 'Cortesias', icon: Gift },
  { id: 'kit_produto', label: 'Kit Produto', icon: Gift },
  { id: 'merchan', label: 'Merchan', icon: ShoppingBag },
  { id: 'faixas_preco_site', label: 'Faixa Preço - Site', icon: Globe },
  { id: 'faixas_preco_grupos', label: 'Faixa Preço - Grupos', icon: UsersRound },
  { id: 'taxas', label: 'Taxas', icon: DollarSign },  
];

const Cadastro: React.FC = () => {
  const { isDark } = useTheme();
  const { permissions, canViewCampo, canEditCampo } = usePermissions();
  const isAdmin = permissions?.is_admin || false;
  const [cadastros, setCadastros] = useState<CadastroEvento[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [loadingEditId, setLoadingEditId] = useState<number | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedCadastro, setSelectedCadastro] = useState<CadastroEvento | null>(null);
  const [editItem, setEditItem] = useState<CadastroEvento | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [activeTab, setActiveTab] = useState('info_geral');
  const [busca, setBusca] = useState('');
  const [filterMes, setFilterMes] = useState('');
  const [filterModalidade, setFilterModalidade] = useState('');
  const [filterTipoEvento, setFilterTipoEvento] = useState('');
  const [filterLei, setFilterLei] = useState('');
  const [filterLocalizacao, setFilterLocalizacao] = useState('');
  
  const [circuitos, setCircuitos] = useState<{id: number; nome: string}[]>([]);
  const [localizacoes, setLocalizacoes] = useState<{id: number; nome: string}[]>([]);
  const [editingCircuito, setEditingCircuito] = useState<{id: number; nome: string} | null>(null);
  const [editingLocalizacao, setEditingLocalizacao] = useState<{id: number; nome: string} | null>(null);
  const [newCircuito, setNewCircuito] = useState('');
  const [newLocalizacao, setNewLocalizacao] = useState('');
  const [showAddCircuito, setShowAddCircuito] = useState(false);
  const [showAddLocalizacao, setShowAddLocalizacao] = useState(false);

  const [distanciasOptions, setDistanciasOptions] = useState<string[]>(distanciasOptionsFallback);
  const [showAddDistancia, setShowAddDistancia] = useState(false);
  const [newDistancia, setNewDistancia] = useState('');

  const [lixeira, setLixeira] = useState<any[]>([]);
  const [showLixeira, setShowLixeira] = useState(false);
  const [loadingLixeira, setLoadingLixeira] = useState(false);
  const [merchanMode, setMerchanMode] = useState<'venda' | 'planejamento'>('venda');
  const [collapsedSite, setCollapsedSite] = useState<Record<string, boolean>>({ kit_basico: false, kit_participacao: false, kit_sem_bike: false, kit_com_bike: false });
  const [collapsedGrupos, setCollapsedGrupos] = useState<Record<string, boolean>>({ kit_basico: false, kit_participacao: false, kit_sem_bike: false, kit_com_bike: false });

  const visibleTabs = useMemo(() => {
    return tabs.filter(tab => canViewCampo('eventos', tab.id));
  }, [permissions]);

  useEffect(() => {
    if (visibleTabs.length > 0 && !visibleTabs.find(t => t.id === activeTab)) {
      setActiveTab(visibleTabs[0].id);
    }
  }, [visibleTabs]);

  useEffect(() => {
    loadCadastros();
    loadOpcoes();
    loadDistancias();
  }, []);

  const handleDeleteEvento = async (cadastro: CadastroEvento) => {
    if (!confirm(`Mover "${cadastro.nome}" para a lixeira?\n\nVocê poderá restaurar este evento nos próximos 30 dias.`)) return;
    try {
      await cadastrosService.delete(cadastro.id!);
      setCadastros(prev => prev.filter(c => c.id !== cadastro.id));
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Erro ao mover para lixeira');
    }
  };

  const loadLixeira = async () => {
    setLoadingLixeira(true);
    try {
      const data = await cadastrosService.listLixeira();
      setLixeira(data);
    } catch (err) {
      console.error('Erro ao carregar lixeira:', err);
    } finally {
      setLoadingLixeira(false);
    }
  };

  const handleRestaurar = async (id: number, nome: string) => {
    if (!confirm(`Restaurar "${nome}"?`)) return;
    try {
      await cadastrosService.restore(id);
      setLixeira(prev => prev.filter(c => c.id !== id));
      await loadCadastros();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Erro ao restaurar');
    }
  };

  const loadCadastros = async () => {
    try {
      setLoading(true);
      setLoadError(false);
      const data = await cadastrosService.list();
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const processed = data.map((item: CadastroEvento) => {
        if (item.status !== 'Cancelado' && item.status !== 'Concluído' && item.info_geral?.data) {
          const parts = item.info_geral.data.split('T')[0].split('-');
          const eventDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
          if (eventDate < today) {
            cadastrosService.update(item.id!, { status: 'Concluído' }).catch(() => {});
            return { ...item, status: 'Concluído' };
          }
        }
        return item;
      });
      setCadastros(processed);
    } catch (error) {
      console.error('Erro ao carregar cadastros:', error);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  const loadOpcoes = async () => {
    try {
      const [circData, locData] = await Promise.all([
        cadastrosService.getCircuitos(),
        cadastrosService.getLocalizacoes()
      ]);
      setCircuitos(circData);
      setLocalizacoes(locData);
    } catch (error) {
      console.error('Erro ao carregar opções:', error);
    }
  };

  const loadDistancias = async () => {
    try {
      const res = await api.get('/distancias/');
      if (res.data && res.data.length > 0) {
        setDistanciasOptions(res.data.map((d: any) => d.nome));
      }
    } catch (error) {
      console.error('Erro ao carregar distâncias:', error);
    }
  };

  const handleAddDistancia = async () => {
    const nome = newDistancia.trim();
    if (!nome) return;
    try {
      await api.post('/distancias/', { nome });
      setNewDistancia('');
      setShowAddDistancia(false);
      loadDistancias();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Erro ao adicionar distância');
    }
  };

  const initialFormData: FormData = {
    projeto_id: null,
    nome: '',
    circuito_produto: '',
    localizacao_evento: '',
    ano_evento: new Date().getFullYear(),
    imagem_kv: '',
    status: 'Em andamento',
    modalidade: 'Corrida',
    sku: '',
    produto: '',
    tipo_evento: 'Próprio',
    lei: '',
    capacidade_maxima: null,
    cidade: '',
    estado: '',
    info_geral: {
      data: '',
      horario_largada: '',
      local: '',
      distancias: [],
      dias_encerramento_inscricao: 2
    },
    atletas: {
      site: { pago: 0, tkt_medio: 0 },
      grupos: { pago: 0, tkt_medio: 0 },
      cortesia: 0,
      appai: { pago: 0, tkt_medio: 0 },
      ciclismo: { ...defaultCiclismoData }
    },
    cortesias: [],
    taxas: [],
    retirada_kit: {
      local: '',
      data_horario: ''
    },
    kit_produto: [{ kit: '', produtos: [] }],
    merchan: [],
    faixas_preco_site: {
      kit_basico: [{ ...defaultFaixaRow }],
      kit_participacao: [{ ...defaultFaixaRow }],
      kit_sem_bike: [{ ...defaultFaixaRow }],
      kit_com_bike: [{ ...defaultFaixaRow }]
    },
    faixas_preco_grupos: {
      kit_basico: [{ ...defaultFaixaRow }],
      kit_participacao: [{ ...defaultFaixaRow }],
      kit_sem_bike: [{ ...defaultFaixaRow }],
      kit_com_bike: [{ ...defaultFaixaRow }]
    }
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
    const gruposPago = form.atletas.grupos.pago || 0;
    const cortesias = form.atletas.cortesia || 0;
    const appaiPago = form.atletas.appai?.pago || 0;
    return sitePago + gruposPago + cortesias + appaiPago;
  };

  const getTotalAtletasCadastro = (cadastro: CadastroEvento) => {
    return (cadastro.atletas.site.pago || 0) + 
           (cadastro.atletas.grupos.pago || 0) + 
           (cadastro.atletas.cortesia || 0) +
           (cadastro.atletas.appai?.pago || 0);
  };

  const getTotalCortesiasAlocadas = () => {
    return form.cortesias.reduce((total, c) => total + (c.quantidade || 0), 0);
  };

  const maxCortesias = form.atletas.cortesia || 0;
  const excedeCortesias = getTotalCortesiasAlocadas() > maxCortesias;

  const filteredCadastros = useMemo(() => {
    let result = [...cadastros].sort((a, b) => {
      const da = (a.info_geral.data || '').split('T')[0];
      const db = (b.info_geral.data || '').split('T')[0];
      return db.localeCompare(da);
    });

    if (busca) {
      const q = busca.toLowerCase();
      result = result.filter(c =>
        c.nome.toLowerCase().includes(q) ||
        (c.info_geral.local || '').toLowerCase().includes(q)
      );
    }
    if (filterMes) {
      result = result.filter(c => {
        const data = (c.info_geral.data || '').split('T')[0];
        return data.split('-')[1] === filterMes;
      });
    }
    if (filterModalidade) {
      result = result.filter(c => c.modalidade === filterModalidade);
    }
    if (filterTipoEvento) {
      result = result.filter(c => c.tipo_evento === filterTipoEvento);
    }
    if (filterLei) {
      result = result.filter(c => (c.lei || '') === filterLei);
    }
    if (filterLocalizacao) {
      result = result.filter(c =>
        (c.localizacao_evento || '').toLowerCase().includes(filterLocalizacao.toLowerCase())
      );
    }
    return result;
  }, [cadastros, busca, filterMes, filterModalidade, filterTipoEvento, filterLei, filterLocalizacao]);

  const activeFilterCount = [filterMes, filterModalidade, filterTipoEvento, filterLei, filterLocalizacao].filter(Boolean).length;
  const hasActiveFilters = !!(busca || activeFilterCount);

  const clearAllFilters = () => {
    setBusca('');
    setFilterMes('');
    setFilterModalidade('');
    setFilterTipoEvento('');
    setFilterLei('');
    setFilterLocalizacao('');
  };

  const totalEventos = cadastros.length;
  const emAndamento = cadastros.filter(c => c.status === 'Em andamento').length;
  const concluidos = cadastros.filter(c => c.status === 'Concluído').length;
  const totalAtletas = cadastros.reduce((acc, c) => acc + getTotalAtletasCadastro(c), 0);

  const openNewModal = () => {
    setEditItem(null);
    setForm(initialFormData);
    setActiveTab('info_geral');
    setShowModal(true);
  };

  const handleViewDetails = (cadastro: CadastroEvento) => {
    setSelectedCadastro(cadastro);
    setShowDetailsModal(true);
  };

  const populateForm = (item: CadastroEvento) => {
    setEditItem(item);
    setForm({
      projeto_id: item.projeto_id,
      nome: item.nome,
      circuito_produto: item.circuito_produto || '',
      localizacao_evento: item.localizacao_evento || '',
      ano_evento: item.ano_evento || new Date().getFullYear(),
      imagem_kv: item.imagem_kv,
      status: item.status || 'Em andamento',
      modalidade: item.modalidade || 'Corrida',
      sku: item.sku || '',
      produto: item.produto || '',
      tipo_evento: item.tipo_evento || 'Próprio',
      lei: item.lei || '',
      capacidade_maxima: item.capacidade_maxima || null,
      cidade: item.cidade || '',
      estado: item.estado || '',
      info_geral: { ...item.info_geral },
      atletas: { 
        site: { ...item.atletas.site },
        grupos: { ...item.atletas.grupos },
        cortesia: item.atletas.cortesia || 0,
        appai: item.atletas.appai ? { ...item.atletas.appai } : { pago: 0, tkt_medio: 0 },
        ciclismo: item.atletas.ciclismo ? { ...item.atletas.ciclismo } : { ...defaultCiclismoData }
      },
      cortesias: item.cortesias?.length > 0 ? item.cortesias.map(c => ({ ...c })) : [],
      taxas: item.taxas?.length > 0 ? item.taxas.map(t => ({
        ...t,
        tipo_calculo: ((t.percentual_inscricao || 0) > 0 ? 'percentual' : 'unitario') as 'unitario' | 'percentual'
      })) : [],
      retirada_kit: { ...item.retirada_kit },
      kit_produto: item.kit_produto.length > 0 ? item.kit_produto.map(k => ({ kit: k.kit, ativo_categoria: k.ativo_categoria ?? '', produtos: k.produtos.map(p => ({ ...p, valor_unitario: Number(p.valor_unitario) || 0 })) })) : [{ kit: '', ativo_categoria: '', produtos: [] }],
      merchan: (item.merchan || []).map(mk => ({ kit: mk.kit, itens: (mk.itens || []).map(it => ({ nome: it.nome, valor_venda: Number(it.valor_venda) || 0 })) })),
      faixas_preco_site: {
        kit_basico: item.faixas_preco_site?.kit_basico?.length > 0 
          ? item.faixas_preco_site.kit_basico.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_participacao: item.faixas_preco_site?.kit_participacao?.length > 0 
          ? item.faixas_preco_site.kit_participacao.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_sem_bike: item.faixas_preco_site?.kit_sem_bike?.length > 0 
          ? item.faixas_preco_site.kit_sem_bike.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_com_bike: item.faixas_preco_site?.kit_com_bike?.length > 0 
          ? item.faixas_preco_site.kit_com_bike.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }]
      },
      faixas_preco_grupos: {
        kit_basico: item.faixas_preco_grupos?.kit_basico?.length > 0 
          ? item.faixas_preco_grupos.kit_basico.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_participacao: item.faixas_preco_grupos?.kit_participacao?.length > 0 
          ? item.faixas_preco_grupos.kit_participacao.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_sem_bike: item.faixas_preco_grupos?.kit_sem_bike?.length > 0 
          ? item.faixas_preco_grupos.kit_sem_bike.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }],
        kit_com_bike: item.faixas_preco_grupos?.kit_com_bike?.length > 0 
          ? item.faixas_preco_grupos.kit_com_bike.map(f => ({ ...f })) 
          : [{ faixa: '1', qtd: 0, tkt_medio: 0, total: 0 }]
      }
    });
    setActiveTab('info_geral');
    setShowModal(true);
  };

  const handleEdit = async (item: CadastroEvento) => {
    if (!item.id) return;
    setLoadingEditId(item.id);
    try {
      const full = await cadastrosService.get(item.id);
      populateForm(full);
    } catch {
      populateForm(item);
    } finally {
      setLoadingEditId(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    try {
      setLoading(true);

      const nomeFinal = form.circuito_produto && form.localizacao_evento 
        ? `${form.circuito_produto} - ${form.localizacao_evento} ${form.ano_evento}` 
        : form.nome;

      const nomeDuplicado = cadastros.find(c => 
        c.nome.toLowerCase() === nomeFinal.toLowerCase() && c.id !== editItem?.id
      );
      if (nomeDuplicado) {
        alert(`Já existe um evento com o nome "${nomeFinal}". Escolha uma combinação diferente.`);
        setLoading(false);
        return;
      }

      if (form.sku && form.sku.trim()) {
        const skuDuplicado = cadastros.find(c => 
          c.sku && c.sku.toLowerCase() === form.sku.toLowerCase() && c.id !== editItem?.id
        );
        if (skuDuplicado) {
          alert(`O SKU "${form.sku}" já está sendo usado pelo evento "${skuDuplicado.nome}". Informe um SKU diferente.`);
          setLoading(false);
          return;
        }
      }

      const payload = {
        projeto_id: form.projeto_id,
        nome: nomeFinal,
        circuito_produto: form.circuito_produto,
        localizacao_evento: form.localizacao_evento,
        ano_evento: form.ano_evento,
        imagem_kv: form.imagem_kv,
        status: form.status || 'Em andamento',
        modalidade: form.modalidade || 'Corrida',
        sku: form.sku,
        produto: form.produto,
        tipo_evento: form.tipo_evento,
        lei: form.lei,
        capacidade_maxima: form.capacidade_maxima,
        cidade: form.cidade,
        estado: form.estado,
        info_geral: form.info_geral,
        atletas: form.atletas,
        cortesias: form.cortesias,
        taxas: form.taxas,
        retirada_kit: form.retirada_kit,
        kit_produto: form.kit_produto,
        merchan: form.merchan,
        faixas_preco_site: form.faixas_preco_site,
        faixas_preco_grupos: form.faixas_preco_grupos
      };
      
      if (editItem) {
        await cadastrosService.update(editItem.id, payload);
      } else {
        await cadastrosService.create(payload);
      }
      
      await loadCadastros();
      setShowModal(false);
      setEditItem(null);
    } catch (error) {
      console.error('Erro ao salvar cadastro:', error);
      alert('Erro ao salvar cadastro. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const addArrayField = (field: 'kit_produto' | 'cortesias' | 'taxas') => {
    const defaults: Record<string, any> = {
      kit_produto: { kit: '', ativo_categoria: '', produtos: [] },
      cortesias: { cliente: '', quantidade: 0 },
      taxas: { valor_unitario: 0, percentual_inscricao: 0, tipo_calculo: 'unitario' as const, validado: false, data_validacao: '' }
    };
    setForm(prev => ({
      ...prev,
      [field]: [...(prev as any)[field], defaults[field]]
    }));
  };

  const addFaixaSiteByKit = (kitType: 'kit_basico' | 'kit_participacao') => {
    setForm(prev => {
      const currentFaixas = prev.faixas_preco_site[kitType];
      const nextFaixaNum = currentFaixas.length + 1;
      return {
        ...prev,
        faixas_preco_site: {
          ...prev.faixas_preco_site,
          [kitType]: [...currentFaixas, { faixa: String(nextFaixaNum), qtd: 0, tkt_medio: 0, total: 0 }]
        }
      };
    });
  };

  const removeFaixaSiteByKit = (kitType: 'kit_basico' | 'kit_participacao', index: number) => {
    setForm(prev => {
      const newFaixas = prev.faixas_preco_site[kitType].filter((_: any, i: number) => i !== index);
      const renumberedFaixas = newFaixas.map((f: FaixaPrecoItem, i: number) => ({ ...f, faixa: String(i + 1) }));
      return {
        ...prev,
        faixas_preco_site: {
          ...prev.faixas_preco_site,
          [kitType]: renumberedFaixas
        }
      };
    });
  };

  const updateFaixaSiteByKit = (kitType: 'kit_basico' | 'kit_participacao', index: number, key: string, value: any) => {
    setForm(prev => ({
      ...prev,
      faixas_preco_site: {
        ...prev.faixas_preco_site,
        [kitType]: prev.faixas_preco_site[kitType].map((item: FaixaPrecoItem, i: number) =>
          i === index ? { ...item, [key]: value } : item
        )
      }
    }));
  };

  const addFaixaGruposByKit = (kitType: 'kit_basico' | 'kit_participacao') => {
    setForm(prev => {
      const currentFaixas = prev.faixas_preco_grupos[kitType];
      const nextFaixaNum = currentFaixas.length + 1;
      return {
        ...prev,
        faixas_preco_grupos: {
          ...prev.faixas_preco_grupos,
          [kitType]: [...currentFaixas, { faixa: String(nextFaixaNum), qtd: 0, tkt_medio: 0, total: 0 }]
        }
      };
    });
  };

  const removeFaixaGruposByKit = (kitType: 'kit_basico' | 'kit_participacao', index: number) => {
    setForm(prev => {
      const newFaixas = prev.faixas_preco_grupos[kitType].filter((_: any, i: number) => i !== index);
      const renumberedFaixas = newFaixas.map((f: FaixaPrecoItem, i: number) => ({ ...f, faixa: String(i + 1) }));
      return {
        ...prev,
        faixas_preco_grupos: {
          ...prev.faixas_preco_grupos,
          [kitType]: renumberedFaixas
        }
      };
    });
  };

  const updateFaixaGruposByKit = (kitType: 'kit_basico' | 'kit_participacao', index: number, key: string, value: any) => {
    setForm(prev => ({
      ...prev,
      faixas_preco_grupos: {
        ...prev.faixas_preco_grupos,
        [kitType]: prev.faixas_preco_grupos[kitType].map((item: FaixaPrecoItem, i: number) =>
          i === index ? { ...item, [key]: value } : item
        )
      }
    }));
  };

  const removeArrayField = (field: 'kit_produto' | 'cortesias' | 'taxas', index: number) => {
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

  const calcularTotalizadorFaixa = (faixas: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>) => {
    const totalQtd = faixas.reduce((acc, f) => acc + (f.qtd || 0), 0);
    const totalValor = Math.round(faixas.reduce((acc, f) => acc + (f.total || 0), 0) * 100) / 100;
    const ticketMedioReal = totalQtd > 0 ? Math.round((totalValor / totalQtd) * 100) / 100 : 0;
    return { totalQtd, totalValor, ticketMedioReal };
  };

  const getKitCost = (kitName: string): number => {
    const kit = form.kit_produto.find(k => k.kit === kitName);
    if (!kit) return 0;
    return kit.produtos.reduce((sum, p) => sum + (Number(p.valor_unitario) || 0), 0);
  };

  const renderFaixaKitColumn = (kitType: keyof FaixasPrecoSiteByKit, title: string, colorClass: string) => {
    const faixas = form.faixas_preco_site[kitType] || [];
    const { totalQtd, totalValor, ticketMedioReal } = calcularTotalizadorFaixa(faixas);
    const kitNameMap: Record<string, string> = { kit_basico: 'Kit Básico', kit_participacao: 'Kit Participação', kit_sem_bike: 'Kit sem Bike', kit_com_bike: 'Kit com Bike' };
    const kitName = kitNameMap[kitType] || title;
    const custoUnitarioKit = getKitCost(kitName);
    const custoTotalKit = custoUnitarioKit * totalQtd;
    const margemKit = totalValor - custoTotalKit;
    const isCollapsed = collapsedSite[kitType];

    return (
      <div className="space-y-3">
        <div className={`flex items-center justify-between pb-2 border-b ${isDark ? 'border-gray-600' : 'border-gray-300'}`}>
          <div className="flex items-center gap-2">
            <Box className={`w-5 h-5 ${colorClass}`} />
            <h4 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{title}</h4>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-500'}`}>{faixas.length} faixa{faixas.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`text-right px-2 py-1 rounded ${isDark ? 'bg-gray-700/50' : 'bg-gray-200/50'}`}>
              <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Kit</p>
              <p className={`text-xs font-bold ${colorClass}`}>{formatCurrency(custoUnitarioKit)}</p>
            </div>
            <button
              type="button"
              onClick={() => setCollapsedSite(prev => ({ ...prev, [kitType]: !prev[kitType] }))}
              className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-600 text-gray-400 hover:text-gray-200' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}`}
              title={isCollapsed ? 'Expandir faixas' : 'Recolher faixas'}
            >
              {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            </button>
          </div>
        </div>
        
        {!isCollapsed && faixas.map((faixa, index) => (
          <div key={index} className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
            <div className="flex justify-between items-center mb-2">
              <span className={`text-xs font-bold px-2 py-1 rounded ${isDark ? 'bg-gray-600 text-gray-200' : 'bg-gray-200 text-gray-700'}`}>
                Faixa {faixa.faixa}
              </span>
              {faixas.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeFaixaSiteByKit(kitType, index)}
                  className="p-1 text-red-400 hover:text-red-300 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <FormattedInput
                value={faixa.qtd || 0}
                onChange={(qtd) => {
                  const total = Math.round(qtd * (faixa.tkt_medio || 0) * 100) / 100;
                  updateFaixaSiteByKit(kitType, index, 'qtd', qtd);
                  updateFaixaSiteByKit(kitType, index, 'total', total);
                }}
                label="Qtd"
                placeholder="Qtd"
                className={`px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.tkt_medio || 0}
                onChange={(tkt_medio) => {
                  const total = Math.round((faixa.qtd || 0) * tkt_medio * 100) / 100;
                  updateFaixaSiteByKit(kitType, index, 'tkt_medio', tkt_medio);
                  updateFaixaSiteByKit(kitType, index, 'total', total);
                }}
                label="Tkt Médio"
                placeholder="Tkt Médio"
                allowDecimal={true}
                className={`px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.total || 0}
                onChange={() => {}}
                label="Total"
                placeholder="Total"
                allowDecimal={true}
                readOnly={true}
                className={`px-3 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-600 border-gray-500 text-gray-400' : 'bg-gray-100 border-gray-300 text-gray-500'} cursor-not-allowed`}
              />
            </div>
          </div>
        ))}
        
        {!isCollapsed && (
          <button
            type="button"
            onClick={() => addFaixaSiteByKit(kitType)}
            className={`w-full py-2 rounded-lg border-2 border-dashed ${colorClass.includes('blue') ? 'border-blue-500/50 text-blue-400 hover:bg-blue-500/10' : 'border-green-500/50 text-green-400 hover:bg-green-500/10'} transition-colors flex items-center justify-center gap-2 text-sm`}
          >
            <Plus className="w-4 h-4" />
            Adicionar Faixa ({faixas.length})
          </button>
        )}

        {faixas.length > 0 && faixas.some(f => f.qtd > 0 || f.tkt_medio > 0) && (
          <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-gray-100'}`}>
            <div className="grid grid-cols-3 gap-2 text-center mb-3">
              <div>
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Qtd</p>
                <p className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalQtd) || '0'}</p>
              </div>
              <div>
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</p>
                <p className={`text-sm font-bold text-purple-400`}>{formatCurrency(ticketMedioReal)}</p>
              </div>
              <div>
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faturamento</p>
                <p className={`text-sm font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
              </div>
            </div>
            <div className={`pt-3 border-t ${isDark ? 'border-gray-600' : 'border-gray-300'}`}>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Total</p>
                  <p className={`text-sm font-bold text-orange-400`}>{formatCurrency(custoTotalKit)}</p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem</p>
                  <p className={`text-sm font-bold ${margemKit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemKit)}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const isCiclismo = form.modalidade === 'Ciclismo';

  const renderFaixaPrecoSiteContent = () => {
    const siteKitTypes: { key: keyof FaixasPrecoSiteByKit; title: string; color: string; bg: string }[] = isCiclismo
      ? [
          { key: 'kit_participacao', title: 'Inscrição Participação', color: 'text-green-400', bg: isDark ? 'bg-green-900/20 border-green-500/30' : 'bg-green-50 border-green-200' },
          { key: 'kit_sem_bike', title: 'Kit sem Bike', color: 'text-amber-400', bg: isDark ? 'bg-amber-900/20 border-amber-500/30' : 'bg-amber-50 border-amber-200' },
          { key: 'kit_com_bike', title: 'Kit com Bike', color: 'text-cyan-400', bg: isDark ? 'bg-cyan-900/20 border-cyan-500/30' : 'bg-cyan-50 border-cyan-200' },
        ]
      : [
          { key: 'kit_basico', title: 'Kit Básico', color: 'text-blue-400', bg: isDark ? 'bg-blue-900/20 border-blue-500/30' : 'bg-blue-50 border-blue-200' },
          { key: 'kit_participacao', title: 'Kit Participação', color: 'text-green-400', bg: isDark ? 'bg-green-900/20 border-green-500/30' : 'bg-green-50 border-green-200' },
        ];

    const allFaixas = siteKitTypes.flatMap(kt => form.faixas_preco_site[kt.key] || []);
    const { totalQtd, totalValor, ticketMedioReal } = calcularTotalizadorFaixa(allFaixas);
    
    const atletasOrcado = form.atletas.site.pago || 0;
    const tktMedioOrcado = form.atletas.site.tkt_medio || 0;
    const valorTotalOrcado = atletasOrcado * tktMedioOrcado;
    
    const diferencaQtd = totalQtd - atletasOrcado;
    const diferencaTktMedio = ticketMedioReal - tktMedioOrcado;
    const diferencaValor = totalValor - valorTotalOrcado;
    const percentualPreenchido = atletasOrcado > 0 ? (totalQtd / atletasOrcado) * 100 : 0;
    
    let custoTotalGeral = 0;
    let margemTotal = 0;
    const kitCostEntries = siteKitTypes.map(kt => {
      const faixas = form.faixas_preco_site[kt.key] || [];
      const { totalQtd: kitQtd, totalValor: kitFaturamento } = calcularTotalizadorFaixa(faixas);
      const custoUnitario = getKitCost(kt.title);
      const custoTotal = custoUnitario * kitQtd;
      const margem = kitFaturamento - custoTotal;
      custoTotalGeral += custoTotal;
      margemTotal += margem;
      return { key: kt.key, title: kt.title, kitQtd, kitFaturamento, custoUnitario, custoTotal, margem };
    });
    
    const faturamentoOrcado = atletasOrcado * tktMedioOrcado;
    const custoUnitarioRef = kitCostEntries.length > 0 ? kitCostEntries[0].custoUnitario : 0;
    const custoOrcado = atletasOrcado * custoUnitarioRef;
    const margemOrcada = faturamentoOrcado - custoOrcado;

    return (
      <div className="space-y-4">
        <div className={`grid ${isCiclismo ? 'grid-cols-3' : 'grid-cols-2'} gap-4`}>
          {siteKitTypes.map(kt => (
            <div key={kt.key} className={`p-4 rounded-xl ${kt.bg} border`}>
              {renderFaixaKitColumn(kt.key, kt.title, kt.color)}
            </div>
          ))}
        </div>

        {allFaixas.length > 0 && allFaixas.some(f => f.qtd > 0 || f.tkt_medio > 0) && (
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gradient-to-r from-purple-900/50 to-pink-900/50' : 'bg-gradient-to-r from-purple-50 to-pink-50'} border ${isDark ? 'border-purple-500/30' : 'border-purple-200'}`}>
            <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>
              Totalizador Geral - Site
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
                Comparativo com Orçado (Site)
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
            
            <div className={`mt-4 p-4 rounded-lg ${isDark ? 'bg-gradient-to-r from-emerald-900/50 to-teal-900/50' : 'bg-gradient-to-r from-emerald-50 to-teal-50'} border ${isDark ? 'border-emerald-500/30' : 'border-emerald-200'}`}>
              <h5 className={`text-sm font-bold mb-3 ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>
                Análise de Margem
              </h5>
              <div className="grid grid-cols-3 gap-4 mb-3">
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faturamento Total</p>
                  <p className={`text-lg font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
                </div>
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Total</p>
                  <p className={`text-lg font-bold text-orange-400`}>{formatCurrency(custoTotalGeral)}</p>
                </div>
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem Total</p>
                  <p className={`text-xl font-bold ${margemTotal >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemTotal)}</p>
                </div>
              </div>
              <div className={`grid ${kitCostEntries.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-3`}>
                {kitCostEntries.map(entry => (
                  <div key={entry.key} className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className={`text-xs ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Margem {entry.title}</p>
                        <p className={`text-sm font-bold ${entry.margem >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(entry.margem)}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Custo: {formatCurrency(entry.custoTotal)}</p>
                        <p className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Fat: {formatCurrency(entry.kitFaturamento)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className={`mt-3 p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-white/50'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem Real vs Orçada</p>
                    <p className={`text-lg font-bold ${margemTotal >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemTotal)}</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatCurrency(margemOrcada)}</p>
                    <span className={`text-sm font-bold flex items-center justify-end gap-1 ${
                      margemOrcada > 0 && margemTotal >= margemOrcada ? 'text-green-400' : margemTotal >= margemOrcada * 0.8 ? 'text-blue-400' : 'text-orange-400'
                    }`}>
                      {margemOrcada > 0 ? ((margemTotal / margemOrcada) * 100).toFixed(1) : 0}%
                    </span>
                  </div>
                </div>
                <div className="w-full bg-gray-600 rounded-full h-2.5">
                  <div 
                    className={`h-2.5 rounded-full transition-all ${
                      margemOrcada > 0 && margemTotal >= margemOrcada ? 'bg-emerald-500' : margemOrcada > 0 && margemTotal >= margemOrcada * 0.8 ? 'bg-blue-500' : 'bg-orange-500'
                    }`}
                    style={{ width: `${margemOrcada > 0 ? Math.min((margemTotal / margemOrcada) * 100, 100) : 0}%` }}
                  />
                </div>
                <div className={`mt-2 grid grid-cols-2 gap-2 text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  <div>Fat. Orçado: {formatCurrency(faturamentoOrcado)} | Custo Orçado: {formatCurrency(custoOrcado)}</div>
                  <div className="text-right">Atletas: {formatNumber(atletasOrcado)} × Custo Kit Ref: {formatCurrency(custoUnitarioRef)}</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderFaixaGruposKitColumn = (kitType: keyof FaixasPrecoSiteByKit, title: string, colorClass: string) => {
    const faixas = form.faixas_preco_grupos[kitType] || [];
    const { totalQtd, totalValor, ticketMedioReal } = calcularTotalizadorFaixa(faixas);
    const kitNameMap: Record<string, string> = { kit_basico: 'Kit Básico', kit_participacao: 'Kit Participação', kit_sem_bike: 'Kit sem Bike', kit_com_bike: 'Kit com Bike' };
    const kitName = kitNameMap[kitType] || title;
    const custoUnitarioKit = getKitCost(kitName);
    const custoTotalKit = custoUnitarioKit * totalQtd;
    const margemKit = totalValor - custoTotalKit;
    const isCollapsed = collapsedGrupos[kitType];

    return (
      <div className="space-y-3">
        <div className={`flex items-center justify-between pb-2 border-b ${isDark ? 'border-gray-600' : 'border-gray-300'}`}>
          <div className="flex items-center gap-2">
            <Box className={`w-5 h-5 ${colorClass}`} />
            <h4 className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{title}</h4>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${isDark ? 'bg-gray-700 text-gray-400' : 'bg-gray-200 text-gray-500'}`}>{faixas.length} faixa{faixas.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`text-right px-2 py-1 rounded ${isDark ? 'bg-gray-700/50' : 'bg-gray-200/50'}`}>
              <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Kit</p>
              <p className={`text-xs font-bold ${colorClass}`}>{formatCurrency(custoUnitarioKit)}</p>
            </div>
            <button
              type="button"
              onClick={() => setCollapsedGrupos(prev => ({ ...prev, [kitType]: !prev[kitType] }))}
              className={`p-1.5 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-600 text-gray-400 hover:text-gray-200' : 'hover:bg-gray-200 text-gray-500 hover:text-gray-700'}`}
              title={isCollapsed ? 'Expandir faixas' : 'Recolher faixas'}
            >
              {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            </button>
          </div>
        </div>
        
        {!isCollapsed && faixas.map((faixa, index) => (
          <div key={index} className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/30' : 'bg-gray-100'}`}>
            <div className="flex justify-between items-center mb-2">
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${isDark ? 'bg-gray-600 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>
                Faixa {index + 1}
              </span>
              {faixas.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeFaixaGruposByKit(kitType, index)}
                  className="p-0.5 text-red-400 hover:text-red-300 transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <div className="grid grid-cols-3 gap-2">
              <FormattedInput
                value={faixa.qtd || 0}
                onChange={(qtd) => {
                  const total = Math.round(qtd * (faixa.tkt_medio || 0) * 100) / 100;
                  updateFaixaGruposByKit(kitType, index, 'qtd', qtd);
                  updateFaixaGruposByKit(kitType, index, 'total', total);
                }}
                label="Qtd"
                placeholder="Qtd"
                className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.tkt_medio || 0}
                onChange={(tkt_medio) => {
                  const total = Math.round((faixa.qtd || 0) * tkt_medio * 100) / 100;
                  updateFaixaGruposByKit(kitType, index, 'tkt_medio', tkt_medio);
                  updateFaixaGruposByKit(kitType, index, 'total', total);
                }}
                label="Tkt Médio"
                placeholder="Tkt Médio"
                allowDecimal={true}
                className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
              <FormattedInput
                value={faixa.total || 0}
                onChange={() => {}}
                label="Total"
                placeholder="Total"
                allowDecimal={true}
                readOnly={true}
                className={`px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-600 border-gray-500 text-gray-400' : 'bg-gray-100 border-gray-300 text-gray-500'} cursor-not-allowed`}
              />
            </div>
          </div>
        ))}
        
        {!isCollapsed && (
          <button
            type="button"
            onClick={() => addFaixaGruposByKit(kitType)}
            className={`w-full py-2 rounded-lg border-2 border-dashed ${colorClass.replace('text-', 'border-').replace('400', '500/50')} ${colorClass} hover:bg-gray-700/30 transition-colors flex items-center justify-center gap-1 text-sm`}
          >
            <Plus className="w-4 h-4" />
            Adicionar ({faixas.length})
          </button>
        )}

        {faixas.some(f => f.qtd > 0 || f.tkt_medio > 0) && (
          <div className={`p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'} mt-2`}>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Qtd</p>
                <p className={`text-sm font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalQtd)}</p>
              </div>
              <div>
                <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</p>
                <p className={`text-sm font-bold ${colorClass}`}>{formatCurrency(ticketMedioReal)}</p>
              </div>
              <div>
                <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faturamento</p>
                <p className={`text-sm font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center mt-2 pt-2 border-t border-gray-600">
              <div>
                <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Total</p>
                <p className={`text-sm font-bold text-orange-400`}>{formatCurrency(custoTotalKit)}</p>
              </div>
              <div>
                <p className={`text-[10px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem</p>
                <p className={`text-sm font-bold ${margemKit >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemKit)}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderFaixaPrecoGruposContent = () => {
    const gruposKitTypes: { key: keyof FaixasPrecoSiteByKit; title: string; color: string; bg: string }[] = isCiclismo
      ? [
          { key: 'kit_participacao', title: 'Inscrição Participação', color: 'text-green-400', bg: isDark ? 'bg-green-900/20 border-green-500/30' : 'bg-green-50 border-green-200' },
          { key: 'kit_sem_bike', title: 'Kit sem Bike', color: 'text-amber-400', bg: isDark ? 'bg-amber-900/20 border-amber-500/30' : 'bg-amber-50 border-amber-200' },
          { key: 'kit_com_bike', title: 'Kit com Bike', color: 'text-cyan-400', bg: isDark ? 'bg-cyan-900/20 border-cyan-500/30' : 'bg-cyan-50 border-cyan-200' },
        ]
      : [
          { key: 'kit_basico', title: 'Kit Básico', color: 'text-blue-400', bg: isDark ? 'bg-blue-900/20 border-blue-500/30' : 'bg-blue-50 border-blue-200' },
          { key: 'kit_participacao', title: 'Kit Participação', color: 'text-green-400', bg: isDark ? 'bg-green-900/20 border-green-500/30' : 'bg-green-50 border-green-200' },
        ];

    const allFaixas = gruposKitTypes.flatMap(kt => form.faixas_preco_grupos[kt.key] || []);
    const { totalQtd, totalValor, ticketMedioReal } = calcularTotalizadorFaixa(allFaixas);
    
    const atletasOrcado = form.atletas.grupos.pago || 0;
    const tktMedioOrcado = form.atletas.grupos.tkt_medio || 0;
    const valorTotalOrcado = atletasOrcado * tktMedioOrcado;
    
    const diferencaQtd = totalQtd - atletasOrcado;
    const diferencaTktMedio = ticketMedioReal - tktMedioOrcado;
    const diferencaValor = totalValor - valorTotalOrcado;
    const percentualPreenchido = atletasOrcado > 0 ? (totalQtd / atletasOrcado) * 100 : 0;
    
    let custoTotalGeral = 0;
    let margemTotal = 0;
    const kitCostEntries = gruposKitTypes.map(kt => {
      const faixas = form.faixas_preco_grupos[kt.key] || [];
      const { totalQtd: kitQtd, totalValor: kitFaturamento } = calcularTotalizadorFaixa(faixas);
      const custoUnitario = getKitCost(kt.title);
      const custoTotal = custoUnitario * kitQtd;
      const margem = kitFaturamento - custoTotal;
      custoTotalGeral += custoTotal;
      margemTotal += margem;
      return { key: kt.key, title: kt.title, kitQtd, kitFaturamento, custoUnitario, custoTotal, margem };
    });
    
    const faturamentoOrcado = atletasOrcado * tktMedioOrcado;
    const custoUnitarioRef = kitCostEntries.length > 0 ? kitCostEntries[0].custoUnitario : 0;
    const custoOrcado = atletasOrcado * custoUnitarioRef;
    const margemOrcada = faturamentoOrcado - custoOrcado;

    return (
      <div className="space-y-4">
        <div className={`grid ${isCiclismo ? 'grid-cols-3' : 'grid-cols-2'} gap-4`}>
          {gruposKitTypes.map(kt => (
            <div key={kt.key} className={`p-4 rounded-xl ${kt.bg} border`}>
              {renderFaixaGruposKitColumn(kt.key, kt.title, kt.color)}
            </div>
          ))}
        </div>

        {allFaixas.length > 0 && allFaixas.some(f => f.qtd > 0 || f.tkt_medio > 0) && (
          <div className={`p-4 rounded-xl ${isDark ? 'bg-gradient-to-r from-purple-900/50 to-pink-900/50' : 'bg-gradient-to-r from-purple-50 to-pink-50'} border ${isDark ? 'border-purple-500/30' : 'border-purple-200'}`}>
            <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>
              Totalizador Geral
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
                Comparativo com Orçado (Grupos)
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
            
            <div className={`mt-4 p-4 rounded-lg ${isDark ? 'bg-gradient-to-r from-emerald-900/50 to-teal-900/50' : 'bg-gradient-to-r from-emerald-50 to-teal-50'} border ${isDark ? 'border-emerald-500/30' : 'border-emerald-200'}`}>
              <h5 className={`text-sm font-bold mb-3 ${isDark ? 'text-emerald-300' : 'text-emerald-700'}`}>
                Análise de Margem
              </h5>
              <div className="grid grid-cols-3 gap-4 mb-3">
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faturamento Total</p>
                  <p className={`text-lg font-bold text-green-400`}>{formatCurrency(totalValor)}</p>
                </div>
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Custo Total</p>
                  <p className={`text-lg font-bold text-orange-400`}>{formatCurrency(custoTotalGeral)}</p>
                </div>
                <div className="text-center">
                  <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem Total</p>
                  <p className={`text-xl font-bold ${margemTotal >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemTotal)}</p>
                </div>
              </div>
              <div className={`grid ${kitCostEntries.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-3`}>
                {kitCostEntries.map(entry => (
                  <div key={entry.key} className={`p-3 rounded-lg ${isDark ? 'bg-gray-700/50' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className={`text-xs ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>Margem {entry.title}</p>
                        <p className={`text-sm font-bold ${entry.margem >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(entry.margem)}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Custo: {formatCurrency(entry.custoTotal)}</p>
                        <p className={`text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Fat: {formatCurrency(entry.kitFaturamento)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className={`mt-3 p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-white/50'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Margem Real vs Orçada</p>
                    <p className={`text-lg font-bold ${margemTotal >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(margemTotal)}</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Orçado: {formatCurrency(margemOrcada)}</p>
                    <span className={`text-sm font-bold flex items-center justify-end gap-1 ${
                      margemOrcada > 0 && margemTotal >= margemOrcada ? 'text-green-400' : margemTotal >= margemOrcada * 0.8 ? 'text-blue-400' : 'text-orange-400'
                    }`}>
                      {margemOrcada > 0 ? ((margemTotal / margemOrcada) * 100).toFixed(1) : 0}%
                    </span>
                  </div>
                </div>
                <div className="w-full bg-gray-600 rounded-full h-2.5">
                  <div 
                    className={`h-2.5 rounded-full transition-all ${
                      margemOrcada > 0 && margemTotal >= margemOrcada ? 'bg-emerald-500' : margemOrcada > 0 && margemTotal >= margemOrcada * 0.8 ? 'bg-blue-500' : 'bg-orange-500'
                    }`}
                    style={{ width: `${margemOrcada > 0 ? Math.min((margemTotal / margemOrcada) * 100, 100) : 0}%` }}
                  />
                </div>
                <div className={`mt-2 grid grid-cols-2 gap-2 text-[10px] ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  <div>Fat. Orçado: {formatCurrency(faturamentoOrcado)} | Custo Orçado: {formatCurrency(custoOrcado)}</div>
                  <div className="text-right">Atletas: {formatNumber(atletasOrcado)} × Custo Kit Ref: {formatCurrency(custoUnitarioRef)}</div>
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
            {/* Nome do Evento - Circuito/Produto + Localização + Ano */}
            <div className={`p-4 rounded-xl border ${isDark ? 'bg-gray-800/50 border-gray-700' : 'bg-gray-50 border-gray-200'} mb-4`}>
              <h3 className={`text-sm font-bold mb-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Flag className="w-4 h-4 inline mr-2 text-purple-500" />
                Nome do Evento
              </h3>
              <div className="grid grid-cols-12 gap-2">
                <div className="col-span-5">
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Circuito / Produto</label>
                  <div className="flex gap-1">
                    <select
                      value={form.circuito_produto}
                      onChange={(e) => setForm(prev => ({ ...prev, circuito_produto: e.target.value }))}
                      className={`flex-1 px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    >
                      <option value="">Selecione...</option>
                      {circuitos.map(c => <option key={c.id} value={c.nome}>{c.nome}</option>)}
                    </select>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => setShowAddCircuito(true)}
                        className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
                        title="Gerenciar opções"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="col-span-5">
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Localização</label>
                  <div className="flex gap-1">
                    <select
                      value={form.localizacao_evento}
                      onChange={(e) => setForm(prev => ({ ...prev, localizacao_evento: e.target.value }))}
                      className={`flex-1 px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    >
                      <option value="">Selecione...</option>
                      {localizacoes.map(l => <option key={l.id} value={l.nome}>{l.nome}</option>)}
                    </select>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => setShowAddLocalizacao(true)}
                        className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors"
                        title="Gerenciar opções"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="col-span-2">
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Ano</label>
                  <input
                    type="number"
                    value={form.ano_evento}
                    onChange={(e) => setForm(prev => ({ ...prev, ano_evento: Number(e.target.value) }))}
                    className={`w-full px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
              </div>

              <div className="grid grid-cols-12 gap-3 mt-3">
                <div className="col-span-6">
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Cidade</label>
                  <input
                    type="text"
                    value={form.cidade}
                    onChange={(e) => setForm(prev => ({ ...prev, cidade: e.target.value }))}
                    placeholder="Ex: São Paulo"
                    className={`w-full px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
                <div className="col-span-6">
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Estado</label>
                  <select
                    value={form.estado}
                    onChange={(e) => setForm(prev => ({ ...prev, estado: e.target.value }))}
                    className={`w-full px-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Selecione...</option>
                    <option value="AC">AC</option><option value="AL">AL</option><option value="AP">AP</option>
                    <option value="AM">AM</option><option value="BA">BA</option><option value="CE">CE</option>
                    <option value="DF">DF</option><option value="ES">ES</option><option value="GO">GO</option>
                    <option value="MA">MA</option><option value="MT">MT</option><option value="MS">MS</option>
                    <option value="MG">MG</option><option value="PA">PA</option><option value="PB">PB</option>
                    <option value="PR">PR</option><option value="PE">PE</option><option value="PI">PI</option>
                    <option value="RJ">RJ</option><option value="RN">RN</option><option value="RS">RS</option>
                    <option value="RO">RO</option><option value="RR">RR</option><option value="SC">SC</option>
                    <option value="SP">SP</option><option value="SE">SE</option><option value="TO">TO</option>
                  </select>
                </div>
              </div>
            </div>

            {showAddCircuito && (
              <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => { setShowAddCircuito(false); setEditingCircuito(null); setNewCircuito(''); }}>
                <div className={`w-full max-w-md mx-4 rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'} p-6`} onClick={e => e.stopPropagation()}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Gerenciar Circuitos</h3>
                    <button type="button" onClick={() => { setShowAddCircuito(false); setEditingCircuito(null); setNewCircuito(''); }} className="p-1 rounded-lg hover:bg-gray-500/20">
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="flex gap-2 mb-4">
                    <input
                      type="text"
                      value={newCircuito}
                      onChange={(e) => setNewCircuito(e.target.value)}
                      placeholder="Novo circuito..."
                      className={`flex-1 px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                      onKeyDown={async (e) => {
                        if (e.key === 'Enter' && newCircuito.trim()) {
                          e.preventDefault();
                          try {
                            if (editingCircuito) {
                              await cadastrosService.updateCircuito(editingCircuito.id, newCircuito.trim());
                              setEditingCircuito(null);
                            } else {
                              await cadastrosService.createCircuito(newCircuito.trim());
                            }
                            const data = await cadastrosService.getCircuitos();
                            setCircuitos(data);
                            setNewCircuito('');
                          } catch (err: any) {
                            alert(err?.response?.data?.detail || 'Erro ao salvar');
                          }
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        if (!newCircuito.trim()) return;
                        try {
                          if (editingCircuito) {
                            await cadastrosService.updateCircuito(editingCircuito.id, newCircuito.trim());
                            setEditingCircuito(null);
                          } else {
                            await cadastrosService.createCircuito(newCircuito.trim());
                          }
                          const data = await cadastrosService.getCircuitos();
                          setCircuitos(data);
                          setNewCircuito('');
                        } catch (err: any) {
                          alert(err?.response?.data?.detail || 'Erro ao salvar');
                        }
                      }}
                      className="px-4 py-2 rounded-lg bg-purple-500 text-white hover:bg-purple-600 transition-colors font-medium"
                    >
                      {editingCircuito ? 'Salvar' : 'Adicionar'}
                    </button>
                  </div>
                  <div className="max-h-60 overflow-y-auto space-y-1">
                    {circuitos.map(c => (
                      <div key={c.id} className={`flex items-center justify-between px-3 py-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}>
                        <span className={`${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{c.nome}</span>
                        <div className="flex gap-1">
                          <button type="button" onClick={() => { setEditingCircuito(c); setNewCircuito(c.nome); }} className="p-1 rounded hover:bg-blue-500/20 text-blue-400" title="Editar">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button type="button" onClick={async () => {
                            if (!confirm(`Excluir "${c.nome}"?`)) return;
                            try {
                              await cadastrosService.deleteCircuito(c.id);
                              const data = await cadastrosService.getCircuitos();
                              setCircuitos(data);
                            } catch (err: any) { alert(err?.response?.data?.detail || 'Erro ao excluir'); }
                          }} className="p-1 rounded hover:bg-red-500/20 text-red-400" title="Excluir">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {showAddLocalizacao && (
              <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => { setShowAddLocalizacao(false); setEditingLocalizacao(null); setNewLocalizacao(''); }}>
                <div className={`w-full max-w-md mx-4 rounded-2xl shadow-2xl ${isDark ? 'bg-gray-800' : 'bg-white'} p-6`} onClick={e => e.stopPropagation()}>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Gerenciar Localizações</h3>
                    <button type="button" onClick={() => { setShowAddLocalizacao(false); setEditingLocalizacao(null); setNewLocalizacao(''); }} className="p-1 rounded-lg hover:bg-gray-500/20">
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="flex gap-2 mb-4">
                    <input
                      type="text"
                      value={newLocalizacao}
                      onChange={(e) => setNewLocalizacao(e.target.value)}
                      placeholder="Nova localização..."
                      className={`flex-1 px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                      onKeyDown={async (e) => {
                        if (e.key === 'Enter' && newLocalizacao.trim()) {
                          e.preventDefault();
                          try {
                            if (editingLocalizacao) {
                              await cadastrosService.updateLocalizacao(editingLocalizacao.id, newLocalizacao.trim());
                              setEditingLocalizacao(null);
                            } else {
                              await cadastrosService.createLocalizacao(newLocalizacao.trim());
                            }
                            const data = await cadastrosService.getLocalizacoes();
                            setLocalizacoes(data);
                            setNewLocalizacao('');
                          } catch (err: any) {
                            alert(err?.response?.data?.detail || 'Erro ao salvar');
                          }
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        if (!newLocalizacao.trim()) return;
                        try {
                          if (editingLocalizacao) {
                            await cadastrosService.updateLocalizacao(editingLocalizacao.id, newLocalizacao.trim());
                            setEditingLocalizacao(null);
                          } else {
                            await cadastrosService.createLocalizacao(newLocalizacao.trim());
                          }
                          const data = await cadastrosService.getLocalizacoes();
                          setLocalizacoes(data);
                          setNewLocalizacao('');
                        } catch (err: any) {
                          alert(err?.response?.data?.detail || 'Erro ao salvar');
                        }
                      }}
                      className="px-4 py-2 rounded-lg bg-purple-500 text-white hover:bg-purple-600 transition-colors font-medium"
                    >
                      {editingLocalizacao ? 'Salvar' : 'Adicionar'}
                    </button>
                  </div>
                  <div className="max-h-60 overflow-y-auto space-y-1">
                    {localizacoes.map(l => (
                      <div key={l.id} className={`flex items-center justify-between px-3 py-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}>
                        <span className={`${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{l.nome}</span>
                        <div className="flex gap-1">
                          <button type="button" onClick={() => { setEditingLocalizacao(l); setNewLocalizacao(l.nome); }} className="p-1 rounded hover:bg-blue-500/20 text-blue-400" title="Editar">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button type="button" onClick={async () => {
                            if (!confirm(`Excluir "${l.nome}"?`)) return;
                            try {
                              await cadastrosService.deleteLocalizacao(l.id);
                              const data = await cadastrosService.getLocalizacoes();
                              setLocalizacoes(data);
                            } catch (err: any) { alert(err?.response?.data?.detail || 'Erro ao excluir'); }
                          }} className="p-1 rounded hover:bg-red-500/20 text-red-400" title="Excluir">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Campos do Projeto */}
            <div className={`p-4 rounded-xl border ${isDark ? 'bg-gray-800/50 border-gray-700' : 'bg-gray-50 border-gray-200'} mb-4`}>
              <h3 className={`text-sm font-bold mb-3 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Flag className="w-4 h-4 inline mr-2 text-purple-500" />
                Dados do Evento
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>SKU</label>
                  <input
                    type="text"
                    value={form.sku}
                    onChange={(e) => setForm(prev => ({ ...prev, sku: e.target.value }))}
                    placeholder="Código SKU"
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
                <div>
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Modalidade</label>
                  <select
                    value={form.modalidade || 'Corrida'}
                    onChange={(e) => setForm(prev => ({ ...prev, modalidade: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    {modalidadesOptions.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Tipo Evento</label>
                  <select
                    value={form.tipo_evento || 'Próprio'}
                    onChange={(e) => setForm(prev => ({ ...prev, tipo_evento: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    {tiposEventoOptions.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Lei</label>
                  <select
                    value={form.lei || ''}
                    onChange={(e) => setForm(prev => ({ ...prev, lei: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    {leisOptions.map(l => <option key={l} value={l}>{l || 'Nenhuma'}</option>)}
                  </select>
                </div>
                <div>
                  <label className={`block text-xs font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Status</label>
                  <select
                    value={form.status || 'Em andamento'}
                    onChange={(e) => setForm(prev => ({ ...prev, status: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    {statusOptions.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
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
              <div>
                <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                  <Timer className="w-4 h-4 inline mr-2 text-purple-500" />
                  Dias p/ encerrar inscrições
                </label>
                <input
                  type="number"
                  min={0}
                  value={form.info_geral.dias_encerramento_inscricao ?? 2}
                  onChange={(e) => setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, dias_encerramento_inscricao: parseInt(e.target.value) || 0 } }))}
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
              {form.modalidade === 'Triathlon' ? (
              <div className="grid grid-cols-3 gap-3">
                {(['nado', 'ciclismo', 'corrida'] as const).map((campo) => {
                  const triObj = (form.info_geral.distancias.length > 0 && typeof form.info_geral.distancias[0] === 'object') ? form.info_geral.distancias[0] : { nado: '', ciclismo: '', corrida: '' };
                  const labelMap: Record<string, string> = { nado: 'Nado', ciclismo: 'Ciclismo', corrida: 'Corrida' };
                  const placeholderMap: Record<string, string> = { nado: 'Ex: 750m', ciclismo: 'Ex: 20k', corrida: 'Ex: 5k' };
                  return (
                    <div key={campo}>
                      <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>{labelMap[campo]}</label>
                      <input
                        type="text"
                        value={triObj[campo] || ''}
                        onChange={(e) => {
                          const newObj = { ...triObj, [campo]: e.target.value };
                          setForm(prev => ({ ...prev, info_geral: { ...prev.info_geral, distancias: [newObj] } }));
                        }}
                        placeholder={placeholderMap[campo]}
                        className={`w-full px-4 py-2.5 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                      />
                    </div>
                  );
                })}
              </div>
              ) : (
              <div className="flex flex-wrap gap-2 items-center">
                {distanciasOptions.map(d => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => {
                      const distancias = form.info_geral.distancias.includes(d)
                        ? form.info_geral.distancias.filter((dist: any) => dist !== d)
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
                {isAdmin && !showAddDistancia && (
                  <button
                    type="button"
                    onClick={() => setShowAddDistancia(true)}
                    className="px-3 py-2 rounded-xl font-medium transition-all bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-lg hover:opacity-90"
                    title="Adicionar nova distância"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                )}
                {isAdmin && showAddDistancia && (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newDistancia}
                      onChange={(e) => setNewDistancia(e.target.value)}
                      placeholder="Ex: 13k"
                      className={`w-24 px-3 py-2 rounded-xl border text-sm ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-emerald-500`}
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddDistancia(); } }}
                    />
                    <button type="button" onClick={handleAddDistancia} className="p-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600">
                      <Check className="w-4 h-4" />
                    </button>
                    <button type="button" onClick={() => { setShowAddDistancia(false); setNewDistancia(''); }} className="p-2 rounded-xl bg-gray-500 text-white hover:bg-gray-600">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
              )}
            </div>
          </div>
        );

      case 'atletas': {
        const cic = form.atletas.ciclismo || defaultCiclismoData;
        const ciclismoSitePago = isCiclismo
          ? (cic.participacao_pago + cic.sem_bike_pago + cic.com_bike_pago)
          : (form.atletas.site.pago || 0);
        const ciclismoSiteTktMedio = isCiclismo
          ? (() => {
              const totalPagosCic = cic.sem_bike_pago + cic.com_bike_pago;
              if (totalPagosCic === 0) return 0;
              return (cic.sem_bike_pago * cic.sem_bike_tkt_medio + cic.com_bike_pago * cic.com_bike_tkt_medio) / totalPagosCic;
            })()
          : (form.atletas.site.tkt_medio || 0);
        const totalPagos = ciclismoSitePago + (form.atletas.grupos.pago || 0) + (form.atletas.appai?.pago || 0);
        const totalCortesias = form.atletas.cortesia || 0;
        const totalGeral = totalPagos + totalCortesias;
        const isRJ = form.localizacao_evento === 'Rio de Janeiro';

        const updateCiclismo = (field: keyof CiclismoCenariosData, val: number) => {
          setForm(prev => {
            const newCic = { ...(prev.atletas.ciclismo || defaultCiclismoData), [field]: val };
            const totalP = newCic.sem_bike_pago + newCic.com_bike_pago;
            const aggPago = newCic.participacao_pago + totalP;
            const aggTkt = totalP > 0
              ? (newCic.sem_bike_pago * newCic.sem_bike_tkt_medio + newCic.com_bike_pago * newCic.com_bike_tkt_medio) / totalP
              : 0;
            return {
              ...prev,
              atletas: {
                ...prev.atletas,
                ciclismo: newCic,
                site: { pago: aggPago, tkt_medio: Math.round(aggTkt * 100) / 100 }
              }
            };
          });
        };

        return (
          <div className="space-y-6">
            {isCiclismo ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className={`p-4 rounded-xl ${isDark ? 'bg-green-900/20 border-green-500/30' : 'bg-green-50 border-green-200'} border`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Globe className="w-5 h-5 text-green-400" />
                      <h3 className={`font-bold ${isDark ? 'text-green-300' : 'text-green-700'}`}>Inscrição Participação</h3>
                    </div>
                    <div className="space-y-3">
                      <FormattedInput
                        value={cic.participacao_pago}
                        onChange={(val) => updateCiclismo('participacao_pago', val)}
                        label="Pago (ticket R$ 0)"
                        placeholder="Qtd"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-green-500`}
                      />
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                        Inscrição gratuita / sem kit
                      </p>
                    </div>
                  </div>

                  <div className={`p-4 rounded-xl ${isDark ? 'bg-amber-900/20 border-amber-500/30' : 'bg-amber-50 border-amber-200'} border`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Package className="w-5 h-5 text-amber-400" />
                      <h3 className={`font-bold ${isDark ? 'text-amber-300' : 'text-amber-700'}`}>Kit sem Bike</h3>
                    </div>
                    <div className="space-y-3">
                      <FormattedInput
                        value={cic.sem_bike_pago}
                        onChange={(val) => updateCiclismo('sem_bike_pago', val)}
                        label="Pago"
                        placeholder="Qtd"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-amber-500`}
                      />
                      <FormattedInput
                        value={cic.sem_bike_tkt_medio}
                        onChange={(val) => updateCiclismo('sem_bike_tkt_medio', val)}
                        label="Ticket Médio"
                        placeholder="R$ Ticket Médio"
                        allowDecimal={true}
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-amber-500`}
                      />
                    </div>
                  </div>

                  <div className={`p-4 rounded-xl ${isDark ? 'bg-cyan-900/20 border-cyan-500/30' : 'bg-cyan-50 border-cyan-200'} border`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Activity className="w-5 h-5 text-cyan-400" />
                      <h3 className={`font-bold ${isDark ? 'text-cyan-300' : 'text-cyan-700'}`}>Kit com Bike</h3>
                    </div>
                    <div className="space-y-3">
                      <FormattedInput
                        value={cic.com_bike_pago}
                        onChange={(val) => updateCiclismo('com_bike_pago', val)}
                        label="Pago"
                        placeholder="Qtd"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-cyan-500`}
                      />
                      <FormattedInput
                        value={cic.com_bike_tkt_medio}
                        onChange={(val) => updateCiclismo('com_bike_tkt_medio', val)}
                        label="Ticket Médio"
                        placeholder="R$ Ticket Médio"
                        allowDecimal={true}
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-cyan-500`}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
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
                        placeholder="Qtd Pagos"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                      />
                      <FormattedInput
                        value={form.atletas.grupos.tkt_medio || 0}
                        onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, grupos: { ...prev.atletas.grupos, tkt_medio: val } } }))}
                        label="Ticket Médio"
                        placeholder="R$ Ticket Médio"
                        allowDecimal={true}
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                      />
                    </div>
                  </div>

                  <div className={`p-4 rounded-xl ${isDark ? 'bg-pink-900/20 border-pink-500/30' : 'bg-pink-50 border-pink-200'} border`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Gift className="w-5 h-5 text-pink-400" />
                      <h3 className={`font-bold ${isDark ? 'text-pink-300' : 'text-pink-700'}`}>Cortesia</h3>
                    </div>
                    <div className="space-y-3">
                      <FormattedInput
                        value={form.atletas.cortesia || 0}
                        onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, cortesia: val } }))}
                        label="Total Cortesias"
                        placeholder="Qtd Total Cortesias"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-pink-500`}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className={`grid ${isRJ ? 'grid-cols-4' : 'grid-cols-3'} gap-4`}>
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
                      placeholder="Qtd Pagos"
                      className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-blue-500`}
                    />
                    <FormattedInput
                      value={form.atletas.site.tkt_medio || 0}
                      onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, site: { ...prev.atletas.site, tkt_medio: val } } }))}
                      label="Ticket Médio"
                      placeholder="R$ Ticket Médio"
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
                      placeholder="Qtd Pagos"
                      className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                    />
                    <FormattedInput
                      value={form.atletas.grupos.tkt_medio || 0}
                      onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, grupos: { ...prev.atletas.grupos, tkt_medio: val } } }))}
                      label="Ticket Médio"
                      placeholder="R$ Ticket Médio"
                      allowDecimal={true}
                      className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-orange-500`}
                    />
                  </div>
                </div>

                <div className={`p-4 rounded-xl ${isDark ? 'bg-pink-900/20 border-pink-500/30' : 'bg-pink-50 border-pink-200'} border`}>
                  <div className="flex items-center gap-2 mb-4">
                    <Gift className="w-5 h-5 text-pink-400" />
                    <h3 className={`font-bold ${isDark ? 'text-pink-300' : 'text-pink-700'}`}>Cortesia</h3>
                  </div>
                  <div className="space-y-3">
                    <FormattedInput
                      value={form.atletas.cortesia || 0}
                      onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, cortesia: val } }))}
                      label="Total Cortesias"
                      placeholder="Qtd Total Cortesias"
                      className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-pink-500`}
                    />
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      Total de cortesias do evento (Site + Grupos)
                    </p>
                  </div>
                </div>

                {isRJ && (
                  <div className={`p-4 rounded-xl ${isDark ? 'bg-teal-900/20 border-teal-500/30' : 'bg-teal-50 border-teal-200'} border`}>
                    <div className="flex items-center gap-2 mb-4">
                      <Building2 className="w-5 h-5 text-teal-400" />
                      <h3 className={`font-bold ${isDark ? 'text-teal-300' : 'text-teal-700'}`}>Appai / Assist.</h3>
                    </div>
                    <div className="space-y-3">
                      <FormattedInput
                        value={form.atletas.appai?.pago || 0}
                        onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, appai: { ...prev.atletas.appai, pago: val } } }))}
                        label="Quantidade"
                        placeholder="Qtd Appai"
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-teal-500`}
                      />
                      <FormattedInput
                        value={form.atletas.appai?.tkt_medio || 0}
                        onChange={(val) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, appai: { ...prev.atletas.appai, tkt_medio: val } } }))}
                        label="Ticket Médio"
                        placeholder="R$ Ticket Médio"
                        allowDecimal={true}
                        className={`w-full px-3 py-2 rounded-lg border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-teal-500`}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className={`p-5 rounded-xl ${isDark ? 'bg-gradient-to-r from-purple-900/50 to-pink-900/50 border-purple-500/30' : 'bg-gradient-to-r from-purple-50 to-pink-50 border-purple-200'} border`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="w-6 h-6 text-purple-400" />
                  <span className={`text-lg font-bold ${isDark ? 'text-purple-300' : 'text-purple-700'}`}>Total Geral de Atletas</span>
                </div>
                <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(totalGeral) || '0'}</p>
              </div>
            </div>
          </div>
        );
      }

      case 'faixas_preco_site':
        return renderFaixaPrecoSiteContent();

      case 'faixas_preco_grupos':
        return renderFaixaPrecoGruposContent();

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

      case 'cortesias': {
        const totalAlocado = getTotalCortesiasAlocadas();
        const restante = maxCortesias - totalAlocado;
        
        return (
          <div className="space-y-4">
            <div className={`p-4 rounded-xl border ${excedeCortesias 
              ? (isDark ? 'bg-red-900/30 border-red-500/50' : 'bg-red-50 border-red-300') 
              : (isDark ? 'bg-purple-900/20 border-purple-500/30' : 'bg-purple-50 border-purple-200')}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Gift className={`w-5 h-5 ${excedeCortesias ? 'text-red-400' : 'text-purple-400'}`} />
                  <span className={`font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>Controle de Cortesias</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-center">
                    <span className={`block text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Alocadas</span>
                    <span className={`text-lg font-bold ${excedeCortesias ? 'text-red-400' : 'text-purple-400'}`}>{formatNumber(totalAlocado) || '0'}</span>
                  </div>
                  <div className="text-center">
                    <span className={`block text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Orçado</span>
                    <span className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(maxCortesias) || '0'}</span>
                  </div>
                  <div className="text-center">
                    <span className={`block text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Restantes</span>
                    <span className={`text-lg font-bold ${restante < 0 ? 'text-red-400' : 'text-green-400'}`}>{formatNumber(restante)}</span>
                  </div>
                </div>
              </div>
              {excedeCortesias && (
                <div className="mt-2 flex items-center gap-2 text-red-400">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-sm">Quantidade de cortesias excede o limite orçado na aba Atletas!</span>
                </div>
              )}
            </div>

            {form.cortesias.map((cortesia, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Cortesia {index + 1}</span>
                  {form.cortesias.length > 0 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('cortesias', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Cliente
                    </label>
                    <input
                      type="text"
                      value={cortesia.cliente}
                      onChange={(e) => updateArrayField('cortesias', index, 'cliente', e.target.value)}
                      placeholder="Nome do cliente"
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    />
                  </div>
                  <div>
                    <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Quantidade
                    </label>
                    <FormattedInput
                      value={cortesia.quantidade || 0}
                      onChange={(val) => {
                        const currentTotal = getTotalCortesiasAlocadas() - (cortesia.quantidade || 0);
                        const maxAllowed = maxCortesias - currentTotal;
                        const safeVal = Math.min(val, Math.max(0, maxAllowed));
                        updateArrayField('cortesias', index, 'quantidade', val);
                      }}
                      label="Quantidade"
                      placeholder="0"
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    />
                  </div>
                </div>
              </div>
            ))}

            <button
              type="button"
              onClick={() => addArrayField('cortesias')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Cortesia
            </button>
          </div>
        );
      }

      case 'taxas':
        return (
          <div className="space-y-4">
            {form.taxas.map((taxa, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Taxa {index + 1}</span>
                  {form.taxas.length > 0 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('taxas', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="mb-4">
                  <label className={`block text-xs font-semibold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                    Tipo de cálculo
                  </label>
                  <div className={`inline-flex rounded-lg p-0.5 ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                    {(['unitario', 'percentual'] as const).map(tipo => (
                      <button
                        key={tipo}
                        type="button"
                        onClick={() => {
                          setForm(prev => {
                            const taxas = [...prev.taxas];
                            taxas[index] = {
                              ...taxas[index],
                              tipo_calculo: tipo,
                              valor_unitario: tipo === 'unitario' ? taxas[index].valor_unitario : 0,
                              percentual_inscricao: tipo === 'percentual' ? taxas[index].percentual_inscricao : 0,
                            };
                            return { ...prev, taxas };
                          });
                        }}
                        className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-semibold transition-all ${
                          taxa.tipo_calculo === tipo
                            ? 'bg-purple-600 text-white shadow'
                            : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-600 hover:text-gray-800'
                        }`}
                      >
                        {tipo === 'unitario' ? (
                          <><DollarSign className="w-3.5 h-3.5" /> Valor Unitário</>
                        ) : (
                          <><Percent className="w-3.5 h-3.5" /> do Valor Inscrição</>
                        )}
                      </button>
                    ))}
                  </div>
                </div>

                {taxa.tipo_calculo === 'unitario' ? (
                  <div className="mb-4">
                    <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <DollarSign className="w-4 h-4 inline mr-2 text-green-500" />
                      Valor Unitário
                    </label>
                    <FormattedInput
                      value={taxa.valor_unitario || 0}
                      onChange={(val) => updateArrayField('taxas', index, 'valor_unitario', val)}
                      label="Valor"
                      placeholder="0,00"
                      allowDecimal
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    />
                    <div className={`mt-3 w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-600/50 border-gray-500 text-emerald-400' : 'bg-gray-100 border-gray-300 text-emerald-600'} font-bold text-base flex items-center gap-2`}>
                      <TrendingUp className="w-4 h-4 flex-shrink-0" />
                      <span>Total: R$ {((taxa.valor_unitario || 0) * (form.atletas.site.pago || 0)).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                      <span className={`text-xs font-normal ml-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>({form.atletas.site.pago || 0} atletas × R$ {(taxa.valor_unitario || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })})</span>
                    </div>
                  </div>
                ) : (
                  <div className="mb-4">
                    <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      % do Valor Inscrição
                    </label>
                    <div className="flex items-center gap-2">
                      <FormattedInput
                        value={taxa.percentual_inscricao || 0}
                        onChange={(val) => updateArrayField('taxas', index, 'percentual_inscricao', val)}
                        label="Percentual"
                        placeholder="0,00"
                        allowDecimal
                        className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                      />
                      <span className={`text-lg font-bold ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>%</span>
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-3">
                    <label className={`block text-sm font-semibold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      Validado
                    </label>
                    <button
                      type="button"
                      onClick={() => updateArrayField('taxas', index, 'validado', !taxa.validado)}
                      className={`relative w-12 h-6 rounded-full transition-colors ${
                        taxa.validado 
                          ? 'bg-gradient-to-r from-green-500 to-emerald-500' 
                          : isDark ? 'bg-gray-600' : 'bg-gray-300'
                      }`}
                    >
                      <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                        taxa.validado ? 'translate-x-7' : 'translate-x-1'
                      }`} />
                    </button>
                    {taxa.validado && (
                      <Check className="w-4 h-4 text-green-500" />
                    )}
                  </div>
                  <div>
                    <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                      <Calendar className="w-4 h-4 inline mr-2 text-purple-500" />
                      Data da Validação
                    </label>
                    <input
                      type="date"
                      value={taxa.data_validacao}
                      onChange={(e) => updateArrayField('taxas', index, 'data_validacao', e.target.value)}
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    />
                  </div>
                </div>
              </div>
            ))}

            <button
              type="button"
              onClick={() => addArrayField('taxas')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Taxa
            </button>
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
                <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
                  <div className="flex-1">
                    <label className={`block text-xs font-medium mb-1 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Tipo de Kit
                    </label>
                    <select
                      value={kit.kit}
                      onChange={(e) => {
                        const selectedKit = e.target.value;
                        const defaultProdutos = (produtosPadraoPorKit[selectedKit] || []).map(p => ({ ...p }));
                        setForm(prev => {
                          const kitBasico = prev.kit_produto.find(k => k.kit === 'Kit Básico');
                          let produtosFinais = defaultProdutos;
                          if (kitBasico && selectedKit !== 'Kit Básico') {
                            if (selectedKit === 'Kit Participação') {
                              produtosFinais = defaultProdutos.map(p => {
                                const matchBasico = kitBasico.produtos.find(bp => bp.nome === p.nome);
                                return matchBasico ? { ...p, valor_unitario: matchBasico.valor_unitario } : p;
                              });
                            } else {
                              const basicoProdutos = kitBasico.produtos.map(bp => ({ ...bp }));
                              const extras = produtosExtrasPorKit[selectedKit] || [];
                              const extraProdutos = extras
                                .filter(nome => !basicoProdutos.some(bp => bp.nome === nome))
                                .map(nome => ({ nome, valor_unitario: 0 }));
                              produtosFinais = [...basicoProdutos, ...extraProdutos];
                            }
                          }
                          return {
                            ...prev,
                            kit_produto: prev.kit_produto.map((k, i) => 
                              i === index ? { ...k, kit: selectedKit, produtos: produtosFinais } : k
                            )
                          };
                        });
                      }}
                      className={`w-full px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                    >
                      <option value="">Selecione o Kit</option>
                      {kitOptions.filter(k => !form.kit_produto.some((fk, i) => i !== index && fk.kit === k)).map(k => (
                        <option key={k} value={k}>{k}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div>
                  <label className={`block text-xs font-medium mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                    Produtos do Kit (clique para adicionar/remover)
                  </label>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {produtosDisponiveis.map(produto => {
                      const isSelected = kit.produtos.some(p => p.nome === produto);
                      return (
                        <button
                          key={produto}
                          type="button"
                          onClick={() => {
                            setForm(prev => {
                              const currentKit = prev.kit_produto[index];
                              const isKitBasico = currentKit.kit === 'Kit Básico';
                              let produtos;
                              if (isSelected) {
                                produtos = currentKit.produtos.filter(p => p.nome !== produto);
                              } else {
                                let valorInicial = 0;
                                if (!isKitBasico) {
                                  const kitBasico = prev.kit_produto.find(k => k.kit === 'Kit Básico');
                                  const matchBasico = kitBasico?.produtos.find(bp => bp.nome === produto);
                                  if (matchBasico) valorInicial = matchBasico.valor_unitario;
                                }
                                produtos = [...currentKit.produtos, { nome: produto, valor_unitario: valorInicial }];
                              }
                              let updatedKits = prev.kit_produto.map((k, i) => 
                                i === index ? { ...k, produtos } : k
                              );
                              if (isKitBasico) {
                                updatedKits = updatedKits.map((k, i) => {
                                  if (i === index || k.kit === 'Kit Participação' || !k.kit) return k;
                                  if (isSelected) {
                                    return { ...k, produtos: k.produtos.filter(p => p.nome !== produto) };
                                  } else {
                                    if (!k.produtos.some(p => p.nome === produto)) {
                                      return { ...k, produtos: [...k.produtos, { nome: produto, valor_unitario: 0 }] };
                                    }
                                  }
                                  return k;
                                });
                              }
                              return { ...prev, kit_produto: updatedKits };
                            });
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
                  {kit.produtos.length > 0 && (
                    <div className={`mt-3 p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-gray-100'}`}>
                      <label className={`block text-xs font-medium mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                        Valores Unitários dos Produtos
                      </label>
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {kit.produtos.map((produto, prodIndex) => (
                          <div key={produto.nome} className="flex flex-col gap-1">
                            <span className={`text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{produto.nome}</span>
                            <div className="relative">
                              <span className={`absolute left-2 top-1/2 -translate-y-1/2 text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>R$</span>
                              <input
                                type="number"
                                step="0.01"
                                min="0"
                                value={produto.valor_unitario || ''}
                                onChange={(e) => {
                                  const newValue = parseFloat(e.target.value) || 0;
                                  const produtoNome = produto.nome;
                                  setForm(prev => {
                                    const isKitBasico = prev.kit_produto[index]?.kit === 'Kit Básico';
                                    return {
                                      ...prev,
                                      kit_produto: prev.kit_produto.map((k, i) => {
                                        if (i === index) {
                                          return {
                                            ...k,
                                            produtos: k.produtos.map((p, pi) => 
                                              pi === prodIndex ? { ...p, valor_unitario: newValue } : p
                                            )
                                          };
                                        }
                                        if (isKitBasico && k.kit && k.kit !== 'Kit Básico') {
                                          return {
                                            ...k,
                                            produtos: k.produtos.map(p => 
                                              p.nome === produtoNome ? { ...p, valor_unitario: newValue } : p
                                            )
                                          };
                                        }
                                        return k;
                                      })
                                    };
                                  });
                                }}
                                placeholder="0,00"
                                className={`w-full pl-7 pr-2 py-1.5 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
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

          </div>
        );

      case 'merchan': {
        const kitsMerchan = ['Kit Vip', 'Kit Plus', 'Kit Super'];
        const kitBasicoProdutos = new Set(
          (form.kit_produto.find(k => k.kit === 'Kit Básico')?.produtos ?? []).map(p => p.nome)
        );
        const merchanKitsFromProduto = form.kit_produto
          .filter(k => kitsMerchan.includes(k.kit))
          .map(k => ({
            ...k,
            produtos: k.produtos.filter(p => !kitBasicoProdutos.has(p.nome))
          }))
          .filter(k => k.produtos.length > 0);

        const getMerchanItem = (kitName: string, produtoNome: string) => {
          const mk = form.merchan.find(m => m.kit === kitName);
          return mk?.itens.find(it => it.nome === produtoNome) ?? null;
        };

        const setMerchanValorVenda = (kitName: string, produtoNome: string, valor: number) => {
          setForm(prev => {
            const merchan = [...prev.merchan];
            const mkIdx = merchan.findIndex(m => m.kit === kitName);
            if (mkIdx === -1) {
              merchan.push({ kit: kitName, itens: [{ nome: produtoNome, valor_venda: valor }] });
            } else {
              const mk = { ...merchan[mkIdx], itens: [...merchan[mkIdx].itens] };
              const itIdx = mk.itens.findIndex(it => it.nome === produtoNome);
              if (itIdx === -1) {
                mk.itens.push({ nome: produtoNome, valor_venda: valor });
              } else {
                mk.itens = mk.itens.map((it, i) => i === itIdx ? { ...it, valor_venda: valor } : it);
              }
              merchan[mkIdx] = mk;
            }
            return { ...prev, merchan };
          });
        };

        const calcMarkupMultiplier = (custo: number, venda: number): string => {
          if (!custo || custo === 0 || !venda || venda === 0) return '—';
          const markup = venda / custo;
          return `${markup.toFixed(2).replace('.', ',')}x`;
        };

        const markupColor = (custo: number, venda: number): string => {
          if (!custo || custo === 0 || !venda || venda === 0) return isDark ? 'text-gray-400' : 'text-gray-500';
          return venda >= custo
            ? 'text-green-500'
            : 'text-red-400';
        };

        if (merchanKitsFromProduto.length === 0) {
          return (
            <div className={`flex flex-col items-center justify-center py-12 gap-3 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              <ShoppingBag className="w-10 h-10 opacity-40" />
              <p className="text-sm text-center">
                Nenhum produto exclusivo de Merchan encontrado.<br />
                Configure os kits Vip, Plus ou Super na aba <strong>Kit Produto</strong> com itens além do Kit Básico.
              </p>
            </div>
          );
        }

        return (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Exibindo apenas os itens exclusivos de cada kit (não presentes no Kit Básico).
              </p>
              <div className={`flex items-center rounded-lg p-0.5 gap-0.5 self-start sm:self-auto ${isDark ? 'bg-gray-700' : 'bg-gray-100'}`}>
                <button
                  type="button"
                  onClick={() => {
                    if (merchanMode !== 'venda') {
                      setMerchanMode('venda');
                      setForm(prev => ({ ...prev, merchan: [] }));
                    }
                  }}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                    merchanMode === 'venda'
                      ? isDark ? 'bg-gray-600 text-white shadow-sm' : 'bg-white text-gray-800 shadow-sm'
                      : isDark ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Já sei o preço de venda
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (merchanMode !== 'planejamento') {
                      setMerchanMode('planejamento');
                      setForm(prev => ({ ...prev, merchan: [] }));
                    }
                  }}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                    merchanMode === 'planejamento'
                      ? isDark ? 'bg-purple-600 text-white shadow-sm' : 'bg-purple-600 text-white shadow-sm'
                      : isDark ? 'text-gray-400 hover:text-gray-300' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Simular preço de venda
                </button>
              </div>
            </div>

            {merchanMode === 'planejamento' && (
              <div className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs ${isDark ? 'bg-purple-900/20 border border-purple-700/30 text-purple-300' : 'bg-purple-50 border border-purple-200 text-purple-700'}`}>
                <span className="mt-0.5">💡</span>
                <span>Defina o <strong>markup desejado</strong> (multiplicador) e o preço de venda será calculado automaticamente. Ex: markup 2,5x sobre custo de R$ 10,00 → venda R$ 25,00.</span>
              </div>
            )}

            {merchanKitsFromProduto.map(kit => (
              <div key={kit.kit} className={`p-4 rounded-xl border ${isDark ? 'bg-gray-700/30 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                <h3 className={`text-sm font-bold mb-4 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
                  {kit.kit}
                </h3>
                {kit.produtos.length === 0 ? (
                  <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Nenhum produto neste kit.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={`text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                          <th className="text-left pb-2 pr-4">Produto</th>
                          <th className="text-right pb-2 pr-4">Custo Unit.</th>
                          {merchanMode === 'venda' ? (
                            <>
                              <th className="text-right pb-2 pr-4">Valor Venda</th>
                              <th className="text-right pb-2">Markup</th>
                            </>
                          ) : (
                            <>
                              <th className="text-right pb-2 pr-4">Markup Desejado</th>
                              <th className="text-right pb-2">Preço Sugerido</th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200/20">
                        {kit.produtos.map(produto => {
                          const custo = Number(produto.valor_unitario) || 0;
                          const merchanIt = getMerchanItem(kit.kit, produto.nome);
                          const venda = merchanIt ? Number(merchanIt.valor_venda) : 0;
                          const markupAtual = custo > 0 && venda > 0 ? venda / custo : 0;

                          return (
                            <tr key={produto.nome}>
                              <td className={`py-2 pr-4 font-medium ${isDark ? 'text-gray-200' : 'text-gray-700'}`}>
                                {produto.nome}
                              </td>
                              <td className={`py-2 pr-4 text-right ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                                {custo > 0 ? `R$ ${custo.toFixed(2).replace('.', ',')}` : <span className="text-gray-400">—</span>}
                              </td>

                              {merchanMode === 'venda' ? (
                                <>
                                  <td className="py-2 pr-4 text-right">
                                    <div className="flex items-center justify-end gap-1">
                                      <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>R$</span>
                                      <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        value={venda || ''}
                                        onChange={e => setMerchanValorVenda(kit.kit, produto.nome, parseFloat(e.target.value) || 0)}
                                        placeholder="0,00"
                                        disabled={!canEditCampo('eventos', 'merchan')}
                                        className={`w-24 px-2 py-1 text-sm rounded-lg border text-right ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 disabled:opacity-60 disabled:cursor-not-allowed`}
                                      />
                                    </div>
                                  </td>
                                  <td className={`py-2 text-right font-semibold text-sm ${markupColor(custo, venda)}`}>
                                    {calcMarkupMultiplier(custo, venda)}
                                  </td>
                                </>
                              ) : (
                                <>
                                  <td className="py-2 pr-4 text-right">
                                    <div className="flex items-center justify-end gap-1">
                                      <input
                                        type="number"
                                        step="0.1"
                                        min="0"
                                        value={markupAtual > 0 ? markupAtual.toFixed(2) : ''}
                                        onChange={e => {
                                          const m = parseFloat(e.target.value) || 0;
                                          if (custo > 0 && m > 0) {
                                            setMerchanValorVenda(kit.kit, produto.nome, custo * m);
                                          } else {
                                            setMerchanValorVenda(kit.kit, produto.nome, 0);
                                          }
                                        }}
                                        placeholder="ex: 2.5"
                                        disabled={!canEditCampo('eventos', 'merchan') || custo === 0}
                                        className={`w-24 px-2 py-1 text-sm rounded-lg border text-right ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500 disabled:opacity-60 disabled:cursor-not-allowed`}
                                      />
                                      <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>x</span>
                                    </div>
                                    {custo === 0 && (
                                      <p className={`text-xs mt-0.5 text-right ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>sem custo cadastrado</p>
                                    )}
                                  </td>
                                  <td className={`py-2 text-right font-semibold text-sm ${venda > 0 ? 'text-green-500' : isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                    {venda > 0 ? `R$ ${venda.toFixed(2).replace('.', ',')}` : '—'}
                                  </td>
                                </>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      }

      default:
        return null;
    }
  };

  const exportToCSV = () => {
    const headers = [
      'Nome', 'SKU', 'Status', 'Modalidade', 'Tipo Evento', 'Lei',
      'Data Evento', 'Horário Largada', 'Local', 'Cidade', 'Estado',
      'Distâncias', 'Circuito', 'Localização',
      'Capacidade Máxima', 'Atletas Site (Pago)', 'TKT Médio Site',
      'Atletas Grupos (Pago)', 'TKT Médio Grupos',
      'Atletas APPAI (Pago)', 'TKT Médio APPAI',
      'Cortesias', 'Total Atletas',
      'Retirada Kit - Local', 'Retirada Kit - Data/Horário',
      'Dias Encerramento Inscrição'
    ];

    const rows = filteredCadastros.map(c => {
      const total = getTotalAtletasCadastro(c);
      const distancias = (c.info_geral.distancias || []).join('; ');
      return [
        c.nome,
        c.sku || '',
        c.status || '',
        c.modalidade || '',
        c.tipo_evento || '',
        c.lei || '',
        c.info_geral.data ? c.info_geral.data.split('T')[0] : '',
        c.info_geral.horario_largada || '',
        c.info_geral.local || '',
        c.cidade || '',
        c.estado || '',
        distancias,
        c.circuito_produto || '',
        c.localizacao_evento || '',
        c.capacidade_maxima ?? '',
        c.atletas.site.pago || 0,
        c.atletas.site.tkt_medio || 0,
        c.atletas.grupos.pago || 0,
        c.atletas.grupos.tkt_medio || 0,
        c.atletas.appai?.pago || 0,
        c.atletas.appai?.tkt_medio || 0,
        c.atletas.cortesia || 0,
        total,
        c.retirada_kit?.local || '',
        c.retirada_kit?.data_horario || '',
        c.info_geral.dias_encerramento_inscricao ?? ''
      ];
    });

    const escape = (val: any) => {
      const str = String(val ?? '');
      if (str.includes(';') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    };

    const csvContent = [headers, ...rows]
      .map(row => row.map(escape).join(';'))
      .join('\n');

    const bom = '\uFEFF';
    const blob = new Blob([bom + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const today = new Date().toISOString().split('T')[0];
    link.download = `cadastro_eventos_${today}.csv`;
    link.click();
    URL.revokeObjectURL(url);
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

          <div className="flex items-center gap-3">
            <button
              onClick={() => { setShowLixeira(v => { if (!v) loadLixeira(); return !v; }); }}
              title="Ver eventos na lixeira (excluídos nos últimos 30 dias)"
              className={`flex items-center gap-2 px-4 py-3 rounded-2xl border font-semibold transition-all duration-300 hover:scale-105 ${
                showLixeira
                  ? 'border-red-500 text-red-400 bg-red-500/10'
                  : isDark
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700 hover:border-gray-500'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <Trash2 className="w-5 h-5" />
              Lixeira{lixeira.length > 0 && !showLixeira && <span className="ml-1 px-1.5 py-0.5 rounded-full bg-red-500 text-white text-xs">{lixeira.length}</span>}
            </button>
            <button
              onClick={exportToCSV}
              title={`Exportar ${filteredCadastros.length} evento(s) para CSV`}
              className={`flex items-center gap-2 px-4 py-3 rounded-2xl border font-semibold transition-all duration-300 hover:scale-105 ${
                isDark
                  ? 'border-gray-600 text-gray-300 hover:bg-gray-700 hover:border-gray-500'
                  : 'border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400'
              }`}
            >
              <Download className="w-5 h-5" />
              Exportar
            </button>

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
        </div>

        <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50 backdrop-blur-xl border border-gray-700/50' : 'bg-white/70 backdrop-blur-xl border border-gray-200'}`}>
          <div className="flex flex-col md:flex-row gap-3">
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

            <button
              onClick={() => setShowFilters(f => !f)}
              className={`flex items-center gap-2 px-4 py-3 rounded-xl border font-medium transition-all ${
                showFilters || activeFilterCount > 0
                  ? isDark ? 'border-purple-500 bg-purple-500/20 text-purple-300' : 'border-purple-500 bg-purple-50 text-purple-700'
                  : isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Filter className="w-4 h-4" />
              <span>Filtros</span>
              {activeFilterCount > 0 && (
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-purple-500 text-white text-[10px] font-bold">
                  {activeFilterCount}
                </span>
              )}
            </button>

            {hasActiveFilters && (
              <button
                onClick={clearAllFilters}
                className={`flex items-center gap-2 px-4 py-3 rounded-xl border ${isDark ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-300 text-gray-700 hover:bg-gray-50'} transition-all`}
              >
                <RotateCcw className="w-4 h-4" />
                <span className="font-medium">Limpar</span>
              </button>
            )}
          </div>

          {showFilters && (
            <div className={`mt-3 pt-3 border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div>
                  <label className={`block text-[11px] font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Mês do Evento</label>
                  <select
                    value={filterMes}
                    onChange={(e) => setFilterMes(e.target.value)}
                    className={`w-full px-2 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Todos</option>
                    {mesesOptions.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                </div>

                <div>
                  <label className={`block text-[11px] font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Modalidade</label>
                  <select
                    value={filterModalidade}
                    onChange={(e) => setFilterModalidade(e.target.value)}
                    className={`w-full px-2 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Todas</option>
                    {modalidadesOptions.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>

                <div>
                  <label className={`block text-[11px] font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tipo Evento</label>
                  <select
                    value={filterTipoEvento}
                    onChange={(e) => setFilterTipoEvento(e.target.value)}
                    className={`w-full px-2 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Todos</option>
                    {tiposEventoOptions.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                <div>
                  <label className={`block text-[11px] font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Lei</label>
                  <select
                    value={filterLei}
                    onChange={(e) => setFilterLei(e.target.value)}
                    className={`w-full px-2 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Todas</option>
                    {leisOptions.filter(l => l).map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>

                <div>
                  <label className={`block text-[11px] font-semibold mb-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Localização</label>
                  <select
                    value={filterLocalizacao}
                    onChange={(e) => setFilterLocalizacao(e.target.value)}
                    className={`w-full px-2 py-2 text-sm rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Todas</option>
                    {localizacoes.map(l => <option key={l.id} value={l.nome}>{l.nome}</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}
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
          ) : loadError ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20 gap-4">
              <div className={`text-center ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                <p className="text-lg font-medium mb-1">Não foi possível carregar os eventos</p>
                <p className="text-sm">O servidor pode estar inicializando. Aguarde alguns instantes e tente novamente.</p>
              </div>
              <button
                onClick={loadCadastros}
                className="px-5 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-colors"
              >
                Tentar novamente
              </button>
            </div>
          ) : filteredCadastros.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center py-20">
              <div className="p-4 rounded-2xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 mb-4">
                <Trophy className="w-12 h-12 text-purple-400" />
              </div>
              <p className={`text-lg font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Nenhum cadastro encontrado
              </p>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                {hasActiveFilters ? 'Tente ajustar os filtros ou limpar a busca' : 'Crie seu primeiro cadastro clicando no botão acima'}
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
                    {cadastro.info_geral.distancias.length > 0 && typeof cadastro.info_geral.distancias[0] === 'object' ? (
                      (() => {
                        const tri = cadastro.info_geral.distancias[0] as { nado?: string; ciclismo?: string; corrida?: string };
                        return (
                          <>
                            {tri.nado && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-blue-400 text-xs font-bold">Nado: {tri.nado}</span>}
                            {tri.ciclismo && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-green-500/20 to-emerald-500/20 text-green-400 text-xs font-bold">Ciclismo: {tri.ciclismo}</span>}
                            {tri.corrida && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-orange-500/20 to-red-500/20 text-orange-400 text-xs font-bold">Corrida: {tri.corrida}</span>}
                          </>
                        );
                      })()
                    ) : (
                      cadastro.info_geral.distancias.map((d: any) => (
                        <span 
                          key={d}
                          className="px-3 py-1 rounded-full bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-purple-400 text-xs font-bold"
                        >
                          {d}
                        </span>
                      ))
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 min-h-[26px]">
                    {cadastro.lei && (
                      <span className="px-3 py-1 rounded-full bg-gradient-to-r from-yellow-500/20 to-amber-500/20 border border-yellow-500/30 text-yellow-400 text-xs font-bold flex items-center gap-1">
                        <Scale className="w-3 h-3" />
                        {cadastro.lei}
                      </span>
                    )}
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
                      disabled={loadingEditId === cadastro.id}
                      className="flex-1 py-2.5 rounded-xl font-semibold bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 transition-all flex items-center justify-center gap-2 disabled:opacity-70"
                    >
                      {loadingEditId === cadastro.id ? (
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      ) : (
                        <Pencil className="w-4 h-4" />
                      )}
                      {loadingEditId === cadastro.id ? 'Abrindo...' : 'Editar'}
                    </button>
                    {isAdmin && (
                      <button
                        onClick={() => handleDeleteEvento(cadastro)}
                        title="Mover para lixeira"
                        className="p-2.5 rounded-xl font-semibold transition-all flex items-center justify-center text-red-400 hover:bg-red-500/20 hover:text-red-300"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showLixeira && (
        <div className={`mt-4 rounded-3xl border p-6 ${isDark ? 'bg-gray-800/80 border-red-500/30' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-red-500/20">
                <Trash2 className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h2 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Lixeira</h2>
                <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Eventos excluídos nos últimos 30 dias — clique em Restaurar para recuperar</p>
              </div>
            </div>
            <button
              onClick={() => loadLixeira()}
              className={`p-2 rounded-xl transition-all ${isDark ? 'hover:bg-gray-700 text-gray-400' : 'hover:bg-gray-100 text-gray-500'}`}
              title="Atualizar lixeira"
            >
              <RefreshCw className={`w-4 h-4 ${loadingLixeira ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {loadingLixeira ? (
            <div className="flex items-center justify-center py-8">
              <div className="w-8 h-8 border-4 border-red-500/30 border-t-red-500 rounded-full animate-spin" />
            </div>
          ) : lixeira.length === 0 ? (
            <div className="text-center py-8">
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Nenhum evento na lixeira</p>
            </div>
          ) : (
            <div className="space-y-2">
              {lixeira.map((item: any) => (
                <div
                  key={item.id}
                  className={`flex items-center justify-between p-3 rounded-xl ${isDark ? 'bg-gray-700/50' : 'bg-white'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}
                >
                  <div className="flex-1 min-w-0">
                    <p className={`font-semibold text-sm truncate ${isDark ? 'text-white' : 'text-gray-900'}`}>{item.nome}</p>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                      SKU: {item.sku || '—'} • Excluído em: {item.deleted_at ? new Date(item.deleted_at).toLocaleDateString('pt-BR') : '—'}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRestaurar(item.id, item.nome)}
                    className="ml-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-all text-xs font-semibold"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Restaurar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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

            <div className="p-6 space-y-6 overflow-y-auto flex-1">

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Calendar className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                  <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Info Geral</h3>
                </div>
                <div className={`grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'}`}>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Circuito/Produto</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.circuito_produto || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Localização</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.localizacao_evento || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Ano</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.ano_evento || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Modalidade</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.modalidade || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>SKU</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.sku || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Produto</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.produto || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Tipo de Evento</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.tipo_evento || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Lei</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.lei || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Status</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.status || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Data</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatDateDisplay(selectedCadastro.info_geral.data)}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Horário Largada</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.info_geral.horario_largada || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Local</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.info_geral.local || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Dias p/ encerrar inscrições</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.info_geral.dias_encerramento_inscricao ?? 2}</p>
                  </div>
                  {selectedCadastro.info_geral.distancias && selectedCadastro.info_geral.distancias.length > 0 && (
                    <div className="col-span-full">
                      <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'} mb-1`}>Distâncias</p>
                      <div className="flex flex-wrap gap-2">
                        {typeof selectedCadastro.info_geral.distancias[0] === 'object' ? (
                          (() => {
                            const tri = selectedCadastro.info_geral.distancias[0] as { nado?: string; ciclismo?: string; corrida?: string };
                            return (
                              <>
                                {tri.nado && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 text-white text-xs font-bold">Nado: {tri.nado}</span>}
                                {tri.ciclismo && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-green-500 to-emerald-500 text-white text-xs font-bold">Ciclismo: {tri.ciclismo}</span>}
                                {tri.corrida && <span className="px-3 py-1 rounded-full bg-gradient-to-r from-orange-500 to-red-500 text-white text-xs font-bold">Corrida: {tri.corrida}</span>}
                              </>
                            );
                          })()
                        ) : (
                          selectedCadastro.info_geral.distancias.map((d: any) => (
                            <span key={d} className="px-3 py-1 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 text-white text-xs font-bold">{d}</span>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Users className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                  <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Atletas</h3>
                </div>
                <div className={`grid grid-cols-2 md:grid-cols-3 ${selectedCadastro.localizacao_evento === 'Rio de Janeiro' ? 'lg:grid-cols-5' : 'lg:grid-cols-4'} gap-4`}>
                  <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Atletas</p>
                    <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(getTotalAtletasCadastro(selectedCadastro)) || '0'}</p>
                  </div>
                  <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Site - Pago</p>
                    <p className="text-2xl font-bold text-blue-400">{formatNumber(selectedCadastro.atletas.site.pago || 0) || '0'}</p>
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Tkt Médio: R$ {formatNumber(selectedCadastro.atletas.site.tkt_medio || 0) || '0'}</p>
                  </div>
                  <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Grupos - Pago</p>
                    <p className="text-2xl font-bold text-orange-400">{formatNumber(selectedCadastro.atletas.grupos.pago || 0) || '0'}</p>
                    <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Tkt Médio: R$ {formatNumber(selectedCadastro.atletas.grupos.tkt_medio || 0) || '0'}</p>
                  </div>
                  <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                    <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Cortesias</p>
                    <p className="text-2xl font-bold text-emerald-400">{formatNumber(selectedCadastro.atletas.cortesia || 0) || '0'}</p>
                  </div>
                  {selectedCadastro.localizacao_evento === 'Rio de Janeiro' && (
                    <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Appai/Assist - Pago</p>
                      <p className="text-2xl font-bold text-cyan-400">{formatNumber(selectedCadastro.atletas.appai?.pago || 0) || '0'}</p>
                      <p className={`text-xs mt-1 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Tkt Médio: R$ {formatNumber(selectedCadastro.atletas.appai?.tkt_medio || 0) || '0'}</p>
                    </div>
                  )}
                </div>
              </div>

              {selectedCadastro.cortesias && selectedCadastro.cortesias.length > 0 && (
                <>
                  <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Gift className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Cortesias</h3>
                    </div>
                    <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                      <table className="w-full">
                        <thead>
                          <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Quem</th>
                            <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Quantidade</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCadastro.cortesias.map((c: any, i: number) => (
                            <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                              <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{c.cliente || '-'}</td>
                              <td className={`px-4 py-2 text-sm text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{c.quantidade || 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}

              {selectedCadastro.taxas && selectedCadastro.taxas.length > 0 && (
                <>
                  <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <DollarSign className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Taxas</h3>
                    </div>
                    <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                      <table className="w-full">
                        <thead>
                          <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Valor Unitário</th>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Valor Total</th>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>% Inscrição</th>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Validado</th>
                            <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Data Validação</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCadastro.taxas.map((t: any, i: number) => (
                            <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                              <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(t.valor_unitario || 0) || '0'}</td>
                              <td className={`px-4 py-2 text-sm font-semibold ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>R$ {((t.valor_unitario || 0) * (selectedCadastro.atletas.site.pago || 0)).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                              <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(t.percentual_inscricao || 0) || '0'}%</td>
                              <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.validado ? 'Sim' : 'Não'}</td>
                              <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{t.data_validacao ? formatDateDisplay(t.data_validacao) : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}

              <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Package className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                  <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Retirada de Kit</h3>
                </div>
                <div className={`grid grid-cols-2 gap-4 p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'}`}>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Local</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.retirada_kit?.local || '-'}</p>
                  </div>
                  <div>
                    <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Data/Horário</p>
                    <p className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.retirada_kit?.data_horario ? formatDateDisplay(selectedCadastro.retirada_kit.data_horario) : '-'}</p>
                  </div>
                </div>
              </div>

              {selectedCadastro.kit_produto && selectedCadastro.kit_produto.length > 0 && (
                <>
                  <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Box className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Kit & Produtos</h3>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {selectedCadastro.kit_produto.filter((k: any) => k.kit).map((kit: any, i: number) => (
                        <div key={i} className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'}`}>
                          <p className={`text-sm font-bold mb-2 ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>{kit.kit}</p>
                          {kit.produtos && kit.produtos.length > 0 ? (
                            <div className="space-y-1">
                              {kit.produtos.map((p: any, j: number) => (
                                <div key={j} className="flex justify-between items-center">
                                  <span className={`text-xs ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{p.nome}</span>
                                  <span className={`text-xs font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(p.valor_unitario || 0) || '0'}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>Sem produtos</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {selectedCadastro.faixas_preco_site && (selectedCadastro.faixas_preco_site.kit_basico?.length > 0 || selectedCadastro.faixas_preco_site.kit_participacao?.length > 0) && (
                <>
                  <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <Globe className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Faixas de Preço - Site</h3>
                    </div>
                    <div className="space-y-4">
                      {selectedCadastro.faixas_preco_site.kit_basico?.length > 0 && (
                        <div>
                          <p className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Kit Básico</p>
                          <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead>
                                <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                                  <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faixa</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedCadastro.faixas_preco_site.kit_basico.map((f: any, i: number) => (
                                  <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                                    <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{f.faixa}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(f.qtd || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(f.tkt_medio || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(Math.round((f.total || 0) * 100) / 100)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                      {selectedCadastro.faixas_preco_site.kit_participacao?.length > 0 && (
                        <div>
                          <p className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Kit Participação</p>
                          <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead>
                                <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                                  <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faixa</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedCadastro.faixas_preco_site.kit_participacao.map((f: any, i: number) => (
                                  <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                                    <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{f.faixa}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(f.qtd || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(f.tkt_medio || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(Math.round((f.total || 0) * 100) / 100)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              {selectedCadastro.faixas_preco_grupos && (selectedCadastro.faixas_preco_grupos.kit_basico?.length > 0 || selectedCadastro.faixas_preco_grupos.kit_participacao?.length > 0) && (
                <>
                  <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'}`} />
                  <div>
                    <div className="flex items-center gap-2 mb-3">
                      <UsersRound className={`w-5 h-5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`} />
                      <h3 className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>Faixas de Preço - Grupos</h3>
                    </div>
                    <div className="space-y-4">
                      {selectedCadastro.faixas_preco_grupos.kit_basico?.length > 0 && (
                        <div>
                          <p className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Kit Básico</p>
                          <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead>
                                <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                                  <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faixa</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedCadastro.faixas_preco_grupos.kit_basico.map((f: any, i: number) => (
                                  <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                                    <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{f.faixa}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(f.qtd || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(f.tkt_medio || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(Math.round((f.total || 0) * 100) / 100)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                      {selectedCadastro.faixas_preco_grupos.kit_participacao?.length > 0 && (
                        <div>
                          <p className={`text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Kit Participação</p>
                          <div className={`rounded-2xl overflow-hidden border ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                            <table className="w-full">
                              <thead>
                                <tr className={isDark ? 'bg-gray-800' : 'bg-gray-50'}>
                                  <th className={`text-left px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Faixa</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Qtd</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</th>
                                  <th className={`text-right px-4 py-2 text-xs font-semibold ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedCadastro.faixas_preco_grupos.kit_participacao.map((f: any, i: number) => (
                                  <tr key={i} className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-100'}`}>
                                    <td className={`px-4 py-2 text-sm ${isDark ? 'text-white' : 'text-gray-900'}`}>{f.faixa}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatNumber(f.qtd || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right ${isDark ? 'text-white' : 'text-gray-900'}`}>R$ {formatNumber(f.tkt_medio || 0) || '0'}</td>
                                    <td className={`px-4 py-2 text-sm text-right font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{formatCurrency(Math.round((f.total || 0) * 100) / 100)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              <div className={`border-t ${isDark ? 'border-gray-700/50' : 'border-gray-200'} pt-4`}>
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
            <div className="p-6 pb-3">
              <div className="flex items-center justify-between mb-2">
                <h2 className={`text-xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                  {editItem ? 'Editar Evento' : 'Novo Evento'}
                </h2>
                <button 
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditItem(null);
                  }}
                  className={`p-2 rounded-full ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-200'} transition-colors`}
                >
                  <X className="w-6 h-6" />
                </button>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <ImageIcon className={`w-3 h-3 flex-shrink-0 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                <input
                  type="text"
                  value={form.imagem_kv}
                  onChange={(e) => setForm(prev => ({ ...prev, imagem_kv: e.target.value }))}
                  placeholder="URL da imagem do evento"
                  className={`flex-1 px-2 py-1 text-xs rounded-lg border ${isDark ? 'bg-gray-800/50 border-gray-700/50 text-gray-400 placeholder-gray-600' : 'bg-gray-50 border-gray-200 text-gray-500 placeholder-gray-400'} focus:ring-1 focus:ring-purple-500/50 outline-none`}
                />
                {form.imagem_kv && (
                  <img src={form.imagem_kv} alt="" className="w-6 h-6 rounded object-cover flex-shrink-0" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                )}
              </div>
              {form.circuito_produto && form.localizacao_evento && (
                <div className={`mt-2 p-3 rounded-xl border ${isDark ? 'bg-purple-900/30 border-purple-500/40' : 'bg-purple-50 border-purple-300'}`}>
                  <p className={`text-xs font-medium mb-0.5 ${isDark ? 'text-purple-400' : 'text-purple-600'}`}>Nome do Evento</p>
                  <p className={`text-lg font-bold tracking-wide ${isDark ? 'text-white' : 'text-gray-900'}`}>
                    {form.circuito_produto} - {form.localizacao_evento} {form.ano_evento}
                  </p>
                </div>
              )}
            </div>

            <div className="flex overflow-x-auto scrollbar-hide border-b border-gray-700/50 flex-shrink-0">
              {visibleTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                const tabEditable = canEditCampo('eventos', tab.id);
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-3 font-medium whitespace-nowrap transition-all relative flex-shrink-0 ${
                      isActive
                        ? isDark ? 'text-purple-400' : 'text-purple-600'
                        : isDark ? 'text-gray-400 hover:text-gray-300' : 'text-gray-600 hover:text-gray-800'
                    }`}
                  >
                    <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? 'text-purple-500' : ''}`} />
                    <span className="text-xs font-medium">{tab.label}</span>
                    {isActive && (
                      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-purple-500 to-pink-500" />
                    )}
                  </button>
                );
              })}
            </div>

            <form onSubmit={handleSubmit} className="flex-1 flex flex-col min-h-0">
              <div className="p-6 flex-1 overflow-y-auto scrollbar-thin-custom">
                {!canEditCampo('eventos', activeTab) ? (
                  <div>
                    <div className={`flex items-center justify-center gap-2 py-1.5 px-4 rounded-lg text-xs font-medium mx-auto w-fit mb-4 ${isDark ? 'bg-gray-700/80 text-gray-400' : 'bg-gray-100/90 text-gray-500'}`}>
                      <Eye className="w-3 h-3" />
                      Visualização
                    </div>
                    <div className="pointer-events-none select-none">
                      {renderTabContent()}
                    </div>
                  </div>
                ) : renderTabContent()}
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
                  disabled={excedeCortesias || loading}
                  className={`px-8 py-3 rounded-xl font-semibold transition-all flex items-center gap-2 ${
                    excedeCortesias || loading
                      ? 'bg-gray-500 text-gray-300 cursor-not-allowed opacity-60' 
                      : 'bg-gradient-to-r from-purple-500 via-pink-500 to-orange-500 text-white shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40'
                  }`}
                  title={excedeCortesias ? 'Quantidade de cortesias excede o limite orçado na aba Atletas' : ''}
                >
                  {loading ? (
                    <RotateCcw className="w-5 h-5 animate-spin" />
                  ) : (
                    <Check className="w-5 h-5" />
                  )}
                  {loading ? 'Salvando...' : (editItem ? 'Salvar Alterações' : 'Criar Cadastro')}
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
