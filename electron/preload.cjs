const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('kiwi', {
  pickDirectory: () => ipcRenderer.invoke('dialog:directory'),
  pickOutputFile: () => ipcRenderer.invoke('dialog:save-file'),
})
