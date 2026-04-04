let ws;

export function initWS(addMessage){
  console.log("In IOhandler.js initWS")
  try {
      ws = new WebSocket("ws://localhost:3000/ws");
      ws.onopen = () => {
        console.log("Connected to server")
      }  
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addMessage("dot", data.data);
        console.log(data)
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