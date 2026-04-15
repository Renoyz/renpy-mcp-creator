import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { ProjectProvider } from './context/ProjectContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </ErrorBoundary>
  </StrictMode>,
)
