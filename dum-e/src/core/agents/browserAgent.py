import json
async def browserAgent(websocket, task):
  output = f"browser agent triggered {task}"
  await websocket.send_text(json.dumps({"type": "stream", "data": output}))