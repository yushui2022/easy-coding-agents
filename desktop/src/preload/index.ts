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
  copy: async (text: string) => Boolean(await ipcRenderer.invoke('eca:copy', text))
});
