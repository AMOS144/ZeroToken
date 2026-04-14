"""
Stealth mode: launch args and init script to reduce automation detection.
Used when controller.start(stealth=True).
"""

# Launch args to disable common automation indicators (Chromium)
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--window-size=1920,1080",
]

# Init script run before any page script: mask navigator.webdriver and common checks.
# Runs in browser context; must be valid JS.
STEALTH_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    if (window.chrome && window.chrome.runtime) {} else {
      window.chrome = { runtime: {} };
    }
  } catch (e) {}
  try {
    if (!navigator.plugins || navigator.plugins.length === 0) {
      const makePlugin = (name, filename, description) => ({
        name, filename, description,
        length: 1,
        item: function(i) { return i === 0 ? { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: this } : null; },
        namedItem: function() { return null; }
      });
      const plugins = [
        makePlugin('Chrome PDF Plugin', 'internal-pdf-viewer', 'Portable Document Format'),
        makePlugin('Chrome PDF Viewer', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', ''),
        makePlugin('Native Client', 'internal-nacl-plugin', '')
      ];
      Object.defineProperty(navigator, 'plugins', {
        get: () => ({ length: 3, item: i => plugins[i] || null, namedItem: n => plugins.find(p => p.name === n) || null }),
        configurable: true,
        enumerable: true
      });
    }
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['zh-CN', 'zh', 'en'],
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'platform', {
      get: () => 'Win32',
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: () => 8,
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'deviceMemory', {
      get: () => 8,
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'maxTouchPoints', {
      get: () => 0,
      configurable: true,
      enumerable: true
    });
  } catch (e) {}
  try {
    const WEBGL_VENDOR = 'Google Inc. (NVIDIA)';
    const WEBGL_RENDERER = 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0)';
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      const ctx = origGetContext.apply(this, [type, ...args]);
      if (ctx && (type === 'webgl' || type === 'webgl2')) {
        const origGetParam = ctx.getParameter.bind(ctx);
        ctx.getParameter = function(pname) {
          if (pname === 37445) return WEBGL_VENDOR;
          if (pname === 37446) return WEBGL_RENDERER;
          return origGetParam(pname);
        };
      }
      return ctx;
    };
  } catch (e) {}
})();
"""

# Realistic Chrome UA (Windows, recent Chromium)
DEFAULT_STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
