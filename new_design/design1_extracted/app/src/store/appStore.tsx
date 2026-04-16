import { useState, useCallback, type ReactNode } from 'react';
import type { Chapter, Scene, SceneStatus, BlueprintData, AuditReport, Project, BlueprintPhase, ChatMessage } from '@/types';
import { apiGet, apiPost } from '@/api/client';
import { ensureProjectData, deriveFlowEdges, mockProjects } from '@/api/__mocks__';
import { AppContext, type AppState } from './appContext';

export function AppProvider({ children }: { children: ReactNode }) {
  const initialData = ensureProjectData('campus_romance');
  const [state, setState] = useState<AppState>({
    currentProject: 'campus_romance',
    selectedChapterId: null,
    selectedSceneId: null,
    activeTab: 'blueprint',
    chapters: initialData.chapters,
    blueprint: initialData.blueprint,
    auditReport: initialData.auditReport,
    isGenerating: false,
    generationProgress: null,
    projects: mockProjects,
    flowEdges: deriveFlowEdges(initialData.chapters),
    blueprintPhase: 'editing',
    messages: [],
  });

  const setSelectedChapter = useCallback((chapterId: string | null) => {
    setState(prev => ({
      ...prev,
      selectedChapterId: chapterId,
      selectedSceneId: null,
      activeTab: 'blueprint',
    }));
  }, []);

  const setSelectedScene = useCallback((sceneId: string | null) => {
    setState(prev => {
      let chapterId: string | null = null;
      for (const ch of prev.chapters) {
        const scene = ch.scenes.find((s: Scene) => s.id === sceneId);
        if (scene) {
          chapterId = ch.id;
          break;
        }
      }
      return {
        ...prev,
        selectedSceneId: sceneId,
        selectedChapterId: chapterId,
        activeTab: sceneId ? 'script' : prev.activeTab,
      };
    });
  }, []);

  const jumpToScene = useCallback((sceneId: string) => {
    setState(prev => {
      let chapterId: string | null = null;
      for (const ch of prev.chapters) {
        const scene = ch.scenes.find((s: Scene) => s.id === sceneId);
        if (scene) {
          chapterId = ch.id;
          break;
        }
      }
      const nextChapters = prev.chapters.map((ch: Chapter) =>
        ch.id === chapterId ? { ...ch, expanded: true } : ch
      );
      return {
        ...prev,
        selectedSceneId: sceneId,
        selectedChapterId: chapterId,
        activeTab: 'script',
        chapters: nextChapters,
      };
    });
  }, []);

  const setActiveTab = useCallback((tab: string) => {
    setState(prev => ({ ...prev, activeTab: tab }));
  }, []);

  const toggleChapter = useCallback((chapterId: string) => {
    setState(prev => ({
      ...prev,
      chapters: prev.chapters.map((ch: Chapter) =>
        ch.id === chapterId ? { ...ch, expanded: !ch.expanded } : ch
      ),
    }));
  }, []);

  const updateSceneStatus = useCallback((sceneId: string, status: SceneStatus) => {
    setState(prev => ({
      ...prev,
      chapters: prev.chapters.map((ch: Chapter) => ({
        ...ch,
        scenes: ch.scenes.map((s: Scene) =>
          s.id === sceneId ? { ...s, status } : s
        ),
      })),
    }));
  }, []);

  const setBlueprintPhase = useCallback((phase: BlueprintPhase) => {
    setState(prev => ({ ...prev, blueprintPhase: phase }));
  }, []);

  const startBlueprintCollection = useCallback(() => {
    setState(prev => ({ ...prev, blueprintPhase: 'collecting' }));
  }, []);

  const submitBlueprintGeneration = useCallback(() => {
    setState(prev => {
      const updatedProjects = prev.projects.map((p: Project) =>
        p.id === prev.currentProject ? { ...p, status: 'blueprinting' as const } : p
      );
      return {
        ...prev,
        projects: updatedProjects,
        blueprintPhase: 'generating',
        isGenerating: true,
        generationProgress: {
          chapterId: '',
          sceneId: '',
          sceneName: '',
          step: '正在分析创作意图...',
          percent: 10,
        },
      };
    });

    const steps = [
      { step: '正在设计角色设定...', percent: 30 },
      { step: '正在构建章节大纲...', percent: 55 },
      { step: '正在编排场景结构...', percent: 80 },
      { step: '正在完善分支与结局...', percent: 95 },
    ];

    let index = 0;
    const interval = setInterval(() => {
      if (index < steps.length) {
        setState(prev => ({
          ...prev,
          generationProgress: {
            chapterId: '',
            sceneId: '',
            sceneName: '',
            step: steps[index].step,
            percent: steps[index].percent,
          },
        }));
        index++;
      } else {
        clearInterval(interval);
        setState(prev => {
          const data = ensureProjectData(prev.currentProject);
          const updatedProjects = prev.projects.map((p: Project) =>
            p.id === prev.currentProject
              ? {
                  ...p,
                  status: 'editing' as const,
                  chapterCount: data.blueprint.chapters.length,
                  sceneCount: data.chapters.reduce((acc, ch) => acc + ch.scenes.length, 0),
                  confirmedScenes: 0,
                }
              : p
          );
          return {
            ...prev,
            projects: updatedProjects,
            blueprintPhase: 'editing',
            isGenerating: false,
            generationProgress: null,
            blueprint: data.blueprint,
            chapters: data.chapters,
            flowEdges: deriveFlowEdges(data.chapters),
            auditReport: null,
          };
        });
      }
    }, 600);
  }, []);

  const confirmBlueprint = useCallback(() => {
    submitBlueprintGeneration();
  }, [submitBlueprintGeneration]);

  const createEmptyBlueprint = useCallback(() => {
    setState(prev => {
      const emptyBlueprint: BlueprintData = {
        title: prev.projects.find((p: Project) => p.id === prev.currentProject)?.name || prev.currentProject,
        genre: prev.projects.find((p: Project) => p.id === prev.currentProject)?.genre || '未分类',
        worldview: '',
        themes: [],
        targetAudience: '',
        estimatedPlayTime: '',
        artStyle: '',
        audioStyle: '',
        characters: [],
        chapters: [],
      };
      const updatedProjects = prev.projects.map((p: Project) =>
        p.id === prev.currentProject
          ? { ...p, status: 'editing' as const, chapterCount: 0, sceneCount: 0, confirmedScenes: 0 }
          : p
      );
      return {
        ...prev,
        projects: updatedProjects,
        blueprint: emptyBlueprint,
        chapters: [],
        flowEdges: [],
        auditReport: null,
        blueprintPhase: 'editing',
      };
    });
  }, []);

  const setBlueprint = useCallback((blueprint: BlueprintData | null) => {
    setState(prev => ({ ...prev, blueprint }));
  }, []);

  const updateBlueprint = useCallback((updates: Partial<BlueprintData>) => {
    setState(prev => ({
      ...prev,
      blueprint: prev.blueprint ? { ...prev.blueprint, ...updates } : null,
    }));
  }, []);

  const setAuditReport = useCallback((report: AuditReport | null) => {
    setState(prev => ({ ...prev, auditReport: report }));
  }, []);

  const fixIssue = useCallback((issueId: string) => {
    setState(prev => {
      if (!prev.auditReport) return prev;
      const updatedIssues = prev.auditReport.issues.filter(i => i.id !== issueId);
      return {
        ...prev,
        auditReport: {
          ...prev.auditReport,
          issues: updatedIssues,
          status: updatedIssues.length === 0 ? 'passed' : 'failed',
          overallScore: updatedIssues.length === 0 ? 100 : Math.min(100, prev.auditReport.overallScore + 10),
        },
      };
    });
  }, []);

  const switchProject = useCallback((projectId: string) => {
    setState(prev => {
      const project = prev.projects.find((p: Project) => p.id === projectId);
      const isDraft = project?.status === 'draft';
      const data = isDraft ? null : ensureProjectData(projectId);
      return {
        ...prev,
        currentProject: projectId,
        selectedChapterId: null,
        selectedSceneId: null,
        activeTab: 'blueprint',
        blueprint: data?.blueprint || null,
        chapters: data?.chapters || [],
        auditReport: data?.auditReport || null,
        flowEdges: data ? deriveFlowEdges(data.chapters) : [],
        isGenerating: false,
        generationProgress: null,
        blueprintPhase: isDraft ? 'idle' : 'editing',
        messages: [],
      };
    });
  }, []);

  const loadProjects = useCallback(async () => {
    try {
      const projects = await apiGet<Project[]>('/api/projects');
      setState(prev => ({ ...prev, projects }));
    } catch {
      setState(prev => ({ ...prev, projects: mockProjects }));
    }
  }, []);

  const createProject = useCallback(async (name: string, description: string, genre: string) => {
    try {
      const newProject = await apiPost<Project>('/api/projects', { name: name.trim(), description: description.trim(), genre });
      setState(prev => ({
        ...prev,
        projects: [newProject, ...prev.projects],
        currentProject: newProject.id,
        selectedChapterId: null,
        selectedSceneId: null,
        activeTab: 'blueprint',
        blueprint: null,
        chapters: [],
        auditReport: null,
        flowEdges: [],
        isGenerating: false,
        generationProgress: null,
        blueprintPhase: 'idle',
        messages: [],
      }));
    } catch {
      const newProject: Project = {
        id: name.toLowerCase().replace(/\s+/g, '_'),
        name: name.trim(),
        description: description.trim(),
        genre,
        updatedAt: new Date().toISOString().split('T')[0],
        chapterCount: 0,
        sceneCount: 0,
        confirmedScenes: 0,
        status: 'draft',
      };
      setState(prev => ({
        ...prev,
        projects: [newProject, ...prev.projects],
        currentProject: newProject.id,
        selectedChapterId: null,
        selectedSceneId: null,
        activeTab: 'blueprint',
        blueprint: null,
        chapters: [],
        auditReport: null,
        flowEdges: [],
        isGenerating: false,
        generationProgress: null,
        blueprintPhase: 'idle',
        messages: [],
      }));
    }
  }, []);

  const addUserMessage = useCallback((content: string) => {
    setState(prev => ({
      ...prev,
      messages: [...prev.messages, { id: crypto.randomUUID(), role: 'user', content, type: 'text' }],
    }));
  }, []);

  const addAssistantMessage = useCallback((content: string, type?: ChatMessage['type'], data?: unknown) => {
    setState(prev => ({
      ...prev,
      messages: [...prev.messages, { id: crypto.randomUUID(), role: 'assistant', content, type, data }],
    }));
  }, []);

  const setMessages = useCallback((messages: ChatMessage[]) => {
    setState(prev => ({ ...prev, messages }));
  }, []);

  const clearMessages = useCallback(() => {
    setState(prev => ({ ...prev, messages: [] }));
  }, []);

  const simulateGenerationProgress = useCallback(() => {
    addAssistantMessage('已开始按章节生成脚本，完成后你可以在左侧切换 Scene 查看。', 'progress', {
      chapterId: 'ch1',
      sceneId: 's1-1',
      sceneName: '初见',
      step: '准备生成...',
      percent: 10,
    });
    setState(prev => ({
      ...prev,
      isGenerating: true,
      generationProgress: {
        chapterId: 'ch1',
        sceneId: 's1-1',
        sceneName: '初见',
        step: '准备生成...',
        percent: 10,
      },
    }));
    setTimeout(() => {
      setState(prev => ({
        ...prev,
        isGenerating: false,
        generationProgress: null,
        chapters: prev.chapters.map((ch: Chapter, idx: number) =>
          idx === 0
            ? {
                ...ch,
                scenes: ch.scenes.map((s: Scene) =>
                  s.status === 'pending' ? { ...s, status: 'generated' as SceneStatus } : s
                ),
              }
            : ch
        ),
      }));
    }, 2000);
  }, [addAssistantMessage]);

  const simulateAuditReport = useCallback(() => {
    const report = ensureProjectData(state.currentProject).auditReport;
    if (report) {
      setState(prev => ({ ...prev, auditReport: report }));
      addAssistantMessage('审计报告已生成，请查看 Dashboard 中的 Audit 标签页。', 'audit', {
        status: report.status,
        score: report.overallScore,
        issues: report.issues,
      });
    }
  }, [addAssistantMessage, state.currentProject]);

  const simulateBlueprintInterview = useCallback((userInput: string) => {
    const assistantContent = (() => {
      if (/风格|视觉|画风/.test(userInput)) {
        return `已记录你对视觉风格的要求。\n\n接下来我们可以聊聊游戏的背景设定或核心角色。`;
      }
      if (/角色|人物|主角/.test(userInput)) {
        return `已记录角色信息。\n\n还有几个关键问题：故事的起点场景在哪里？主要冲突是什么？`;
      }
      if (/场景|地点/.test(userInput)) {
        return `很好。接下来我会用这些信息为你生成一份结构化的项目蓝图。确认后，我们会进入分章生成。\n\n请再简单描述一下游戏的整体氛围（例如：轻松、悬疑、治愈）。`;
      }
      return `收到。为了生成更准确的蓝图，请补充一下：\n1. 世界观或时代背景\n2. 核心角色（1-3位）\n3. 你希望的游戏时长`;
    })();
    addAssistantMessage(assistantContent);
  }, [addAssistantMessage]);

  const value = {
    ...state,
    setSelectedChapter,
    setSelectedScene,
    jumpToScene,
    toggleChapter,
    setActiveTab,
    setBlueprint,
    setBlueprintPhase,
    updateBlueprint,
    startBlueprintCollection,
    submitBlueprintGeneration,
    createEmptyBlueprint,
    confirmBlueprint,
    setAuditReport,
    fixIssue,
    updateSceneStatus,
    switchProject,
    createProject,
    loadProjects,
    addUserMessage,
    addAssistantMessage,
    setMessages,
    clearMessages,
    simulateGenerationProgress,
    simulateAuditReport,
    simulateBlueprintInterview,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}
