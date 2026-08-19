let ws;

export function initWS(addMessage, setMessages, setIsLoading) {
  console.log("In IOhandler.js initWS");
  try {
    ws = new WebSocket("ws://localhost:3000/ws");
    ws.onopen = () => {
      console.log("Connected to server");
    };
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "result") {
        setMessages((prev) => [...prev, { role: "dot", content: payload.data }]);
        if (setIsLoading) setIsLoading(false);
      }
    };
    ws.onerror = (err) => {
      console.error("WS Error:", err);
      if (setIsLoading) setIsLoading(false);
    };
    ws.onclose = () => {
      if (setIsLoading) setIsLoading(false);
    };
  } catch (error) {
    console.log("Error In IOhandler.js: " + error);
    if (setIsLoading) setIsLoading(false);
  }
}

export async function toDot(text, setIsLoading) {
  try {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.error("WS not ready");
      if (setIsLoading) setIsLoading(false);
      return;
    }
    console.log("in toDot sending the text: " + text);
    if (setIsLoading) setIsLoading(true);
    ws.send(JSON.stringify(text));
  } catch (e) {
    console.error(e);
    if (setIsLoading) setIsLoading(false);
  }
}