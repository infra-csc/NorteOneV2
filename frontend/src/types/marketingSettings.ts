export interface EventGoal {
  id: string;
  eventId: string;
  eventName: string;
  salesGoal: number;
  revenueGoal: number;
  conversionTarget: number;
  averageTicketTarget: number;
  createdAt: string;
  updatedAt: string;
}

export interface BenchmarkCurve {
  id: string;
  name: string;
  description: string;
  type: 'aggressive' | 'moderate' | 'conservative';
  dataPoints: BenchmarkDataPoint[];
  isDefault: boolean;
  createdAt: string;
}

export interface BenchmarkDataPoint {
  dMinus: number;
  expectedPercentage: number;
}

export interface ISCParameters {
  ia730Weight: number;
  curvaDWeight: number;
  rolling14dWeight: number;
  greenThreshold: number;
  yellowThreshold: number;
  criticalWindowStart: number;
  criticalWindowEnd: number;
  promotionDeadline: number;
  useNormalizedCurveForISC?: boolean;
}

export interface EventCategory {
  id: string;
  name: string;
  description: string;
  color: string;
  icon: string;
  defaultCapacity: number;
  defaultTicketPrice: number;
  isActive: boolean;
  eventCount: number;
}

export interface AlertConfig {
  id: string;
  name: string;
  description: string;
  condition: AlertCondition;
  channels: AlertChannel[];
  isActive: boolean;
  createdAt: string;
}

export interface AlertCondition {
  type: 'isc_below' | 'isc_above' | 'sales_below' | 'sales_above' | 'dMinus_reached' | 'critical_window';
  value: number;
  comparison?: 'less_than' | 'greater_than' | 'equals';
}

export interface AlertChannel {
  type: 'email' | 'sms' | 'push' | 'slack';
  target: string;
  isEnabled: boolean;
}

export interface SettingsTab {
  id: string;
  label: string;
  icon: string;
}
