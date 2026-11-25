import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const REMARK_PLUGINS = [remarkGfm];

/**
 * Renders a code block with language header and copy button.
 * Complies with ASD-STE100 rules.
 */
function CodeBlock({ language, code }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 1200);
    } catch (err) {
      console.warn("Clipboard write warning:", err);
    }
  };

  return (
    <div className="my-2 rounded-xl bg-[#0e0e10] border border-white/10 overflow-hidden font-mono text-[11px] shadow-sm">
      <div className="flex items-center justify-between px-3 py-1 bg-white/5 border-b border-white/5 text-[9.5px] text-zinc-400">
        <span className="font-semibold text-zinc-300 uppercase">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="hover:text-white cursor-pointer px-1.5 py-0.5 rounded hover:bg-white/10 transition-colors"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="p-2.5 overflow-x-auto text-zinc-200 leading-normal select-text">
        <code>{code}</code>
      </pre>
    </div>
  );
}

const markdownComponents = {
  code({ node, inline, className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const codeText = String(children).replace(/\n$/, "");
    if (!inline && (match || codeText.includes("\n"))) {
      return <CodeBlock language={match ? match[1] : ""} code={codeText} />;
    }
    return (
      <code
        className="bg-white/10 border border-white/15 px-1 py-0.2 rounded text-[10.5px] text-zinc-200 font-mono"
        {...props}
      >
        {children}
      </code>
    );
  },
};

const MessageItem = memo(function MessageItem({ msg }) {
  const [copiedMsg, setCopiedMsg] = useState(false);

  if (msg.role === "user") {
    return (
      <div className="self-end max-w-[85%] bg-[#27272a] border border-white/10 text-white px-3.5 py-2 rounded-2xl rounded-br-sm text-[12.5px] leading-relaxed font-sans break-words">
        {msg.content}
      </div>
    );
  }

  const handleCopyMessage = () => {
    if (!msg.content) return;
    navigator.clipboard?.writeText(msg.content)
      .then(() => {
        setCopiedMsg(true);
        setTimeout(() => setCopiedMsg(false), 1500);
      })
      .catch(() => {});
  };

  return (
    <div className="group relative self-start max-w-[90%] bg-[#18181b] border border-white/8 text-zinc-200 px-3.5 py-2.5 rounded-2xl rounded-bl-sm text-[12px] leading-relaxed font-sans break-words">
      {msg.content && (
        <button
          type="button"
          onClick={handleCopyMessage}
          className="opacity-0 group-hover:opacity-100 absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded bg-zinc-800/90 hover:bg-zinc-700 border border-white/10 text-[9.5px] font-mono text-zinc-300 transition-opacity cursor-pointer"
          title="Copy response"
        >
          {copiedMsg ? "Copied" : "Copy"}
        </button>
      )}
      <div className="prose prose-invert max-w-none text-[12px] leading-relaxed">
        <ReactMarkdown
          remarkPlugins={REMARK_PLUGINS}
          components={markdownComponents}
        >
          {msg.content || ""}
        </ReactMarkdown>
      </div>
    </div>
  );
});

/**
 * Displays chat message list or starter chips.
 * Complies with ASD-STE100 rules.
 */
export default function ChatContainer({
  messages,
  onSelectPrompt,
  clarification,
  onClarifyAnswer,
}) {
  const containerRef = useRef(null);
  const scrollRafRef = useRef(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (scrollRafRef.current) cancelAnimationFrame(scrollRafRef.current);
    scrollRafRef.current = requestAnimationFrame(() => {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
      scrollRafRef.current = null;
    });
    return () => {
      if (scrollRafRef.current) {
        cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
  }, [messages, clarification]);

  const getChoiceLabel = (choice) => {
    if (typeof choice === 'string') return choice;
    if (choice && typeof choice === 'object') {
      return choice.text || choice.label || choice.title || choice.value || choice.name || JSON.stringify(choice);
    }
    return String(choice ?? '');
  };

  const renderClarificationCard = () => {
    if (!clarification) return null;
    return (
      <div className="w-full my-2 p-3.5 rounded-2xl bg-[#202024] border border-[#FF5A5F]/40 shadow-lg text-zinc-100 flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-[#FF5A5F] flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FF5A5F] animate-ping" />
            Clarification Needed
          </span>
          <span className="text-[9.5px] font-mono text-zinc-400">Loop paused</span>
        </div>
        <p className="text-[12.5px] font-sans font-medium text-white leading-relaxed">
          {clarification.question || "Please clarify or select an option to continue."}
        </p>
        {Array.isArray(clarification.choices) && clarification.choices.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {clarification.choices.map((choice, idx) => {
              const label = getChoiceLabel(choice);
              if (!label) return null;
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onClarifyAnswer && onClarifyAnswer(label)}
                  className="px-3 py-1.5 rounded-xl bg-[#2a2a30] hover:bg-[#FF5A5F] hover:text-white border border-white/10 hover:border-[#FF5A5F] text-[11.5px] font-sans text-zinc-200 transition-all cursor-pointer active:scale-95 shadow-sm"
                >
                  {label}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[11px] text-zinc-400">
            <span>Type reply below and press Enter to continue.</span>
            <button
              type="button"
              onClick={() => onClarifyAnswer && onClarifyAnswer("Proceed autonomously with best guess")}
              className="px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-[#FF5A5F] hover:text-white text-[10.5px] text-zinc-300 transition-colors cursor-pointer"
            >
              Resume
            </button>
          </div>
        )}
      </div>
    );
  };

  if (messages.length === 0) {
    return (
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto chat-scroll px-4 pt-14 pb-2 flex flex-col gap-2.5 z-10 font-sans"
      >
        {renderClarificationCard()}
        <div className="flex flex-col items-center justify-center py-3 space-y-2 font-sans select-none">
          <div className="text-[10px] text-zinc-400 uppercase tracking-wider font-semibold font-mono mb-0.5">
            Quick Actions
          </div>
          <div className="w-full flex flex-col gap-1.5">
            <button
              type="button"
              onClick={() => onSelectPrompt("Play relaxing music on YouTube")}
              className="text-left px-3 py-2 rounded-xl bg-[#202024] hover:bg-[#27272c] border border-white/6 hover:border-white/12 text-[11.5px] text-zinc-300 hover:text-white transition-all cursor-pointer flex items-center justify-between group shadow-sm"
            >
              <span className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded-md bg-[#FF5A5F]/15 text-[#FF5A5F] border border-[#FF5A5F]/30 text-[9.5px] font-mono uppercase font-medium">
                  Browser
                </span>
                <span>Play relaxing music on YouTube</span>
              </span>
              <span className="text-zinc-500 group-hover:text-zinc-300 transition-colors">
                &rarr;
              </span>
            </button>

            <button
              type="button"
              onClick={() => onSelectPrompt("Search latest AI and technology news")}
              className="text-left px-3 py-2 rounded-xl bg-[#202024] hover:bg-[#27272c] border border-white/6 hover:border-white/12 text-[11.5px] text-zinc-300 hover:text-white transition-all cursor-pointer flex items-center justify-between group shadow-sm"
            >
              <span className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded-md bg-[#FF5A5F]/20 text-[#FF5A5F] border border-[#FF5A5F]/30 text-[9.5px] font-mono uppercase font-medium">
                  Search
                </span>
                <span>Search latest AI news</span>
              </span>
              <span className="text-zinc-500 group-hover:text-zinc-300 transition-colors">
                &rarr;
              </span>
            </button>

            <button
              type="button"
              onClick={() => onSelectPrompt("Open Programiz online Python compiler and test bubble sort")}
              className="text-left px-3 py-2 rounded-xl bg-[#202024] hover:bg-[#27272c] border border-white/6 hover:border-white/12 text-[11.5px] text-zinc-300 hover:text-white transition-all cursor-pointer flex items-center justify-between group shadow-sm"
            >
              <span className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[9.5px] font-mono uppercase font-medium">
                  Desktop
                </span>
                <span>Open Python compiler & test sort</span>
              </span>
              <span className="text-zinc-500 group-hover:text-zinc-300 transition-colors">
                &rarr;
              </span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto chat-scroll px-4 pt-14 pb-2 flex flex-col gap-2.5 z-10 font-sans"
    >
      {messages.map((msg, index) => (
        <MessageItem key={index} msg={msg} />
      ))}
      {renderClarificationCard()}
    </div>
  );
}
