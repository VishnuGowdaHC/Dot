/**
 * Renders the control shelf above the input pill.
 * Contains the token context bar, model quick toggle, and settings button.
 * Complies with ASD-STE100 rules.
 */
export default function ControlShelf({
  tokenUsage,
  inputValue = "",
  browserHeadless = true,
  onToggleBrowser,
  activeModel = "Gemma 4B",
  isCloudModel = false,
  onOpenSettings,
}) {
  const totalTokens = tokenUsage?.total_tokens ?? 924;
  const contextLimit = tokenUsage?.context_limit ?? 8192;
  const typingDelta = inputValue.trim().length > 0 ? Math.max(1, Math.ceil(inputValue.trim().length / 3.6)) : 0;

  return (
    <div className="flex items-center justify-between gap-1.5 font-mono select-none">
      {/* Token Context Bar */}
      <div className="flex-1 h-7 px-2.5 bg-[#202024] border border-white/8 rounded-xl flex items-center justify-between text-xs min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-zinc-400 text-[9.5px] shrink-0 font-sans">Context:</span>
          <span className="text-white font-semibold text-[9.5px] truncate font-mono">
            <span>{totalTokens.toLocaleString()}</span>
            <span className="text-zinc-500 font-normal"> / {contextLimit.toLocaleString()}</span>
          </span>
          {typingDelta > 0 && (
            <span className="text-[8.5px] bg-[#FF5A5F]/20 text-[#FF5A5F] border border-[#FF5A5F]/30 px-1 rounded animate-pulse font-mono">
              +{typingDelta}
            </span>
          )}
        </div>
      </div>

      {/* Active Model Pill */}
      <button
        type="button"
        onClick={onOpenSettings}
        className="h-7 px-2.5 bg-[#202024] border border-white/8 rounded-xl flex items-center gap-1.5 text-[9px] font-sans text-zinc-300 hover:text-white hover:border-white/20 transition-all cursor-pointer shrink-0"
        title="Active model. Click to configure settings."
      >
        
        <span className="truncate max-w-[120px] font-medium">{activeModel}</span>
      </button>

      {/* 3-Dots Settings Button */}
      <button
        type="button"
        onClick={onOpenSettings}
        className="w-7 h-7 rounded-xl bg-[#202024] border border-white/8 flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-all cursor-pointer shrink-0"
        title="Settings (Model, Cloud, MCP, Browser)"
      >
        <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
          <circle cx="12" cy="5" r="2" />
          <circle cx="12" cy="12" r="2" />
          <circle cx="12" cy="19" r="2" />
        </svg>
      </button>
    </div>
  );
}
