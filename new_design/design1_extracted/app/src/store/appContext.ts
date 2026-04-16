import { createContext } from 'react';
import type {
  Chapter,
  SceneStatus,
  BlueprintData,
  GenerationProgress,
  AuditReport,
  Project,
  FlowEdge,
  BlueprintPhase,
  ChatMessage,
} from '@/types';

export interface AppState {
  currentProject: string;
  selectedChapterId: string | null;
  selectedSceneId: string | null;
  activeTab: string;
  chapters: Chapter[];
  blueprint: BlueprintData | null;
  auditReport: AuditReport | null;
  isGenerating: boolean;
  generationProgress: GenerationProgress | null;
  projects: Project[];
  flowEdges: FlowEdge[];
  blueprintPhase: BlueprintPhase;
  messages: ChatMessage[];
}

export interface AppContextValue extends AppState {
  // Chapter/Scene navigation
  setSelectedChapter: (chapterId: string | null) => void;
  setSelectedScene: (sceneId: string | null) => void;
  jumpToScene: (sceneId: string) => void;
  toggleChapter: (chapterId: string) => void;

  // Tab & Blueprint
  setActiveTab: (tab: string) => void;
  setBlueprint: (blueprint: BlueprintData | null) => void;
  setBlueprintPhase: (phase: BlueprintPhase) => void;
  updateBlueprint: (updates: Partial<BlueprintData>) => void;
  startBlueprintCollection: () => void;
  submitBlueprintGeneration: () => void;
  createEmptyBlueprint: () => void;
  confirmBlueprint: () => void;

  // Audit
  setAuditReport: (report: AuditReport | null) => void;
  fixIssue: (issueId: string) => void;

  // Scene editing
  updateSceneStatus: (sceneId: string, status: SceneStatus) => void;

  // Projects
  switchProject: (projectId: string) => void;
  createProject: (name: string, description: string, genre: string) => Promise<void>;
  loadProjects: () => Promise<void>;

  // Chat (proxied)
  addUserMessage: (content: string) => void;
  addAssistantMessage: (content: string, type?: ChatMessage['type'], data?: unknown) => void;
  setMessages: (messages: ChatMessage[]) => void;
  clearMessages: () => void;

  // Simulation helpers
  simulateGenerationProgress: () => void;
  simulateAuditReport: () => void;
  simulateBlueprintInterview: (userInput: string) => void;
}

export const AppContext = createContext<AppContextValue | null>(null);
