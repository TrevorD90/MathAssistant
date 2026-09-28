import React from "react";
import ReactDOM from "react-dom/client";
import "katex/dist/katex.min.css";
import "./styles.css";
import { initToken } from "./api/client";
import { App } from "./App";

const token = initToken();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App hasToken={Boolean(token)} />
  </React.StrictMode>,
);
