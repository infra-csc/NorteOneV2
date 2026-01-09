import { 
  EventGoal, 
  BenchmarkCurve, 
  ISCParameters, 
  EventCategory, 
  AlertConfig 
} from '../types/marketingSettings';

export const mockEventGoals: EventGoal[] = [
  {
    id: '1',
    eventId: '1',
    eventName: 'São Paulo Marathon 30K',
    salesGoal: 12000,
    revenueGoal: 2278800,
    conversionTarget: 80,
    averageTicketTarget: 189.90,
    createdAt: '2024-01-15',
    updatedAt: '2024-01-20'
  },
  {
    id: '2',
    eventId: '2',
    eventName: 'EcoRun Floripa',
    salesGoal: 2500,
    revenueGoal: 324750,
    conversionTarget: 83,
    averageTicketTarget: 129.90,
    createdAt: '2024-01-15',
    updatedAt: '2024-01-18'
  },
  {
    id: '3',
    eventId: '3',
    eventName: 'Night Run RJ',
    salesGoal: 4000,
    revenueGoal: 599600,
    conversionTarget: 80,
    averageTicketTarget: 149.90,
    createdAt: '2024-01-16',
    updatedAt: '2024-01-16'
  },
  {
    id: '4',
    eventId: '4',
    eventName: 'Trail Serra Gaúcha',
    salesGoal: 1200,
    revenueGoal: 299880,
    conversionTarget: 80,
    averageTicketTarget: 249.90,
    createdAt: '2024-01-17',
    updatedAt: '2024-01-17'
  },
  {
    id: '5',
    eventId: '5',
    eventName: 'Meia Maratona BH',
    salesGoal: 6500,
    revenueGoal: 1104350,
    conversionTarget: 81,
    averageTicketTarget: 169.90,
    createdAt: '2024-01-18',
    updatedAt: '2024-01-18'
  }
];

export const mockBenchmarkCurves: BenchmarkCurve[] = [
  {
    id: '1',
    name: 'Curva Agressiva',
    description: 'Para eventos com alta demanda e histórico de vendas rápidas',
    type: 'aggressive',
    dataPoints: [
      { dMinus: 90, expectedPercentage: 20 },
      { dMinus: 75, expectedPercentage: 35 },
      { dMinus: 60, expectedPercentage: 50 },
      { dMinus: 45, expectedPercentage: 70 },
      { dMinus: 30, expectedPercentage: 85 },
      { dMinus: 15, expectedPercentage: 95 },
      { dMinus: 0, expectedPercentage: 100 }
    ],
    isDefault: false,
    createdAt: '2024-01-01'
  },
  {
    id: '2',
    name: 'Curva Moderada',
    description: 'Para eventos com comportamento de vendas padrão',
    type: 'moderate',
    dataPoints: [
      { dMinus: 90, expectedPercentage: 15 },
      { dMinus: 75, expectedPercentage: 25 },
      { dMinus: 60, expectedPercentage: 40 },
      { dMinus: 45, expectedPercentage: 55 },
      { dMinus: 30, expectedPercentage: 75 },
      { dMinus: 15, expectedPercentage: 90 },
      { dMinus: 0, expectedPercentage: 100 }
    ],
    isDefault: true,
    createdAt: '2024-01-01'
  },
  {
    id: '3',
    name: 'Curva Conservadora',
    description: 'Para eventos novos ou com histórico de vendas mais lento',
    type: 'conservative',
    dataPoints: [
      { dMinus: 90, expectedPercentage: 10 },
      { dMinus: 75, expectedPercentage: 18 },
      { dMinus: 60, expectedPercentage: 30 },
      { dMinus: 45, expectedPercentage: 45 },
      { dMinus: 30, expectedPercentage: 65 },
      { dMinus: 15, expectedPercentage: 85 },
      { dMinus: 0, expectedPercentage: 100 }
    ],
    isDefault: false,
    createdAt: '2024-01-01'
  }
];

export const defaultISCParameters: ISCParameters = {
  ia730Weight: 33.33,
  curvaDWeight: 33.33,
  rolling14dWeight: 33.34,
  greenThreshold: 1.10,
  yellowThreshold: 0.90,
  criticalWindowStart: 45,
  criticalWindowEnd: 40,
  promotionDeadline: 40
};

