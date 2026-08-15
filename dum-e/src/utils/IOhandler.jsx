let ws;

export function initWS(addMessage, setMessages) {
  console.log("In IOhandler.js initWS")
  try {
      ws = new WebSocket("ws://localhost:3000/ws");
      ws.onopen = () => {
        console.log("Connected to server")
      }  
      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "result") {
          setMessages((prev) => [...prev, { role: "dot", content: payload.data }]);
        }
      }
  } catch (error) {
      console.log("Error In IOhandler.js: "+error)
  }
}

export async function toDot(text) {
    try{
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.error("WS not ready")
        return
      }
      console.log("in toDot sending the text: "+text)
      ws.send(JSON.stringify(text))
    } catch(e) {
      console.error(e)
    }
}