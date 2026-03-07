import { create } from 'zustand';

export interface AIInsight {
  timestamp: string;
  controller: string;
  pv: number;
  sp: number;
  co: number;
  anomaly: {
    anomaly: boolean;
    score: number;
    reason: string | null;
  };
  alarm_prediction: {
    predicted_alarm: boolean;
    confidence: number;
    projected_error?: number;
    minutes_ahead?: number;
  };
  clpm: {
    score: number | null;
    grade: string;
    iae: number;
    aae: number;
    pv_std: number;
    co_travel: number;
    oscillation_index: number;
  };
}

interface AIStore {
  insights: Record<string, AIInsight>;  // keyed by controller
  updateInsights: (batch: AIInsight[]) => void;
}

export const useAIStore = create<AIStore>((set) => ({
  insights: {},
  updateInsights: (batch) => {
    const updates: Record<string, AIInsight> = {};
    for (const insight of batch) {
      updates[insight.controller] = insight;
    }
    set((state) => ({ insights: { ...state.insights, ...updates } }));
  },
}));
