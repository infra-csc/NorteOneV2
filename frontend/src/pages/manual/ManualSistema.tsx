import React, { useState, useMemo } from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  BookOpen,
  Search,
  LayoutDashboard,
  Package,
  Activity,
  Settings,
  BarChart3,
  Users,
  UserCog,
  Sparkles,
  Plane,
  Building2,
  Target,
  Database,
  ChevronRight,
  Lightbulb,
  AlertTriangle,
  Info,
  CheckCircle2,
  ArrowRight,
  Globe
} from 'lucide-react';

interface Section {
  id: string;
  title: string;
  icon: React.ElementType;
  keywords: string[];
}

const sections: Section[] = [
  { id: 'visao-geral', title: 'Visão Geral', icon: Globe, keywords: ['sistema', 'introdução', 'arquitetura', 'sobre', 'geral'] },
  { id: 'dashboard', title: 'Dashboard Principal', icon: LayoutDashboard, keywords: ['dashboard', 'kpi', 'filtros', 'indicadores', 'principal'] },
  { id: 'sku-mapping', title: 'Mapeamento de SKU', icon: Package, keywords: ['sku', 'mapeamento', 'mapear', 'evento externo', 'ativo', 'magento', 'grupo'] },
  { id: 'dash-isc', title: 'Dashboard ISC', icon: Activity, keywords: ['isc', 'saúde comercial', 'curva', 'rolling', 'ia 7/30', 'aceleração', 'marketing'] },
  { id: 'config-marketing', title: 'Configurações de Marketing', icon: Settings, keywords: ['configuração', 'pesos', 'benchmark', 'meta', 'parâmetros'] },
  { id: 'comparativo', title: 'Comparativo de Eventos', icon: BarChart3, keywords: ['comparativo', 'comparação', 'eventos', 'análise'] },
  { id: 'usuarios', title: 'Gestão de Usuários', icon: UserCog, keywords: ['usuário', 'permissão', 'perfil', 'acesso', 'módulo'] },
  { id: 'nori', title: 'Nori - Assistente IA', icon: Sparkles, keywords: ['nori', 'assistente', 'ia', 'voz', 'inteligência artificial', 'chat'] },
  { id: 'cotacoes', title: 'Cotações e Importação', icon: Plane, keywords: ['cotação', 'importação', 'câmbio', 'fornecedor'] },
  { id: 'centros-custo', title: 'Centros de Custo', icon: Building2, keywords: ['centro', 'custo', 'departamento'] },
  { id: 'categorias-atletas', title: 'Categorias de Atletas', icon: Target, keywords: ['categoria', 'atleta', 'inscrição', 'modalidade'] },
  { id: 'dados-consolidados', title: 'Dados Consolidados', icon: Database, keywords: ['dados', 'consolidado', 'snapshot', 'cache', 'manutenção'] },
];

const TipBox: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return (
    <div className={`flex gap-3 p-4 rounded-xl border ${isDark ? 'bg-blue-900/20 border-blue-700/30 text-blue-300' : 'bg-blue-50 border-blue-200 text-blue-800'}`}>
      <Lightbulb className="w-5 h-5 mt-0.5 flex-shrink-0" />
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
};

const AlertBox: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return (
    <div className={`flex gap-3 p-4 rounded-xl border ${isDark ? 'bg-amber-900/20 border-amber-700/30 text-amber-300' : 'bg-amber-50 border-amber-200 text-amber-800'}`}>
      <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0" />
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
};

const InfoBox: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return (
    <div className={`flex gap-3 p-4 rounded-xl border ${isDark ? 'bg-purple-900/20 border-purple-700/30 text-purple-300' : 'bg-purple-50 border-purple-200 text-purple-800'}`}>
      <Info className="w-5 h-5 mt-0.5 flex-shrink-0" />
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
};

const Step: React.FC<{ number: number; title: string; children: React.ReactNode }> = ({ number, title, children }) => {
  const { isDark } = useTheme();
  return (
    <div className="flex gap-4 mb-4">
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${isDark ? 'bg-indigo-600 text-white' : 'bg-indigo-500 text-white'}`}>
        {number}
      </div>
      <div className="flex-1">
        <h4 className={`font-semibold mb-1 ${isDark ? 'text-white' : 'text-gray-900'}`}>{title}</h4>
        <div className={`text-sm leading-relaxed ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>{children}</div>
      </div>
    </div>
  );
};

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return <h3 className={`text-lg font-bold mb-4 ${isDark ? 'text-white' : 'text-gray-900'}`}>{children}</h3>;
};

const SubTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return <h4 className={`text-base font-semibold mb-2 mt-6 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>{children}</h4>;
};

const Paragraph: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return <p className={`text-sm leading-relaxed mb-4 ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>{children}</p>;
};

const FormulaBox: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isDark } = useTheme();
  return (
    <div className={`p-4 rounded-xl font-mono text-sm mb-4 ${isDark ? 'bg-gray-900 border border-gray-700 text-green-400' : 'bg-gray-100 border border-gray-300 text-gray-800'}`}>
      {children}
    </div>
  );
};

const StatusBadge: React.FC<{ color: 'green' | 'yellow' | 'red'; label: string; description: string }> = ({ color, label, description }) => {
  const { isDark } = useTheme();
  const colors = {
    green: isDark ? 'bg-green-900/30 border-green-700/50 text-green-400' : 'bg-green-50 border-green-200 text-green-700',
    yellow: isDark ? 'bg-yellow-900/30 border-yellow-700/50 text-yellow-400' : 'bg-yellow-50 border-yellow-200 text-yellow-700',
    red: isDark ? 'bg-red-900/30 border-red-700/50 text-red-400' : 'bg-red-50 border-red-200 text-red-700',
  };
  return (
    <div className={`p-3 rounded-lg border ${colors[color]}`}>
      <span className="font-semibold">{label}</span>
      <span className={`ml-2 text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{description}</span>
    </div>
  );
};

const VisaoGeralContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Visão Geral do Sistema</SectionTitle>
    <Paragraph>
      O DW Financeiro - Eventos é uma plataforma de gestão e Data Warehouse desenvolvida para monitoramento
      de vendas de ingressos, análise de saúde comercial de eventos esportivos e tomada de decisão baseada em dados.
    </Paragraph>
    <SubTitle>Principais Módulos</SubTitle>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {[
        { icon: LayoutDashboard, label: 'Dashboard', desc: 'Visão consolidada de KPIs e indicadores' },
        { icon: Activity, label: 'Marketing / ISC', desc: 'Monitoramento da saúde comercial dos eventos' },
        { icon: Package, label: 'Mapeamento SKU', desc: 'Vinculação de eventos internos e externos' },
        { icon: Sparkles, label: 'Nori (IA)', desc: 'Assistente inteligente para análise e recomendações' },
        { icon: Plane, label: 'Cotações', desc: 'Gestão de cotações e importações' },
        { icon: UserCog, label: 'Administração', desc: 'Usuários, permissões e dados consolidados' },
      ].map((item) => (
        <ModuleCard key={item.label} icon={item.icon} label={item.label} desc={item.desc} />
      ))}
    </div>
    <SubTitle>Fontes de Dados</SubTitle>
    <Paragraph>
      O sistema se conecta a duas bases de dados externas para obter informações de vendas em tempo real:
    </Paragraph>
    <ul className="list-disc list-inside text-sm space-y-1 text-gray-600 dark:text-gray-300 mb-4">
      <li><strong>Ativo</strong> — Sistema de gestão de eventos e ingressos (acesso via SSH Tunnel)</li>
      <li><strong>Magento</strong> — Plataforma de e-commerce para vendas online</li>
    </ul>
    <TipBox>
      Os dados das bases externas são sincronizados automaticamente pelo sistema através de um processo de cache warming
      que roda em segundo plano, garantindo que os dashboards sempre exibam informações atualizadas.
    </TipBox>
  </div>
);

const ModuleCard: React.FC<{ icon: React.ElementType; label: string; desc: string }> = ({ icon: Icon, label, desc }) => {
  const { isDark } = useTheme();
  return (
    <div className={`flex items-start gap-3 p-3 rounded-lg ${isDark ? 'bg-gray-800/50' : 'bg-gray-50'}`}>
      <Icon className={`w-5 h-5 mt-0.5 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
      <div>
        <div className={`text-sm font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{label}</div>
        <div className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{desc}</div>
      </div>
    </div>
  );
};

const DashboardContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Dashboard Principal</SectionTitle>
    <Paragraph>
      O Dashboard é a página inicial do sistema e oferece uma visão consolidada dos principais indicadores
      de performance. Ele reúne KPIs financeiros e de vendas em cards visuais de fácil leitura.
    </Paragraph>
    <SubTitle>Funcionalidades</SubTitle>
    <Step number={1} title="Filtros de Período">
      Use os filtros no topo da página para selecionar o período de análise desejado. Os KPIs se atualizam automaticamente.
    </Step>
    <Step number={2} title="Cards de KPI">
      Cada card exibe um indicador específico (receita, vendas, ticket médio, etc.) com comparativos em relação ao período anterior.
    </Step>
    <Step number={3} title="Gráficos">
      Abaixo dos cards, gráficos de barras e linhas mostram a evolução dos indicadores ao longo do tempo.
    </Step>
    <TipBox>
      Passe o mouse sobre os gráficos para ver detalhes de cada ponto. Os tooltips mostram valores exatos e comparativos.
    </TipBox>
  </div>
);

const SkuMappingContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Mapeamento de SKU</SectionTitle>
    <Paragraph>
      O mapeamento de SKU é o processo que conecta os códigos internos dos projetos (SKUs) aos IDs dos eventos
      nas plataformas externas (Ativo e Magento). Essa vinculação é essencial para que o sistema consiga
      consolidar dados de vendas de múltiplas fontes para um mesmo evento.
    </Paragraph>

    <SubTitle>O que é um SKU?</SubTitle>
    <Paragraph>
      SKU (Stock Keeping Unit) é um código único que identifica um evento internamente. Exemplo: <code className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-sm font-mono">CE25SP</code> pode representar
      o "Circuito das Estações 2025 - São Paulo". O sistema usa esse código para agrupar dados de diferentes plataformas.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Admin</strong> → <strong>Mapeamento SKUs</strong>.
    </Paragraph>

    <SubTitle>Abas da página</SubTitle>
    <Paragraph>A página possui três abas principais:</Paragraph>

    <InfoBox>
      <strong>1. Mapeamentos</strong> — Visualize e gerencie todos os mapeamentos existentes, agrupados por Grupo de Evento.
      Filtre por fonte (Ativo/Magento), ano, grupo e status. Exporte os dados para CSV.
    </InfoBox>
    <div className="h-2" />
    <InfoBox>
      <strong>2. Eventos Externos</strong> — Descubra novos eventos nas bases externas que ainda não foram mapeados.
      O sistema sugere automaticamente mapeamentos baseados em eventos de anos anteriores.
    </InfoBox>
    <div className="h-2" />
    <InfoBox>
      <strong>3. Grupos de Evento</strong> — Gerencie os grupos que agrupam múltiplos SKUs sob um mesmo nome
      (ex: "Circuito das Estações - SP" pode incluir eventos de vários anos).
    </InfoBox>

    <SubTitle>Processo de Descoberta Automática</SubTitle>
    <Step number={1} title="Acesse a aba 'Eventos Externos'">
      Ao clicar nesta aba, o sistema automaticamente escaneia as bases do Ativo e do Magento em busca de novos eventos.
    </Step>
    <Step number={2} title="Revise as sugestões">
      Os resultados aparecem em duas seções: <strong>Sugeridos</strong> (matches encontrados automaticamente baseados em
      nomes e SKUs normalizados de anos anteriores) e <strong>Sem Match</strong> (eventos que precisam de mapeamento manual).
    </Step>
    <Step number={3} title="Ajuste se necessário">
      Para sugestões automáticas, o sistema pré-preenche o SKU e o Grupo sugeridos. Você pode editar esses campos antes de salvar.
      Para eventos sem match, preencha manualmente o Grupo e o SKU.
    </Step>
    <Step number={4} title="Salve os mapeamentos">
      Selecione os eventos desejados e clique em "Salvar Mapeamentos". O sistema criará os registros e invalidará
      automaticamente os snapshots de dados para garantir a consistência das análises.
    </Step>

    <SubTitle>Criação Manual de Mapeamento</SubTitle>
    <Step number={1} title="Clique em 'Novo Mapeamento'">
      Na aba Mapeamentos, use o botão para abrir o formulário de criação.
    </Step>
    <Step number={2} title="Preencha os campos">
      Informe o SKU interno, selecione a fonte (Ativo ou Magento), o ID externo do evento na plataforma, o ano e o Grupo de Evento.
    </Step>
    <Step number={3} title="Salve">
      Após salvar, o sistema vincula automaticamente as vendas desse evento externo ao SKU interno.
    </Step>

    <AlertBox>
      Ao atualizar um mapeamento (como mudar a data do evento), o sistema invalida automaticamente os snapshots
      históricos relacionados. Isso força um recálculo dos dados para manter a consistência das análises.
    </AlertBox>
  </div>
);

const DashISCContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Dashboard ISC (Índice de Saúde Comercial)</SectionTitle>
    <Paragraph>
      O ISC é um indicador proprietário que mede a saúde comercial de cada evento. Ele combina três métricas
      de vendas para gerar um número que indica se o evento está acelerando, estável ou desacelerando comercialmente.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Marketing Performance</strong> → <strong>Dashboard ISC</strong>.
    </Paragraph>

    <SubTitle>Visão da Torre de Controle</SubTitle>
    <Paragraph>
      O dashboard apresenta uma visão tipo "Torre de Controle" com todos os eventos ativos, categorizados
      por zonas de saúde comercial. Cada evento é representado por um card com o valor do ISC e as métricas
      que o compõem.
    </Paragraph>

    <SubTitle>Componentes do ISC</SubTitle>
    <Paragraph>O ISC é composto por três métricas principais:</Paragraph>

    <InfoBox>
      <strong>1. Curva D-% (Progresso de Vendas)</strong><br />
      Compara o percentual de vendas realizadas versus o esperado para o dia atual em relação à data do evento.
      Usa a curva de vendas do ano anterior como referência. Se não houver dados históricos, utiliza um modelo linear de 90 dias.
    </InfoBox>
    <div className="h-2" />
    <FormulaBox>
      Curva D-% = Vendas Realizadas (%) / Vendas Esperadas (%)
    </FormulaBox>

    <InfoBox>
      <strong>2. Rolling 14d (Velocidade de Vendas)</strong><br />
      Mede se a velocidade de vendas dos últimos 14 dias está atingindo o ritmo esperado definido pela curva histórica.
      Um valor acima de 1.0 significa que as vendas nas últimas 2 semanas estão acima do esperado.
    </InfoBox>
    <div className="h-2" />
    <FormulaBox>
      Rolling 14d = Soma Vendas (últimos 14 dias) / Vendas Esperadas (últimos 14 dias)
    </FormulaBox>

    <InfoBox>
      <strong>3. IA 7/30 (Índice de Aceleração)</strong><br />
      Compara a média de vendas dos últimos 7 dias com a média dos últimos 30 dias.
      Se a última semana está vendendo mais que a média do mês, o índice fica acima de 1.0, indicando aceleração.
    </InfoBox>
    <div className="h-2" />
    <FormulaBox>
      IA 7/30 = Média Vendas (últimos 7 dias) / Média Vendas (últimos 30 dias)
    </FormulaBox>

    <SubTitle>Fórmula Final do ISC</SubTitle>
    <Paragraph>
      Os três componentes são combinados com pesos configuráveis para gerar o ISC final.
      Cada componente tem seu desvio em relação a 1.0 limitado (cap) para evitar que valores extremos distorçam o índice.
    </Paragraph>
    <FormulaBox>
      ISC = 1.0 + (Peso_Curva × ΔCurva + Peso_Rolling × ΔRolling + Peso_IA × ΔIA)
    </FormulaBox>
    <Paragraph>
      Pesos padrão: Curva D-% = 40%, Rolling 14d = 40%, IA 7/30 = 20%. Cap padrão: ±0.30 por componente.
    </Paragraph>

    <SubTitle>Zonas de Status</SubTitle>
    <div className="space-y-2">
      <StatusBadge color="green" label="🟢 Acelerando (ISC > 1.10)" description="Evento forte. Considerar aumento de preço." />
      <StatusBadge color="yellow" label="🟡 Estável (0.90 ≤ ISC ≤ 1.10)" description="Monitorar e ajustar comunicação." />
      <StatusBadge color="red" label="🔴 Desacelerando (ISC < 0.90)" description="Evento fraco. Abrir janela para ação promocional (se D- > 40 dias)." />
    </div>

    <TipBox>
      A regra D-40: ações promocionais só são sugeridas quando faltam mais de 40 dias para o evento.
      Isso evita promoções próximas demais da data do evento, que poderiam prejudicar a percepção de valor.
    </TipBox>

    <SubTitle>Detalhes do Evento</SubTitle>
    <Paragraph>
      Clique em qualquer evento no dashboard para ver uma página detalhada com gráficos de evolução de vendas,
      curvas históricas comparativas, simulador de preços e lista de ações comerciais recomendadas pela Nori.
    </Paragraph>
  </div>
);

const ConfigMarketingContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Configurações de Marketing</SectionTitle>
    <Paragraph>
      Nesta tela você ajusta os parâmetros que controlam o cálculo do ISC e define benchmarks e metas para os eventos.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Marketing Performance</strong> → <strong>Configurações</strong>.
    </Paragraph>

    <SubTitle>Parâmetros do ISC</SubTitle>
    <Step number={1} title="Pesos dos Componentes">
      Ajuste os pesos de cada componente do ISC (Curva D-%, Rolling 14d, IA 7/30).
      A soma dos pesos deve ser igual a 100%. O sistema valida automaticamente e exibe um indicador visual.
    </Step>
    <Step number={2} title="Cap (Limite de Desvio)">
      Define o limite máximo de desvio de cada componente em relação a 1.0. O padrão é ±0.30.
      Um cap maior permite que eventos com performance muito acima ou abaixo da média tenham ISC mais extremo.
    </Step>
    <Step number={3} title="Limiares de Status">
      Configure os limites que definem as zonas verde (aceleração), amarela (estável) e vermelha (desaceleração).
      Valores padrão: verde acima de 1.10 e vermelho abaixo de 0.90.
    </Step>

    <SubTitle>Benchmarks e Metas</SubTitle>
    <Paragraph>
      Na aba de Benchmarks, defina metas de vendas e receita para cada evento. Esses valores são usados
      como referência nos cálculos de progresso e nas análises comparativas.
    </Paragraph>

    <AlertBox>
      Alterar os pesos do ISC afeta imediatamente todos os cálculos em tempo real. Antes de fazer mudanças,
      considere o impacto nas análises em andamento. Use o botão "Restaurar Padrão" para voltar aos valores originais.
    </AlertBox>
  </div>
);

const ComparativoContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Comparativo de Eventos</SectionTitle>
    <Paragraph>
      A ferramenta de comparativo permite analisar a performance de dois ou mais eventos lado a lado,
      facilitando a identificação de padrões e a tomada de decisão.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Marketing Performance</strong> → <strong>Comparativo</strong>.
    </Paragraph>

    <SubTitle>Como usar</SubTitle>
    <Step number={1} title="Selecione os eventos">
      Use os seletores no topo da página para escolher os eventos que deseja comparar.
    </Step>
    <Step number={2} title="Analise os gráficos">
      O sistema exibe gráficos sobrepostos das curvas de vendas, permitindo comparar ritmo, volume e tendências.
    </Step>
    <Step number={3} title="Compare métricas">
      Abaixo dos gráficos, uma tabela comparativa mostra métricas-chave como ISC, total de vendas,
      ticket médio e progresso de meta para cada evento selecionado.
    </Step>

    <TipBox>
      Compare eventos da mesma categoria ou do mesmo circuito em anos diferentes para identificar
      tendências de crescimento ou declínio.
    </TipBox>
  </div>
);

const UsuariosContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Gestão de Usuários e Permissões</SectionTitle>
    <Paragraph>
      O sistema possui um controle granular de acesso, onde cada usuário é associado a um Perfil de Acesso
      que define quais módulos ele pode visualizar e editar.
    </Paragraph>

    <SubTitle>Gerenciar Usuários</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Admin</strong> → <strong>Usuários</strong>.
    </Paragraph>
    <Step number={1} title="Criar novo usuário">
      Clique em "Novo Usuário" e preencha nome, email, senha inicial e selecione o perfil de acesso.
    </Step>
    <Step number={2} title="Editar usuário">
      Na listagem, clique no ícone de edição para alterar dados do usuário ou mudar seu perfil de acesso.
    </Step>
    <Step number={3} title="Desativar usuário">
      Usuários podem ser desativados sem serem excluídos, mantendo o histórico de ações.
    </Step>

    <SubTitle>Perfis de Acesso</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Admin</strong> → <strong>Perfis de Acesso</strong>.
    </Paragraph>
    <Paragraph>
      Cada perfil define permissões por módulo. Para cada módulo, é possível definir:
    </Paragraph>
    <ul className="list-disc list-inside text-sm space-y-1 text-gray-600 dark:text-gray-300 mb-4">
      <li><strong>Visualizar</strong> — Permite acessar e ver o conteúdo do módulo</li>
      <li><strong>Editar</strong> — Permite criar, alterar e excluir dados no módulo</li>
    </ul>

    <SubTitle>Módulos Disponíveis</SubTitle>
    <Paragraph>Os módulos que podem ser controlados por permissão incluem:</Paragraph>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
      {[
        'Dashboard', 'Nori (Assistente)', 'Categorias Atletas', 'Eventos',
        'Marketing Dashboard', 'Marketing Comparativo', 'Marketing Configurações',
        'Cotações e Importação', 'Dados Consolidados', 'Mapeamento SKUs',
        'Usuários', 'Perfis de Acesso', 'Centros de Custo', 'Monitoramento'
      ].map((mod) => (
        <div key={mod} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          <CheckCircle2 className="w-4 h-4 text-green-500" />
          {mod}
        </div>
      ))}
    </div>

    <SubTitle>Monitoramento de Atividades</SubTitle>
    <Paragraph>
      Em <strong>Admin</strong> → <strong>Monitoramento</strong>, acompanhe as atividades dos usuários no sistema,
      incluindo logins, ações realizadas e horários de acesso.
    </Paragraph>
  </div>
);

const NoriContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Nori - Assistente IA</SectionTitle>
    <Paragraph>
      A Nori é a assistente virtual do sistema, alimentada por inteligência artificial. Ela analisa dados de marketing,
      sugere ações comerciais e ajuda na tomada de decisões estratégicas.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Há duas formas de acessar a Nori:
    </Paragraph>
    <ul className="list-disc list-inside text-sm space-y-1 text-gray-600 dark:text-gray-300 mb-4">
      <li>Pelo menu lateral: <strong>Nori - Assistente</strong></li>
      <li>Pelo botão flutuante no canto inferior direito da tela (disponível em qualquer página)</li>
    </ul>

    <SubTitle>O que a Nori pode fazer</SubTitle>
    <Step number={1} title="Análise de Eventos">
      Pergunte sobre o desempenho de um evento específico. A Nori consulta os dados do ISC e gera uma análise
      detalhada com recomendações de ação.
    </Step>
    <Step number={2} title="Recomendações Proativas">
      A Nori identifica automaticamente eventos que precisam de atenção e sugere ações como:
      ajuste de preço, abertura de promoção ou intensificação de comunicação.
    </Step>
    <Step number={3} title="Criação de Tarefas">
      A Nori pode criar tarefas de gestão e mencionar membros específicos da equipe,
      facilitando o acompanhamento das ações recomendadas.
    </Step>
    <Step number={4} title="Interação por Voz">
      Use o recurso de voz para falar com a Nori. Ela suporta reconhecimento de fala (Speech-to-Text)
      e pode responder por áudio (Text-to-Speech).
    </Step>

    <TipBox>
      Para melhores resultados, seja específico nas perguntas. Em vez de "como estão as vendas?", pergunte
      "como está o ISC do Circuito das Estações SP 2025?".
    </TipBox>
  </div>
);

const CotacoesContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Cotações e Importação</SectionTitle>
    <Paragraph>
      O módulo de Cotações e Importação gerencia o processo de cotação com fornecedores e controle de importações
      relacionadas aos eventos.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Cotação & Importação</strong>.
    </Paragraph>

    <SubTitle>Funcionalidades</SubTitle>
    <Step number={1} title="Registro de Cotações">
      Cadastre novas cotações informando fornecedor, itens, quantidades e valores.
    </Step>
    <Step number={2} title="Comparação de Propostas">
      Compare cotações de diferentes fornecedores para o mesmo item ou serviço.
    </Step>
    <Step number={3} title="Acompanhamento">
      Acompanhe o status de cada cotação: pendente, aprovada, em andamento ou concluída.
    </Step>

    <TipBox>
      Mantenha todas as cotações registradas no sistema, mesmo as não aprovadas, para ter um histórico
      completo de negociações com fornecedores.
    </TipBox>
  </div>
);

const CentrosCustoContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Centros de Custo</SectionTitle>
    <Paragraph>
      Os Centros de Custo representam as áreas ou departamentos responsáveis pelos gastos associados aos eventos.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Admin</strong> → <strong>Centros de Custo</strong>.
    </Paragraph>

    <SubTitle>Manutenção</SubTitle>
    <Step number={1} title="Cadastrar novo Centro de Custo">
      Clique em "Novo Centro de Custo" e preencha o nome e a descrição.
    </Step>
    <Step number={2} title="Editar">
      Na listagem, use o botão de edição para atualizar as informações.
    </Step>
    <Step number={3} title="Desativar">
      Centros de custo que não estão mais em uso podem ser desativados para evitar seleção acidental em novos cadastros.
    </Step>

    <AlertBox>
      Não exclua centros de custo que possuem registros vinculados. Prefira desativá-los para manter a integridade dos dados históricos.
    </AlertBox>
  </div>
);

const CategoriasAtletasContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Categorias de Atletas</SectionTitle>
    <Paragraph>
      As Categorias de Atletas definem os tipos de inscrição e modalidades disponíveis nos eventos esportivos.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Cadastros</strong> → <strong>Categorias Atletas</strong>.
    </Paragraph>

    <SubTitle>Manutenção</SubTitle>
    <Step number={1} title="Cadastrar nova categoria">
      Clique em "Nova Categoria" e defina o nome, a modalidade e os detalhes da categoria.
    </Step>
    <Step number={2} title="Associar a eventos">
      As categorias cadastradas ficam disponíveis para associação nos cadastros de eventos.
    </Step>
    <Step number={3} title="Editar ou desativar">
      Atualize informações ou desative categorias que não serão mais utilizadas em novos eventos.
    </Step>
  </div>
);

const DadosConsolidadosContent: React.FC = () => (
  <div className="space-y-4">
    <SectionTitle>Dados Consolidados</SectionTitle>
    <Paragraph>
      A tela de Dados Consolidados é uma ferramenta administrativa para gerenciar os snapshots e caches
      que alimentam os dashboards e análises do sistema.
    </Paragraph>

    <SubTitle>Como acessar</SubTitle>
    <Paragraph>
      Acesse pelo menu lateral: <strong>Admin</strong> → <strong>Dados Consolidados</strong>.
    </Paragraph>

    <SubTitle>O que são Snapshots?</SubTitle>
    <Paragraph>
      Os snapshots são "fotografias" dos dados de vendas em um determinado momento. O sistema cria snapshots
      diários automaticamente para permitir análises históricas sem precisar consultar as bases externas repetidamente.
    </Paragraph>

    <SubTitle>Manutenção</SubTitle>
    <Step number={1} title="Verificar status dos dados">
      A tela mostra o status de cada snapshot: quando foi gerado, qual período cobre e se está atualizado.
    </Step>
    <Step number={2} title="Forçar recálculo">
      Se os dados parecerem desatualizados ou inconsistentes, você pode forçar um recálculo seletivo
      de snapshots específicos.
    </Step>
    <Step number={3} title="Limpar cache">
      Em casos extremos (como mudança de regra de negócio), é possível limpar caches específicos
      para forçar a regeneração completa dos dados.
    </Step>

    <AlertBox>
      Forçar o recálculo de todos os snapshots pode levar vários minutos, dependendo do volume de dados.
      Prefira recalcular apenas os eventos ou períodos necessários.
    </AlertBox>

    <TipBox>
      O sistema executa um "Cache Warmup" automático na inicialização e periodicamente durante o dia.
      Na maioria dos casos, não é necessário intervenção manual na tela de Dados Consolidados.
    </TipBox>
  </div>
);

const sectionContentMap: Record<string, React.FC> = {
  'visao-geral': VisaoGeralContent,
  'dashboard': DashboardContent,
  'sku-mapping': SkuMappingContent,
  'dash-isc': DashISCContent,
  'config-marketing': ConfigMarketingContent,
  'comparativo': ComparativoContent,
  'usuarios': UsuariosContent,
  'nori': NoriContent,
  'cotacoes': CotacoesContent,
  'centros-custo': CentrosCustoContent,
  'categorias-atletas': CategoriasAtletasContent,
  'dados-consolidados': DadosConsolidadosContent,
};

const ManualSistema: React.FC = () => {
  const { isDark } = useTheme();
  const [activeSection, setActiveSection] = useState('visao-geral');
  const [searchQuery, setSearchQuery] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const filteredSections = useMemo(() => {
    if (!searchQuery.trim()) return sections;
    const query = searchQuery.toLowerCase();
    return sections.filter(
      (s) =>
        s.title.toLowerCase().includes(query) ||
        s.keywords.some((k) => k.includes(query))
    );
  }, [searchQuery]);

  const ActiveContent = sectionContentMap[activeSection];

  return (
    <div className="min-h-screen relative">
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className={`absolute top-1/4 left-1/4 w-96 h-96 rounded-full blur-3xl opacity-20 ${isDark ? 'bg-blue-600' : 'bg-blue-300'}`} />
        <div className={`absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full blur-3xl opacity-20 ${isDark ? 'bg-purple-600' : 'bg-purple-300'}`} />
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2.5 rounded-xl ${isDark ? 'bg-indigo-600/20' : 'bg-indigo-100'}`}>
              <BookOpen className={`w-6 h-6 ${isDark ? 'text-indigo-400' : 'text-indigo-600'}`} />
            </div>
            <div>
              <h1 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-gray-900'}`}>
                Manual do Sistema
              </h1>
              <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Guia completo de funcionalidades e manutenção
              </p>
            </div>
          </div>

          <div className="relative mt-4 max-w-md">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
            <input
              type="text"
              placeholder="Buscar no manual..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={`w-full pl-10 pr-4 py-2.5 rounded-xl border text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                isDark
                  ? 'bg-gray-800/60 border-gray-700 text-white placeholder-gray-500'
                  : 'bg-white/80 border-gray-200 text-gray-900 placeholder-gray-400'
              }`}
            />
          </div>
        </div>

        <div className="flex gap-6">
          <div className={`hidden lg:block w-64 flex-shrink-0`}>
            <div className={`sticky top-6 rounded-2xl border p-3 backdrop-blur-xl ${
              isDark ? 'bg-gray-800/60 border-gray-700/50' : 'bg-white/80 border-gray-200'
            }`}>
              <nav className="space-y-1">
                {filteredSections.map((section) => {
                  const Icon = section.icon;
                  const isActive = activeSection === section.id;
                  return (
                    <button
                      key={section.id}
                      onClick={() => {
                        setActiveSection(section.id);
                        setSearchQuery('');
                      }}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-all text-left ${
                        isActive
                          ? isDark
                            ? 'bg-indigo-600/20 text-indigo-400 font-medium'
                            : 'bg-indigo-50 text-indigo-700 font-medium'
                          : isDark
                            ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
                            : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }`}
                    >
                      <Icon className="w-4 h-4 flex-shrink-0" />
                      <span className="truncate">{section.title}</span>
                      {isActive && <ChevronRight className="w-3 h-3 ml-auto flex-shrink-0" />}
                    </button>
                  );
                })}
              </nav>
            </div>
          </div>

          <div className="flex-1 min-w-0">
            <div className="lg:hidden mb-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all ${
                  isDark
                    ? 'bg-gray-800/60 border-gray-700 text-gray-300 hover:bg-gray-700/60'
                    : 'bg-white/80 border-gray-200 text-gray-700 hover:bg-gray-50'
                }`}
              >
                <BookOpen className="w-4 h-4" />
                Seções
                <ChevronRight className={`w-3 h-3 transition-transform ${sidebarOpen ? 'rotate-90' : ''}`} />
              </button>

              {sidebarOpen && (
                <div className={`mt-2 rounded-xl border p-2 backdrop-blur-xl ${
                  isDark ? 'bg-gray-800/80 border-gray-700/50' : 'bg-white/90 border-gray-200'
                }`}>
                  <div className="grid grid-cols-2 gap-1">
                    {filteredSections.map((section) => {
                      const Icon = section.icon;
                      const isActive = activeSection === section.id;
                      return (
                        <button
                          key={section.id}
                          onClick={() => {
                            setActiveSection(section.id);
                            setSidebarOpen(false);
                            setSearchQuery('');
                          }}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-all text-left ${
                            isActive
                              ? isDark
                                ? 'bg-indigo-600/20 text-indigo-400 font-medium'
                                : 'bg-indigo-50 text-indigo-700 font-medium'
                              : isDark
                                ? 'text-gray-400 hover:text-gray-200 hover:bg-gray-700/50'
                                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                          }`}
                        >
                          <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                          <span className="truncate">{section.title}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <div className={`rounded-2xl border p-6 sm:p-8 backdrop-blur-xl ${
              isDark ? 'bg-gray-800/60 border-gray-700/50' : 'bg-white/80 border-gray-200'
            }`}>
              {ActiveContent ? <ActiveContent /> : (
                <div className={`text-center py-12 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                  <BookOpen className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Selecione uma seção para visualizar</p>
                </div>
              )}
            </div>

            {filteredSections.length > 1 && (
              <div className="flex justify-between mt-4">
                {(() => {
                  const currentIndex = filteredSections.findIndex((s) => s.id === activeSection);
                  const prevSection = currentIndex > 0 ? filteredSections[currentIndex - 1] : null;
                  const nextSection = currentIndex < filteredSections.length - 1 ? filteredSections[currentIndex + 1] : null;
                  return (
                    <>
                      {prevSection ? (
                        <button
                          onClick={() => setActiveSection(prevSection.id)}
                          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm transition-all ${
                            isDark
                              ? 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                              : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                          }`}
                        >
                          <ArrowRight className="w-4 h-4 rotate-180" />
                          {prevSection.title}
                        </button>
                      ) : <div />}
                      {nextSection ? (
                        <button
                          onClick={() => setActiveSection(nextSection.id)}
                          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm transition-all ${
                            isDark
                              ? 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                              : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                          }`}
                        >
                          {nextSection.title}
                          <ArrowRight className="w-4 h-4" />
                        </button>
                      ) : <div />}
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ManualSistema;
