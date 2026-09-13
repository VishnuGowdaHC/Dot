let ws;

export function initWS(addMessage, setMessages, setIsLoading, setIsStreaming, appendStreamChunk, setVoiceStatus) {
  console.log("In IOhandler.js initWS");
  try {
    ws = new WebSocket("ws://localhost:3000/ws");
    ws.onopen = () => {
      console.log("Connected to server");
    };
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "voice_status") {
        if (setVoiceStatus) setVoiceStatus(payload.status);
      } else if (payload.type === "voice_input") {
        setMessages((prev) => [...prev, { role: "user", content: payload.text }]);
        if (setIsLoading) setIsLoading(true);
      } else if (payload.type === "result") {
        setMessages((prev) => [...prev, { role: "dot", content: payload.data }]);
        if (setIsLoading) setIsLoading(false);
      } else if (payload.type === "stream_start") {
        if (setIsLoading) setIsLoading(false);
        if (setIsStreaming) setIsStreaming(true);
      } else if (payload.type === "stream") {
        if (appendStreamChunk) appendStreamChunk(payload.data);
      } else if (payload.type === "stream_end") {
        if (setIsStreaming) setIsStreaming(false);
      }
    };
    ws.onerror = (err) => {
      console.error("WS Error:", err);
      if (setIsLoading) setIsLoading(false);
      if (setIsStreaming) setIsStreaming(false);
    };
    ws.onclose = () => {
      if (setIsLoading) setIsLoading(false);
      if (setIsStreaming) setIsStreaming(false);
    };
  } catch (error) {
    console.log("Error In IOhandler.js: " + error);
    if (setIsLoading) setIsLoading(false);
    if (setIsStreaming) setIsStreaming(false);
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