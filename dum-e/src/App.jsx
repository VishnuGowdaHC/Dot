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
  const {messages, addMessage, setMessages} = useMessage()

  const now = new Date();
  const day = now.toLocaleDateString('en-US', { weekday: 'long' });
  const date = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric' });
  
 
  initConfig();

  useEffect(() => {
    console.log("In App.js initWS initiated")
    initWS(addMessage, setMessages)
  }, []) 
  
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  async function handleEnter() {
    if (!value.trim()) return;
    
    const textTosend = value
    addMessage("user", value)
    console.log("input:"+textTosend)
    setValue("");
    
    await toDot(textTosend)
  }

  const handleKey = (e) => {
    if(e.key === "Enter") {
      handleEnter()
    }
  }

  return (
    <div className="w-full h-screen bg-black overflow-hidden flex flex-col">
    
      {/* Header */}
      <div className="flex shrink-0 justify-center items-center px-6 pt-5 pb-2">
        <h1 className="text-[21px] font-semibold">Dot</h1>
      </div>
      
      {/* Messages — fills remaining space */}
      <div ref={chatRef} className="flex-1  overflow-y-auto px-8 py-5 flex flex-col gap-5">
    
        <div className="flex justify-center">
          <span className="text-[11px] tracking-widest uppercase text-zinc-600">{day} {date}</span>
        </div>
        {
           messages.map((message, index) => ( 
            message.role === "user" ? (
              <div key={index} className="flex justify-end">
                <div className="bg-[#242424] rounded-2xl rounded-tr-sm px-4 py-3 max-w-[88%]">
                  {message.content}
                </div>
              </div>
            ) : (
              <div className="bg-[#161616] shrink-0 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[88%] text-zinc-200 overflow-hidden break-words">
    
                <div className="prose prose-invert max-w-none">
                  <ReactMarkdown 
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({node, inline, className, children, ...props}) {
                        // Check if it's a code block with a language (e.g., ```javascript)
                        const match = /language-(\w+)/.exec(className || '');
                        
                        return !inline && match ? (
                          // This is a block of code (multi-line)
                          <div className="overflow-x-auto w-full my-4 rounded-lg">
                            <SyntaxHighlighter
                              {...props}
                              style={vscDarkPlus}
                              language={match[1]}
                              PreTag="div"
                              // Removes that weird trailing new line LLMs sometimes add
                              children={String(children).replace(/\n$/, '')} 
                            />
                          </div>
                        ) : (
                          // This is an inline code snippet like `this`
                          <code {...props} className="bg-[#242424] px-1.5 py-0.5 rounded-md text-sm font-mono text-zinc-300">
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
            )
           ))
         }
 
      </div>
    
      {/* Input bar — pinned to bottom */}
      <div className="shrink-0 px-8 pb-6 pt-3 ">
        <div className="flex items-center gap-3 bg-[#1a1a1a] rounded-2xl px-4 py-3">
          <button className="w-8 h-8 rounded-xl bg-[#1a1a1a] flex items-center justify-center cursor-pointer"
          >
            <img src="/file.svg" alt="" />
          </button>
          <input
            type="text"
            placeholder="What's on your mind?..."
            value={value}
            onKeyDown={handleKey}
            onChange={(e)=>{setValue(e.target.value)}}
            autoFocus
            className="flex-1 bg-transparent text-[14px] text-zinc-200 placeholder-zinc-600 outline-none"
          />
          <button className="w-8 h-8 rounded-xl bg-[#e5332a] flex items-center justify-center cursor-pointer"
            onClick={() => handleEnter()}
          >
            <img src="/send.svg" alt="" />
          </button>
        </div>
      </div>
    
    </div>

  );
}