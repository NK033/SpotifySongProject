import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import { AppProvider } from './contexts/AppContext'; // Import the provider

if (!("Notification" in window)) {
  console.log("Injecting Notification polyfill for Android");
  window.Notification = {
    permission: "denied",
    requestPermission: () => Promise.resolve("denied")
  };
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppProvider> {/* Wrap the App */}
      <App />
    </AppProvider>
  </React.StrictMode>
);