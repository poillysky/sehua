import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './layout/RequireAuth'
import { LoginPage } from './pages/LoginPage'
import { ResourcesPage } from './pages/ResourcesPage'
import { CrawlerPage } from './pages/CrawlerPage'
import { ParseTestPage } from './pages/ParseTestPage'
import { DataMgmtPage } from './pages/DataMgmtPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<Navigate to="/resources" replace />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/crawler" element={<CrawlerPage />} />
        <Route path="/parse-test" element={<ParseTestPage />} />
        <Route path="/data" element={<DataMgmtPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/resources" replace />} />
    </Routes>
  )
}
