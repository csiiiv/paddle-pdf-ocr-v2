import React from "react";
import {createRoot} from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";
import "./mobile-landscape.css";
import "./pdf-status.css";
import "./token-geometry.css";

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
