// Run after replacing apps/mobile/assets/icon.png to regenerate platform sizes.
const fs = require('node:fs/promises');
const path = require('node:path');
const { generateImageAsync } = require('../apps/mobile/node_modules/@expo/image-utils');
const root = path.resolve(__dirname, '..');
const src = path.join(root, 'apps/mobile/assets/icon.png');
const res = path.join(root, 'apps/mobile/android/app/src/main/res');

async function resize(destination, size) {
  const { source } = await generateImageAsync({ projectRoot: root }, {
    src, width: size, height: size, resizeMode: 'contain',
    backgroundColor: '#101827', removeTransparency: true,
  });
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.writeFile(destination, source);
}

async function main() {
  for (const [density, scale] of Object.entries({ mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 })) {
    for (const name of ['ic_launcher', 'ic_launcher_round']) {
      await resize(path.join(res, `mipmap-${density}`, `${name}.png`), 48 * scale);
      await fs.rm(path.join(res, `mipmap-${density}`, `${name}.webp`), { force: true });
    }
    await resize(path.join(res, `mipmap-${density}`, 'ic_launcher_foreground.png'), 108 * scale);
  }
  const adaptive = '<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n  <background android:drawable="@color/icon_background" />\n  <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n</adaptive-icon>\n';
  const adaptiveDir = path.join(res, 'mipmap-anydpi-v26');
  await fs.mkdir(adaptiveDir, { recursive: true });
  for (const name of ['ic_launcher', 'ic_launcher_round']) {
    await fs.writeFile(path.join(adaptiveDir, `${name}.xml`), adaptive);
  }
  await resize(path.join(root, 'apps/windows-admin/public/icon.png'), 64);
  console.log('Generated Android launcher/adaptive icons and admin favicon.');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
