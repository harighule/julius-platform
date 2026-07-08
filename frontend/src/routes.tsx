import { createBrowserRouter } from 'react-router-dom'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { LoginPage } from './auth/LoginPage'
import { DashboardPanel } from './panels/DashboardPanel'
import { ScannerPanel } from './panels/ScannerPanel'
import { ExploitsPanel } from './panels/ExploitsPanel'
import { BehavioralPanel } from './panels/BehavioralPanel'
import { MonitorPanel } from './panels/MonitorPanel'
import { IdentityPanel } from './panels/IdentityPanel'
import { EventsPanel } from './panels/EventsPanel'
import { FilesPanel } from './panels/FilesPanel'
import { SettingsPanel } from './panels/SettingsPanel'
import { DarkWebPanel } from './panels/DarkWebPanel'
import { InsightsPanel } from './panels/InsightsPanel'
import { ToolsPanel } from './panels/ToolsPanel'
import { ThreatFeedsPanel } from './panels/ThreatFeedsPanel'
import { TerminalPanel } from './panels/TerminalPanel'
import { PantheonCommandCenterPanel } from './panels/PantheonCommandCenterPanel'
import { ChatPanel } from './panels/ChatPanel'
import { SignalCollectionPanel } from './panels/SignalCollectionPanel'
import { StratumOmnisPanel } from './panels/StratumOmnisPanel'
import AISystems from './panels/AISystems'
import { VeilPanel } from './panels/VeilPanel'
import { GuardianDashboard } from './panels/GuardianDashboard'
import { BgpMitmPanel } from './panels/BgpMitmPanel'
import { CutsMonitor } from './components/CutsMonitor';
import IntelligencePage from './pages/IntelligencePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ProtectedRoute />,
    children: [
      { index: true, element: <DashboardPanel /> },
      { path: 'scanner', element: <ScannerPanel /> },
      { path: 'exploits', element: <ExploitsPanel /> },
      { path: 'behavioral', element: <BehavioralPanel /> },
      { path: 'monitor', element: <MonitorPanel /> },
      { path: 'identity', element: <IdentityPanel /> },
      { path: 'darkweb', element: <DarkWebPanel /> },
      { path: 'events', element: <EventsPanel /> },
      { path: 'files', element: <FilesPanel /> },
      { path: 'insights', element: <InsightsPanel /> },
      { path: 'tools', element: <ToolsPanel /> },
      { path: 'threat-feeds', element: <ThreatFeedsPanel /> },
      { path: 'signals', element: <SignalCollectionPanel /> },
      { path: 'stratum', element: <StratumOmnisPanel /> },
      { path: 'terminal', element: <TerminalPanel /> },
      { path: 'pantheon', element: <PantheonCommandCenterPanel /> },
      { path: 'settings', element: <SettingsPanel /> },
      { path: 'chat', element: <ChatPanel /> },
      { path: 'ai', element: <ChatPanel /> },
      { path: "/ai-systems", element: <AISystems /> },
      { path: 'veil', element: <VeilPanel /> },
      { path: 'guardian', element: <GuardianDashboard /> },
      { path: 'bgp-mitm', element: <BgpMitmPanel /> },
      { path: 'intelligence', element: <IntelligencePage /> },    
      { path: "cuts-monitor", element: <CutsMonitor /> },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: "cuts-monitor", element: <CutsMonitor /> },
])
