/**
 * Renders the primary user input pill.
 * Removes attachment button per requirements.
 * Complies with ASD-STE100 rules.
 */
export default function InputPill({
  value,
  onChange,
  onSend,
  onKeyDown,
  voiceStatus = "idle",
  disabled = false,
  inputRef,
}) {
  const isRecording = voiceStatus === "recording";

  return (
    <div
      id="input-pill"
      className="h-12 rounded-full bg-[#202024] border border-white/8 shadow-[0_8px_24px_rgba(0,0,0,0.55)] backdrop-blur-xl flex items-center px-3.5 gap-2.5 transition-all duration-200 focus-within:border-[#FF5A5F]/60 focus-within:shadow-[0_10px_28px_rgba(0,0,0,0.7),0_0_0_1px_rgba(255,90,95,0.25)] select-none"
    >
      {/* Text Input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={isRecording ? "Listening to voice input..." : "Ask or command Dot..."}
        disabled={disabled || isRecording}
        className="min-w-0 flex-1 bg-transparent text-[13px] text-white placeholder-zinc-500 outline-none font-sans"
        autoComplete="off"
      />

      {/* Right Controls */}
      <div className="flex items-center shrink-0">
        {/* Warm Coral Red Send Pill Button */}
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className={`w-7 h-7 rounded-full bg-[#FF5A5F] hover:bg-[#FF454A] active:scale-95 text-white flex items-center justify-center transition-all cursor-pointer shadow-[0_0_12px_rgba(255,90,95,0.35)] shrink-0 ${disabled || !value.trim() ? "opacity-50 cursor-not-allowed" : ""
            }`}
          title="Send (Enter)"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  );
}
