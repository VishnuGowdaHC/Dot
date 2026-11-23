/**
 * Neutralino window manager for Dot floating HUD.
 * Complies with ASD-STE100 writing rules.
 */

export function getDpr() {
  return window.devicePixelRatio || 1;
}

export async function nativeCall(fn) {
  if (typeof window !== "undefined" && window.Neutralino && window.Neutralino.window) {
    try {
      return await fn();
    } catch (err) {
      console.warn("Neutralino window call warning:", err);
    }
  }
  return null;
}

export const windowConfig = {
  windowWidth: 440,
  idleHeight: 184,
  expandedHeight: 460,
  settingsHeight: 560,
  margin: 24,
};

/**
 * Positions the HUD at the bottom-right corner of the monitor.
 */
export async function dockWindow(mode = "idle") {
  // Retry up to 5 times if Neutralino is still connecting
  for (let attempt = 0; attempt < 5; attempt++) {
    if (typeof window !== "undefined" && window.Neutralino && window.Neutralino.window) {
      break;
    }
    await new Promise((r) => setTimeout(r, 200));
  }

  const dpr = getDpr();
  const physWidth = Math.round(windowConfig.windowWidth * dpr);
  let targetHeight = windowConfig.idleHeight;
  if (mode === "settings") {
    targetHeight = windowConfig.settingsHeight;
  } else if (mode === "chat" || mode === true) {
    targetHeight = windowConfig.expandedHeight;
  }
  const physHeight = Math.round(targetHeight * dpr);

  const screenLeft = Math.round((window.screen.availLeft || 0) * dpr);
  const screenTop = Math.round((window.screen.availTop || 0) * dpr);
  const screenW = Math.round((window.screen.availWidth || 1920) * dpr);
  const screenH = Math.round((window.screen.availHeight || 1080) * dpr);
  const physMargin = Math.round(windowConfig.margin * dpr);

  const physX = screenLeft + screenW - physWidth - physMargin;
  const physY = screenTop + screenH - physHeight - physMargin;

  await nativeCall(() => window.Neutralino.window.setSize({ width: physWidth, height: physHeight }));
  await nativeCall(() => window.Neutralino.window.move(physX, physY));
}

/**
 * Expands or collapses the native window upwards to keep bottom anchored.
 */
export async function updateNativeWindowSize(mode = "idle") {
  const dpr = getDpr();
  const physWidth = Math.round(windowConfig.windowWidth * dpr);
  let targetHeight = windowConfig.idleHeight;
  if (mode === "settings") {
    targetHeight = windowConfig.settingsHeight;
  } else if (mode === "chat" || mode === true) {
    targetHeight = windowConfig.expandedHeight;
  }
  const physTargetHeight = Math.round(targetHeight * dpr);

  const pos = await nativeCall(() => window.Neutralino.window.getPosition());
  const size = await nativeCall(() => window.Neutralino.window.getSize());

  if (pos && size) {
    const physBottom = pos.y + size.height;
    const newPhysY = physBottom - physTargetHeight;
    await nativeCall(() => window.Neutralino.window.move(pos.x, newPhysY));
    await nativeCall(() => window.Neutralino.window.setSize({ width: physWidth, height: physTargetHeight }));
  } else {
    await nativeCall(() => window.Neutralino.window.setSize({ width: physWidth, height: physTargetHeight }));
  }
}

export async function minimizeWindow() {
  if (typeof window !== "undefined" && window.Neutralino && window.Neutralino.window) {
    try {
      await window.Neutralino.window.minimize();
    } catch (err) {
      console.warn("Minimize error, trying hide:", err);
      try {
        await window.Neutralino.window.hide();
      } catch (e) {}
    }
  }
}

export async function closeApp() {
  if (typeof window !== "undefined" && window.Neutralino) {
    try {
      if (window.Neutralino.app) {
        await window.Neutralino.app.exit(0);
        return;
      }
    } catch (e) {
      console.warn("Neutralino app.exit warning:", e);
    }
    try {
      if (window.Neutralino.window) {
        await window.Neutralino.window.hide();
      }
    } catch (e) {}
  }
  window.close();
}
