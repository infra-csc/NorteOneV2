import { Event, DailySales, CommercialAction, getISCStatus, getSuggestedAction } from '../types/marketingPerformance';

function generateDailySales(daysBack: number, pattern: 'strong' | 'weak' | 'stable', baseExpected: number): DailySales[] {
  const sales: DailySales[] = [];
  const today = new Date();
  
  for (let i = daysBack; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    
    let multiplier = 1;
    const dayProgress = (daysBack - i) / daysBack;
    
    if (pattern === 'strong') {
      multiplier = 0.8 + (dayProgress * 0.6) + (Math.random() * 0.3);
    } else if (pattern === 'weak') {
      multiplier = 0.5 + (dayProgress * 0.2) + (Math.random() * 0.2);
    } else {
      multiplier = 0.7 + (dayProgress * 0.3) + (Math.random() * 0.25);
    }
    
    const expectedBase = baseExpected * (1 + dayProgress * 0.5);
    
    sales.push({
      date: date.toISOString().split('T')[0],
      sales: Math.round(baseExpected * multiplier),
      expected: Math.round(expectedBase)
    });
  }
  
  return sales;
}

function generateCommercialActions(eventName: string, pattern: 'strong' | 'weak' | 'stable'): CommercialAction[] {
  const actions: CommercialAction[] = [];
  const today = new Date();
  
  if (pattern === 'strong') {
    actions.push({
      id: '1',
      date: new Date(today.setDate(today.getDate() - 20)).toISOString().split('T')[0],
      type: 'price_increase',
      description: 'Aumento de 10% no lote atual',
      impact: '+R$ 15.000 receita estimada'
    });
    actions.push({
      id: '2',
      date: new Date(today.setDate(today.getDate() - 10)).toISOString().split('T')[0],
      type: 'campaign',
      description: 'Campanha de mídia social',
      impact: '+250 inscrições'
    });
  } else if (pattern === 'weak') {
    actions.push({
      id: '1',
      date: new Date(today.setDate(today.getDate() - 30)).toISOString().split('T')[0],
      type: 'communication',
      description: 'E-mail marketing para base de leads',
      impact: '+80 inscrições'
    });
    actions.push({
      id: '2',
      date: new Date(today.setDate(today.getDate() - 15)).toISOString().split('T')[0],
      type: 'promotion',
      description: 'Desconto de 15% para grupos',
      impact: '+120 inscrições'
    });
  } else {
    actions.push({
      id: '1',
      date: new Date(today.setDate(today.getDate() - 25)).toISOString().split('T')[0],
      type: 'communication',
      description: 'Parceria com influenciadores',
      impact: '+150 inscrições'
    });
  }
  
  return actions;
}

function calculateCumulativeSales(dailySales: DailySales[]): number {
  return dailySales.reduce((sum, day) => sum + day.sales, 0);
}

function calculateIA730(dailySales: DailySales[]): number {
  const last7 = dailySales.slice(-7).reduce((sum, d) => sum + d.sales, 0);
  const last30 = dailySales.slice(-30).reduce((sum, d) => sum + d.sales, 0);
  
  if (last30 === 0) return 1;
  return (last7 / last30) * (30 / 7);
}

function calculateCurvaDPercent(dailySales: DailySales[]): number {
  const totalSales = dailySales.reduce((sum, d) => sum + d.sales, 0);
  const expectedSales = dailySales.reduce((sum, d) => sum + d.expected, 0);
  
  if (expectedSales === 0) return 1;
  return totalSales / expectedSales;
}

function calculateRolling14d(dailySales: DailySales[]): number {
  const last14 = dailySales.slice(-14);
  const avg = last14.reduce((sum, d) => sum + d.sales, 0) / 14;
  const allDaysAvg = dailySales.reduce((sum, d) => sum + d.sales, 0) / dailySales.length;
  
  if (allDaysAvg === 0) return 1;
  return avg / allDaysAvg;
}

