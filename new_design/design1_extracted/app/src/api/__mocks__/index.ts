import type { Project, BlueprintData, Chapter, AuditReport, BlueprintCharacter, FlowEdge, SceneStatus } from '@/types';

export const mockCharacters: BlueprintCharacter[] = [
  { name: '樱', role: '女主角', personality: '温柔内向', appearance: '长发、眼镜、图书管理员制服', variants: ['neutral', 'happy', 'sad', 'surprised', 'angry'] },
  { name: '小林', role: '男主角', personality: '开朗直率', appearance: '短发、运动服、阳光笑容', variants: ['neutral', 'happy', 'sad', 'surprised', 'angry'] },
];

export const mockBlueprint: BlueprintData = {
  title: 'campus_romance',
  genre: '校园恋爱',
  worldview: '现代日本高中，樱花盛开的校园',
  themes: ['初恋', '成长', '选择'],
  targetAudience: '青少年及年轻成人',
  estimatedPlayTime: '2-3 小时',
  artStyle: '日系动漫风格',
  audioStyle: '轻快钢琴与弦乐',
  characters: mockCharacters,
  chapters: [
    { id: 'ch1', name: '图书馆相遇', order: 1, scenes: [
      { id: 's1-1', name: '初见', order: 1, characters: ['小林', '樱'], backgrounds: ['图书馆早晨'], music: 'bgm_peaceful.mp3', status: 'confirmed' as SceneStatus, type: 'normal' },
      { id: 's1-2', name: '借书', order: 2, characters: ['小林', '樱'], backgrounds: ['图书馆柜台'], music: 'bgm_peaceful.mp3', status: 'confirmed' as SceneStatus, type: 'normal' },
      { id: 's1-3', name: '告别', order: 3, characters: ['小林', '樱'], backgrounds: ['图书馆入口'], music: 'bgm_peaceful.mp3', status: 'audit_fail' as SceneStatus, type: 'normal' },
    ]},
    { id: 'ch2', name: '社团活动', order: 2, scenes: [
      { id: 's2-1', name: '招募', order: 1, characters: ['小林', '樱'], backgrounds: ['社团教室'], music: 'bgm_peaceful.mp3', status: 'generated' as SceneStatus, type: 'normal' },
      { id: 's2-2', name: '合作', order: 2, characters: ['小林', '樱'], backgrounds: ['社团教室'], music: 'bgm_peaceful.mp3', status: 'pending' as SceneStatus, type: 'normal' },
    ]},
    { id: 'ch3', name: '告白', order: 3, scenes: [
      { id: 's3-1', name: '犹豫', order: 1, characters: ['小林'], backgrounds: ['樱花树下'], music: 'bgm_tension.mp3', status: 'generated' as SceneStatus, type: 'branch_point', choices: [
        { text: '鼓起勇气告白', nextSceneId: 's3-2a' },
        { text: '把话咽回去', nextSceneId: 's3-2b' },
      ]},
      { id: 's3-2a', name: '决心·告白线', order: 2, characters: ['小林', '樱'], backgrounds: ['樱花树下'], music: 'bgm_tension.mp3', status: 'pending' as SceneStatus, type: 'normal' },
      { id: 's3-2b', name: '决心·友情线', order: 3, characters: ['小林', '樱'], backgrounds: ['樱花树下'], music: 'bgm_tension.mp3', status: 'pending' as SceneStatus, type: 'normal' },
    ]},
  ],
};

export const mockChapters: Chapter[] = mockBlueprint.chapters.map((ch) => ({ ...ch, expanded: ch.order === 1 }));

export const mockAuditReport: AuditReport = {
  status: 'failed',
  overallScore: 78,
  summary: '第一章存在角色情绪不一致与资源分辨率问题。',
  issues: [
    { id: 'i1', type: 'characterization', severity: 'high', description: 'Scene 1.3 中角色"樱"的情绪与 Blueprint 设定不符', sceneId: 's1-3', suggestion: '调整樱在告别场景中的台词，使其更符合温柔内向的设定。' },
    { id: 'i2', type: 'consistency', severity: 'medium', description: '背景图片"library_evening.jpg"分辨率过低', sceneId: 's1-2', suggestion: '重新生成或替换为高分辨率背景图。' },
  ],
};

