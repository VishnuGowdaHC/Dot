import { useEffect, useState, useRef, useCallback } from "react";
import { useMessage } from "./utils/messageContext";
import { initWS, closeWS, toDot, sendClarification } from "./utils/IOhandler";
import {
  dockWindow,
  updateNativeWindowSize,
  minimizeWindow,
  closeApp,
} from "./utils/neutralinoWindow";
import ChatContainer from "./components/ChatContainer";
import ThinkingPill from "./components/ThinkingPill";
import ControlShelf from "./components/ControlShelf";
import InputPill from "./components/InputPill";
import SettingsModal from "./components/SettingsModal";

/**
 * Main application HUD component.
 * Renders the compact floating desktop companion.
 * Complies with ASD-STE100 rules.
 */
export default function App() {
  const [inputValue, setInputValue] = useState("");
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [clarification, setClarification] = useState(null);
  const [hopTelemetry, setHopTelemetry] = useState(null);
  const inputRef = useRef(null);

  const {
    messages,
    addMessage,
    appendStreamChunk,
    setMessages,
    clearChat,
    isLoading,
    setIsLoading,
    isStreaming,
    setIsStreaming,
    activeThoughts,
    setActiveThoughts,
    setLastMessageThoughts,
    actionText,
    setActionText,
    voiceStatus,
    setVoiceStatus,
    sandboxStatus,
    setSandboxStatus,
    intervention,
    setIntervention,
    browserHeadless,
    setBrowserHeadless,
    activeModel,
    setActiveModel,
    isCloudModel,
    setIsCloudModel,
    tokenUsage,
    setTokenUsage,
  } = useMessage();

  const windowMode = isSettingsOpen
    ? "settings"
    : messages.length > 0 || Boolean(intervention) || Boolean(clarification)
      ? "chat"
      : "idle";
  const shellHeight = windowMode === "settings" ? 530 : windowMode === "chat" ? 430 : 154;
  const isExpanded = windowMode === "chat";

  // Fetch initial system settings from the server.
  useEffect(() => {
    async function loadInitialSettings() {
      try {
        const res = await fetch("http://localhost:3000/api/settings");
        if (res.ok) {
          const data = await res.json();
          const active = data.active_settings || {};
          const cloud = data.cloud || {};
          if (active.backend === "cloud") {
            setActiveModel(cloud.model || "Cloud Model");
            setIsCloudModel(true);
          } else {
            setActiveModel(`${active.selected_tier || "4B"} Local`);
            setIsCloudModel(false);
          }
          if (active.browser_headless !== undefined) {
            setBrowserHeadless(active.browser_headless);
          }
        }
      } catch (e) {
        console.warn("Initial settings load warning:", e);
      }
    }
    loadInitialSettings();
  }, [setActiveModel, setIsCloudModel, setBrowserHeadless]);

  // Initialize WebSocket and native Neutralino window
  useEffect(() => {
    initWS({
      addMessage,
      appendStreamChunk,
      setMessages,
      setIsLoading,
      setIsStreaming,
      setActiveThoughts,
      setLastMessageThoughts,
      setActionText,
      setVoiceStatus,
      setSandboxStatus,
      setIntervention,
      setTokenUsage,
      setBrowserHeadless,
      setActiveModel,
      setIsCloudModel,
      setClarification,
      setHopTelemetry,
    });

    const initWindow = async () => {
      if (typeof window !== "undefined" && window.Neutralino) {
        try {
          await window.Neutralino.window?.setDraggableRegion("drag-handle");
          await dockWindow("idle");
        } catch (e) {
          console.warn("Native window setup warning:", e);
        }
      }
    };

    if (typeof window !== "undefined" && window.Neutralino?.events) {
      window.Neutralino.events.on("ready", initWindow);
    }
    initWindow();

    return () => {
      closeWS();
    };
  }, [
    addMessage,
    appendStreamChunk,
    setMessages,
    setIsLoading,
    setIsStreaming,
    setActiveThoughts,
    setLastMessageThoughts,
    setActionText,
    setVoiceStatus,
    setSandboxStatus,
    setIntervention,
    setTokenUsage,
    setBrowserHeadless,
    setActiveModel,
    setIsCloudModel,
    setClarification,
    setHopTelemetry,
  ]);

  // Adjust native window dimensions when expanding or collapsing
  useEffect(() => {
    updateNativeWindowSize(windowMode);
  }, [windowMode]);

  // Keyboard shortcuts (Ctrl+L for clear chat)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") {
        e.preventDefault();
        clearChat();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [clearChat]);

  // Handle user response to clarification pause
  const handleClarifyAnswer = useCallback(
    (answer) => {
      if (!clarification?.id) return;
      sendClarification(clarification.id, answer);
      addMessage("user", answer);
      setClarification(null);
      setIsLoading(true);
    },
    [clarification, addMessage, setIsLoading]
  );

  // Send user message
  const handleSendPrompt = useCallback(
    async (text) => {
      const prompt = (text || inputValue).trim();
      if (!prompt) return;

      if (clarification?.id) {
        setInputValue("");
        handleClarifyAnswer(prompt);
        return;
      }

      if (isLoading) return;

      addMessage("user", prompt);
      setInputValue("");
      setIsLoading(true);

      await toDot(prompt, setIsLoading);
    },
    [inputValue, isLoading, addMessage, setIsLoading, clarification, handleClarifyAnswer]
  );

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendPrompt();
    }
  };

  const handleToggleBrowser = async () => {
    try {
      const res = await fetch("http://localhost:3000/api/browser/toggle", {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setBrowserHeadless(data.browser_headless);
      }
    } catch (err) {
      console.warn("Failed to toggle browser mode:", err);
    }
  };

  const handleApproveIntervention = async () => {
    try {
      await fetch("http://localhost:3000/api/intervention/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved: true }),
      });
      setIntervention(null);
    } catch (err) {
      console.warn("Failed to approve intervention:", err);
    }
  };

  const handleOpenSandboxCLI = () => {
    window.open("http://localhost:3000/api/sandbox/terminal", "_blank");
  };

  return (
    <div className="bg-transparent overflow-hidden select-none font-sans text-zinc-100 h-screen w-screen relative m-0 p-0">
      {/* Outer Padding Container */}
      <div className="absolute inset-0 p-3 flex flex-col justify-end pointer-events-none">
        {/* Main Corner Shell Card */}
        <div
          id="corner-shell"
          className="w-full relative flex flex-col justify-end overflow-hidden pointer-events-auto transition-all"
          style={{
            height: `${shellHeight}px`,
            borderRadius: "32px",
          }}
        >
          {/* Frosted Acrylic Backdrop Card */}
          <div
            className="absolute inset-0 rounded-[32px] pointer-events-none"
            style={{
              background: "#18181b",
              border: "1px solid rgba(255, 255, 255, 0.08)",
            }}
          />

          {/* Interactive Content Layer */}
          <div className="relative z-10 flex flex-col justify-end w-full h-full">
            {/* Top Window Headline & Control Header */}
            <div className="absolute top-0 left-0 right-0 h-8 flex items-center justify-between px-4 mt-2 z-30 select-none opacity-90 hover:opacity-100 transition-opacity">
              {/* Drag Handle Region - Draggable Area */}
              <div
                id="drag-handle"
                className="flex-1 h-full flex items-center gap-2 cursor-move"
              >
                <div className="flex items-center gap-1.5 text-zinc-400 pointer-events-none">
                  <span className="font-sans ml-1 font-medium text-[11px] text-zinc-300 tracking-wide">Dot</span>
                </div>
                <div className="flex-1 h-full" />
              </div>

              {/* Action Buttons Container - Isolated from dragging */}
              <div
                className="flex items-center gap-1.5 shrink-0 z-40"
                onMouseDown={(e) => e.stopPropagation()}
                onPointerDown={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={clearChat}
                  className="w-5 h-5 rounded-md flex items-center justify-center text-zinc-400 hover:text-[#FF5A5F] hover:bg-white/10 transition-colors cursor-pointer"
                  title="Clear Chat History (Ctrl+L)"
                >
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={minimizeWindow}
                  className="w-5 h-5 rounded-md flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                  title="Minimize"
                >
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={closeApp}
                  className="w-5 h-5 rounded-md flex items-center justify-center text-zinc-400 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
                  title="Close"
                >
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Chat Messages Container */}
            {isExpanded && (
              <ChatContainer
                messages={messages}
                onSelectPrompt={handleSendPrompt}
                clarification={clarification}
                onClarifyAnswer={handleClarifyAnswer}
              />
            )}

            {/* Active Minimalist Thinking Indicator */}
            {(isLoading || actionText) && !isStreaming && (
              <ThinkingPill actionText={actionText || "Thinking..."} />
            )}

            {/* Active Voice Recording Banner */}
            {voiceStatus === "recording" && (
              <div className="px-4 py-0.5 z-10 select-none">
                <div className="bg-zinc-900 border border-white/20 text-white px-2.5 py-1 rounded-xl text-[11px] font-mono flex items-center justify-between animate-pulse">
                  <span>Recording audio...</span>
                  <span>
                    Release{" "}
                    <kbd className="px-1 py-0.2 rounded bg-white/10 border border-white/20 text-white text-[9px]">
                      Alt
                    </kbd>
                  </span>
                </div>
              </div>
            )}

            {/* Active Human Intervention Banner */}
            {intervention && (
              <div className="px-4 py-1 z-20 select-none">
                <div className="bg-red-950/90 border border-red-500/50 text-red-200 px-3 py-2 rounded-xl text-[11px] font-mono flex flex-col gap-1.5 shadow-lg">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-red-300">
                      Confirmation Required
                    </span>
                    <span className="text-[9px] text-red-400/80">Action Paused</span>
                  </div>
                  <div className="text-zinc-200 text-[10.5px]">
                    {intervention.reason || "Action requires user confirmation."}
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5 justify-end">
                    <button
                      type="button"
                      onClick={handleOpenSandboxCLI}
                      className="px-2 py-0.5 rounded bg-white/10 hover:bg-white/20 text-white text-[9.5px] cursor-pointer"
                    >
                      Open CLI
                    </button>
                    <button
                      type="button"
                      onClick={handleApproveIntervention}
                      className="px-2 py-0.5 rounded bg-red-600 hover:bg-red-500 text-white font-semibold text-[9.5px] cursor-pointer"
                    >
                      Approve
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Control Shelf and Input Pill */}
            <div className="relative z-10 px-3.5 pt-1.5 pb-2.5 flex flex-col gap-2">
              <ControlShelf
                tokenUsage={tokenUsage}
                inputValue={inputValue}
                browserHeadless={browserHeadless}
                onToggleBrowser={handleToggleBrowser}
                activeModel={activeModel}
                isCloudModel={isCloudModel}
                onOpenSettings={() => setIsSettingsOpen(true)}
                hopTelemetry={hopTelemetry}
              />
              <InputPill
                inputRef={inputRef}
                value={inputValue}
                onChange={setInputValue}
                onSend={() => handleSendPrompt()}
                onKeyDown={handleKeyDown}
                voiceStatus={voiceStatus}
                disabled={isLoading && !clarification}
                placeholder={clarification ? "Type reply to clarify..." : undefined}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSettingsSaved={() => {
          // Settings refreshed
        }}
      />
    </div>
  );
}
