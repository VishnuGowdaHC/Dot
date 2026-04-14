import json
import asyncio
import src.core.agents.visionAgent as visionAgent
import src.core.agents.systemAgent as systemAgent
import src.core.agents.browserAgent as browserAgent
async def masterAgent(websocket, task):
  print("master agent triggered" + task)
  agentTable = {
    1 : visionAgent.visionAgent,
    2 : systemAgent.systemAgent,  
    3 : browserAgent.browserAgent, 
  }

  steps = json.loads(task)

  for step in steps:
    agentId = step.get("a")
    command = step.get("cmd")

    targetAgent = agentTable.get(agentId)
    if targetAgent:
      await targetAgent(websocket, command)

  await websocket.send_text(json.dumps({"type": "stream", "data": task}))