import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./app/App";
import { ServicesProvider } from "./controller/services";
import { HttpApiClient } from "./http/HttpApiClient";
import { applyTheme, useUiStore } from "./model/stores/ui";
import { createServices } from "./services";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1 } },
});
const services = createServices(new HttpApiClient(), queryClient);

applyTheme(useUiStore.getState().theme);
useUiStore.subscribe((state) => applyTheme(state.theme));

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ServicesProvider services={services}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ServicesProvider>
    </QueryClientProvider>
  </StrictMode>,
);
