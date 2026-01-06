import React, { useState, useMemo } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { 
  Plus, Pencil, X, Check, Calendar, MapPin, Users, 
  Trophy, Zap, Target, Sparkles, Clock, Package,
  Image as ImageIcon, Search, Filter, Eye,
  ChevronDown, RotateCcw, DollarSign, Timer,
  Hash, Award, Ticket, Droplets, Gift, Layers,
  UserPlus, Building2, ShoppingBag, Ruler
} from 'lucide-react';

interface CadastroEvento {
  id: number;
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
    total: number;
    pago: number;
    cortesia: number;
    tkt_medio: number;
  };
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  pelotoes: Array<{ pelotao: string; atletas: number }>;
  cronometragem: Array<{
    distancia: string;
    tempo_limite: string;
    tempo_corte: string;
    num_peito: number;
    chip: number;
    alfinete: number;
  }>;
  patrocinadores: Array<{ cliente: string; tipo_venda: string }>;
  kit_produto: Array<{ kit: string; trofeu: number; qtd: number }>;
  producao: {
    agua: number;
    isotonico: number;
  };
  faixas_preco: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
}

interface FormData {
  nome: string;
  imagem_kv: string;
  info_geral: {
    data: string;
    horario_largada: string;
    local: string;
    distancias: string[];
  };
  atletas: {
    total: number;
    pago: number;
    cortesia: number;
    tkt_medio: number;
  };
  retirada_kit: {
    local: string;
    data_horario: string;
  };
  pelotoes: Array<{ pelotao: string; atletas: number }>;
  cronometragem: Array<{
    distancia: string;
    tempo_limite: string;
    tempo_corte: string;
    num_peito: number;
    chip: number;
    alfinete: number;
  }>;
  patrocinadores: Array<{ cliente: string; tipo_venda: string }>;
  kit_produto: Array<{ kit: string; trofeu: number; qtd: number }>;
  producao: {
    agua: number;
    isotonico: number;
  };
  faixas_preco: Array<{ faixa: string; qtd: number; tkt_medio: number; total: number }>;
}

const distanciasOptions = ['3k', '5k', '10k', '15k', '21k', '42k'];
const pelotoesOptions = ['Quênia', 'Azul', 'Verde', 'Branco'];
const tipoVendaOptions = ['Patrocínio', 'Permuta', 'Ativação'];
const kitOptions = ['Kit Básico', 'Kit Vip', 'Kit Plus', 'Kit Super'];
const faixaOptions = ['1', '2', '3', '4', '5'];

const createDefaultCadastro = (): Omit<CadastroEvento, 'id'> => ({
  nome: '',
  imagem_kv: '',
  status: 'Em andamento',
  modalidade: 'Corrida',
  info_geral: { data: '', horario_largada: '', local: '', distancias: [] },
  atletas: { total: 0, pago: 0, cortesia: 0, tkt_medio: 0 },
  retirada_kit: { local: '', data_horario: '' },
  pelotoes: [{ pelotao: '', atletas: 0 }],
  cronometragem: [{ distancia: '', tempo_limite: '', tempo_corte: '', num_peito: 0, chip: 0, alfinete: 0 }],
  patrocinadores: [{ cliente: '', tipo_venda: '' }],
  kit_produto: [{ kit: '', trofeu: 0, qtd: 0 }],
  producao: { agua: 0, isotonico: 0 },
  faixas_preco: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
});

