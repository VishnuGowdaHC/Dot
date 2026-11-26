import { useState, useEffect, useCallback, useRef } from "react";

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
export default function SettingsModal({ isOpen, onClose, onSettingsSaved, initialTab = "model" }) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [updateInfo, setUpdateInfo] = useState(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [updateMessage, setUpdateMessage] = useState(null);
  const [updateProgress, setUpdateProgress] = useState(null);
  const updatePollRef = useRef(null);

  useEffect(() => {
    if (isOpen && initialTab) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab]);

  const [backend, setBackend] = useState("cuda");
  const [selectedTier, setSelectedTier] = useState("4B");
  const [browserHeadless, setBrowserHeadless] = useState(false);
  const [browserProfileMode, setBrowserProfileMode] = useState("persistent");
  const [browserProfileName, setBrowserProfileName] = useState("Default");
  const [chromeProfiles, setChromeProfiles] = useState([]);
  const [verifyingBrowser, setVerifyingBrowser] = useState(false);
  const [browserVerifyStatus, setBrowserVerifyStatus] = useState(null);
  const [installedApps, setInstalledApps] = useState([]);
  const [allowedProcesses, setAllowedProcesses] = useState([]);
  const [appSearch, setAppSearch] = useState("");
  const [customAppInput, setCustomAppInput] = useState("");

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

  const [engineStatus, setEngineStatus] = useState({
    state: "stopped",
    running: false,
    healthy: false,
    port: 11434,
    tier: "4B",
    model: "",
    context_size: 8192,
    detail: "Local inference engine is stopped.",
    last_log: "",
    error: null,
    command: "",
  });
  const [engineLoading, setEngineLoading] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [showEngineLogs, setShowEngineLogs] = useState(false);
  const [engineLogs, setEngineLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const copyTimerRef = useRef(null);
  const closeTimerRef = useRef(null);
  const engineRefreshTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
      if (engineRefreshTimerRef.current) clearTimeout(engineRefreshTimerRef.current);
      if (updatePollRef.current) clearInterval(updatePollRef.current);
    };
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setLoading(true);
    setErrorMessage("");
    setSaveSuccess(false);

    async function fetchSettings() {
      try {
        const [settingsResult, serversResult, profilesResult, appsResult] = await Promise.allSettled([
          fetch("http://localhost:3000/api/settings"),
          fetch("http://localhost:3000/api/mcp/servers"),
          fetch("http://localhost:3000/api/browser/profiles"),
          fetch("http://localhost:3000/api/apps/installed"),
        ]);

        if (settingsResult.status === "fulfilled" && settingsResult.value.ok) {
          const data = await settingsResult.value.json();
          if (isMounted) {
            const active = data.active_settings || {};
            const cloud = data.cloud || {};
            setBackend(active.backend || "cuda");
            setSelectedTier(active.selected_tier || "4B");
            setBrowserHeadless(Boolean(active.browser_headless));
            setBrowserProfileMode(active.browser_profile_mode || "persistent");
            setBrowserProfileName(active.browser_profile_name || "Default");

            setCloudProvider(cloud.provider || "gemini");
            setCloudBaseUrl(cloud.base_url || "https://generativelanguage.googleapis.com/v1beta/openai/");
            setCloudModel(cloud.model || "gemini-2.5-flash");
            setCloudApiKey(cloud.api_key || "");
            setGithubToken(data.github_token || "");
            setAllowedProcesses(Array.isArray(data.allowed_processes) ? data.allowed_processes : []);
          }
        } else if (isMounted) {
          setErrorMessage("Failed to load settings. Verify backend server is active.");
        }

        if (serversResult.status === "fulfilled" && serversResult.value.ok) {
          const sData = await serversResult.value.json();
          if (isMounted) {
            setMcpServers(sData.servers || []);
          }
        }

        if (profilesResult.status === "fulfilled" && profilesResult.value.ok) {
          const pData = await profilesResult.value.json();
          if (isMounted) {
            setChromeProfiles(pData.profiles || []);
          }
        }

        if (appsResult.status === "fulfilled" && appsResult.value.ok) {
          const aData = await appsResult.value.json();
          if (isMounted) {
            setInstalledApps(aData.installed || []);
            if (Array.isArray(aData.allowed)) {
              setAllowedProcesses(aData.allowed);
            }
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

  const fetchEngineStatus = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:3000/api/engine/status");
      if (res.ok) {
        const data = await res.json();
        setEngineStatus(data);
        return data;
      }
    } catch (e) {
      console.warn("Engine status check warning:", e);
    }
    return null;
  }, []);

  // Adaptive polling loop while settings modal is open in local mode on the model tab
  useEffect(() => {
    if (!isOpen || backend === "cloud" || activeTab !== "model") return;

    let timer = null;
    let isMounted = true;

    const poll = async () => {
      const data = await fetchEngineStatus();
      if (!isMounted) return;

      const isBusy = data?.state === "starting" || data?.state === "loading";
      const delay = isBusy ? 800 : 4000;
      timer = setTimeout(poll, delay);
    };

    poll();

    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
  }, [isOpen, backend, activeTab, fetchEngineStatus]);

  const handleToggleEngine = async () => {
    setEngineLoading(true);
    try {
      const isRunning =
        engineStatus.running ||
        engineStatus.state === "ready" ||
        engineStatus.state === "loading";
      const endpoint = isRunning ? "/api/engine/stop" : "/api/engine/start";
      const res = await fetch(`http://localhost:3000${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier: selectedTier }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status === "error") {
          setEngineStatus((prev) => ({
            ...prev,
            state: "error",
            running: false,
            healthy: false,
            detail: data.message || "Failed to start local engine.",
            error: data.message || "Engine startup error.",
          }));
          return;
        }

        if (!isRunning) {
          setEngineStatus((prev) => ({
            ...prev,
            state: "starting",
            running: true,
            healthy: false,
            detail: data.message || "Starting engine process...",
            error: null,
          }));
        } else {
          setEngineStatus((prev) => ({
            ...prev,
            state: "stopped",
            running: false,
            healthy: false,
            detail: data.message || "Engine stopped.",
            error: null,
          }));
        }
      }
      if (engineRefreshTimerRef.current) clearTimeout(engineRefreshTimerRef.current);
      engineRefreshTimerRef.current = setTimeout(fetchEngineStatus, 500);
    } catch (err) {
      console.warn("Engine toggle warning:", err);
      setEngineStatus((prev) => ({
        ...prev,
        state: "error",
        running: false,
        healthy: false,
        detail: "Connection to backend server failed.",
        error: String(err),
      }));
    } finally {
      setEngineLoading(false);
    }
  };

  const toggleEngineLogs = async () => {
    if (!showEngineLogs) {
      setLoadingLogs(true);
      try {
        const res = await fetch("http://localhost:3000/api/engine/logs?lines=30");
        if (res.ok) {
          const data = await res.json();
          setEngineLogs(data.lines || []);
        }
      } catch (err) {
        console.warn("Failed to load engine logs:", err);
      } finally {
        setLoadingLogs(false);
      }
    }
    setShowEngineLogs((prev) => !prev);
  };

  const handleCopyCommand = async () => {
    const cmd = engineStatus.command || `bin\\llama-server.exe -m gemma-4-E${selectedTier}_q4_0-it.gguf --port 11434`;
    try {
      await navigator.clipboard.writeText(cmd);
      setCopiedCmd(true);
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => setCopiedCmd(false), 2000);
    } catch (err) {
      console.warn("Clipboard write warning:", err);
    }
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
        browser_profile_mode: browserProfileMode,
        browser_profile_name: browserProfileName,
        allowed_processes: allowedProcesses,
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
        if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
        closeTimerRef.current = setTimeout(() => {
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

  const handleCheckUpdate = async () => {
    setCheckingUpdate(true);
    setUpdateMessage(null);
    try {
      const res = await fetch("http://localhost:3000/api/update/check");
      const data = await res.json();
      setUpdateInfo(data);
      if (data.status === "error") {
        setUpdateMessage({ type: "error", text: data.error || "Failed to check updates." });
      } else if (!data.update_available) {
        setUpdateMessage({ type: "success", text: `Dot v${data.current_version} is up to date.` });
      }
    } catch (err) {
      setUpdateMessage({ type: "error", text: `Update check failed: ${err.message}` });
    } finally {
      setCheckingUpdate(false);
    }
  };

  const stopUpdatePolling = () => {
    if (updatePollRef.current) {
      clearInterval(updatePollRef.current);
      updatePollRef.current = null;
    }
  };

  const handleInstallUpdate = async () => {
    if (!updateInfo?.download_url) return;
    setInstallingUpdate(true);
    setUpdateMessage(null);
    setUpdateProgress({
      stage: "downloading",
      percent: 0,
      downloaded_bytes: 0,
      total_bytes: updateInfo.asset_size || 0,
      speed_bps: 0,
      detail: "Starting update download...",
      error: null,
    });

    try {
      const res = await fetch("http://localhost:3000/api/update/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          download_url: updateInfo.download_url,
          sha256_url: updateInfo.sha256_url || null,
          asset_size: updateInfo.asset_size || 0,
        }),
      });
      const data = await res.json();
      if (data.status === "error") {
        setUpdateMessage({ type: "error", text: data.message || "Update install failed." });
        setInstallingUpdate(false);
        return;
      }

      stopUpdatePolling();
      updatePollRef.current = setInterval(async () => {
        try {
          const stRes = await fetch("http://localhost:3000/api/update/status");
          if (!stRes.ok) return;
          const st = await stRes.json();
          setUpdateProgress(st);
          if (st.stage === "installing") {
            stopUpdatePolling();
            setUpdateMessage({
              type: "success",
              text: st.detail || "Installer running. Dot will close and restart automatically.",
            });
          } else if (st.stage === "error") {
            stopUpdatePolling();
            setUpdateMessage({ type: "error", text: st.error || st.detail || "Update failed." });
            setInstallingUpdate(false);
          }
        } catch {
          // Backend may exit once installer takes over.
        }
      }, 300);
    } catch (err) {
      stopUpdatePolling();
      setUpdateMessage({ type: "error", text: `Install error: ${err.message}` });
      setInstallingUpdate(false);
    }
  };

  const handleOpenLogsFolder = async () => {
    try {
      await fetch("http://localhost:3000/api/logs/open", { method: "POST" });
    } catch (err) {
      console.warn("Failed to open logs folder:", err);
    }
  };

  if (!isOpen) return null;

  const currentPreset = PROVIDER_PRESETS.find((p) => p.id === cloudProvider) || PROVIDER_PRESETS[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-transparent select-none">
      <div className="absolute inset-0" onClick={onClose} />

      <div className="relative w-full max-w-[440px] bg-[#18181b] border border-zinc-800 rounded-2xl overflow-hidden flex flex-col max-h-[520px] z-10 text-zinc-200 text-xs shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/80 bg-[#141417]">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-lg bg-[#FF5A5F]/15 border border-[#FF5A5F]/30 flex items-center justify-center text-[#FF5A5F]">
              <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.488.488 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
              </svg>
            </div>
            <div>
              <h2 className="text-xs font-semibold text-white tracking-tight">Dot Settings</h2>
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
        <div className="flex items-center px-4 border-b border-zinc-800 bg-[#121215] text-[11px] font-medium">
          <button
            type="button"
            onClick={() => setActiveTab("model")}
            className={`py-2.5 px-3 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "model"
                ? "border-[#FF5A5F] text-white font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>Engine</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("browser")}
            className={`py-2.5 px-3 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "browser"
                ? "border-[#FF5A5F] text-white font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>Browser</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("mcp")}
            className={`py-2.5 px-3 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "mcp"
                ? "border-[#FF5A5F] text-white font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>Tools</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab("updates");
              if (!updateInfo) handleCheckUpdate();
            }}
            className={`py-2.5 px-3 border-b-2 transition-colors flex items-center gap-1.5 cursor-pointer ${
              activeTab === "updates"
                ? "border-[#FF5A5F] text-white font-semibold"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span>Updates</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto chat-scroll p-4 space-y-4 text-xs font-sans max-h-[390px]">
          {loading && (
            <div className="py-8 text-center text-zinc-400 font-mono text-[11px] animate-pulse">
              Loading active configuration...
            </div>
          )}

          {errorMessage && (
            <div className="p-3 bg-red-950/40 border border-red-800/80 rounded-xl text-red-200 text-[10.5px] font-mono">
              {errorMessage}
            </div>
          )}

          {!loading && activeTab === "model" && (
            <div className="space-y-4">
              <div>
                <label className="block text-[10.5px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                  Inference
                </label>
                <div className="grid grid-cols-2 gap-2.5">
                  <button
                    type="button"
                    onClick={() => setBackend("cuda")}
                    className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                      backend !== "cloud"
                        ? "bg-[#FF5A5F]/10 border-[#FF5A5F] text-white shadow-sm"
                        : "bg-[#141417] border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="font-semibold text-xs flex items-center justify-between">
                      <span>Local</span>
                      {backend !== "cloud" && <span className="text-[10px] text-[#FF5A5F] font-mono">Active</span>}
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setBackend("cloud")}
                    className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                      backend === "cloud"
                        ? "bg-[#FF5A5F]/10 border-[#FF5A5F] text-white shadow-sm"
                        : "bg-[#141417] border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="font-semibold text-xs flex items-center justify-between">
                      <span>Cloud</span>
                      {backend === "cloud" && <span className="text-[10px] text-[#FF5A5F] font-mono">Active</span>}
                    </div>
                  </button>
                </div>
              </div>

              {backend !== "cloud" && (
                <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-3.5">
                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1.5">
                      Model Tier
                    </label>
                    <select
                      value={selectedTier}
                      onChange={(e) => setSelectedTier(e.target.value)}
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-[#FF5A5F]"
                    >
                      <option value="2B">Gemma 2B (Fast - 8K)</option>
                      <option value="4B">Gemma 4B (Balanced - 8K)</option>
                      <option value="12B">Gemma 12B (Reasoning - 4K)</option>
                    </select>
                  </div>

                  {/* Engine Controller & Detailed Status */}
                  <div className="p-3 bg-[#101013] border border-zinc-800 rounded-xl space-y-2.5">
                    {/* Header Row: Status Indicator & Action Button */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={`w-2.5 h-2.5 rounded-full ${
                            engineStatus.state === "ready"
                              ? "bg-emerald-400 animate-pulse"
                              : engineStatus.state === "loading"
                              ? "bg-amber-400 animate-ping"
                              : engineStatus.state === "starting"
                              ? "bg-sky-400 animate-pulse"
                              : engineStatus.state === "error"
                              ? "bg-rose-500"
                              : "bg-zinc-600"
                          }`}
                        />
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11.5px] font-semibold text-zinc-100">
                            {engineStatus.state === "ready"
                              ? "Working (Ready)"
                              : engineStatus.state === "loading"
                              ? "Loading Weights..."
                              : engineStatus.state === "starting"
                              ? "Starting Engine..."
                              : engineStatus.state === "error"
                              ? "Start Failed"
                              : "Stopped"}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase font-semibold ${
                              engineStatus.state === "ready"
                                ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                : engineStatus.state === "loading"
                                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                                : engineStatus.state === "starting"
                                ? "bg-sky-500/15 text-sky-400 border border-sky-500/30"
                                : engineStatus.state === "error"
                                ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                                : "bg-zinc-800 text-zinc-400 border border-zinc-700/60"
                            }`}
                          >
                            {engineStatus.state || "stopped"}
                          </span>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={handleToggleEngine}
                        disabled={engineLoading || engineStatus.state === "starting" || engineStatus.state === "loading"}
                        className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1.5 cursor-pointer shadow-sm ${
                          engineStatus.state === "ready"
                            ? "bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border border-rose-500/40 active:scale-95"
                            : engineStatus.state === "starting" || engineStatus.state === "loading"
                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 opacity-80 cursor-wait"
                            : engineStatus.state === "error"
                            ? "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/40 active:scale-95"
                            : "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40 active:scale-95"
                        }`}
                      >
                        {(engineLoading || engineStatus.state === "starting" || engineStatus.state === "loading") && (
                          <svg className="w-3 h-3 animate-spin text-amber-300" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                          </svg>
                        )}
                        <span>
                          {engineStatus.state === "starting"
                            ? "Starting..."
                            : engineStatus.state === "loading"
                            ? "Loading..."
                            : engineStatus.state === "ready"
                            ? "Stop Engine"
                            : engineStatus.state === "error"
                            ? "Retry Start"
                            : "Start Local Model"}
                        </span>
                      </button>
                    </div>

                    {/* Progress Bar during Starting / Loading */}
                    {(engineStatus.state === "starting" || engineStatus.state === "loading") && (
                      <div className="w-full h-1.5 bg-zinc-800/90 rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-amber-500 via-amber-300 to-amber-500 animate-pulse rounded-full w-full" />
                      </div>
                    )}

                    {/* Status Detail Callout */}
                    <div className="text-[10.5px] text-zinc-300 bg-[#09090b] rounded-lg border border-zinc-800/80 p-2 space-y-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="leading-relaxed">
                          {engineStatus.detail || "Local inference engine is stopped."}
                        </span>
                        {engineStatus.healthy && (
                          <span className="shrink-0 text-[9.5px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
                            Health: OK
                          </span>
                        )}
                      </div>

                      {/* Ready Telemetry Pills */}
                      {engineStatus.state === "ready" && (
                        <div className="flex flex-wrap gap-1.5 pt-1 border-t border-zinc-800/60 font-mono text-[9px] text-zinc-400">
                          <span className="px-1.5 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/50">
                            Port: {engineStatus.port || 11434}
                          </span>
                          <span className="px-1.5 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/50">
                            Context: {(engineStatus.context_size || 8192).toLocaleString()}
                          </span>
                          {engineStatus.model && (
                            <span className="px-1.5 py-0.5 rounded bg-zinc-800/80 border border-zinc-700/50 truncate max-w-[200px]" title={engineStatus.model}>
                              {engineStatus.model}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Last Log Line Preview */}
                      {engineStatus.last_log && (engineStatus.state === "starting" || engineStatus.state === "loading") && (
                        <div className="text-[9.5px] font-mono text-zinc-400 pt-0.5 truncate">
                          Log: <span className="text-zinc-300">{engineStatus.last_log}</span>
                        </div>
                      )}

                      {/* Error Diagnostic Message */}
                      {engineStatus.error && engineStatus.state === "error" && (
                        <div className="text-[10px] font-mono text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded p-1.5 mt-1 leading-snug">
                          {engineStatus.error}
                        </div>
                      )}
                    </div>

                    {/* Command Preview and Log Toggle */}
                    <div className="flex items-center gap-2 bg-[#09090b] rounded-lg border border-zinc-800/80 px-2.5 py-1.5">
                      <span className="font-mono text-[9.5px] text-zinc-400 truncate flex-1 select-all" title={engineStatus.command}>
                        {engineStatus.command || `bin\\llama-server.exe -m gemma-4-E${selectedTier}_q4_0-it.gguf --port 11434`}
                      </span>
                      <button
                        type="button"
                        onClick={handleCopyCommand}
                        className="text-[10px] text-[#FF5A5F] hover:text-[#FF7075] font-medium shrink-0 cursor-pointer"
                      >
                        {copiedCmd ? "Copied" : "Copy"}
                      </button>
                      <button
                        type="button"
                        onClick={toggleEngineLogs}
                        className="text-[10px] text-zinc-400 hover:text-zinc-200 font-medium shrink-0 cursor-pointer border-l border-zinc-800 pl-2"
                      >
                        {showEngineLogs ? "Hide Log" : "View Log"}
                      </button>
                    </div>

                    {/* Collapsible Log Viewer Drawer */}
                    {showEngineLogs && (
                      <div className="p-2 bg-[#060608] border border-zinc-800 rounded-lg font-mono text-[9.5px] text-zinc-300 max-h-36 overflow-y-auto space-y-0.5 select-text">
                        <div className="flex items-center justify-between text-zinc-500 pb-1 border-b border-zinc-800/80 text-[8.5px]">
                          <span>Engine Logs (logs/engine.log)</span>
                          <button
                            type="button"
                            onClick={toggleEngineLogs}
                            className="hover:text-zinc-300 text-[9px] cursor-pointer"
                          >
                            Refresh
                          </button>
                        </div>
                        {loadingLogs ? (
                          <div className="text-zinc-500 py-1">Loading engine logs...</div>
                        ) : engineLogs.length > 0 ? (
                          engineLogs.map((logLine, idx) => (
                            <div key={idx} className="whitespace-pre-wrap leading-tight text-zinc-400 hover:text-zinc-200">
                              {logLine}
                            </div>
                          ))
                        ) : (
                          <div className="text-zinc-500 py-1">No log output recorded yet.</div>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-[10.5px] font-mono text-zinc-400 pt-0.5">
                    <span>Backend</span>
                    <span className="uppercase text-zinc-200 font-semibold">{backend}</span>
                  </div>
                </div>
              )}

              {backend === "cloud" && (
                <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-3.5">
                  <div>
                    <label className="block text-[10.5px] font-medium text-zinc-300 mb-1.5">
                      Provider
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {PROVIDER_PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectProvider(preset.id)}
                          className={`px-2.5 py-1 rounded-md text-[10.5px] font-medium transition-all cursor-pointer ${
                            cloudProvider === preset.id
                              ? "bg-[#FF5A5F] text-white shadow-sm"
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
                      Base URL
                    </label>
                    <input
                      type="text"
                      value={cloudBaseUrl}
                      onChange={(e) => setCloudBaseUrl(e.target.value)}
                      placeholder="https://generativelanguage.googleapis.com/v1beta/openai/"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-[#FF5A5F]"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[10.5px] font-medium text-zinc-300">
                        Model
                      </label>
                    </div>
                    <input
                      type="text"
                      value={cloudModel}
                      onChange={(e) => setCloudModel(e.target.value)}
                      placeholder="e.g. gemini-2.5-flash"
                      className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-[#FF5A5F]"
                    />

                    {currentPreset?.suggestedModels?.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1 mt-1.5">
                        <span className="text-[9.5px] text-zinc-500 font-mono">Suggested:</span>
                        {currentPreset.suggestedModels.map((sm) => (
                          <button
                            key={sm}
                            type="button"
                            onClick={() => setCloudModel(sm)}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-zinc-700/60 cursor-pointer"
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
                        placeholder={currentPreset?.keyPlaceholder || "API Key"}
                        className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg pl-2.5 pr-9 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-[#FF5A5F]"
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
            <div className="space-y-4">
              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Headless Mode</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      {browserHeadless
                        ? "Runs silently in background"
                        : "Connects to visible desktop window"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setBrowserHeadless(!browserHeadless)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      browserHeadless ? "bg-[#FF5A5F]" : "bg-zinc-700"
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
                  <span>Port 9222 CDP</span>
                  <span className={browserHeadless ? "text-zinc-500" : "text-emerald-400 font-semibold"}>
                    {browserHeadless ? "Disabled" : "Active"}
                  </span>
                </div>
              </div>

              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-2.5">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-100">Browser Profile & Login State</h3>
                  <p className="text-[10px] text-zinc-400 mt-0.5">
                    Keep logins across restarts or reuse a local Chrome profile
                  </p>
                </div>

                <select
                  value={browserProfileMode}
                  onChange={(e) => setBrowserProfileMode(e.target.value)}
                  className="w-full px-2.5 py-2 bg-[#0d0d10] border border-zinc-800 rounded-lg text-xs text-zinc-100 focus:outline-none focus:border-[#FF5A5F]/60"
                >
                  <option value="persistent">Dot Persistent Profile (Recommended)</option>
                  <option value="chrome_profile">Use Local Chrome Profile</option>
                  <option value="auto_connect">Auto-Connect Running Chrome</option>
                  <option value="ephemeral">Ephemeral (Clean Session)</option>
                </select>

                {browserProfileMode === "chrome_profile" && (
                  <div className="space-y-1.5">
                    <label className="block text-[10px] font-medium text-zinc-400">Chrome Profile</label>
                    {chromeProfiles.length > 0 ? (
                      <select
                        value={browserProfileName}
                        onChange={(e) => setBrowserProfileName(e.target.value)}
                        className="w-full px-2.5 py-2 bg-[#0d0d10] border border-zinc-800 rounded-lg text-xs text-zinc-100 focus:outline-none focus:border-[#FF5A5F]/60"
                      >
                        {chromeProfiles.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.id} ({p.label})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={browserProfileName}
                        onChange={(e) => setBrowserProfileName(e.target.value)}
                        placeholder="Default"
                        className="w-full px-2.5 py-2 bg-[#0d0d10] border border-zinc-800 rounded-lg text-xs text-zinc-100 focus:outline-none focus:border-[#FF5A5F]/60"
                      />
                    )}
                    <p className="text-[10px] text-amber-400/90">
                      Close regular Chrome before using a shared Chrome profile, then restart Dot backend.
                    </p>
                  </div>
                )}

                {browserProfileMode === "persistent" && (
                  <div className="space-y-2">
                    <p className="text-[10px] text-zinc-400">
                      Sign in once in Dot&apos;s clean Chrome window. Logins persist across restarts even while your main Chrome is open.
                    </p>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await fetch("http://localhost:3000/api/browser/open-login", { method: "POST" });
                        } catch (err) {
                          console.warn("Failed to open login browser:", err);
                        }
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-[#1c1c21] hover:bg-[#25252b] border border-zinc-700/80 text-[11px] font-medium text-zinc-200 transition-colors cursor-pointer"
                    >
                      Open Browser to Sign In
                    </button>
                  </div>
                )}

                {browserProfileMode === "auto_connect" && (
                  <p className="text-[10px] text-zinc-400">
                    Attaches to a running Chrome instance with remote debugging enabled.
                  </p>
                )}

                <div className="pt-2 border-t border-zinc-800/80 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-zinc-400">Verify automation browser &amp; open test page</span>
                    <button
                      type="button"
                      disabled={verifyingBrowser}
                      onClick={async () => {
                        setVerifyingBrowser(true);
                        setBrowserVerifyStatus(null);
                        try {
                          const r = await fetch("http://localhost:3000/api/browser/verify", { method: "POST" });
                          const d = await r.json();
                          setBrowserVerifyStatus({
                            ok: r.ok && d.status === "ok",
                            text: d.status === "ok"
                              ? `Verified (${d.agent_browser_found ? "agent-browser" : "Playwright fallback"}). Opened example.com.`
                              : (d.detail || "Browser verification failed."),
                          });
                        } catch (err) {
                          setBrowserVerifyStatus({ ok: false, text: `Verify failed: ${err.message}` });
                        } finally {
                          setVerifyingBrowser(false);
                        }
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-[#FF5A5F] hover:bg-[#FF454A] text-white text-[11px] font-medium transition-colors disabled:opacity-50 cursor-pointer shrink-0"
                    >
                      {verifyingBrowser ? "Opening..." : "Open & Verify Browser"}
                    </button>
                  </div>
                  {browserVerifyStatus && (
                    <div
                      className={`p-2 rounded-lg text-[10px] font-mono ${
                        browserVerifyStatus.ok
                          ? "bg-emerald-950/40 border border-emerald-800/80 text-emerald-200"
                          : "bg-red-950/40 border border-red-800/80 text-red-200"
                      }`}
                    >
                      {browserVerifyStatus.text}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {!loading && activeTab === "mcp" && (
            <div className="space-y-3.5">
              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">GitHub Token</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">Required for repo and issue tools</p>
                  </div>
                  <span
                    className={`text-[9.5px] font-mono px-1.5 py-0.5 rounded border ${
                      githubToken
                        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                    }`}
                  >
                    {githubToken ? "Set" : "Missing"}
                  </span>
                </div>

                <div className="relative">
                  <input
                    type={showGithubToken ? "text" : "password"}
                    value={githubToken}
                    onChange={(e) => setGithubToken(e.target.value)}
                    placeholder="ghp_... or github_pat_..."
                    className="w-full bg-[#101013] border border-zinc-700/80 rounded-lg pl-2.5 pr-9 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-[#FF5A5F]"
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
                  <label className="block text-[10.5px] font-semibold text-zinc-400 uppercase tracking-wider">
                    MCP Servers
                  </label>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {mcpServers.length} active
                  </span>
                </div>

                <div className="space-y-1.5">
                  {mcpServers.map((server) => (
                    <div
                      key={server}
                      className="px-3 py-1.5 bg-[#141417] border border-zinc-800/90 rounded-lg flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        <span className="font-semibold text-zinc-200">{server}</span>
                      </div>
                      <span className="text-[9.5px] font-mono text-zinc-500 bg-zinc-800/70 px-1.5 py-0.5 rounded">
                        stdio
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Tool Registry</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      Refresh schemas and ChromaDB index
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncMcp}
                    disabled={mcpSyncing}
                    className="px-3 py-1.5 bg-[#FF5A5F] hover:bg-[#FF454A] active:scale-95 text-white rounded-lg text-xs font-medium transition-all disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
                  >
                    {mcpSyncing && (
                      <span className="w-2.5 h-2.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    )}
                    <span>{mcpSyncing ? "Syncing..." : "Sync"}</span>
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

              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Allowed Applications</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      Select installed apps Dot is permitted to launch
                    </p>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-400">
                    {allowedProcesses.length} allowed
                  </span>
                </div>

                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={appSearch}
                    onChange={(e) => setAppSearch(e.target.value)}
                    placeholder="Filter installed apps..."
                    className="flex-1 bg-[#101013] border border-zinc-700/80 rounded-lg px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-[#FF5A5F]"
                  />
                  <input
                    type="text"
                    value={customAppInput}
                    onChange={(e) => setCustomAppInput(e.target.value)}
                    placeholder="Add exe..."
                    className="w-28 bg-[#101013] border border-zinc-700/80 rounded-lg px-2 py-1.5 text-xs text-zinc-100 font-mono outline-none focus:border-[#FF5A5F]"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const val = customAppInput.trim().toLowerCase();
                      if (!val) return;
                      const exe = val.endsWith(".exe") ? val : `${val}.exe`;
                      if (!allowedProcesses.includes(exe)) {
                        setAllowedProcesses([...allowedProcesses, exe]);
                      }
                      setCustomAppInput("");
                    }}
                    className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 rounded-lg text-[11px] font-medium cursor-pointer"
                  >
                    Add
                  </button>
                </div>

                <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                  {installedApps
                    .filter((a) => {
                      const q = appSearch.trim().toLowerCase();
                      if (!q) return true;
                      return a.name.toLowerCase().includes(q) || a.exe.toLowerCase().includes(q);
                    })
                    .slice(0, 60)
                    .map((app) => {
                      const checked = allowedProcesses.includes(app.exe);
                      return (
                        <label
                          key={app.exe}
                          className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-[#101013] border border-zinc-800/80 hover:border-zinc-700 cursor-pointer text-xs"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                setAllowedProcesses(
                                  checked
                                    ? allowedProcesses.filter((p) => p !== app.exe)
                                    : [...allowedProcesses, app.exe]
                                );
                              }}
                              className="accent-[#FF5A5F]"
                            />
                            <span className="text-zinc-200 truncate">{app.name}</span>
                          </div>
                          <span className="text-[10px] font-mono text-zinc-500 ml-2 shrink-0">{app.exe}</span>
                        </label>
                      );
                    })}
                </div>
              </div>
            </div>
          )}

          {/* UPDATES & DIAGNOSTICS TAB */}
          {!loading && activeTab === "updates" && (
            <div className="space-y-4">
              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl space-y-2.5">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-100">Application Updates</h3>
                    <p className="text-[10px] text-zinc-400 mt-0.5">
                      Installed version: <span className="text-zinc-200 font-mono">v{updateInfo?.current_version || "3.0.2"}</span>
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleCheckUpdate}
                    disabled={checkingUpdate || installingUpdate}
                    className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 rounded-lg text-[11px] font-medium transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {checkingUpdate ? "Checking..." : "Check Now"}
                  </button>
                </div>

                {updateInfo?.update_available && (
                  <div className="p-2.5 bg-emerald-950/30 border border-emerald-700/50 rounded-lg space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-emerald-300">
                        New release v{updateInfo.latest_version} available
                      </span>
                      {updateInfo.asset_size > 0 && (
                        <span className="text-[10px] font-mono text-zinc-400">
                          {(updateInfo.asset_size / (1024 * 1024)).toFixed(1)} MB
                        </span>
                      )}
                    </div>
                    {updateInfo.release_notes && (
                      <div className="text-[10px] text-zinc-300 max-h-24 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                        {updateInfo.release_notes}
                      </div>
                    )}
                    {updateInfo.download_url ? (
                      <button
                        type="button"
                        onClick={handleInstallUpdate}
                        disabled={installingUpdate}
                        className="w-full py-1.5 bg-[#FF5A5F] hover:bg-[#FF454A] text-white rounded-lg text-[11px] font-semibold transition-all disabled:opacity-50 cursor-pointer"
                      >
                        {installingUpdate ? "Updating..." : "Download & Install Update"}
                      </button>
                    ) : (
                      updateInfo.html_url && (
                        <a
                          href={updateInfo.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="block w-full text-center py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 rounded-lg text-[11px] font-medium transition-colors"
                        >
                          Open Release Page
                        </a>
                      )
                    )}
                  </div>
                )}

                {updateProgress && updateProgress.stage !== "idle" && (
                  <div className="p-2.5 bg-[#0e0e11] border border-zinc-800 rounded-lg space-y-2">
                    <div className="grid grid-cols-4 gap-1 text-[9.5px] font-mono">
                      {[
                        { key: "downloading", label: "1. Download" },
                        { key: "verifying", label: "2. Verify" },
                        { key: "launching", label: "3. Launch" },
                        { key: "installing", label: "4. Restart" },
                      ].map((step, idx, arr) => {
                        const order = arr.findIndex((s) => s.key === updateProgress.stage);
                        const active = step.key === updateProgress.stage;
                        const done = order > idx || updateProgress.stage === "installing";
                        return (
                          <div
                            key={step.key}
                            className={`px-1.5 py-1 rounded text-center border ${
                              active
                                ? "bg-[#FF5A5F]/15 border-[#FF5A5F]/60 text-white font-semibold"
                                : done
                                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                                : "bg-zinc-900/60 border-zinc-800 text-zinc-500"
                            }`}
                          >
                            {step.label}
                          </div>
                        );
                      })}
                    </div>

                    <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#FF5A5F] transition-all duration-200"
                        style={{ width: `${Math.max(0, Math.min(100, updateProgress.percent || 0))}%` }}
                      />
                    </div>

                    <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400">
                      <span className="truncate pr-2 text-zinc-200">{updateProgress.detail}</span>
                      <span className="shrink-0 text-zinc-300">{updateProgress.percent || 0}%</span>
                    </div>
                  </div>
                )}

                {updateMessage && (
                  <div
                    className={`p-2 rounded-lg text-[10px] font-mono ${
                      updateMessage.type === "error"
                        ? "bg-red-950/40 border border-red-800/80 text-red-200"
                        : updateMessage.type === "success"
                        ? "bg-emerald-950/40 border border-emerald-800/80 text-emerald-200"
                        : "bg-zinc-900 border border-zinc-700 text-zinc-300"
                    }`}
                  >
                    {updateMessage.text}
                  </div>
                )}
              </div>

              <div className="p-3.5 bg-[#141417] border border-zinc-800/90 rounded-xl flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-semibold text-zinc-100">Diagnostics</h3>
                  <p className="text-[10px] text-zinc-400 mt-0.5">
                    Open backend and engine log files
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleOpenLogsFolder}
                  className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg text-[11px] font-medium transition-colors cursor-pointer"
                >
                  Open Logs
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-zinc-800/80 bg-[#121215]">
          <div>
            {saveSuccess && (
              <span className="text-[11px] text-emerald-400 font-medium animate-in fade-in">
                Saved
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
              className="px-4 py-1.5 rounded-lg text-xs font-medium bg-[#FF5A5F] hover:bg-[#FF454A] active:scale-95 text-white transition-all disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              {saving && (
                <span className="w-2.5 h-2.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              <span>{saving ? "Saving..." : "Save"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

