import json
async def systemAgent(websocket, task):
  output = f"system agent triggered {task}"
  await websocket.send_text(json.dumps({"type": "stream", "data": output}))