import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { TopBar } from '@/components/TopBar';
import { Dashboard } from '@/components/Dashboard';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { StatusBar } from '@/components/StatusBar';
import { ProjectListPage } from '@/pages/ProjectListPage';

function WorkspaceLayout() {
  return (
    <div className="h-screen flex flex-col bg-white dark:bg-gray-950">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0">
          <Dashboard />
        </div>
        <div className="w-[400px] flex-shrink-0 border-l border-gray-200 dark:border-gray-800">
          <ChatPanel />
        </div>
      </div>
      <StatusBar />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ProjectListPage />} />
        <Route path="/project/:id" element={<WorkspaceLayout />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
