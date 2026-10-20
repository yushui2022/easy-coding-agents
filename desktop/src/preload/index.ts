import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('eca', {
  invoke: async (method: string, params: Record<string, unknown> = {}) => {
    const result = await ipcRenderer.invoke('eca:invoke', method, params);
    if (!result.ok) throw new Error(result.error);
    return result.value;
  },
  subscribe: (callback: (data: {event?:string}) => void) => {
    const listener = (_event:unknown, data:{event?:string}) => callback(data || {});
    ipcRenderer.on('eca:changed', listener);
    return () => ipcRenderer.removeListener('eca:changed', listener);
  },
  onFailure: (callback: (message: string) => void) => {
    const listener = (_event: unknown, message: string) => callback(message);
    ipcRenderer.on('eca:failure', listener);
    return () => ipcRenderer.removeListener('eca:failure', listener);
  },
  copy: async (text: string) => Boolean(await ipcRenderer.invoke('eca:copy', text)),
  windowControl: async (action: string) => Boolean(await ipcRenderer.invoke('eca:window', action)),
  theme: async () => String(await ipcRenderer.invoke('eca:theme', {action: 'get'})),
  setTheme: async (source: string) => String(await ipcRenderer.invoke('eca:theme', {action: 'set', source})),
  onTheme: (callback: (source: string) => void) => {
    const listener = (_event: unknown, source: string) => callback(String(source));
    ipcRenderer.on('eca:theme', listener);
    return () => ipcRenderer.removeListener('eca:theme', listener);
  },
  onMaximized: (callback: (value: boolean) => void) => {
    const listener = (_event: unknown, value: boolean) => callback(Boolean(value));
    ipcRenderer.on('eca:maximized', listener);
    return () => ipcRenderer.removeListener('eca:maximized', listener);
  }
});
