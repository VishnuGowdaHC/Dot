import "./index.css";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { MessageProvider } from "./utils/messageContext.jsx";

/**
 * Mounts the React application.
 * Initializes the Neutralino client library when present.
 * Complies with ASD-STE100 writing rules.
 */
if (typeof window !== "undefined" && window.Neutralino) {
  try {
    window.Neutralino.init();
  } catch (err) {
    console.warn("Neutralino init warning:", err);
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <MessageProvider>
      <App />
    </MessageProvider>
  </React.StrictMode>
);
