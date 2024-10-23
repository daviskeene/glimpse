import React from "react";

import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Demo from "./pages/Demo";
import Layout from "./components/Layout";
import DocsPage from "./pages/Docs";

const AppRoutes: React.FC = () => (
  <Router>
    <Layout>
      <Routes>
        <Route path="/" element={<Demo />} />
        <Route path="/docs" element={<DocsPage />} />
      </Routes>
    </Layout>
  </Router>
);

export default AppRoutes;
