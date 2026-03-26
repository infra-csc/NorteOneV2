export interface PlaybookEntry {
  letter: string;
  name: string;
  stage: string;
  stageName: string;
  iscLabel: string;
  objective: string;
  narrative: string;
  actions: string[];
  kpis: string[];
  cutoffs: string[];
}

export interface DailySales {
  date: string;
  sales: number;
  expected: number;
  normalizedSales?: number;
  cumulativeNormalized?: number;
  localMedian?: number | null;
  outlierLimit?: number | null;
  isOutlier?: boolean;
  excessRemoved?: number;
  excessReceived?: number;
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
  budgetTicket: number;
  dMinus: number;
  dMinusInscricoes: number;
  isc: number;
  iscComponents: ISCComponents;
  iscStatus: ISCStatus;
  suggestedAction: PlaybookEntry;
  lastAction?: CommercialAction;
  dailySales: DailySales[];
  commercialActions: CommercialAction[];
  isActive: boolean;
  sku?: string;
  kitCostPerUnit: number;
  margemOrcadaUnit: number;
  margemOrcadaTotal: number;
  margemOrcadaPct: number;
  margemRealizadaUnit: number;
  margemRealizadaTotal: number;
  margemRealizadaPct: number;
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
    case 'accelerating': return '😁';
    case 'stable': return '😐';
    case 'decelerating': return '😢';
  }
}

export function getPlaybookColor(stage: string): string {
  switch (stage) {
    case 'analitico': return '#6366f1';
    case 'estrategico': return '#f59e0b';
    case 'operacional': return '#ef4444';
    default: return '#6b7280';
  }
}

export function isInCriticalWindow(dMinus: number): boolean {
  return dMinus >= 40 && dMinus <= 45;
}

export interface PricingMetrics {
  rollingIndex: number;
  rollingAvg14d: number;
  rollingAvg14dLastYear: number;
  paceRequired: number;
  ied: number;
  projection: number;
  paceSeguranca: number;
  fem: number;
  ia: number;
}

export interface ElasticityScenario {
  priceIncrease: number;
  newPrice: number;
  newMargin: number;
  acceptableVolumeDrop: number;
  minPace: number;
}

export interface PricingDecision {
  action: 'increase_now' | 'increase_gradual' | 'maintain' | 'decrease';
  reason: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface PricingEvent {
  id: string;
  name: string;
  date: string;
  location: string;
  category: string;
  totalCapacity: number;
  currentSales: number;
  salesGoal: number;
  averageTicket: number;
  kitCost: number;
  dMinus: number;
  isActive: boolean;
  sku?: string;
  pricingMetrics: PricingMetrics;
  elasticityScenarios: ElasticityScenario[];
  decision: PricingDecision;
  iscStatus: ISCStatus;
}

export function getPricingDecisionColor(action: PricingDecision['action']): string {
  switch (action) {
    case 'increase_now': return '#22c55e';
    case 'increase_gradual': return '#84cc16';
    case 'maintain': return '#eab308';
    case 'decrease': return '#ef4444';
  }
}

export function getPricingDecisionLabel(action: PricingDecision['action']): string {
  switch (action) {
    case 'increase_now': return 'Subir Preco Agora';
    case 'increase_gradual': return 'Subir Gradualmente';
    case 'maintain': return 'Manter Preco';
    case 'decrease': return 'Considerar Reducao';
  }
}
