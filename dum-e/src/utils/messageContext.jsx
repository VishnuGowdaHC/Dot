import { createContext, useState, useContext } from "react";

const MessageContext = createContext();

export function MessageProvider({ children }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const addMessage = (role, content) => {
    setMessages((prev) => [...prev, { role, content }]);
  };

  return (
    <MessageContext.Provider value={{ messages, addMessage, setMessages, isLoading, setIsLoading }}>
      {children}
    </MessageContext.Provider>
  );
}

export const useMessage = () => useContext(MessageContext);