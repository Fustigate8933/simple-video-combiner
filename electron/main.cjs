const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { spawn } = require('node:child_process')
const path = require('node:path')

app.disableHardwareAcceleration()

let backendProcess = null
let mainWindow = null

function startBackend() {
  if (backendProcess) {
    return
  }

  backendProcess = spawn(
    'python',
    [
      '-m',
      'uvicorn',
      'backend.app.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      '8765',
    ],
    {
      cwd: path.join(__dirname, '..'),
      stdio: 'inherit',
    }
  )

  backendProcess.on('exit', () => {
    backendProcess = null
  })
}

function stopBackend() {
  if (!backendProcess) {
    return
  }

  backendProcess.kill()
  backendProcess = null
}

async function waitForBackend() {
  const deadline = Date.now() + 15000
  while (Date.now() < deadline) {
    try {
      const response = await fetch('http://127.0.0.1:8765/health')
      if (response.ok) {
        return
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300))
    }
  }

  throw new Error('Backend did not start within 15 seconds')
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    backgroundColor: '#f8fbf1',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  await mainWindow.loadURL('http://127.0.0.1:5173')
}

ipcMain.handle('dialog:directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('dialog:save-file', async () => {
  const result = await dialog.showSaveDialog({
    filters: [{ name: 'MP4 Video', extensions: ['mp4'] }],
  })
  return result.canceled ? null : result.filePath
})

app.whenReady().then(async () => {
  startBackend()
  await waitForBackend()
  await createWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopBackend()
})