const mockCadastros: CadastroEvento[] = [
  {
    id: 1,
    nome: 'Maratona de São Paulo 2026',
    imagem_kv: 'https://images.unsplash.com/photo-1513593771513-7b58b6c4af38?w=800',
    status: 'Em andamento',
    modalidade: 'Corrida',
    info_geral: { data: '2026-04-12', horario_largada: '06:30', local: 'Ibirapuera, São Paulo - SP', distancias: ['10k', '21k', '42k'] },
    atletas: { total: 15000, pago: 12500, cortesia: 2500, tkt_medio: 189.90 },
    retirada_kit: { local: 'Pavilhão do Ibirapuera', data_horario: '2026-04-11T10:00' },
    pelotoes: [{ pelotao: 'Quênia', atletas: 50 }, { pelotao: 'Azul', atletas: 2000 }, { pelotao: 'Verde', atletas: 5000 }],
    cronometragem: [
      { distancia: '10k', tempo_limite: '01:30:00', tempo_corte: '01:15:00', num_peito: 5000, chip: 5000, alfinete: 20000 },
      { distancia: '21k', tempo_limite: '03:00:00', tempo_corte: '02:30:00', num_peito: 6000, chip: 6000, alfinete: 24000 },
      { distancia: '42k', tempo_limite: '06:00:00', tempo_corte: '05:00:00', num_peito: 4000, chip: 4000, alfinete: 16000 }
    ],
    patrocinadores: [{ cliente: 'Nike', tipo_venda: 'Patrocínio' }, { cliente: 'Gatorade', tipo_venda: 'Permuta' }],
    kit_produto: [{ kit: 'Kit Básico', trofeu: 0, qtd: 10000 }, { kit: 'Kit Vip', trofeu: 1, qtd: 5000 }],
    producao: { agua: 50000, isotonico: 30000 },
    faixas_preco: [{ faixa: '1', qtd: 5000, tkt_medio: 149.90, total: 749500 }, { faixa: '2', qtd: 5000, tkt_medio: 189.90, total: 949500 }, { faixa: '3', qtd: 5000, tkt_medio: 229.90, total: 1149500 }]
  },
  {
    id: 2,
    nome: 'Night Run Rio 2026',
    imagem_kv: 'https://images.unsplash.com/photo-1552674605-db6ffd4facb5?w=800',
    status: 'Em andamento',
    modalidade: 'Corrida',
    info_geral: { data: '2026-06-20', horario_largada: '20:00', local: 'Aterro do Flamengo, Rio de Janeiro - RJ', distancias: ['5k', '10k'] },
    atletas: { total: 8000, pago: 7200, cortesia: 800, tkt_medio: 129.90 },
    retirada_kit: { local: 'Marina da Glória', data_horario: '2026-06-19T14:00' },
    pelotoes: [{ pelotao: 'Azul', atletas: 3000 }, { pelotao: 'Verde', atletas: 5000 }],
    cronometragem: [
      { distancia: '5k', tempo_limite: '01:00:00', tempo_corte: '00:45:00', num_peito: 4000, chip: 4000, alfinete: 16000 },
      { distancia: '10k', tempo_limite: '01:30:00', tempo_corte: '01:15:00', num_peito: 4000, chip: 4000, alfinete: 16000 }
    ],
    patrocinadores: [{ cliente: 'Adidas', tipo_venda: 'Patrocínio' }],
    kit_produto: [{ kit: 'Kit Básico', trofeu: 0, qtd: 8000 }],
    producao: { agua: 24000, isotonico: 16000 },
    faixas_preco: [{ faixa: '1', qtd: 4000, tkt_medio: 99.90, total: 399600 }, { faixa: '2', qtd: 4000, tkt_medio: 159.90, total: 639600 }]
  },
  {
    id: 3,
    nome: 'Trail Run Serra Gaúcha',
    imagem_kv: 'https://images.unsplash.com/photo-1551698618-1dfe5d97d256?w=800',
    status: 'Em andamento',
    modalidade: 'Corrida',
    info_geral: { data: '2026-09-15', horario_largada: '07:00', local: 'Gramado - RS', distancias: ['15k', '21k'] },
    atletas: { total: 3500, pago: 3000, cortesia: 500, tkt_medio: 249.90 },
    retirada_kit: { local: 'Praça das Etnias', data_horario: '2026-09-14T09:00' },
    pelotoes: [{ pelotao: 'Quênia', atletas: 20 }, { pelotao: 'Azul', atletas: 1500 }],
    cronometragem: [
      { distancia: '15k', tempo_limite: '03:00:00', tempo_corte: '02:30:00', num_peito: 1500, chip: 1500, alfinete: 6000 },
      { distancia: '21k', tempo_limite: '04:00:00', tempo_corte: '03:30:00', num_peito: 2000, chip: 2000, alfinete: 8000 }
    ],
    patrocinadores: [{ cliente: 'The North Face', tipo_venda: 'Patrocínio' }, { cliente: 'Red Bull', tipo_venda: 'Ativação' }],
    kit_produto: [{ kit: 'Kit Plus', trofeu: 1, qtd: 3500 }],
    producao: { agua: 15000, isotonico: 10000 },
    faixas_preco: [{ faixa: '1', qtd: 1500, tkt_medio: 199.90, total: 299850 }, { faixa: '2', qtd: 2000, tkt_medio: 299.90, total: 599800 }]
  },
  {
    id: 4,
    nome: 'Corrida Kids Esportiva',
    imagem_kv: 'https://images.unsplash.com/photo-1571008887538-b36bb32f4571?w=800',
    status: 'Concluído',
    modalidade: 'Corrida',
    info_geral: { data: '2026-03-08', horario_largada: '09:00', local: 'Parque Villa Lobos, São Paulo - SP', distancias: ['3k', '5k'] },
    atletas: { total: 2000, pago: 1500, cortesia: 500, tkt_medio: 79.90 },
    retirada_kit: { local: 'Parque Villa Lobos - Entrada Principal', data_horario: '2026-03-07T10:00' },
    pelotoes: [{ pelotao: 'Branco', atletas: 2000 }],
    cronometragem: [
      { distancia: '3k', tempo_limite: '00:40:00', tempo_corte: '00:30:00', num_peito: 1000, chip: 1000, alfinete: 4000 },
      { distancia: '5k', tempo_limite: '01:00:00', tempo_corte: '00:45:00', num_peito: 1000, chip: 1000, alfinete: 4000 }
    ],
    patrocinadores: [{ cliente: 'Nestlé', tipo_venda: 'Permuta' }],
    kit_produto: [{ kit: 'Kit Básico', trofeu: 1, qtd: 2000 }],
    producao: { agua: 6000, isotonico: 4000 },
    faixas_preco: [{ faixa: '1', qtd: 2000, tkt_medio: 79.90, total: 159800 }]
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
  { id: 'retirada_kit', label: 'Retirada Kit', icon: Package },
  { id: 'pelotoes', label: 'Pelotões', icon: Layers },
  { id: 'cronometragem', label: 'Cronometragem', icon: Timer },
  { id: 'patrocinadores', label: 'Patrocinadores', icon: Building2 },
  { id: 'kit_produto', label: 'Kit Produto', icon: Gift },
  { id: 'producao', label: 'Produção', icon: Droplets },
  { id: 'faixas_preco', label: 'Faixas de Preço', icon: DollarSign },
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

  const initialFormData: FormData = {
    nome: '',
    imagem_kv: '',
    info_geral: {
      data: '',
      horario_largada: '',
      local: '',
      distancias: []
    },
    atletas: {
      total: 0,
      pago: 0,
      cortesia: 0,
      tkt_medio: 0
    },
    retirada_kit: {
      local: '',
      data_horario: ''
    },
    pelotoes: [{ pelotao: '', atletas: 0 }],
    cronometragem: [{ distancia: '', tempo_limite: '', tempo_corte: '', num_peito: 0, chip: 0, alfinete: 0 }],
    patrocinadores: [{ cliente: '', tipo_venda: '' }],
    kit_produto: [{ kit: '', trofeu: 0, qtd: 0 }],
    producao: {
      agua: 0,
      isotonico: 0
    },
    faixas_preco: [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
  };

  const [form, setForm] = useState<FormData>(initialFormData);

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
  const totalAtletas = cadastros.reduce((acc, c) => acc + c.atletas.total, 0);

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

  const handleEdit = (item: CadastroEvento) => {
    setEditItem(item);
    setForm({
      nome: item.nome,
      imagem_kv: item.imagem_kv,
      info_geral: { ...item.info_geral },
      atletas: { ...item.atletas },
      retirada_kit: { ...item.retirada_kit },
      pelotoes: item.pelotoes.length > 0 ? [...item.pelotoes] : [{ pelotao: '', atletas: 0 }],
      cronometragem: item.cronometragem.length > 0 ? [...item.cronometragem] : [{ distancia: '', tempo_limite: '', tempo_corte: '', num_peito: 0, chip: 0, alfinete: 0 }],
      patrocinadores: item.patrocinadores.length > 0 ? [...item.patrocinadores] : [{ cliente: '', tipo_venda: '' }],
      kit_produto: item.kit_produto.length > 0 ? [...item.kit_produto] : [{ kit: '', trofeu: 0, qtd: 0 }],
      producao: { ...item.producao },
      faixas_preco: item.faixas_preco.length > 0 ? [...item.faixas_preco] : [{ faixa: '', qtd: 0, tkt_medio: 0, total: 0 }]
    });
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
              nome: form.nome,
              imagem_kv: form.imagem_kv,
              info_geral: { ...form.info_geral },
              atletas: { ...form.atletas },
              retirada_kit: { ...form.retirada_kit },
              pelotoes: [...form.pelotoes],
              cronometragem: [...form.cronometragem],
              patrocinadores: [...form.patrocinadores],
              kit_produto: [...form.kit_produto],
              producao: { ...form.producao },
              faixas_preco: [...form.faixas_preco]
            }
          : c
      ));
    } else {
      const newCadastro: CadastroEvento = {
        id: cadastros.length > 0 ? Math.max(...cadastros.map(c => c.id)) + 1 : 1,
        nome: form.nome,
        imagem_kv: form.imagem_kv,
        status: 'Em andamento',
        modalidade: 'Corrida',
        info_geral: { ...form.info_geral },
        atletas: { ...form.atletas },
        retirada_kit: { ...form.retirada_kit },
        pelotoes: [...form.pelotoes],
        cronometragem: [...form.cronometragem],
        patrocinadores: [...form.patrocinadores],
        kit_produto: [...form.kit_produto],
        producao: { ...form.producao },
        faixas_preco: [...form.faixas_preco]
      };
      setCadastros(prev => [...prev, newCadastro]);
    }
    setShowModal(false);
    setEditItem(null);
  };

  const addArrayField = (field: 'pelotoes' | 'cronometragem' | 'patrocinadores' | 'kit_produto' | 'faixas_preco') => {
    const newItems = {
      pelotoes: { pelotao: '', atletas: 0 },
      cronometragem: { distancia: '', tempo_limite: '', tempo_corte: '', num_peito: 0, chip: 0, alfinete: 0 },
      patrocinadores: { cliente: '', tipo_venda: '' },
      kit_produto: { kit: '', trofeu: 0, qtd: 0 },
      faixas_preco: { faixa: '', qtd: 0, tkt_medio: 0, total: 0 }
    };
    setForm(prev => ({
      ...prev,
      [field]: [...prev[field], newItems[field]]
    }));
  };

  const removeArrayField = (field: 'pelotoes' | 'cronometragem' | 'patrocinadores' | 'kit_produto' | 'faixas_preco', index: number) => {
    setForm(prev => ({
      ...prev,
      [field]: prev[field].filter((_, i) => i !== index)
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
        return (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                Total
              </label>
              <input
                type="number"
                value={form.atletas.total || ''}
                onChange={(e) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, total: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                Pago
              </label>
              <input
                type="number"
                value={form.atletas.pago || ''}
                onChange={(e) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, pago: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                Cortesia
              </label>
              <input
                type="number"
                value={form.atletas.cortesia || ''}
                onChange={(e) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, cortesia: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <DollarSign className="w-4 h-4 inline mr-1 text-green-500" />
                Ticket Médio
              </label>
              <input
                type="number"
                step="0.01"
                value={form.atletas.tkt_medio || ''}
                onChange={(e) => setForm(prev => ({ ...prev, atletas: { ...prev.atletas, tkt_medio: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
          </div>
        );

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
                  <input
                    type="number"
                    value={pelotao.atletas || ''}
                    onChange={(e) => updateArrayField('pelotoes', index, 'atletas', Number(e.target.value))}
                    placeholder="Qtd Atletas"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
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
            {form.cronometragem.map((crono, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Distância {index + 1}</span>
                  {form.cronometragem.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('cronometragem', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <select
                    value={crono.distancia}
                    onChange={(e) => updateArrayField('cronometragem', index, 'distancia', e.target.value)}
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Distância</option>
                    {distanciasOptions.filter(d => !form.cronometragem.some((fc, i) => i !== index && fc.distancia === d)).map(d => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={crono.tempo_limite}
                    onChange={(e) => updateArrayField('cronometragem', index, 'tempo_limite', e.target.value)}
                    placeholder="Tempo Limite"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="text"
                    value={crono.tempo_corte}
                    onChange={(e) => updateArrayField('cronometragem', index, 'tempo_corte', e.target.value)}
                    placeholder="Tempo de Corte"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <input
                    type="number"
                    value={crono.num_peito || ''}
                    onChange={(e) => updateArrayField('cronometragem', index, 'num_peito', Number(e.target.value))}
                    placeholder="N° de Peito"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="number"
                    value={crono.chip || ''}
                    onChange={(e) => updateArrayField('cronometragem', index, 'chip', Number(e.target.value))}
                    placeholder="Chip"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="number"
                    value={crono.alfinete || ''}
                    onChange={(e) => updateArrayField('cronometragem', index, 'alfinete', Number(e.target.value))}
                    placeholder="Alfinete"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addArrayField('cronometragem')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Distância
            </button>
          </div>
        );

      case 'patrocinadores':
        return (
          <div className="space-y-4">
            {form.patrocinadores.map((patrocinador, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Patrocinador {index + 1}</span>
                  {form.patrocinadores.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('patrocinadores', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    value={patrocinador.cliente}
                    onChange={(e) => updateArrayField('patrocinadores', index, 'cliente', e.target.value)}
                    placeholder="Nome do Cliente"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <select
                    value={patrocinador.tipo_venda}
                    onChange={(e) => updateArrayField('patrocinadores', index, 'tipo_venda', e.target.value)}
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Tipo de Venda</option>
                    {tipoVendaOptions.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addArrayField('patrocinadores')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Patrocinador
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
                <div className="grid grid-cols-3 gap-3">
                  <select
                    value={kit.kit}
                    onChange={(e) => updateArrayField('kit_produto', index, 'kit', e.target.value)}
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Selecione</option>
                    {kitOptions.filter(k => !form.kit_produto.some((fk, i) => i !== index && fk.kit === k)).map(k => (
                      <option key={k} value={k}>{k}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={kit.trofeu || ''}
                    onChange={(e) => updateArrayField('kit_produto', index, 'trofeu', Number(e.target.value))}
                    placeholder="Troféu"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="number"
                    value={kit.qtd || ''}
                    onChange={(e) => updateArrayField('kit_produto', index, 'qtd', Number(e.target.value))}
                    placeholder="Quantidade"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
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

      case 'producao':
        return (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Droplets className="w-4 h-4 inline mr-2 text-blue-400" />
                Água (unidades)
              </label>
              <input
                type="number"
                value={form.producao.agua || ''}
                onChange={(e) => setForm(prev => ({ ...prev, producao: { ...prev.producao, agua: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
            <div>
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Droplets className="w-4 h-4 inline mr-2 text-green-400" />
                Isotônico (unidades)
              </label>
              <input
                type="number"
                value={form.producao.isotonico || ''}
                onChange={(e) => setForm(prev => ({ ...prev, producao: { ...prev.producao, isotonico: Number(e.target.value) } }))}
                className={`w-full px-4 py-3 rounded-xl border ${isDark ? 'bg-gray-700/50 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
            </div>
          </div>
        );

      case 'faixas_preco':
        return (
          <div className="space-y-4">
            {form.faixas_preco.map((faixa, index) => (
              <div key={index} className={`p-4 rounded-xl ${isDark ? 'bg-gray-700/30' : 'bg-gray-50'} border ${isDark ? 'border-gray-600' : 'border-gray-200'}`}>
                <div className="flex justify-between items-center mb-3">
                  <span className={`text-sm font-bold ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>Faixa de Preço {index + 1}</span>
                  {form.faixas_preco.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeArrayField('faixas_preco', index)}
                      className="p-1 text-red-400 hover:text-red-300 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-4 gap-3">
                  <select
                    value={faixa.faixa}
                    onChange={(e) => updateArrayField('faixas_preco', index, 'faixa', e.target.value)}
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  >
                    <option value="">Faixa</option>
                    {faixaOptions.filter(f => !form.faixas_preco.some((ff, i) => i !== index && ff.faixa === f)).map(f => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={faixa.qtd || ''}
                    onChange={(e) => updateArrayField('faixas_preco', index, 'qtd', Number(e.target.value))}
                    placeholder="Qtd"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="number"
                    step="0.01"
                    value={faixa.tkt_medio || ''}
                    onChange={(e) => updateArrayField('faixas_preco', index, 'tkt_medio', Number(e.target.value))}
                    placeholder="Tkt Médio"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                  <input
                    type="number"
                    step="0.01"
                    value={faixa.total || ''}
                    onChange={(e) => updateArrayField('faixas_preco', index, 'total', Number(e.target.value))}
                    placeholder="Total"
                    className={`px-4 py-2 rounded-lg border ${isDark ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
                  />
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addArrayField('faixas_preco')}
              className="w-full py-3 rounded-xl border-2 border-dashed border-purple-500/50 text-purple-400 hover:bg-purple-500/10 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-5 h-5" />
              Adicionar Faixa de Preço
            </button>
          </div>
        );

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
              <p className={`text-3xl font-black ${isDark ? 'text-white' : 'text-gray-900'}`}>{totalAtletas.toLocaleString()}</p>
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
                      <p className={`text-lg font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{cadastro.atletas.total.toLocaleString()}</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Pagos</p>
                      <p className={`text-lg font-bold text-green-400`}>{cadastro.atletas.pago.toLocaleString()}</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Tkt Médio</p>
                      <p className={`text-lg font-bold text-purple-400`}>{formatCurrency(cadastro.atletas.tkt_medio)}</p>
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
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl w-full max-w-4xl my-8 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative h-64 overflow-hidden">
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
                    <span>{formatDateDisplay(selectedCadastro.data)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-5 h-5" />
                    <span>{selectedCadastro.horario_largada}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MapPin className="w-5 h-5" />
                    <span>{selectedCadastro.local}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div className="grid grid-cols-4 gap-4">
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Total Atletas</p>
                  <p className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>{selectedCadastro.total_atletas.toLocaleString()}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Atletas Pagos</p>
                  <p className="text-2xl font-bold text-green-400">{selectedCadastro.atletas_pagos.toLocaleString()}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Cortesias</p>
                  <p className="text-2xl font-bold text-orange-400">{selectedCadastro.atletas_cortesia.toLocaleString()}</p>
                </div>
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                  <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Ticket Médio</p>
                  <p className="text-2xl font-bold text-purple-400">{formatCurrency(selectedCadastro.ticket_medio)}</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <span className={`text-sm font-medium ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>Distâncias:</span>
                {selectedCadastro.distancias.map(d => (
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
            className={`${isDark ? 'bg-gray-900' : 'bg-white'} rounded-3xl w-full max-w-4xl my-8 shadow-2xl border ${isDark ? 'border-gray-700' : 'border-gray-200'} overflow-hidden`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`relative h-48 overflow-hidden ${isDark ? 'bg-gray-800' : 'bg-gray-100'}`}>
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
                <input
                  type="text"
                  value={form.nome}
                  onChange={(e) => setForm(prev => ({ ...prev, nome: e.target.value }))}
                  placeholder="Nome do Evento"
                  className="w-full text-2xl font-black bg-transparent text-white placeholder-white/50 border-none focus:outline-none focus:ring-0"
                />
              </div>
            </div>

            <div className="p-4 border-b border-gray-700/50">
              <label className={`block text-sm font-semibold mb-2 ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                URL da Imagem do Evento
              </label>
              <input
                type="url"
                value={form.imagem_kv}
                onChange={(e) => setForm(prev => ({ ...prev, imagem_kv: e.target.value }))}
                placeholder="https://exemplo.com/imagem.jpg"
                className={`w-full px-4 py-2 rounded-xl border ${isDark ? 'bg-gray-800 border-gray-600 text-white placeholder-gray-500' : 'bg-white border-gray-300'} focus:ring-2 focus:ring-purple-500`}
              />
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

            <form onSubmit={handleSubmit}>
              <div className="p-6 min-h-[300px] max-h-[400px] overflow-y-auto">
                {renderTabContent()}
              </div>

              <div className={`p-4 border-t ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-200 bg-gray-50'} flex justify-end gap-3`}>
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
