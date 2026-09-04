import { BrowserRouter, Route, Routes } from "react-router-dom";
import { GlimpseProvider } from "@glimpse-run/react";
import { client } from "@/lib/api";
import Layout from "./components/Layout";
import Playground from "./pages/Playground";
import Docs from "./pages/Docs";

export default function App() {
  return (
    <GlimpseProvider client={client}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Playground />} />
            <Route path="/docs" element={<Docs />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </GlimpseProvider>
  );
}
