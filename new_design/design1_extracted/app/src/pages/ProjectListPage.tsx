import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '@/store/useAppStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Search,
  Plus,
  FolderOpen,
  Film,
  CheckCircle2,
  Clock,
  MoreHorizontal,
  Sparkles,
} from 'lucide-react';
import type { Project, ProjectStatus } from '@/types';
import { cn } from '@/lib/utils';

const genreOptions = [
  '校园恋爱',
  '悬疑科幻',
  '奇幻冒险',
  '恐怖惊悚',
  '日常喜剧',
  '历史穿越',
];

export function ProjectListPage() {
  const { projects, switchProject, createProject, loadProjects } = useAppStore();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [genreFilter, setGenreFilter] = useState<string>('all');
  const [newProjectOpen, setNewProjectOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newGenre, setNewGenre] = useState('校园恋爱');

  const filteredProjects = projects.filter((p: Project) => {
    const matchesSearch =
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      (p.description || '').toLowerCase().includes(search.toLowerCase());
    const matchesGenre = genreFilter === 'all' || p.genre === genreFilter;
    return matchesSearch && matchesGenre;
  });

  const handleOpenProject = (projectId: string) => {
    switchProject(projectId);
    navigate(`/project/${projectId}`);
  };

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await createProject(newName.trim(), newDesc.trim(), newGenre);
    setNewProjectOpen(false);
    setNewName('');
    setNewDesc('');
    navigate(`/project/${newName.toLowerCase().replace(/\s+/g, '_')}`);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <div className="border-b bg-white dark:bg-gray-900 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                AI Galgame Creator
              </h1>
              <p className="text-xs text-gray-500">基于 Spec + Dual-Agent 的 Ren'Py 视觉小说创作平台</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Dialog open={newProjectOpen} onOpenChange={setNewProjectOpen}>
              <DialogTrigger asChild>
                <Button className="gap-2">
                  <Plus className="w-4 h-4" />
                  新建项目
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>新建项目</DialogTitle>
                  <DialogDescription>
                    创建一个新的视觉小说项目，AI 将协助你生成蓝图和脚本。
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">项目名称</label>
                    <Input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="例如：樱花树下的约定"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">类型</label>
                    <Select value={newGenre} onValueChange={setNewGenre}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {genreOptions.map((g) => (
                          <SelectItem key={g} value={g}>
                            {g}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">描述</label>
                    <Input
                      value={newDesc}
                      onChange={(e) => setNewDesc(e.target.value)}
                      placeholder="简短描述项目主题..."
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setNewProjectOpen(false)}>
                    取消
                  </Button>
                  <Button onClick={handleCreate} disabled={!newName.trim()}>
                    创建
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索项目..."
              className="pl-9"
            />
          </div>
          <Select value={genreFilter} onValueChange={setGenreFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="全部类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              {genreOptions.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <Card>
            <CardContent className="p-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                <FolderOpen className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">{projects.length}</p>
                <p className="text-xs text-gray-500">项目总数</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {projects.filter((p) => p.confirmedScenes === p.sceneCount && (p.sceneCount || 0) > 0).length}
                </p>
                <p className="text-xs text-gray-500">已完成项目</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center">
                <Film className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {projects.reduce((acc, p) => acc + (p.sceneCount || 0), 0)}
                </p>
                <p className="text-xs text-gray-500">总场景数</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Project Grid */}
        {filteredProjects.length === 0 ? (
          <div className="text-center py-20">
            <FolderOpen className="w-16 h-16 mx-auto text-gray-300 mb-4" />
            <p className="text-gray-500">没有找到符合条件的项目</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {filteredProjects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onOpen={() => handleOpenProject(project.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ProjectCard({
  project,
  onOpen,
}: {
  project: Project;
  onOpen: () => void;
}) {
  const progress =
    (project.sceneCount || 0) > 0
      ? Math.round(((project.confirmedScenes || 0) / (project.sceneCount || 1)) * 100)
      : 0;

  const statusConfig: Record<ProjectStatus, { label: string; className: string; pulse?: boolean }> = {
    draft: { label: '草稿', className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
    blueprinting: { label: '生成蓝图', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', pulse: true },
    blueprinted: { label: '待确认', className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
    generating: { label: '生成场景', className: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400', pulse: true },
    editing: { label: '创作中', className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
    in_progress: { label: '创作中', className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
    completed: { label: '已完成', className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  };

  const status = statusConfig[project.status];

  return (
    <Card className="group overflow-hidden hover:shadow-md transition-shadow cursor-pointer" onClick={onOpen}>
      <div className="h-24 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 relative">
        <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-white/80 hover:text-white hover:bg-white/20"
            disabled
            title="功能开发中"
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button>
        </div>
      </div>
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h3 className="font-bold text-gray-900 dark:text-white text-lg">{project.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant="secondary">
                {project.genre}
              </Badge>
              <Badge className={cn('border-0 text-xs', status.className)}>
                {status.pulse && <span className="relative flex h-1.5 w-1.5 mr-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-current" />
                </span>}
                {status.label}
              </Badge>
            </div>
          </div>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-4">
          {project.description}
        </p>

        <div className="flex items-center gap-4 text-sm text-gray-500 mb-4">
          <div className="flex items-center gap-1">
            <Film className="w-4 h-4" />
            <span>{project.chapterCount} 章</span>
          </div>
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" />
            <span>
              {project.confirmedScenes}/{project.sceneCount} 场景已确认
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="w-4 h-4" />
            <span>{project.updatedAt}</span>
          </div>
        </div>

        {/* Progress */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-500">完成度</span>
            <span className={cn(
              'font-medium',
              progress === 100 ? 'text-green-600' : project.sceneCount === 0 ? 'text-gray-400' : 'text-blue-600'
            )}>
              {project.sceneCount === 0 ? '尚未开始' : `${progress}%`}
            </span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all',
                progress === 100 ? 'bg-green-500' : project.sceneCount === 0 ? 'bg-gray-300 dark:bg-gray-600' : 'bg-blue-500'
              )}
              style={{ width: project.sceneCount === 0 ? '0%' : `${progress}%` }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
