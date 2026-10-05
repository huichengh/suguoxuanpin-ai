import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import './index.css'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Compare from './pages/Compare'
import AbcShelf from './pages/AbcShelf'
import CategoryHealth from './pages/CategoryHealth'
import Association from './pages/Association'
import Forecast from './pages/Forecast'
import DatePattern from './pages/DatePattern'
import Stores from './pages/Stores'
import PrivateLabel from './pages/PrivateLabel'
import NewProducts from './pages/NewProducts'
import AgentChat from './pages/AgentChat'
import DataCenter from './pages/DataCenter'
import Approvals from './pages/Approvals'
import Admin from './pages/Admin'

function Protected({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('suguo_token')
  if (!token) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <HashRouter>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/compare" element={<Protected><Compare /></Protected>} />
      <Route path="/abc-shelf" element={<Protected><AbcShelf /></Protected>} />
      <Route path="/category-health" element={<Protected><CategoryHealth /></Protected>} />
      <Route path="/association" element={<Protected><Association /></Protected>} />
      <Route path="/forecast" element={<Protected><Forecast /></Protected>} />
      <Route path="/date-pattern" element={<Protected><DatePattern /></Protected>} />
      <Route path="/stores" element={<Protected><Stores /></Protected>} />
      <Route path="/private-label" element={<Protected><PrivateLabel /></Protected>} />
      <Route path="/new-products" element={<Protected><NewProducts /></Protected>} />
      <Route path="/agent" element={<Protected><AgentChat /></Protected>} />
      <Route path="/data" element={<Protected><DataCenter /></Protected>} />
      <Route path="/approvals" element={<Protected><Approvals /></Protected>} />
      <Route path="/admin" element={<Protected><Admin /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </HashRouter>,
)
