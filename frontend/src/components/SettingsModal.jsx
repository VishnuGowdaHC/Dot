import { useState, useEffect } from "react";

const PROVIDER_PRESETS = [
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

export default function SettingsModal({ isOpen, onClose, onSettingsSaved }) {
  const [activeTab, setActiveTab] = useState("model");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // Settings state
  const [backend, setBackend] = useState("cuda"); // "cuda" | "cpu" | "cloud"
  const [selectedTier, setSelectedTier] = useState("4B"); // "2B" | "4B" | "12B"
  const [browserHeadless, setBrowserHeadless] = useState(false);
  
  // Cloud settings state
  const [cloudProvider, setCloudProvider] = useState("openai");
  const [cloudBaseUrl, setCloudBaseUrl] = useState("https://api.openai.com/v1");
  const [cloudModel, setCloudModel] = useState("gpt-4o-mini");
  const [cloudApiKey, setCloudApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  // MCP & GitHub PAT state
  const [githubToken, setGithubToken] = useState("");
  const [showGithubToken, setShowGithubToken] = useState(false);
  const [mcpServers, setMcpServers] = useState([]);
  const [mcpSyncing, setMcpSyncing] = useState(false);
  const [mcpSyncStatus, setMcpSyncStatus] = useState(null);

  // Load current settings from backend on open
  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setLoading(true);
    setErrorMessage("");
    setSaveSuccess(false);

    async function fetchSettings() {
      try {
        const [settingsRes, serversRes] = await Promise.all([
          fetch("http://localhost:3000/api/settings"),
          fetch("http://localhost:3000/api/mcp/servers")
        ]);

        if (settingsRes.ok) {
          const data = await settingsRes.json();
          if (isMounted) {
            const active = data.active_settings || {};
            const cloud = data.cloud || {};
            setBackend(active.backend || "cuda");
            setSelectedTier(active.selected_tier || "4B");
            setBrowserHeadless(Boolean(active.browser_headless));

            setCloudProvider(cloud.provider || "openai");
            setCloudBaseUrl(cloud.base_url || "https://api.openai.com/v1");
            setCloudModel(cloud.model || "gpt-4o-mini");
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
          setErrorMessage("Failed to load settings. Is the server running?");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchSettings();

    // Close on Escape key
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      isMounted = false;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Handle provider preset selection
  const handleSelectProvider = (presetId) => {
    setCloudProvider(presetId);
    const preset = PROVIDER_PRESETS.find((p) => p.id === presetId);
    if (preset) {
      if (preset.baseUrl) {
        setCloudBaseUrl(preset.baseUrl);
      }
      if (preset.suggestedModels?.length > 0 && (!cloudModel || cloudModel === "dot-engine")) {
        setCloudModel(preset.suggestedModels[0]);
      }
    }
  };

  // Save updated settings to backend
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
        github_token: githubToken.trim(),
      };

      const res = await fetch("http://localhost:3000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      setSaveSuccess(true);
      if (onSettingsSaved) {
        onSettingsSaved(payload);
      }
      setTimeout(() => {
        setSaveSuccess(false);
        onClose();
      }, 700);
    } catch (err) {
      setErrorMessage(`Failed to save settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  // Trigger MCP Tool synchronization
  const handleSyncMcp = async () => {
    setMcpSyncing(true);
    setMcpSyncStatus(null);
    try {
      // Persist the token first so MCP servers use fresh credentials
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
          message: `Synchronized successfully! Active services: ${(data.services || []).join(", ") || "tools ready"}`,
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

  const currentPreset = PROVIDER_PRESETS.find((p) => p.id === cloudProvider) || PROVIDER_PRESETS[PROVIDER_PRESETS.length - 1];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150 select-none">
      {/* Click outside backdrop */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Modal Dialog Card */}
      <div className="relative w-full max-w-xl bg-[#121215] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] z-10 text-zinc-200">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-[#16161a]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.488.488 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/>
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-white tracking-tight">Dot Settings</h2>
              <p className="text-xs text-zinc-400">Configure model engine, browser automation, and MCP tools.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center px-6 border-b border-zinc-800 bg-[#141418] text-xs font-medium">
          <button
            type="button"
            onClick={() => setActiveTab("model")}
            className={`py-3 px-3 border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "model"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>🤖</span>
            <span>Model & Engine</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("browser")}
            className={`py-3 px-3 border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "browser"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>🌐</span>
            <span>Browser Mode</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("mcp")}
            className={`py-3 px-3 border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "mcp"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>⚡</span>
            <span>MCP Tools</span>
          </button>
        </div>

        {/* Modal Body / Tab Contents */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 text-sm">
          
          {loading && (
            <div className="py-12 text-center text-zinc-400 font-mono text-xs animate-pulse">
              Loading active configuration...
            </div>
          )}

          {errorMessage && (
            <div className="p-3 bg-red-950/40 border border-red-800/80 rounded-xl text-red-200 text-xs font-mono">
              {errorMessage}
            </div>
          )}

          {!loading && activeTab === "model" && (
            <div className="space-y-5 animate-in fade-in duration-100">
              
              {/* Primary Backend Switcher (Local vs Cloud) */}
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2">
                  Inference Mode
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setBackend("cuda")}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      backend !== "cloud"
                        ? "bg-indigo-600/15 border-indigo-500 text-white shadow-[0_0_12px_rgba(99,102,241,0.25)]"
                        : "bg-[#18181c] border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    }`}
                  >
                    <div className="font-semibold text-sm flex items-center justify-between">
                      <span>Local llama-server</span>
                      {backend !== "cloud" && <span className="text-xs text-indigo-400 font-mono">Active</span>}
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">
                      Private offline inference on your GPU/CPU hardware.
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => setBackend("cloud")}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      backend === "cloud"
                        ? "bg-indigo-600/15 border-indigo-500 text-white shadow-[0_0_12px_rgba(99,102,241,0.25)]"
                        : "bg-[#18181c] border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
                    }`}
                  >
                    <div className="font-semibold text-sm flex items-center justify-between">
                      <span>Cloud API Endpoint</span>
                      {backend === "cloud" && <span className="text-xs text-indigo-400 font-mono">Active</span>}
                    </div>
                    <p className="text-xs text-zinc-400 mt-1">
                      High-throughput cloud models (OpenAI, OpenRouter, Groq).
                    </p>
                  </button>
                </div>
              </div>

              {/* Local Hardware Configuration */}
              {backend !== "cloud" && (
                <div className="p-4 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                      Model Tier Selection
                    </label>
                    <select
                      value={selectedTier}
                      onChange={(e) => setSelectedTier(e.target.value)}
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-xl px-3 py-2 text-sm text-zinc-100 outline-none focus:border-indigo-500"
                    >
                      <option value="2B">2B Tier (google/gemma-4-E2B - Fastest, 8K Context)</option>
                      <option value="4B">4B Tier (google/gemma-4-E4B - Balanced, 8K Context)</option>
                      <option value="12B">12B Tier (google/gemma-4-E12B - Reasoning, 4K Context)</option>
                    </select>
                  </div>

                  <div className="flex items-center justify-between text-xs font-mono text-zinc-400 pt-1">
                    <span>Acceleration Backend:</span>
                    <span className="uppercase text-zinc-200 font-semibold">{backend}</span>
                  </div>
                </div>
              )}

              {/* Cloud API Configuration */}
              {backend === "cloud" && (
                <div className="p-4 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-4">
                  {/* Preset Provider Selector */}
                  <div>
                    <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                      Cloud Provider Preset
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {PROVIDER_PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectProvider(preset.id)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
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

                  {/* Base URL Input */}
                  <div>
                    <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                      Endpoint Base URL
                    </label>
                    <input
                      type="text"
                      value={cloudBaseUrl}
                      onChange={(e) => setCloudBaseUrl(e.target.value)}
                      placeholder="https://api.openai.com/v1"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-xl px-3 py-2 text-sm text-zinc-100 font-mono outline-none focus:border-indigo-500"
                    />
                  </div>

                  {/* Free-form Model Name Input (Not hardcoded) */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="block text-xs font-medium text-zinc-300">
                        Model Identifier / Name
                      </label>
                      <span className="text-[11px] text-zinc-500">Fully customizable</span>
                    </div>
                    <input
                      type="text"
                      value={cloudModel}
                      onChange={(e) => setCloudModel(e.target.value)}
                      placeholder="e.g. gpt-4o, claude-3-5-sonnet, deepseek-chat"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-xl px-3 py-2 text-sm text-zinc-100 font-mono outline-none focus:border-indigo-500"
                    />

                    {/* Quick suggestion chips */}
                    {currentPreset?.suggestedModels?.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 mt-2">
                        <span className="text-[10px] text-zinc-500 font-mono">Suggested:</span>
                        {currentPreset.suggestedModels.map((sm) => (
                          <button
                            key={sm}
                            type="button"
                            onClick={() => setCloudModel(sm)}
                            className="px-2 py-0.5 rounded text-[11px] font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-zinc-700/60"
                          >
                            {sm}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* API Key Input with Eye Toggle */}
                  <div>
                    <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                      API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        value={cloudApiKey}
                        onChange={(e) => setCloudApiKey(e.target.value)}
                        placeholder={currentPreset?.keyPlaceholder || "sk-..."}
                        className="w-full bg-[#101013] border border-zinc-700/80 rounded-xl pl-3 pr-10 py-2 text-sm text-zinc-100 font-mono outline-none focus:border-indigo-500"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 text-xs px-1 py-0.5"
                        title={showApiKey ? "Hide key" : "Show key"}
                      >
                        {showApiKey ? "Hide" : "Show"}
                      </button>
                    </div>
                    <p className="text-[11px] text-zinc-500 mt-1">
                      Your key is stored locally in appConfig.json and never logged.
                    </p>
                  </div>
                </div>
              )}

            </div>
          )}

          {!loading && activeTab === "browser" && (
            <div className="space-y-5 animate-in fade-in duration-100">
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2">
                  Browser Automation Execution
                </label>
                <div className="p-4 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-100">Headless Browser Mode</h3>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {browserHeadless
                          ? "Headless: Playwright automates silently without opening a visible window."
                          : "Visible GUI: Launches or connects to a visible Chrome/Edge browser window."}
                      </p>
                    </div>
                    {/* Toggle Switch */}
                    <button
                      type="button"
                      onClick={() => setBrowserHeadless(!browserHeadless)}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        browserHeadless ? "bg-indigo-600" : "bg-zinc-700"
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          browserHeadless ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  <div className="pt-3 border-t border-zinc-800/80 flex items-center justify-between text-xs font-mono text-zinc-400">
                    <span>CDP Port 9222 Integration:</span>
                    <span className={browserHeadless ? "text-zinc-500" : "text-emerald-400 font-semibold"}>
                      {browserHeadless ? "Disabled in Headless" : "Active (Bypasses fresh launch)"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {!loading && activeTab === "mcp" && (
            <div className="space-y-5 animate-in fade-in duration-100">
              
              {/* GitHub MCP Configuration */}
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-2">
                  GitHub MCP Credentials
                </label>
                <div className="p-4 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-300">
                        <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                          <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold text-zinc-100">Personal Access Token (PAT)</h3>
                        <p className="text-xs text-zinc-400 mt-0.5">Required for GitHub MCP tools (issues, PRs, repos, commits).</p>
                      </div>
                    </div>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${githubToken ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-amber-500/15 text-amber-400 border-amber-500/30"}`}>
                      {githubToken ? "Configured" : "Token Missing"}
                    </span>
                  </div>

                  <div className="relative">
                    <input
                      type={showGithubToken ? "text" : "password"}
                      value={githubToken}
                      onChange={(e) => setGithubToken(e.target.value)}
                      placeholder="ghp_... or github_pat_..."
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-xl pl-3 pr-10 py-2 text-sm text-zinc-100 font-mono outline-none focus:border-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => setShowGithubToken(!showGithubToken)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 text-xs px-1 py-0.5 cursor-pointer"
                      title={showGithubToken ? "Hide token" : "Show token"}
                    >
                      {showGithubToken ? "Hide" : "Show"}
                    </button>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-1">
                    <span>Stored locally in .env and appConfig.json</span>
                    <a
                      href="https://github.com/settings/tokens"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-400 hover:underline flex items-center gap-1"
                    >
                      Generate token on GitHub ↗
                    </a>
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                    Configured MCP Servers
                  </label>
                  <span className="text-xs font-mono text-zinc-400">
                    {mcpServers.length} servers active
                  </span>
                </div>

                <div className="space-y-2">
                  {mcpServers.map((server) => (
                    <div
                      key={server}
                      className="p-3 bg-[#16161a] border border-zinc-800/90 rounded-xl flex items-center justify-between text-sm"
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                        <span className="font-semibold text-zinc-200">{server}</span>
                      </div>
                      <span className="text-xs font-mono text-zinc-500 bg-zinc-800/70 px-2 py-0.5 rounded">
                        stdio
                      </span>
                    </div>
                  ))}
                  {mcpServers.length === 0 && (
                    <div className="p-4 text-center text-xs text-zinc-500 font-mono">
                      No MCP servers found in config.
                    </div>
                  )}
                </div>
              </div>

              {/* Sync Action Section */}
              <div className="p-4 bg-[#16161a] border border-zinc-800/90 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-zinc-100">Sync Tool Registry</h3>
                    <p className="text-xs text-zinc-400 mt-0.5">
                      Fetch fresh schemas from running servers and reindex ChromaDB.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncMcp}
                    disabled={mcpSyncing}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white rounded-xl text-xs font-medium transition-all disabled:opacity-50 flex items-center gap-2 cursor-pointer shadow-sm"
                  >
                    {mcpSyncing && (
                      <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    )}
                    <span>{mcpSyncing ? "Syncing..." : "Sync & Reload Tools"}</span>
                  </button>
                </div>

                {mcpSyncStatus && (
                  <div
                    className={`p-2.5 rounded-lg text-xs font-mono ${
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
        <div className="flex items-center justify-between px-6 py-3.5 border-t border-zinc-800/80 bg-[#141418]">
          <div>
            {saveSuccess && (
              <span className="text-xs text-emerald-400 font-medium flex items-center gap-1.5 animate-in fade-in">
                <span>✓</span> Settings saved & clients reloaded
              </span>
            )}
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 rounded-xl text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 rounded-xl text-xs font-medium bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white transition-all disabled:opacity-50 flex items-center gap-2 cursor-pointer shadow-[0_0_12px_rgba(99,102,241,0.3)]"
            >
              {saving && (
                <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              <span>{saving ? "Saving..." : "Save Settings"}</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}