export const mockProjects: Project[] = [
  {
    id: 'campus_romance',
    name: 'campus_romance',
    description: '转学生小林与图书管理员樱的校园恋爱故事',
    genre: '校园恋爱',
    updatedAt: '2026-04-15',
    chapterCount: 3,
    sceneCount: 8,
    confirmedScenes: 2,
    status: 'editing',
  },
  {
    id: 'cyber_detective',
    name: 'cyber_detective',
    description: '赛博朋克风格的侦探推理冒险',
    genre: '悬疑科幻',
    updatedAt: '2026-04-10',
    chapterCount: 5,
    sceneCount: 12,
    confirmedScenes: 8,
    status: 'editing',
  },
  {
    id: 'fantasy_journey',
    name: 'fantasy_journey',
    description: '异世界勇者小队的热血冒险',
    genre: '奇幻冒险',
    updatedAt: '2026-03-28',
    chapterCount: 4,
    sceneCount: 10,
    confirmedScenes: 10,
    status: 'completed',
  },
];

export function deriveFlowEdges(chapters: Chapter[]): FlowEdge[] {
  const edges: FlowEdge[] = [];
  for (const ch of chapters) {
    for (const scene of ch.scenes) {
      if (scene.choices) {
        for (const choice of scene.choices) {
          if (choice.nextSceneId) {
            edges.push({
              fromChapterId: ch.id,
              fromSceneId: scene.id,
              toChapterId: ch.id,
              toSceneId: choice.nextSceneId,
              type: 'branch',
              label: choice.text,
            });
          }
        }
      }
    }
  }
  return edges;
}

export function loadMockData(): { blueprint: BlueprintData; chapters: Chapter[]; auditReport: AuditReport | null } {
  return {
    blueprint: JSON.parse(JSON.stringify(mockBlueprint)),
    chapters: JSON.parse(JSON.stringify(mockChapters)),
    auditReport: JSON.parse(JSON.stringify(mockAuditReport)),
  };
}

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

// In-memory mock state per project
const projectDataMap = new Map<string, { blueprint: BlueprintData; chapters: Chapter[]; auditReport: AuditReport | null }>();

export function ensureProjectData(projectId: string) {
  if (!projectDataMap.has(projectId)) {
    projectDataMap.set(projectId, {
      blueprint: deepClone({ ...mockBlueprint, title: projectId }),
      chapters: deepClone(mockChapters),
      auditReport: deepClone(mockAuditReport),
    });
  }
  return projectDataMap.get(projectId)!;
}

export async function mockApiGet(path: string): Promise<unknown> {
  await new Promise((r) => setTimeout(r, 200));
  if (path === '/api/projects') {
    return deepClone(mockProjects);
  }
  if (path === '/api/projects/current') {
    return deepClone(mockProjects[0]);
  }
  const metaMatch = path.match(/^\/api\/projects\/([^/]+)\/meta$/);
  if (metaMatch) {
    const project = mockProjects.find((p) => p.id === metaMatch[1]);
    return project ? deepClone(project) : null;
  }
  const blueprintMatch = path.match(/^\/api\/projects\/([^/]+)\/blueprint$/);
  if (blueprintMatch) {
    return deepClone(ensureProjectData(blueprintMatch[1]).blueprint);
  }
  const scenesMatch = path.match(/^\/api\/projects\/([^/]+)\/scenes$/);
  if (scenesMatch) {
    return deepClone(ensureProjectData(scenesMatch[1]).chapters);
  }
  throw new Error(`Mock GET ${path} not implemented`);
}

export async function mockApiPost(path: string, body?: unknown): Promise<unknown> {
  await new Promise((r) => setTimeout(r, 200));
  if (path === '/api/projects') {
    const payload = body as { name: string; description?: string; genre?: string };
    const newProject: Project = {
      id: payload.name.toLowerCase().replace(/\s+/g, '_'),
      name: payload.name,
      description: payload.description || '',
      genre: payload.genre || '未分类',
      updatedAt: new Date().toISOString().split('T')[0],
      chapterCount: 0,
      sceneCount: 0,
      confirmedScenes: 0,
      status: 'draft',
    };
    mockProjects.unshift(newProject);
    return deepClone(newProject);
  }
  throw new Error(`Mock POST ${path} not implemented`);
}

export async function mockApiPut(path: string, body?: unknown): Promise<unknown> {
  void body;
  await new Promise((r) => setTimeout(r, 200));
  throw new Error(`Mock PUT ${path} not implemented`);
}