export const mockEventCategories: EventCategory[] = [
  {
    id: '1',
    name: 'Maratona',
    description: 'Corridas de longa distância (42km)',
    color: '#ef4444',
    icon: 'trophy',
    defaultCapacity: 15000,
    defaultTicketPrice: 189.90,
    isActive: true,
    eventCount: 3
  },
  {
    id: '2',
    name: 'Meia Maratona',
    description: 'Corridas de 21km',
    color: '#f97316',
    icon: 'medal',
    defaultCapacity: 8000,
    defaultTicketPrice: 169.90,
    isActive: true,
    eventCount: 5
  },
  {
    id: '3',
    name: 'Trail',
    description: 'Corridas em trilhas e terreno irregular',
    color: '#22c55e',
    icon: 'mountain',
    defaultCapacity: 1500,
    defaultTicketPrice: 249.90,
    isActive: true,
    eventCount: 2
  },
  {
    id: '4',
    name: 'Night Run',
    description: 'Corridas noturnas em ambiente urbano',
    color: '#6366f1',
    icon: 'moon',
    defaultCapacity: 5000,
    defaultTicketPrice: 149.90,
    isActive: true,
    eventCount: 4
  },
  {
    id: '5',
    name: 'Color Run',
    description: 'Corridas recreativas com tintas coloridas',
    color: '#ec4899',
    icon: 'palette',
    defaultCapacity: 10000,
    defaultTicketPrice: 99.90,
    isActive: true,
    eventCount: 2
  },
  {
    id: '6',
    name: 'Beach Run',
    description: 'Corridas na areia da praia',
    color: '#0ea5e9',
    icon: 'sun',
    defaultCapacity: 2500,
    defaultTicketPrice: 139.90,
    isActive: true,
    eventCount: 1
  },
  {
    id: '7',
    name: 'Corrida Popular',
    description: 'Corridas de curta distância para iniciantes',
    color: '#84cc16',
    icon: 'users',
    defaultCapacity: 4000,
    defaultTicketPrice: 79.90,
    isActive: true,
    eventCount: 6
  },
  {
    id: '8',
    name: 'Corrida Ecológica',
    description: 'Eventos com foco em sustentabilidade',
    color: '#10b981',
    icon: 'leaf',
    defaultCapacity: 3000,
    defaultTicketPrice: 129.90,
    isActive: true,
    eventCount: 1
  }
];

export const mockAlertConfigs: AlertConfig[] = [
  {
    id: '1',
    name: 'ISC Crítico',
    description: 'Alerta quando o ISC de um evento cai abaixo de 0.85',
    condition: {
      type: 'isc_below',
      value: 0.85,
      comparison: 'less_than'
    },
    channels: [
      { type: 'email', target: 'marketing@empresa.com', isEnabled: true },
      { type: 'slack', target: '#marketing-alerts', isEnabled: true }
    ],
    isActive: true,
    createdAt: '2024-01-10'
  },
  {
    id: '2',
    name: 'Janela Crítica',
    description: 'Alerta quando um evento entra na janela D-45 a D-40',
    condition: {
      type: 'critical_window',
      value: 45,
      comparison: 'less_than'
    },
    channels: [
      { type: 'email', target: 'gerente@empresa.com', isEnabled: true },
      { type: 'push', target: 'all', isEnabled: true }
    ],
    isActive: true,
    createdAt: '2024-01-10'
  },
  {
    id: '3',
    name: 'Meta de Vendas em Risco',
    description: 'Alerta quando vendas estão 20% abaixo do esperado',
    condition: {
      type: 'sales_below',
      value: 80,
      comparison: 'less_than'
    },
    channels: [
      { type: 'email', target: 'vendas@empresa.com', isEnabled: true }
    ],
    isActive: true,
    createdAt: '2024-01-12'
  },
  {
    id: '4',
    name: 'ISC Excelente',
    description: 'Notificação quando ISC ultrapassa 1.20',
    condition: {
      type: 'isc_above',
      value: 1.20,
      comparison: 'greater_than'
    },
    channels: [
      { type: 'slack', target: '#conquistas', isEnabled: true }
    ],
    isActive: false,
    createdAt: '2024-01-15'
  },
  {
    id: '5',
    name: 'Evento Próximo',
    description: 'Alerta quando evento atinge D-7',
    condition: {
      type: 'dMinus_reached',
      value: 7,
      comparison: 'equals'
    },
    channels: [
      { type: 'email', target: 'operacoes@empresa.com', isEnabled: true },
      { type: 'sms', target: '+5511999999999', isEnabled: false }
    ],
    isActive: true,
    createdAt: '2024-01-18'
  }
];

export function getEventGoals(): EventGoal[] {
  return mockEventGoals;
}

export function getBenchmarkCurves(): BenchmarkCurve[] {
  return mockBenchmarkCurves;
}

export function getISCParameters(): ISCParameters {
  return { ...defaultISCParameters };
}

export function getEventCategories(): EventCategory[] {
  return mockEventCategories;
}

export function getAlertConfigs(): AlertConfig[] {
  return mockAlertConfigs;
}
