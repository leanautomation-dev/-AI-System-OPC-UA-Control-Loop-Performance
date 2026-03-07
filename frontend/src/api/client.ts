import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const api = axios.create({ baseURL: BASE });

export const getControllers   = () => api.get('/api/v1/controllers').then(r => r.data);
export const getLiveTags      = () => api.get('/api/v1/tags/live').then(r => r.data);
export const getControllerLive = (id: string) => api.get(`/api/v1/controllers/${id}/live`).then(r => r.data);
export const getMetrics       = (hours = 24) => api.get('/api/v1/metrics', { params: { hours } }).then(r => r.data);
export const getControllerMetrics = (id: string, hours = 24) =>
  api.get(`/api/v1/controllers/${id}/metrics`, { params: { hours } }).then(r => r.data);
export const getActiveAlarms  = () => api.get('/api/v1/alarms').then(r => r.data);
export const ackAlarm         = (id: number, user = 'operator') =>
  api.post(`/api/v1/alarms/${id}/acknowledge`, null, { params: { user } }).then(r => r.data);
