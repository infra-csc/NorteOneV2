export interface DailySales {
  date: string;
  sales: number;
  expected: number;
}

export interface CommercialAction {
  id: string;
  date: string;
  type: 'price_increase' | 'price_decrease' | 'promotion' | 'communication' | 'campaign';
  description: string;
  impact?: string;
}

export interface ISCComponents {
  ia730: number;
  curvaDPercent: number;
  rolling14d: number;
}

export type ISCStatus = 'accelerating' | 'stable' | 'decelerating';

export interface Event {
  id: string;
  name: string;
  date: string;
  location: string;
  category: string;
  totalCapacity: number;
  currentSales: number;
  salesGoal: number;
  averageTicket: number;
  dMinus: number;
  isc: number;
  iscComponents: ISCComponents;
  iscStatus: ISCStatus;
  suggestedAction: string;
  lastAction?: CommercialAction;
  dailySales: DailySales[];
  commercialActions: CommercialAction[];
  isActive: boolean;
}

export interface DashboardSummary {
  totalActiveEvents: number;
  eventsGreen: number;
  eventsYellow: number;
  eventsRed: number;
}

export interface FilterOptions {
  period: 'all' | '30days' | '60days' | '90days';
  category: string;
  status: 'all' | 'active' | 'closed';
}

export function getISCStatus(isc: number): ISCStatus {
  if (isc > 1.10) return 'accelerating';
  if (isc >= 0.90) return 'stable';
  return 'decelerating';
}

export function getISCColor(status: ISCStatus): string {
  switch (status) {
    case 'accelerating': return '#22c55e';
    case 'stable': return '#eab308';
    case 'decelerating': return '#ef4444';
  }
}

export function getISCEmoji(status: ISCStatus): string {
  switch (status) {
    case 'accelerating': return '🟢';
    case 'stable': return '🟡';
    case 'decelerating': return '🔴';
  }
}

export function getSuggestedAction(isc: number, dMinus: number): string {
  const status = getISCStatus(isc);
  
  if (status === 'accelerating') {
    return 'Evento forte. Considere ajuste de preço para cima.';
  }
  
  if (status === 'stable') {
    if (dMinus >= 40) {
      return 'Evento estável. Monitore e reforce comunicação.';
    }
    return 'Evento estável. Apenas ajustes de comunicação.';
  }
  
  if (dMinus >= 40) {
    return 'Evento fraco. Janela aberta para ação promocional.';
  }
  
  return '⚠️ Evento fraco, mas fora da janela de promoção. Apenas reforço de comunicação.';
}

export function isInCriticalWindow(dMinus: number): boolean {
  return dMinus >= 40 && dMinus <= 45;
}
