import { useState } from "react";

export default function TokenMeter({ usage, inputValue = "", browserHeadless = false, onToggleBrowser }) {
  const [isOpen, setIsOpen] = useState(false);

  // Safe defaults if telemetry has not yet arrived
  const totalTokens = usage?.total_tokens ?? 920;
  const contextLimit = usage?.context_limit ?? 8192;
  const systemTokens = usage?.system_tokens ?? 920;
  const historyTokens = usage?.history_tokens ?? 0;
  const compactionThreshold = usage?.compaction_threshold ?? Math.floor(contextLimit * 0.8);

  // Real-time typing preview calculation (~3.6 chars per token in English/code)
  const typingTokens = inputValue.trim().length > 0 ? Math.max(1, Math.ceil(inputValue.trim().length / 3.6)) : 0;
  const projectedTotal = totalTokens + typingTokens;
  const projectedPct = contextLimit > 0 ? Math.min(100, (projectedTotal / contextLimit) * 100) : 0;
  const systemPct = contextLimit > 0 ? (systemTokens / contextLimit) * 100 : 0;
  const historyPct = contextLimit > 0 ? (historyTokens / contextLimit) * 100 : 0;
  const typingPct = contextLimit > 0 ? (typingTokens / contextLimit) * 100 : 0;
  const remainingTokens = Math.max(0, contextLimit - projectedTotal);

  // Color-coded threshold states
  let statusColor = "text-emerald-400";
  let statusBg = "bg-emerald-500/15 border-emerald-500/30";
  let progressColor = "bg-emerald-500";
  let statusText = "Optimal";

  if (projectedPct >= 80) {
    statusColor = "text-rose-400";
    statusBg = "bg-rose-500/15 border-rose-500/30";
    progressColor = "bg-rose-500";
    statusText = "Compaction Near";
  } else if (projectedPct >= 50) {
    statusColor = "text-amber-400";
    statusBg = "bg-amber-500/15 border-amber-500/30";
    progressColor = "bg-amber-500";
    statusText = "Active Context";
  }

  return (
    <div className="relative w-full select-none mb-1.5">
      {/* Top Shelf / Attached Bar */}
      <div 
        onClick={() => setIsOpen(!isOpen)}
        className="group flex items-center justify-between px-3.5 py-1.5 bg-[#121215]/95 hover:bg-[#161619] border border-zinc-800/90 rounded-t-xl transition-all duration-200 cursor-pointer shadow-sm text-[11px] font-mono"
      >
        {/* Left: Context Summary */}
        <div className="flex items-center gap-2">
          {/* Pulsing Status Dot */}
          <span className="relative flex h-2 w-2">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${progressColor}`} />
            <span className={`relative inline-flex rounded-full h-2 w-2 ${progressColor}`} />
          </span>

          <span className="text-zinc-400 font-medium">Context Meter:</span>
          <span className="text-zinc-200 font-semibold">
            {projectedTotal.toLocaleString()}
            <span className="text-zinc-500 font-normal"> / {contextLimit.toLocaleString()}</span>
          </span>

          {/* Real-time Live Typing Delta */}
          {typingTokens > 0 && (
            <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 animate-pulse">
              +{typingTokens} typing
            </span>
          )}
        </div>

        {/* Right: Mini Stacked Progress & Toggle */}
        <div className="flex items-center gap-2.5">
          {/* Quick Browser Mode Toggle */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleBrowser?.();
            }}
            className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium border transition-all cursor-pointer flex items-center gap-1 ${
              browserHeadless
                ? "bg-zinc-800/80 border-zinc-700/80 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
                : "bg-indigo-500/15 border-indigo-500/35 text-indigo-300 hover:bg-indigo-500/25 shadow-sm"
            }`}
            title={browserHeadless ? "Browser: Headless (Click to switch to Visible GUI)" : "Browser: Visible GUI (Click to switch to Headless)"}
          >
            <span>🌐</span>
            <span>{browserHeadless ? "Headless" : "GUI"}</span>
          </button>

          {/* Multi-segment Micro Progress Track */}
          <div className="w-24 sm:w-36 h-1.5 bg-zinc-800/90 rounded-full overflow-hidden flex relative">
            {/* System Prompt Segment */}
            <div 
              style={{ width: `${systemPct}%` }} 
              className="h-full bg-indigo-500 transition-all duration-300"
              title={`System Prompt: ${systemTokens.toLocaleString()} tokens`}
            />
            {/* History & ReAct Turns Segment */}
            <div 
              style={{ width: `${historyPct}%` }} 
              className="h-full bg-purple-500 transition-all duration-300"
              title={`Conversation & Tools: ${historyTokens.toLocaleString()} tokens`}
            />
            {/* Live Typing Preview Segment */}
            {typingTokens > 0 && (
              <div 
                style={{ width: `${typingPct}%` }} 
                className="h-full bg-sky-400 transition-all duration-150 animate-pulse"
                title={`Input Preview: ~${typingTokens} tokens`}
              />
            )}
          </div>

          {/* Percentage Badge */}
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${statusBg} ${statusColor}`}>
            {projectedPct.toFixed(1)}%
          </span>

          {/* Interactive Info Chevron */}
          <svg 
            className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-200 ${isOpen ? "rotate-180 text-zinc-200" : "group-hover:text-zinc-300"}`} 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Expandable Breakdown Popover */}
      {isOpen && (
        <div className="absolute bottom-full left-0 right-0 mb-1.5 p-3.5 bg-[#121215] border border-zinc-800 rounded-xl shadow-2xl z-30 font-sans text-xs text-zinc-300 animate-in fade-in slide-in-from-bottom-2 duration-150">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80 mb-2.5">
            <span className="font-semibold text-zinc-100 flex items-center gap-1.5">
              <span>Active Context Breakdown</span>
              <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${statusBg} ${statusColor}`}>
                {statusText}
              </span>
            </span>
            <span className="text-[11px] font-mono text-zinc-400">
              Limit: {contextLimit.toLocaleString()} tokens
            </span>
          </div>

          {/* Metric Rows */}
          <div className="space-y-2 font-mono text-[11px]">
            {/* System Prompt Row */}
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-zinc-400">
                <span className="w-2.5 h-2.5 rounded-sm bg-indigo-500 inline-block shrink-0" />
                <span>Base System Prompt:</span>
              </span>
              <span className="text-zinc-200">
                {systemTokens.toLocaleString()} tokens <span className="text-zinc-500">({systemPct.toFixed(1)}%)</span>
              </span>
            </div>

            {/* Conversation & ReAct Observations Row */}
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-zinc-400">
                <span className="w-2.5 h-2.5 rounded-sm bg-purple-500 inline-block shrink-0" />
                <span>Conversation & Tools:</span>
              </span>
              <span className="text-zinc-200">
                {historyTokens.toLocaleString()} tokens <span className="text-zinc-500">({historyPct.toFixed(1)}%)</span>
              </span>
            </div>

            {/* Current Input Preview Row */}
            {typingTokens > 0 && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-indigo-300">
                  <span className="w-2.5 h-2.5 rounded-sm bg-sky-400 inline-block shrink-0" />
                  <span>Pending Input:</span>
                </span>
                <span className="text-indigo-200">
                  +{typingTokens} tokens <span className="text-zinc-500">({typingPct.toFixed(1)}%)</span>
                </span>
              </div>
            )}

            {/* Free Headroom Row */}
            <div className="flex items-center justify-between pt-1 border-t border-zinc-800/60">
              <span className="flex items-center gap-2 text-zinc-400">
                <span className="w-2.5 h-2.5 rounded-sm bg-zinc-700 inline-block shrink-0" />
                <span>Available Headroom:</span>
              </span>
              <span className="text-emerald-400 font-semibold">
                {remainingTokens.toLocaleString()} tokens
              </span>
            </div>

            {/* Compaction Notice */}
            <div className="flex items-center justify-between text-zinc-500 text-[10px] pt-1">
              <span>Automatic compaction threshold:</span>
              <span>{compactionThreshold.toLocaleString()} tokens (80%)</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

