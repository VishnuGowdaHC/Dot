/**
 * Renders the active thinking indicator.
 * Displays a rotating SVG icon and concise action text.
 * Complies with ASD-STE100 rules.
 */
export default function ThinkingPill({ actionText = "Thinking..." }) {
  const displayText = typeof actionText === "string"
    ? actionText
    : actionText?.headline || actionText?.thought || "Thinking...";

  return (
    <div className="px-4 py-0.5 z-10 select-none">
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#1c1c20] border border-white/6">
        <svg
          className="w-3.5 h-3.5 text-[#FF5A5F] animate-spin"
          style={{ animationDuration: "2.2s" }}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
        </svg>
        <span className="text-zinc-400 text-[10.5px] font-sans truncate max-w-[240px]">
          {displayText}
        </span>
      </div>
    </div>
  );
}
