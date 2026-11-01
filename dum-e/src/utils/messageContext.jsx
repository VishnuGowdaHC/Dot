import { createContext, useState, useContext } from "react";

const MessageContext = createContext();

export function MessageProvider({ children }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [browserHeadless, setBrowserHeadless] = useState(false);
  const [tokenUsage, setTokenUsage] = useState({
    total_tokens: 0,
    context_limit: 8192,
    system_tokens: 0,
    history_tokens: 0,
    compaction_threshold: 6553,
    percentage: 0
  });

  const addMessage = (role, content) => {
    setMessages((prev) => [...prev, { role, content }]);
  };

  const appendStreamChunk = (chunk) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last && last.role === "dot") {
        next[next.length - 1] = { role: "dot", content: last.content + chunk };
      } else {
        next.push({ role: "dot", content: chunk });
      }
      return next;
    });
  };

  return (
    <MessageContext.Provider value={{
      messages, addMessage, appendStreamChunk, setMessages,
      isLoading, setIsLoading, isStreaming, setIsStreaming,
      tokenUsage, setTokenUsage,
      browserHeadless, setBrowserHeadless
    }}>
      {children}
    </MessageContext.Provider>
  );
}

export const useMessage = () => useContext(MessageContext);
