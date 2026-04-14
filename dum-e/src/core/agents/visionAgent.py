import json
async def visionAgent(websocket, task):
  output = f"vision agent triggered {task}"
  await websocket.send_text(json.dumps({"type": "stream", "data": output}))