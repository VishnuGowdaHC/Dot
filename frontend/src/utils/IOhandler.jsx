/**
 * WebSocket dispatcher for Dot backend.
 * Complies with ASD-STE100 writing rules.
 */

let ws = null;

export function closeWS() {
  if (ws) {
    try {
      ws.close();
    } catch (err) {
      console.warn("WebSocket close warning:", err);
    }
    ws = null;
  }
}

export function initWS(handlers) {
  closeWS();
  const {
    addMessage,
    appendStreamChunk,
    setMessages,
    setIsLoading,
    setIsStreaming,
    setActiveThoughts,
    setLastMessageThoughts,
    setActionText,
    setVoiceStatus,
    setSandboxStatus,
    setIntervention,
    setTokenUsage,
    setBrowserHeadless,
    setActiveModel,
    setIsCloudModel,
    setClarification,
    setHopTelemetry,
  } = handlers;

  try {
    ws = new WebSocket("ws://localhost:3000/ws");

    ws.onopen = () => {
      console.log("[WS] Connected to Dot backend server");
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type, data } = payload;

        if (type === "voice_status") {
          if (setVoiceStatus) setVoiceStatus(payload.status);
        } else if (type === "voice_input") {
          if (addMessage) addMessage("user", payload.text);
          if (setIsLoading) setIsLoading(true);
        } else if (type === "stream_start") {
          if (setIsLoading) setIsLoading(false);
          if (setIsStreaming) setIsStreaming(true);
          if (setActiveThoughts) setActiveThoughts("");
          if (setActionText) setActionText("");
          if (addMessage) addMessage("dot", "", "");
        } else if (type === "stream") {
          if (appendStreamChunk) appendStreamChunk(data);
        } else if (type === "stream_end") {
          if (setIsStreaming) setIsStreaming(false);
          if (setIsLoading) setIsLoading(false);
          if (setActionText) setActionText("");
        } else if (type === "result") {
          if (setIsLoading) setIsLoading(false);
          if (setIsStreaming) setIsStreaming(false);
          if (setActionText) setActionText("");
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "dot") {
              if (last.content === data) return prev;
              return [...prev.slice(0, -1), { ...last, content: data, thoughts: "" }];
            }
            return [...prev, { role: "dot", content: data, thoughts: "" }];
          });
        } else if (type === "agent_action") {
          if (setIsLoading) setIsLoading(true);
          const headline = typeof data === "string"
            ? data
            : data?.headline || data?.thought || (data?.tool_name ? `Executing ${data.tool_name}...` : "Thinking...");
          if (setActionText) setActionText(headline);
        } else if (type === "chat_cleared") {
          if (setMessages) setMessages([]);
          if (setActiveThoughts) setActiveThoughts("");
          if (setActionText) setActionText("");
          if (setIntervention) setIntervention(null);
        } else if (type === "intervention_required") {
          if (setIntervention) setIntervention(data || { reason: "Confirmation required." });
        } else if (type === "intervention_resolved") {
          if (setIntervention) setIntervention(null);
        } else if (type === "sandbox_status") {
          if (setSandboxStatus) setSandboxStatus(data?.status || "idle");
        } else if (type === "token_usage") {
          if (setTokenUsage) setTokenUsage(data);
        } else if (type === "browser_status") {
          if (setBrowserHeadless && data?.browser_headless !== undefined) {
            setBrowserHeadless(data.browser_headless);
          }
        } else if (type === "clarification_request") {
          if (setIsLoading) setIsLoading(false);
          if (setActionText) setActionText(null);
          if (setClarification) setClarification(data);
        } else if (type === "clarification_resolved") {
          if (setIsLoading) setIsLoading(false);
          if (setClarification) setClarification(null);
        } else if (type === "hop_telemetry") {
          if (setHopTelemetry) setHopTelemetry(data);
        } else if (type === "settings_updated") {
          if (data?.active_settings) {
            if (setBrowserHeadless && data.active_settings.browser_headless !== undefined) {
              setBrowserHeadless(data.active_settings.browser_headless);
            }
            if (setActiveModel && setIsCloudModel) {
              const backend = data.active_settings.backend || "cuda";
              if (backend === "cloud") {
                const modelName = data.cloud?.model || "Cloud Model";
                setActiveModel(modelName);
                setIsCloudModel(true);
              } else {
                setActiveModel(`${data.active_settings.selected_tier || "4B"} Local`);
                setIsCloudModel(false);
              }
            }
          }
        }
      } catch (err) {
        console.error("[WS] Message parsing error:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("[WS] Connection error:", err);
      if (setIsLoading) setIsLoading(false);
      if (setIsStreaming) setIsStreaming(false);
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected from server");
      if (setIsLoading) setIsLoading(false);
      if (setIsStreaming) setIsStreaming(false);
    };
  } catch (error) {
    console.error("[WS] Initialization error:", error);
    if (setIsLoading) setIsLoading(false);
    if (setIsStreaming) setIsStreaming(false);
  }
}

export async function toDot(text, setIsLoading) {
  try {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.error("[WS] Cannot send text: socket closed");
      if (setIsLoading) setIsLoading(false);
      return;
    }
    if (setIsLoading) setIsLoading(true);
    ws.send(JSON.stringify(text));
  } catch (e) {
    console.error("[WS] Send error:", e);
    if (setIsLoading) setIsLoading(false);
  }
}

export function sendClarification(id, answer) {
  try {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.error("[WS] Cannot send clarification: socket closed");
      return;
    }
    ws.send(JSON.stringify({
      type: "clarification_response",
      id,
      answer,
    }));
  } catch (e) {
    console.error("[WS] Clarification send error:", e);
  }
}
