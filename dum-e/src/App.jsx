import { useEffect, useState, useRef } from "react";
import initConfig from "./utils/initConfig";
import { toDot, initWS } from "./utils/IOhandler";
import { useMessage } from "./utils/messageContext";


export default function App() {
  const [value, setValue] = useState("");
  const chatRef = useRef(null);
  const {messages, addMessage} = useMessage()

  const now = new Date();
  const day = now.toLocaleDateString('en-US', { weekday: 'long' });
  const date = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: 'numeric' });
  
 
  initConfig();

  useEffect(() => {
    console.log("In App.js initWS initiated")
    initWS(addMessage)
  }, []) 
  
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scroll;
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
      <div className="flex justify-center items-center px-6 pt-5 pb-2">
        <h1 className="text-[21px] font-semibold">Dot</h1>
      </div>
    
      {/* Messages — fills remaining space */}
      <div className="flex-1 overflow-y-auto px-8 py-5 flex flex-col gap-5">
    
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
              <div key={index} className="flex flex-col gap-1">
                <div className="bg-[#161616] rounded-2xl rounded-tl-sm px-4 py-3 max-w-[88%]">
                  {message.content}
                </div>
              </div>
            )
           ))
         }
 
      </div>
    
      {/* Input bar — pinned to bottom */}
      <div className=" px-8 pb-6 pt-3 ">
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