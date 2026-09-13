import { useEffect, useState, useRef } from "react";
import initConfig from "./utils/initConfig";
import { toDot, initWS } from "./utils/IOhandler";
import { useMessage } from "./utils/messageContext";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const THINKING_PHRASES = [
  "hallucinating...",
  "na just kidding...",
  "finding bs to tell...",
  "nah chill out...",
  "consulting the silicon oracle...",
  "pretending to work hard...",
  "brewing some sarcasm...",
  "overthinking your request...",
  "downloading common sense...",
  "firing up the neurons...",
  "hold up, let me cook...",
  "questioning my life choices...",
];

export default function App() {
  const [value, setValue] = useState("");
  const [typedText, setTypedText] = useState("");
  const [voiceStatus, setVoiceStatus] = useState("idle");
  const chatRef = useRef(null);
  const { messages, addMessage, appendStreamChunk, setMessages, isLoading, setIsLoading, isStreaming, setIsStreaming } = useMessage();

  const now = new Date();
  const day = now.toLocaleDateString('en-US', { weekday: 'long' });
  const date = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric' });

  useEffect(() => {
    initConfig();
    console.log("In App.js initWS initiated");
    initWS(addMessage, setMessages, setIsLoading, setIsStreaming, appendStreamChunk, setVoiceStatus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isLoading || isStreaming) {
      setTypedText("");
      return;
    }

    let isMounted = true;
    let phraseIndex = Math.floor(Math.random() * THINKING_PHRASES.length);
    let charIndex = 0;
    let isDeleting = false;
    let timeoutId = null;

    const tick = () => {
      if (!isMounted) return;

      const currentPhrase = THINKING_PHRASES[phraseIndex];

      if (!isDeleting) {
        // Typing forward
        charIndex++;
        setTypedText(currentPhrase.slice(0, charIndex));

        if (charIndex >= currentPhrase.length) {
          // Finished phrase, pause so user reads the joke
          isDeleting = true;
          timeoutId = setTimeout(tick, 1200);
          return;
        }
        const typeSpeed = 35 + Math.random() * 20;
        timeoutId = setTimeout(tick, typeSpeed);
      } else {
        // Backspacing
        charIndex--;
        setTypedText(currentPhrase.slice(0, charIndex));

        if (charIndex <= 0) {
          // Finished deleting, pick a different phrase
          isDeleting = false;
          let next = Math.floor(Math.random() * THINKING_PHRASES.length);
          while (next === phraseIndex && THINKING_PHRASES.length > 1) {
            next = Math.floor(Math.random() * THINKING_PHRASES.length);
          }
          phraseIndex = next;
          timeoutId = setTimeout(tick, 200);
          return;
        }
        timeoutId = setTimeout(tick, 20);
      }
    };

    timeoutId = setTimeout(tick, 40);

    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [isLoading, isStreaming]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTo({
        top: chatRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [messages, isLoading]);

  async function handleEnter() {
    if (!value.trim() || isLoading) return;

    const textTosend = value;
    addMessage("user", value);
    setValue("");

    await toDot(textTosend, setIsLoading);
  }

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleEnter();
    }
  };

  return (
    <div className="relative w-full h-screen bg-[#0e0e11] text-zinc-100 overflow-hidden flex flex-col select-none font-sans">

      {/* Subtle Generic Backdrop */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute inset-0 bg-[radial-gradient(#ffffff05_1px,transparent_1px)] [background-size:20px_20px] opacity-40 pointer-events-none" />
      </div>

      {/* Generic Header */}
      <header className="shrink-0 bg-[#121215]/90 backdrop-blur-md px-6 sm:px-12 md:px-20 lg:px-28 xl:px-36 py-3.5 z-20 relative border-b border-zinc-800/80">
        <div className="max-w-3xl w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-xl tracking-tight text-white font-semibold">
              Dot
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <span>{day.slice(0, 3)}</span>
            <span className="text-zinc-600">|</span>
            <span>{date}</span>
          </div>
        </div>
      </header>

      {/* Messages Column with responsive full-screen gutters */}
      <main
        ref={chatRef}
        className="flex-1 overflow-y-auto px-6 sm:px-12 md:px-20 lg:px-28 xl:px-36 py-6 flex flex-col z-10 relative"
      >
        <div className="max-w-3xl w-full mx-auto flex flex-col flex-1 space-y-5">
          {/* Generic Empty State */}
          {messages.length === 0 && (
            <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-16 select-none relative z-10">
              <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight text-zinc-100 mb-4">
                Dot
              </h2>

              <div className="inline-flex items-center gap-2.5 bg-zinc-800/70 border border-zinc-700/80 px-4 py-2 text-xs rounded-xl text-zinc-300 shadow-sm">
                <span>Hold</span>
                <kbd className="px-2 py-0.5 rounded bg-zinc-700 text-zinc-200 border border-zinc-600 text-[11px] font-mono">Alt</kbd>
                <span>for voice mode</span>
              </div>
            </div>
          )}

          {/* Transcript Messages */}
          {messages.map((message, index) =>
            message.role === "user" ? (
              <div key={index} className="flex justify-end">
                <div className="bg-zinc-800 text-zinc-100 rounded-2xl px-4 py-2.5 max-w-[82%] text-[14px] leading-relaxed border border-zinc-700/80 shadow-sm">
                  <p className="font-sans">{message.content}</p>
                </div>
              </div>
            ) : (
              <div key={index} className="flex justify-start items-start gap-3">
                <div className="bg-[#161619] border border-zinc-800/90 rounded-2xl px-5 py-4 max-w-[90%] text-[14px] text-zinc-200 leading-relaxed shadow-sm">
                  <div className="prose prose-invert max-w-none text-[14px] text-zinc-200">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ inline, className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || '');
                          return !inline && match ? (
                            <div className="overflow-x-auto w-full my-3 rounded-xl bg-[#0c0c0e] border border-zinc-800">
                              <div className="px-4 py-1.5 border-b border-zinc-800 text-[11px] font-mono text-zinc-400 flex items-center justify-between">
                                <span className="uppercase">{match[1]}</span>
                              </div>
                              <SyntaxHighlighter
                                {...props}
                                style={vscDarkPlus}
                                language={match[1]}
                                PreTag="div"
                                customStyle={{ margin: 0, padding: "14px", background: "transparent", fontSize: "13px" }}
                              >
                                {String(children).replace(/\n$/, '')}
                              </SyntaxHighlighter>
                            </div>
                          ) : (
                            <code {...props} className="bg-zinc-800/80 border border-zinc-700/80 px-1.5 py-0.5 rounded font-mono text-xs text-zinc-200">
                              {children}
                            </code>
                          );
                        }
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                    {isStreaming && index === messages.length - 1 && (
                      <span className="inline-block w-[2px] h-[14px] bg-indigo-400 animate-pulse ml-1 align-middle" />
                    )}
                  </div>
                </div>
              </div>
            )
          )}

          {/* Generic Typewriter Thinking Line */}
          {isLoading && !isStreaming && (
            <div className="inline-flex items-center gap-2 bg-[#161619] border border-zinc-800/90 px-3.5 py-1.5 text-xs rounded-xl w-fit shadow-sm">
              <span className="text-indigo-400 bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 rounded-md font-mono text-[10px] font-semibold uppercase tracking-wider">
                thinking
              </span>
              <span className="text-zinc-500">:</span>
              <span className="text-zinc-200 font-medium">{typedText}</span>
            </div>
          )}
        </div>
      </main>

      {/* Generic Input Section */}
      <footer className="shrink-0 px-6 sm:px-12 md:px-20 lg:px-28 xl:px-36 pb-6 pt-2 z-20 relative">
        <div className="max-w-3xl w-full mx-auto">
          {/* Active Voice Recording Status */}
          {voiceStatus === "recording" && (
            <div className="bg-red-950/40 border border-red-800/80 text-red-200 px-4 py-2 mb-2 rounded-xl text-xs flex items-center justify-between font-mono animate-pulse">
              <span>Recording...</span>
              <span>Release <kbd className="px-1.5 py-0.5 rounded bg-red-900/60 border border-red-700 text-white text-[10px]">Alt</kbd> to send</span>
            </div>
          )}
          {voiceStatus === "transcribing" && (
            <div className="bg-zinc-800/80 border border-zinc-700 text-zinc-300 px-4 py-2 mb-2 rounded-xl text-xs font-mono">
              Transcribing audio...
            </div>
          )}

          {/* Clean Generic Input Pill */}
          <div className="bg-[#161619] border border-zinc-800 rounded-2xl px-3.5 py-2.5 flex items-center gap-3 focus-within:border-zinc-700 transition-colors shadow-sm">
            <button
              type="button"
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-all text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 cursor-pointer shrink-0"
              title="Attach file"
            >
              <img src="/file.svg" alt="attach" className="w-4 h-4 opacity-75 hover:opacity-100 transition-opacity invert" />
            </button>

            <input
              type="text"
              placeholder="Ask or command..."
              value={value}
              disabled={isLoading}
              onKeyDown={handleKey}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
              className="flex-1 bg-transparent text-[14px] text-zinc-100 placeholder-zinc-500 outline-none disabled:opacity-50"
            />

            {/* In-bar Alt key voice badge */}
            <div
              className={`px-2 py-0.5 rounded text-xs font-mono select-none transition-all ${voiceStatus === "recording"
                ? "bg-red-800 text-white font-bold"
                : "bg-zinc-800/90 text-zinc-300 border border-zinc-700"
                }`}
              title="Hold Alt to speak"
            >
              Alt
            </div>

            {/* Accent Send Button */}
            <button
              type="button"
              onClick={handleEnter}
              disabled={!value.trim() || isLoading}
              className="w-8 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-500 active:scale-95 text-white disabled:opacity-25 disabled:cursor-not-allowed flex items-center justify-center transition-all cursor-pointer shrink-0 shadow-[0_0_14px_rgba(99,102,241,0.35)]"
              title="Send"
            >
              <img src="/send.svg" alt="send" className="w-3.5 h-3.5 brightness-200" />
            </button>
          </div>

          {/* Sub-footer instructions */}
          <div className="flex items-center justify-between px-2 pt-2.5 text-[11px] font-mono text-zinc-400 select-none">
            <span className="flex items-center gap-1.5">
              <span>Hold <kbd className="border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 rounded text-[10px] text-zinc-300">Alt</kbd> for voice mode</span>
            </span>
            <span>Enter to send</span>
          </div>
        </div>
      </footer>

    </div>
  );
}