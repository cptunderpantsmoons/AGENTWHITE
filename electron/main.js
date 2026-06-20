const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');
const fs = require('fs');

let mainWindow = null;
let serverProcess = null;
let serverPort = 7860;

function findFreePort(startPort) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(startPort, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      findFreePort(startPort + 1).then(resolve, reject);
    });
  });
}

function getDataDir() {
  const isDev = !app.isPackaged;
  if (isDev) {
    return path.join(__dirname, '..', 'data');
  }
  // 1. Explicit override.
  if (process.env.ODYSSEUS_DATA_DIR) {
    return process.env.ODYSSEUS_DATA_DIR;
  }
  // 2. Portable / USB mode: keep data next to the executable when writable.
  const exeDir = path.dirname(process.execPath);
  const portableData = path.join(exeDir, 'data');
  try {
    fs.mkdirSync(portableData, { recursive: true });
    const probe = path.join(portableData, '.write-test');
    fs.writeFileSync(probe, '1');
    fs.unlinkSync(probe);
    return portableData;
  } catch (err) {
    // Not writable (e.g. installed under Program Files) — fall back to userData.
  }
  return path.join(app.getPath('userData'), 'data');
}

function getPythonPath() {
  const isDev = !app.isPackaged;
  if (isDev) {
    return process.platform === 'win32' ? 'python' : 'python3';
  }
  if (process.platform === 'win32') {
    return path.join(process.resourcesPath, 'python', 'python.exe');
  }
  return path.join(process.resourcesPath, 'python', 'bin', 'python');
}

function getAppDir() {
  const isDev = !app.isPackaged;
  if (isDev) {
    return path.join(__dirname, '..');
  }
  return path.join(process.resourcesPath, 'app.asar');
}

function getRealAppDir() {
  const appDir = getAppDir();
  return appDir.replace(/\.asar$/, '.asar.unpacked');
}

async function startServer() {
  const port = await findFreePort(serverPort);
  serverPort = port;

  const pythonPath = getPythonPath();
  const appDir = getAppDir();
  const dataDir = getDataDir();

  fs.mkdirSync(dataDir, { recursive: true });

  const realAppDir = getRealAppDir();

  const env = {
    ...process.env,
    PYTHONPATH: realAppDir,
    PYTHONUNBUFFERED: '1',
    ODYSSEUS_DATA_DIR: dataDir,
    AUTH_ENABLED: 'true',
  };

  const scriptPath = path.join(realAppDir, 'electron', 'start_server.py');

  serverProcess = spawn(pythonPath, [scriptPath, '--port', String(port), '--data-dir', dataDir], {
    cwd: realAppDir,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  serverProcess.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    console.log('[server]', msg);
  });

  serverProcess.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    console.log('[server:err]', msg);
  });

  serverProcess.on('error', (err) => {
    console.error('Failed to start server:', err);
  });

  serverProcess.on('exit', (code) => {
    console.log(`Server exited with code ${code}`);
    serverProcess = null;
  });
}

function waitForServer(port, maxRetries = 60) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const interval = setInterval(() => {
      const socket = new net.Socket();
      socket.setTimeout(1000);
      socket.on('connect', () => {
        clearInterval(interval);
        socket.destroy();
        resolve();
      });
      socket.on('error', () => {
        socket.destroy();
        retries++;
        if (retries >= maxRetries) {
          clearInterval(interval);
          reject(new Error('Server failed to start'));
        }
      });
      socket.on('timeout', () => {
        socket.destroy();
        retries++;
        if (retries >= maxRetries) {
          clearInterval(interval);
          reject(new Error('Server failed to start'));
        }
      });
      socket.connect(port, '127.0.0.1');
    }, 1000);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    title: '',
    icon: path.join(__dirname, '..', 'static', 'icon-512.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadURL(`http://127.0.0.1:${serverPort}`);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function killServer() {
  if (!serverProcess) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(serverProcess.pid), '/T', '/F'], { windowsHide: true });
    } else {
      process.kill(serverProcess.pid, 'SIGTERM');
    }
  } catch (e) {
    // Process may already be dead
  }
  serverProcess = null;
}

app.on('ready', async () => {
  try {
    await startServer();
    await waitForServer(serverPort);
    createWindow();
  } catch (err) {
    console.error('Startup failed:', err);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  killServer();
  app.quit();
});

app.on('before-quit', () => {
  killServer();
});
