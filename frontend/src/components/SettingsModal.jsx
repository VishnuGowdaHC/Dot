import { useState, useEffect } from "react";

const PROVIDER_PRESETS = [
  {
    id: "gemini",
    name: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    suggestedModels: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
    keyPlaceholder: "AIzaSy...",
  },
  {
    id: "openai",
    name: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    suggestedModels: ["gpt-4o-mini", "gpt-4o", "o1-mini"],
    keyPlaceholder: "sk-proj-...",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    baseUrl: "https://openrouter.ai/api/v1",
    suggestedModels: ["anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat", "meta-llama/llama-3.3-70b-instruct"],
    keyPlaceholder: "sk-or-v1-...",
  },
  {
    id: "groq",
    name: "Groq",
    baseUrl: "https://api.groq.com/openai/v1",
    suggestedModels: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    keyPlaceholder: "gsk_...",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
    suggestedModels: ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
    keyPlaceholder: "sk-...",
  },
  {
    id: "custom",
    name: "Custom OpenAI-Compatible",
    baseUrl: "",
    suggestedModels: [],
    keyPlaceholder: "API key or token",
  },
];

/**
 * Compact settings dialog component for Dot HUD.
 * Complies with ASD-STE100 rules.
 */
export default function SettingsModal({ isOpen, onClose, onSettingsSaved }) {
  const [activeTab, setActiveTab] = useState("model");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const [backend, setBackend] = useState("cuda");
  const [selectedTier, setSelectedTier] = useState("4B");
  const [browserHeadless, setBrowserHeadless] = useState(false);

  const [cloudProvider, setCloudProvider] = useState("gemini");
  const [cloudBaseUrl, setCloudBaseUrl] = useState("https://generativelanguage.googleapis.com/v1beta/openai/");
  const [cloudModel, setCloudModel] = useState("gemini-2.5-flash");
  const [cloudApiKey, setCloudApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  const [githubToken, setGithubToken] = useState("");
  const [showGithubToken, setShowGithubToken] = useState(false);
  const [mcpServers, setMcpServers] = useState([]);
  const [mcpSyncing, setMcpSyncing] = useState(false);
  const [mcpSyncStatus, setMcpSyncStatus] = useState(null);

  const [engineStatus, setEngineStatus] = useState({ running: false, port: 11434, command: "" });
  const [engineLoading, setEngineLoading] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setLoading(true);
    setErrorMessage("");
    setSaveSuccess(false);

    async function fetchSettings() {
      try {
        const [settingsRes, serversRes, engineRes] = await Promise.all([
          fetch("http://localhost:3000/api/settings"),
          fetch("http://localhost:3000/api/mcp/servers"),
          fetch("http://localhost:3000/api/engine/status").catch(() => null),
        ]);

        if (engineRes && engineRes.ok) {
          const eData = await engineRes.json();
          if (isMounted) setEngineStatus(eData);
        }

        if (settingsRes.ok) {
          const data = await settingsRes.json();
          if (isMounted) {
            const active = data.active_settings || {};
            const cloud = data.cloud || {};
            setBackend(active.backend || "cuda");
            setSelectedTier(active.selected_tier || "4B");
            setBrowserHeadless(Boolean(active.browser_headless));

            setCloudProvider(cloud.provider || "gemini");
            setCloudBaseUrl(cloud.base_url || "https://generativelanguage.googleapis.com/v1beta/openai/");
            setCloudModel(cloud.model || "gemini-2.5-flash");
            setCloudApiKey(cloud.api_key || "");
            setGithubToken(data.github_token || "");
          }
        }

        if (serversRes.ok) {
          const sData = await serversRes.json();
          if (isMounted) {
            setMcpServers(sData.servers || []);
          }
        }
      } catch (err) {
        if (isMounted) {
          setErrorMessage("Failed to load settings. Verify backend server is active.");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchSettings();

    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      isMounted = false;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  const handleSelectProvider = (presetId) => {
    setCloudProvider(presetId);
    const preset = PROVIDER_PRESETS.find((p) => p.id === presetId);
    if (preset) {
      if (preset.baseUrl) setCloudBaseUrl(preset.baseUrl);
      if (preset.suggestedModels?.length > 0) {
        setCloudModel(preset.suggestedModels[0]);
      }
    }
  };

  const fetchEngineStatus = async () => {
    try {
      const res = await fetch("http://localhost:3000/api/engine/status");
      if (res.ok) {
        const data = await res.json();
        setEngineStatus(data);
      }
    } catch (e) {
      console.warn("Engine status check warning:", e);
    }
  };

  const handleToggleEngine = async () => {
    setEngineLoading(true);
    try {
      const endpoint = engineStatus.running ? "/api/engine/stop" : "/api/engine/start";
      await fetch(`http://localhost:3000${endpoint}`, { method: "POST" });
      setTimeout(fetchEngineStatus, 1000);
    } catch (err) {
      console.warn("Engine toggle warning:", err);
    } finally {
      setEngineLoading(false);
    }
  };

  const handleCopyCommand = () => {
    const cmd = engineStatus.command || `bin\\llama-server.exe -m gemma-4-E${selectedTier}_q4_0-it.gguf --port 11434`;
    navigator.clipboard.writeText(cmd);
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 2000);
  };

  const handleSave = async () => {
    setSaving(true);
    setErrorMessage("");
    setSaveSuccess(false);

    try {
      const payload = {
        backend,
        selected_tier: selectedTier,
        browser_headless: browserHeadless,
        cloud: {
          provider: cloudProvider,
          base_url: cloudBaseUrl.trim(),
          model: cloudModel.trim(),
          api_key: cloudApiKey.trim(),
        },
        cloud_provider: cloudProvider,
        cloud_base_url: cloudBaseUrl.trim(),
        cloud_model: cloudModel.trim(),
        cloud_api_key: cloudApiKey.trim(),
        github_token: githubToken.trim(),
      };

      const res = await fetch("http://localhost:3000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setSaveSuccess(true);
        if (onSettingsSaved) onSettingsSaved(payload);
        setTimeout(() => {
          onClose();
        }, 600);
      } else {
        const errData = await res.json().catch(() => ({}));
        setErrorMessage(errData.detail || "Failed to persist configuration.");
      }
    } catch (err) {
      setErrorMessage(`Network error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSyncMcp = async () => {
    setMcpSyncing(true);
    setMcpSyncStatus(null);

    try {
      await fetch("http://localhost:3000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_token: githubToken.trim() }),
      });

      const res = await fetch("http://localhost:3000/api/mcp/sync", {
        method: "POST",
      });
      const data = await res.json();
      if (data.status === "ok") {
        setMcpSyncStatus({
          type: "success",
          message: `Synchronized successfully. Active: ${(data.services || []).join(", ") || "tools ready"}`,
        });
      } else {
        setMcpSyncStatus({
          type: "error",
          message: data.message || "Synchronization failed",
        });
      }
    } catch (err) {
      setMcpSyncStatus({
        type: "error",
        message: `Sync failed: ${err.message}`,
      });
    } finally {
      setMcpSyncing(false);
    }
  };

  if (!isOpen) return null;

  const currentPreset = PROVIDER_PRESETS.find((p) => p.id === cloudProvider) || PROVIDER_PRESETS[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150 select-none">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full max-w-[416px] bg-[#18181b] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[500px] z-10 text-zinc-200 text-xs">
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-zinc-800/80 bg-[#16161a]">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.488.488 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xs font-semibold text-white tracking-tight">Dot Settings</h2>
              <p className="text-[10px] text-zinc-400">Configure model engine, browser, and MCP tools.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-6 h-6 rounded-lg flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
            title="Close"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center px-3 border-b border-zinc-800 bg-[#141418] text-[11px] font-medium">
          <button
            type="button"
            onClick={() => setActiveTab("model")}
            className={`py-2 px-2.5 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "model"
                ? "border-[#FF5A5F] text-white bg-white/5"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="9" y="9" width="6" height="6" />
              <line x1="9" y1="1" x2="9" y2="4" />
              <line x1="15" y1="1" x2="15" y2="4" />
            </svg>
            <span>Model & Engine</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("browser")}
            className={`py-2 px-2.5 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "browser"
                ? "border-[#FF5A5F] text-white bg-white/5"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            <span>Browser Mode</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("mcp")}
            className={`py-2 px-2.5 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "mcp"
                ? "border-[#FF5A5F] text-white bg-white/5"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>MCP Tools</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto chat-scroll p-3 space-y-2.5 text-xs font-sans max-h-[380px]">
          {loading && (
            <div className="py-8 text-center text-zinc-400 font-mono text-[11px] animate-pulse">
              Loading active configuration...
            </div>
          )}

          {errorMessage && (
            <div className="p-2.5 bg-red-950/40 border border-red-800/80 rounded-xl text-red-200 text-[10.5px] font-mono">
              {errorMessage}
            </div>
          )}

          {!loading && activeTab === "model" && (
            <div className="space-y-2.5">
              <div>
                <label className="block text-[10.5px] font-semibold text-zinc-300 uppercase tracking-wider mb-1">
                  Inference Mode
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setBackend("cuda")}
                    className={`p-2 rounded-xl border text-left transition-all cursor-pointer ${
                      backend !== "cloud"
                        ? "bg-indigo-600/15 border-indigo-500 text-white shadow-sm"
                        : "bg-[#18181c] border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="font-semibold text-xs flex items-center justify-between">
                      <span>Local llama-server</span>
                      {backend !== "cloud" && <span className="text-[10px] text-indigo-400 font-mono">Active</span>}
                    </div>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      Private offline inference on local GPU/CPU hardware.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => setBackend("cloud")}
                    className={`p-2 rounded-xl border text-left transition-all cursor-pointer ${
                      backend === "cloud"
                        ? "bg-indigo-600/15 border-indigo-500 text-white shadow-sm"
                        : "bg-[#18181c] border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="font-semibold text-xs flex items-center justify-between">
                      <span>Cloud API Endpoint</span>
                      {backend === "cloud" && <span className="text-[10px] text-indigo-400 font-mono">Active</span>}
                    </div>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      High-throughput cloud models (Google Gemini, OpenAI, Groq).
                    </p>
                  </button>
                </div>
              </div>

              {backend !== "cloud" && (
                <div className="p-2.5 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-2.5">
                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1">
                      Model Tier Selection
                    </label>
                    <select
                      value={selectedTier}
                      onChange={(e) => setSelectedTier(e.target.value)}
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-indigo-500"
                    >
                      <option value="2B">2B Tier (google/gemma-4-E2B - Fastest, 8K Context)</option>
                      <option value="4B">4B Tier (google/gemma-4-E4B - Balanced, 8K Context)</option>
                      <option value="12B">12B Tier (google/gemma-4-E12B - Reasoning, 4K Context)</option>
                    </select>
                  </div>

                  {/* Engine Controller & Click-to-Run Command Card */}
                  <div className="p-2 bg-[#101013] border border-zinc-800 rounded-lg space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            engineStatus.running ? "bg-emerald-400 animate-pulse" : "bg-zinc-600"
                          }`}
                        />
                        <span className="text-[11px] font-medium text-zinc-200">
                          {engineStatus.running ? `Engine Running (Port ${engineStatus.port || 11434})` : "Engine Stopped"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={handleToggleEngine}
                        disabled={engineLoading}
                        className={`px-2 py-0.5 rounded text-[10px] font-medium cursor-pointer transition-colors ${
                          engineStatus.running
                            ? "bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30"
                            : "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/30"
                        }`}
                      >
                        {engineLoading ? "Working..." : engineStatus.running ? "Stop Engine" : "Run Local Model"}
                      </button>
                    </div>

                    <div>
                      <div className="flex items-center justify-between text-[9.5px] text-zinc-400 mb-1">
                        <span>Terminal Command:</span>
                        <button
                          type="button"
                          onClick={handleCopyCommand}
                          className="text-indigo-400 hover:text-indigo-300 cursor-pointer flex items-center gap-1 font-medium"
                        >
                          {copiedCmd ? "Copied!" : "Copy Command"}
                        </button>
                      </div>
                      <div className="p-1.5 bg-[#09090b] rounded border border-zinc-800/80 font-mono text-[9px] text-zinc-300 break-all select-all">
                        {engineStatus.command || `bin\\llama-server.exe -m gemma-4-E${selectedTier}_q4_0-it.gguf --port 11434`}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-[10.5px] font-mono text-zinc-400 pt-0.5">
                    <span>Acceleration Backend:</span>
                    <span className="uppercase text-zinc-200 font-semibold">{backend}</span>
                  </div>
                </div>
              )}

              {backend === "cloud" && (
                <div className="p-2.5 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-2.5">
                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1">
                      Cloud Provider Preset
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {PROVIDER_PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectProvider(preset.id)}
                          className={`px-2 py-1 rounded-md text-[10.5px] font-medium transition-all cursor-pointer ${
                            cloudProvider === preset.id
                              ? "bg-indigo-600 text-white shadow-sm"
                              : "bg-[#101013] border border-zinc-700/80 text-zinc-300 hover:border-zinc-600"
                          }`}
                        >
                          {preset.name}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1">
                      Endpoint Base URL
                    </label>
                    <input
                      type="text"
                      value={cloudBaseUrl}
                      onChange={(e) => setCloudBaseUrl(e.target.value)}
                      placeholder="https://generativelanguage.googleapis.com/v1beta/openai/"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[10.5px] font-medium text-zinc-300">
                        Model Identifier
                      </label>
                      <span className="text-[9.5px] text-zinc-500 font-mono">Customizable</span>
                    </div>
                    <input
                      type="text"
                      value={cloudModel}
                      onChange={(e) => setCloudModel(e.target.value)}
                      placeholder="e.g. gemini-2.5-flash, gpt-4o, deepseek-chat"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-indigo-500"
                    />

                    {currentPreset?.suggestedModels?.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1 mt-1.5">
                        <span className="text-[9.5px] text-zinc-500 font-mono">Suggested:</span>
                        {currentPreset.suggestedModels.map((sm) => (
                          <button
                            key={sm}
                            type="button"
                            onClick={() => setCloudModel(sm)}
                            className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-zinc-700/60 cursor-pointer"
                          >
                            {sm}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1">
                      API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        value={cloudApiKey}
                        onChange={(e) => setCloudApiKey(e.target.value)}
                        placeholder={currentPreset?.keyPlaceholder || "sk-..."}
                        className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg pl-2.5 pr-9 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-indigo-500"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 text-[10px] px-1 py-0.5 cursor-pointer font-mono"
                        title={showApiKey ? "Hide key" : "Show key"}
                      >
                        {showApiKey ? "Hide" : "Show"}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && activeTab === "browser" && (
            <div className="space-y-2.5">
              <div className="p-3 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Headless Browser Mode</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      {browserHeadless
                        ? "Headless: Playwright automates silently without opening a visible window."
                        : "Visible GUI: Connects to a visible Chrome or Edge window on desktop."}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setBrowserHeadless(!browserHeadless)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      browserHeadless ? "bg-indigo-600" : "bg-zinc-700"
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                        browserHeadless ? "translate-x-4" : "translate-x-0"
                      }`}
                    />
                  </button>
                </div>
                <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between text-[10.5px] font-mono text-zinc-400">
                  <span>CDP Port 9222 Integration:</span>
                  <span className={browserHeadless ? "text-zinc-500" : "text-emerald-400 font-semibold"}>
                    {browserHeadless ? "Disabled in Headless" : "Active (Bypasses fresh launch)"}
                  </span>
                </div>
              </div>
            </div>
          )}

          {!loading && activeTab === "mcp" && (
            <div className="space-y-2.5">
              <div className="p-3 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">GitHub Personal Access Token</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">Required for GitHub repository and issue tools.</p>
                  </div>
                  <span className={`text-[9.5px] font-mono px-1.5 py-0.2 rounded border ${githubToken ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-amber-500/15 text-amber-400 border-amber-500/30"}`}>
                    {githubToken ? "Configured" : "Token Missing"}
                  </span>
                </div>

                <div className="relative">
                  <input
                    type={showGithubToken ? "text" : "password"}
                    value={githubToken}
                    onChange={(e) => setGithubToken(e.target.value)}
                    placeholder="ghp_... or github_pat_..."
                    className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg pl-2.5 pr-9 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-indigo-500"
                  />
                  <button
                    type="button"
                    onClick={() => setShowGithubToken(!showGithubToken)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 text-[10px] px-1 py-0.5 cursor-pointer font-mono"
                    title={showGithubToken ? "Hide token" : "Show token"}
                  >
                    {showGithubToken ? "Hide" : "Show"}
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-[10.5px] font-semibold text-zinc-300 uppercase tracking-wider">
                    Configured MCP Servers
                  </label>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {mcpServers.length} active
                  </span>
                </div>

                <div className="space-y-1.5">
                  {mcpServers.map((server) => (
                    <div
                      key={server}
                      className="px-2.5 py-1.5 bg-[#16161a] border border-zinc-800/90 rounded-lg flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        <span className="font-semibold text-zinc-200">{server}</span>
                      </div>
                      <span className="text-[9.5px] font-mono text-zinc-500 bg-zinc-800/70 px-1.5 py-0.2 rounded">
                        stdio
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Sync Tool Registry</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      Fetch fresh schemas and reindex ChromaDB.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncMcp}
                    disabled={mcpSyncing}
                    className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white rounded-lg text-xs font-medium transition-all disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
                  >
                    {mcpSyncing && (
                      <span className="w-2.5 h-2.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    )}
                    <span>{mcpSyncing ? "Syncing..." : "Sync Tools"}</span>
                  </button>
                </div>

                {mcpSyncStatus && (
                  <div
                    className={`p-2 rounded-lg text-[10px] font-mono ${
                      mcpSyncStatus.type === "success"
                        ? "bg-emerald-950/40 border border-emerald-800/80 text-emerald-200"
                        : "bg-red-950/40 border border-red-800/80 text-red-200"
                    }`}
                  >
                    {mcpSyncStatus.message}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-3.5 py-2.5 border-t border-zinc-800/80 bg-[#141418]">
          <div>
            {saveSuccess && (
              <span className="text-[11px] text-emerald-400 font-medium animate-in fade-in">
                Saved successfully
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white transition-all disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              {saving && (
                <span className="w-2.5 h-2.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              <span>{saving ? "Saving..." : "Save Settings"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

