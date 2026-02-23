import { useEffect } from "react";
export default function initConfig() {
    useEffect(() => {
      if (!window.Neutralino) return;
    
      const move = async () => {
        try {
          const displays = await window.Neutralino.computer.getDisplays();
          const win = await window.Neutralino.window.getSize();
          const margin = 20;
          const x = displays[0].resolution.width - win.width - margin;
          const y = displays[0].resolution.height - win.height - margin;
          await window.Neutralino.window.move(x, y);
        } catch (e) {
          console.error("error:", e);
        }
      };
    
      window.Neutralino.events.on("ready", move);
      window.Neutralino.init();
    }, []);
    
    return null;
}