import { useEffect, useState, useRef } from "react";
import initConfig from "./utils/initConfig";

export default function App() {
  initConfig();
  async function handleExit() {
    await window.Neutralino.app.exit() 
  }

  const [value, setValue] = useState("");
  const [messages, setMessages] = useState([]);
  const chatRef = useRef(null);

  async function sendText(text) {
    try{
      const res =await fetch("http://localhost:3000/intent", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ text })
      } 
    )
    const data = await res.json()
    console.log(data)
    } catch(e) {
      console.error(e)
    }
  }
  async function handleEnter() {
    setMessages([...messages, value]);
    await sendText(value)
    setValue("");
  }

  const handleKey = async (e) => {
    if(e.key === "Enter") {
      setMessages([...messages, value]);
      await sendText(value)
      setValue("");
    }
  }





  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex  flex-col justify-center text-right h- w-[300px] card bg-black/20 rounded-2xl  p-1">
      <div className=" text-center m-3">
        <button onClick={() => handleExit()}>
        <img className="w-12" src="/logo.svg" alt="" />
        </button>
      </div>
      <div ref={chatRef} className="flex flex-col w-full justify-end h-[100px]  px-4 pb-4 ">
        <div className="flex flex-col-reverse overflow-y-auto">
          <ul id="chatList" className="list-none p-0 m-0 space-y-2">
            {
              messages.map((message, index) => (
                <li
                  className="text-[14px] "
                  key={index}
                >
                  {message}
                </li>
              ))
            }
          </ul>
        </div>
        
        <div className="flex bg-white/10 mt-4 text-white rounded-sm border pl-2 border-white/20">
          <input 
          className="w-full  bg-transparent text-white outline-none" 
          type="text"
          value={value}
          onKeyDown={handleKey}
          onChange={(e)=>{setValue(e.target.value)}}
          autoFocus />
          <button
            className="w-7 invert m-2 cursor-pointer"
            onClick={() => handleEnter()}
          >
              <img src="/send.svg" alt="" />
          </button>
        </div>
        
      </div>
    </div>
  );
}