function createEvent(
  id: string,
  name: string,
  dMinus: number,
  targetISC: number,
  location: string,
  category: string,
  capacity: number,
  goal: number,
  avgTicket: number
): Event {
  const pattern = targetISC > 1.10 ? 'strong' : targetISC < 0.90 ? 'weak' : 'stable';
  const dailySales = generateDailySales(60, pattern, Math.round(goal / 90));
  
  const ia730 = calculateIA730(dailySales);
  const curvaDPercent = calculateCurvaDPercent(dailySales);
  const rolling14d = calculateRolling14d(dailySales);
  
  const adjustedIA = ia730 * (targetISC / ((ia730 + curvaDPercent + rolling14d) / 3));
  const adjustedCurva = curvaDPercent * (targetISC / ((ia730 + curvaDPercent + rolling14d) / 3));
  const adjustedRolling = rolling14d * (targetISC / ((ia730 + curvaDPercent + rolling14d) / 3));
  
  const isc = (adjustedIA + adjustedCurva + adjustedRolling) / 3;
  const iscStatus = getISCStatus(isc);
  
  const currentSales = calculateCumulativeSales(dailySales);
  const commercialActions = generateCommercialActions(name, pattern);
  
  const eventDate = new Date();
  eventDate.setDate(eventDate.getDate() + dMinus);
  
  return {
    id,
    name,
    date: eventDate.toISOString().split('T')[0],
    location,
    category,
    totalCapacity: capacity,
    currentSales: Math.min(currentSales, goal),
    salesGoal: goal,
    averageTicket: avgTicket,
    dMinus,
    isc: Math.round(isc * 100) / 100,
    iscComponents: {
      ia730: Math.round(adjustedIA * 100) / 100,
      curvaDPercent: Math.round(adjustedCurva * 100) / 100,
      rolling14d: Math.round(adjustedRolling * 100) / 100
    },
    iscStatus,
    suggestedAction: getSuggestedAction(isc, dMinus),
    lastAction: commercialActions[commercialActions.length - 1],
    dailySales,
    commercialActions,
    isActive: dMinus > 0
  };
}

export const mockEvents: Event[] = [
  createEvent(
    '1',
    'Circuito do Sol - São Paulo 2026',
    45,
    1.21,
    'São Paulo, SP',
    'Corrida',
    15000,
    12000,
    189.90
  ),
  createEvent(
    '2',
    'Night Run - Etapa 1 - Florianópolis 2026',
    52,
    0.85,
    'Florianópolis, SC',
    'Corrida',
    3000,
    2500,
    129.90
  ),
  createEvent(
    '3',
    'Bravus Speed I - Rio de Janeiro 2026 ',
    38,
    0.95,
    'Rio de Janeiro, RJ',
    'Obstáculo',
    5000,
    4000,
    149.90
  ),
  createEvent(
    '4',
    'Circuito das Estações - Outono - Porto Alegre 2026',
    60,
    1.05,
    'Gramado, RS',
    'Corrida',
    1500,
    1200,
    249.90
  ),
  createEvent(
    '5',
    'Meia Internacional da Cidade de São Paulo - 2026',
    43,
    0.78,
    'São Paulo, SP',
    'Meia Maratona',
    8000,
    6500,
    169.90
  ),
  createEvent(
    '6',
    'Triathlon Internacional de Santos - 2026',
    30,
    1.35,
    'Santos, SP',
    'Triathlon',
    10000,
    8000,
    99.90
  ),
  createEvent(
    '7',
    'Girl Power Run - São Paulo 2026',
    75,
    0.92,
    'São Paulo, SP',
    'Corrida',
    4000,
    3500,
    79.90
  ),
  createEvent(
    '8',
    'Troféu Brasil - Etapa 1 - Santos 2026',
    25,
    1.18,
    'Santos, SP',
    'Triathlon',
    2500,
    2000,
    139.90
  )
];

export function getEventById(id: string): Event | undefined {
  return mockEvents.find(e => e.id === id);
}

export function getFilteredEvents(filters: { 
  period?: string; 
  category?: string; 
  status?: string;
  search?: string;
}): Event[] {
  let filtered = [...mockEvents];
  
  if (filters.category && filters.category !== 'all') {
    filtered = filtered.filter(e => e.category === filters.category);
  }
  
  if (filters.status === 'active') {
    filtered = filtered.filter(e => e.isActive);
  } else if (filters.status === 'closed') {
    filtered = filtered.filter(e => !e.isActive);
  }
  
  if (filters.search) {
    const search = filters.search.toLowerCase();
    filtered = filtered.filter(e => 
      e.name.toLowerCase().includes(search) || 
      e.location.toLowerCase().includes(search)
    );
  }
  
  filtered.sort((a, b) => a.dMinus - b.dMinus);
  
  return filtered;
}

export function getDashboardSummary(): {
  totalActiveEvents: number;
  eventsGreen: number;
  eventsYellow: number;
  eventsRed: number;
} {
  const activeEvents = mockEvents.filter(e => e.isActive);
  
  return {
    totalActiveEvents: activeEvents.length,
    eventsGreen: activeEvents.filter(e => e.iscStatus === 'accelerating').length,
    eventsYellow: activeEvents.filter(e => e.iscStatus === 'stable').length,
    eventsRed: activeEvents.filter(e => e.iscStatus === 'decelerating').length
  };
}

export function getCategories(): string[] {
  const categories = new Set(mockEvents.map(e => e.category));
  return ['all', ...Array.from(categories)];
}
