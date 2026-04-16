export type ProjectStatus = 'draft' | 'blueprinting' | 'blueprinted' | 'generating' | 'editing' | 'in_progress' | 'completed';
export type BlueprintPhase = 'idle' | 'collecting' | 'reviewing' | 'generating' | 'editing';
export type SceneStatus = 'pending' | 'generating' | 'generated' | 'confirmed' | 'audit_fail';
export type SceneType = 'normal' | 'branch_point' | 'ending' | 'hidden';

export interface Scene {
  id: string;
  name: string;
  order: number;
  characters: string[];
  backgrounds: string[];
  music?: string;
  choices?: { text: string; nextSceneId: string; condition?: string }[];
  endingName?: string;
  status: SceneStatus;
  type: SceneType;
  isEnding?: boolean;
}

export interface Chapter {
  id: string;
  name: string;
  order: number;
  scenes: Scene[];
  expanded?: boolean;
}

export interface BlueprintCharacter {
  name: string;
  role: string;
  personality: string;
  appearance: string;
  variants?: string[];
}

export interface BlueprintData {
  title: string;
  genre: string;
  worldview: string;
  themes: string[];
  targetAudience: string;
  estimatedPlayTime: string;
  artStyle: string;
  audioStyle: string;
  characters: BlueprintCharacter[];
  chapters: Chapter[];
}

export interface AuditIssue {
  id: string;
  type: 'plot_hole' | 'consistency' | 'characterization' | 'pacing' | 'sensitive';
  severity: 'high' | 'medium' | 'low';
  description: string;
  sceneId?: string;
  suggestion: string;
}

export interface AuditReport {
  status: 'passed' | 'failed';
  overallScore: number;
  issues: AuditIssue[];
  summary: string;
}

export interface FlowEdge {
  fromChapterId: string;
  fromSceneId: string;
  toChapterId: string;
  toSceneId: string;
  type: 'main' | 'branch' | 'hidden';
  choiceId?: string;
  label?: string;
}

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  updatedAt: string;
  description?: string;
  genre?: string;
  chapterCount?: number;
  sceneCount?: number;
  confirmedScenes?: number;
}

export interface ResourceVariant {
  id: string;
  name: string;
  status: 'ready' | 'generating' | 'missing';
}

export interface ResourceItem {
  id: string;
  name: string;
  type: 'background' | 'character' | 'audio' | 'ui' | 'video';
  status: 'ready' | 'generating' | 'missing' | 'unused';
  size: string;
  updatedAt: string;
  usedIn?: string[];
  variants?: ResourceVariant[];
}

export interface ParsedScriptLine {
  type: 'dialogue' | 'narration' | 'choice' | 'label' | 'menu' | 'jump' | 'other';
  content: string;
  raw: string;
  speaker?: string;
  choiceText?: string;
  choiceTarget?: string;
}

export interface GenerationProgress {
  chapterId: string;
  sceneId: string;
  sceneName: string;
  step: string;
  percent: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'blueprint' | 'progress' | 'audit' | 'resource';
  data?: unknown;
}
