import './index.css'
import App from './App.jsx'
import React from "react";
import ReactDOM from "react-dom/client";
import { MessageProvider } from "./utils/messageContext.jsx";

// Dynamically load neutralino from neu server
const script = document.createElement('script')
script.src = `http://localhost:${window.NL_PORT}/js/neutralino.js`
document.head.appendChild(script)


ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <MessageProvider>
      <App />
    </MessageProvider>
  </React.StrictMode>
);