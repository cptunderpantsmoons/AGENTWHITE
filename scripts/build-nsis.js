const { build, Platform } = require('electron-builder');

build({
  targets: Platform.WINDOWS.createTarget('nsis')
}).then(() => {
  console.log('Build complete!');
  process.exit(0);
}).catch(err => {
  console.error('Build failed:', err);
  process.exit(1);
});
