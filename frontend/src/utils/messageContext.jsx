import { createContext, useState, useContext, useCallback, useMemo } from "react";

const MessageContext = createContext();
const TypingContext = createContext();

export function MessageProvider({ children }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeThoughts, setActiveThoughts] = useState("");
  const [actionText, setActionText] = useState("");
  const [voiceStatus, setVoiceStatus] = useState("idle");
  const [sandboxStatus, setSandboxStatus] = useState("idle");
  const [intervention, setIntervention] = useState(null);
  const [clarification, setClarification] = useState(null);
  const [browserHeadless, setBrowserHeadless] = useState(true);
  const [activeModel, setActiveModel] = useState("gemini-3.5-flash-lite");
  const [isCloudModel, setIsCloudModel] = useState(true);
  const [typingLength, setTypingLength] = useState(0);

  const [tokenUsage, setTokenUsage] = useState({
    total_tokens: 934,
    context_limit: 16384,
    system_tokens: 934,
    history_tokens: 0,
    compaction_threshold: 13107,
    percentage: 6
  });

  const addMessage = useCallback((role, content, thoughts = "") => {
    setMessages((prev) => [...prev, { role, content, thoughts }]);
  }, []);

  const appendStreamChunk = useCallback((chunk) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "dot") {
        next[next.length - 1] = { ...last, content: last.content + chunk };
      } else {
        next.push({ role: "dot", content: chunk, thoughts: "" });
      }
      return next;
    });
  }, []);

  const setLastMessageThoughts = useCallback((thoughts) => {
    setMessages((prev) => {
      if (!prev.length) return prev;
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "dot") {
        next[next.length - 1] = { ...last, thoughts };
      }
      return next;
    });
  }, []);

  const clearChat = useCallback(async () => {
    try {
      await fetch("http://localhost:3000/api/chat/clear", { method: "POST" });
    } catch (e) {
      console.warn("Clear chat error:", e);
    }
    setMessages([]);
    setActiveThoughts("");
    setActionText("");
    setIntervention(null);
    setClarification(null);
  }, []);

  const contextValue = useMemo(() => ({
    messages, setMessages, addMessage, appendStreamChunk, setLastMessageThoughts, clearChat,
    isLoading, setIsLoading,
    isStreaming, setIsStreaming,
    activeThoughts, setActiveThoughts,
    actionText, setActionText,
    voiceStatus, setVoiceStatus,
    sandboxStatus, setSandboxStatus,
    intervention, setIntervention,
    clarification, setClarification,
    browserHeadless, setBrowserHeadless,
    activeModel, setActiveModel,
    isCloudModel, setIsCloudModel,
    tokenUsage, setTokenUsage,
  }), [
    messages, addMessage, appendStreamChunk, setLastMessageThoughts, clearChat,
    isLoading, isStreaming, activeThoughts, actionText, voiceStatus, sandboxStatus,
    intervention, clarification, browserHeadless, activeModel, isCloudModel, tokenUsage,
  ]);

  const typingValue = useMemo(() => ({
    typingLength,
    setTypingLength,
  }), [typingLength]);

  return (
    <MessageContext.Provider value={contextValue}>
      <TypingContext.Provider value={typingValue}>
        {children}
      </TypingContext.Provider>
    </MessageContext.Provider>
  );
}

export const useMessage = () => useContext(MessageContext);
export const useTyping = () => useContext(TypingContext);
