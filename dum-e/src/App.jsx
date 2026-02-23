import { useEffect } from "react";
import initConfig from "./utils/initConfig";

export default function App() {
  initConfig();
  async function handleExit() {
    await window.Neutralino.app.exit() 
  }
  return (
    <div className="flex  flex-col justify-center text-right h-full w-[400px] bg-black/20 rounded-2xl p-1">
      <div className="text-center font-semibold">
        <button onClick={() => handleExit()}>Dot.</button>
      </div>
      <div className="flex  flex-col justify-end text-right w-full h-full card p-4">
        <h1 className="text-xl font-bold">DUM-E</h1>
        <p className="mt-4">Hello, I’m your chatbot!</p>
      </div>
    </div>
  );
}