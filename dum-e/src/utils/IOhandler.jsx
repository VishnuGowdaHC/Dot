
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
        if (payload.type === "stream") {
          setMessages((prev) => {
              const updated = prev[prev.length - 1];

              if (updated && updated.role === "dot") {
                return [
                  ...prev.slice(0, -1),
                  {...updated, content: updated.content + payload.data},
                ]
              }
              return [...prev, {role: "dot", content: payload.data}];
            }
          )
        } else if (payload.type === "result") {

          console.log("In IOhandler.js: "+ payload.data + payload.type)
        }
      }
  } catch (error) {
      console.log("In IOhandler.js: "+error)
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