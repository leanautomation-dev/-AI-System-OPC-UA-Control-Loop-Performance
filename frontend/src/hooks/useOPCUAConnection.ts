import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { useTagStore } from '../store/tagStore';
import { useAlarmStore } from '../store/alarmStore';
import { useAIStore } from '../store/aiStore';

const WS_BASE = import.meta.env.DEV ? 'ws://localhost:8000' : window.location.origin.replace('http', 'ws');

export function useOPCUAConnection() {
  const [connected, setConnected] = useState(false);
  const tagWs   = useRef<WebSocket | null>(null);
  const alarmWs = useRef<WebSocket | null>(null);
  const aiWs    = useRef<WebSocket | null>(null);

  const updateBatch   = useTagStore((s) => s.updateBatch);
  const addAlarm      = useAlarmStore((s) => s.addAlarm);
  const addAlarms     = useAlarmStore((s) => s.addAlarms);
  const updateInsights = useAIStore((s) => s.updateInsights);

  function connectTags() {
    const ws = new WebSocket(`${WS_BASE}/ws/tags`);
    ws.onopen  = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setTimeout(connectTags, 3000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.data) updateBatch(msg.data);
      } catch {}
    };
    tagWs.current = ws;
  }

  function connectAlarms() {
    const ws = new WebSocket(`${WS_BASE}/ws/alarms`);
    ws.onclose = () => setTimeout(connectAlarms, 3000);
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'snapshot') {
          addAlarms(msg.data);
        } else if (msg.data) {
          for (const alarm of msg.data) {
            addAlarm(alarm);
            if (alarm.severity >= 900) {
              toast.error(`🚨 CRITICAL: ${alarm.message}`, { duration: 8000 });
            } else if (alarm.severity >= 500) {
              toast(`⚠️ HIGH: ${alarm.message}`, { duration: 5000 });
            }
          }
        }
      } catch {}
    };
    alarmWs.current = ws;
  }

  function connectAI() {
    const ws = new WebSocket(`${WS_BASE}/ws/ai`);
    ws.onclose = () => setTimeout(connectAI, 3000);
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ai_insights' && msg.data) {
          updateInsights(msg.data);
        }
      } catch {}
    };
    aiWs.current = ws;
  }

  useEffect(() => {
    connectTags();
    connectAlarms();
    connectAI();
    return () => {
      tagWs.current?.close();
      alarmWs.current?.close();
      aiWs.current?.close();
    };
  }, []);

  return { connected };
}
