import { useEffect, useState, useRef } from "react";
import initConfig from "./utils/initConfig";
import { toDot, initWS } from "./utils/IOhandler";
import { useMessage } from "./utils/messageContext";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

export default function App() {
  const [value, setValue] = useState("");
  const chatRef = useRef(null);
  const { messages, addMessage, setMessages, isLoading, setIsLoading } = useMessage();

  const now = new Date();
  const day = now.toLocaleDateString('en-US', { weekday: 'long' });
  const date = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric' });

  useEffect(() => {
    initConfig(); 
    console.log("In App.js initWS initiated");
    initWS(addMessage, setMessages, setIsLoading);
  }, []);

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
    <div className="w-full h-screen bg-black overflow-hidden flex flex-col select-none">
      
      {/* Header */}
      <div className="flex shrink-0 justify-center items-center px-6 pt-5 pb-2 border-b border-zinc-900/50">
        <h1 className="text-[18px] font-medium tracking-wide text-zinc-200">Dot</h1>
      </div>

      {/* Messages */}
      <div ref={chatRef} className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
        <div className="flex justify-center my-2">
          <span className="text-[11px] tracking-widest uppercase text-zinc-600 font-mono">
            {day} {date}
          </span>
        </div>

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <div className="bg-[#242424] text-zinc-100 rounded-2xl rounded-tr-sm px-4 py-2.5 max-w-[85%] text-[14px] leading-relaxed shadow-sm">
                {message.content}
              </div>
            </div>
          ) : (
            <div key={index} className="flex justify-start">
              <div className="bg-[#161616] rounded-2xl rounded-tl-sm px-4 py-3 max-w-[88%] text-zinc-200 overflow-hidden break-words text-[14px] leading-relaxed border border-zinc-800/40">
                <div className="prose prose-invert max-w-none text-[14px]">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({ node, inline, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '');
                        return !inline && match ? (
                          <div className="overflow-x-auto w-full my-3 rounded-lg border border-zinc-800">
                            <SyntaxHighlighter
                              {...props}
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              customStyle={{ margin: 0, padding: "12px", fontSize: "13px" }}
                            >
                              {String(children).replace(/\n$/, '')}
                            </SyntaxHighlighter>
                          </div>
                        ) : (
                          <code {...props} className="bg-[#242424] px-1.5 py-0.5 rounded-md text-xs font-mono text-zinc-300">
                            {children}
                          </code>
                        );
                      }
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          )
        )}

        {/* Typing / Loading Indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-[#161616] border border-zinc-800/40 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
              <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
              <span className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce"></span>
            </div>
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 px-6 pb-6 pt-2">
        <div className="flex items-center gap-3 bg-[#1a1a1a] border border-zinc-800/60 rounded-2xl px-4 py-2.5 focus-within:border-zinc-700 transition-colors">
          <button 
            type="button"
            className="w-8 h-8 rounded-xl bg-transparent hover:bg-zinc-800/60 flex items-center justify-center transition-colors text-zinc-400"
          >
            <img src="/file.svg" alt="attach" className="w-4 h-4 opacity-70" />
          </button>
          
          <input
            type="text"
            placeholder={isLoading ? "Dot is thinking..." : "What's on your mind?..."}
            value={value}
            disabled={isLoading}
            onKeyDown={handleKey}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
            className="flex-1 bg-transparent text-[14px] text-zinc-200 placeholder-zinc-600 outline-none disabled:opacity-50"
          />

          <button
            type="button"
            onClick={handleEnter}
            disabled={!value.trim() || isLoading}
            className="w-8 h-8 rounded-xl bg-[#e5332a] disabled:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all cursor-pointer"
          >
            <img src="/send.svg" alt="send" className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

    </div>
  );
}