import { createContext, useState, useContext } from "react";

const MessageContext = createContext()

export function MessageProvider({ children }) {
    const [messages, setMessages] = useState([])

    const addMessage = (role, content) => {
        setMessages(prev => [...prev, {role: role, content: content}])
    }
    return (
        <MessageContext.Provider value={{messages, addMessage, setMessages}}>
            {children}
        </MessageContext.Provider>
    )
}

export const useMessage = () => useContext(MessageContext)