import { useState } from "react";
import { useTyping } from "../utils/messageContext";

/**
 * Renders the primary user input pill.
 * Manages local input state to prevent parent re-renders while typing.
 * Complies with ASD-STE100 rules.
 */
export default function InputPill({
  onSend,
  voiceStatus = "idle",
  disabled = false,
  inputRef,
  placeholder,
}) {
  const [value, setValue] = useState("");
  const { setTypingLength } = useTyping();
  const isRecording = voiceStatus === "recording";

  const handleChange = (e) => {
    const next = e.target.value;
    setValue(next);
    setTypingLength(next.trim().length);
  };

  const submitPrompt = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || isRecording) return;
    setValue("");
    setTypingLength(0);
    onSend(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitPrompt();
    }
  };

  return (
    <div
      id="input-pill"
      className="h-12 rounded-full bg-[#202024] border border-white/8 flex items-center px-3.5 gap-2.5 transition-all duration-200 focus-within:border-[#FF5A5F]/60 select-none"
    >
      {/* Text Input */}
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={isRecording ? "Listening to voice input..." : placeholder || "Ask or command Dot..."}
        disabled={disabled || isRecording}
        className="min-w-0 flex-1 bg-transparent text-[13px] text-white placeholder-zinc-500 outline-none font-sans"
        autoComplete="off"
      />

      {/* Right Controls */}
      <div className="flex items-center shrink-0">
        {/* Warm Coral Red Send Pill Button */}
        <button
          type="button"
          onClick={submitPrompt}
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
