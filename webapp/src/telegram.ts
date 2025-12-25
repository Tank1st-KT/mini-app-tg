declare global {
  interface Window {
    Telegram?: any;
  }
}

export function getTg() {
  return window.Telegram?.WebApp;
}

export function getInitData(): string {
  const tg = getTg();
  return tg?.initData || "";
}

export function getTgUser() {
  const tg = getTg();
  return tg?.initDataUnsafe?.user || null;
}

export function tgReadyExpand() {
  const tg = getTg();
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
  } catch {
    // ignore
  }
}
