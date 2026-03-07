import { create } from 'zustand';

export interface Alarm {
  id: number;
  time: string;
  event_type: string;
  source_name: string;
  message: string;
  severity: number;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
}

interface AlarmState {
  alarms: Alarm[];
  unacknowledgedCount: number;
  addAlarms: (alarms: Alarm[]) => void;
  addAlarm: (alarm: Alarm) => void;
  acknowledgeAlarm: (id: number) => void;
}

export const useAlarmStore = create<AlarmState>((set, get) => ({
  alarms: [],
  unacknowledgedCount: 0,

  addAlarms: (alarms) => {
    set({
      alarms,
      unacknowledgedCount: alarms.filter((a) => !a.acknowledged).length,
    });
  },

  addAlarm: (alarm) => {
    const existing = get().alarms;
    const updated = [alarm, ...existing].slice(0, 500);
    set({
      alarms: updated,
      unacknowledgedCount: updated.filter((a) => !a.acknowledged).length,
    });
  },

  acknowledgeAlarm: (id) => {
    const alarms = get().alarms.map((a) =>
      a.id === id ? { ...a, acknowledged: true } : a
    );
    set({ alarms, unacknowledgedCount: alarms.filter((a) => !a.acknowledged).length });
  },
}));
