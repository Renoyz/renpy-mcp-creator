import { useState, useMemo } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Search,
  Image,
  Music,
  User,
  LayoutTemplate,
  Video,
  RefreshCw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FolderOpen,
} from 'lucide-react';
import type { Scene, ResourceItem } from '@/types';
import { cn } from '@/lib/utils';

const mockResources: ResourceItem[] = [
  { id: 'r1', name: '图书馆早晨', type: 'background', status: 'ready', size: '2.4 MB', updatedAt: '2026-04-14', usedIn: ['s1-1', 's1-2'] },
  { id: 'r2', name: '图书馆柜台', type: 'background', status: 'ready', size: '2.1 MB', updatedAt: '2026-04-14', usedIn: ['s1-2'] },
  { id: 'r3', name: '图书馆入口', type: 'background', status: 'generating', size: '-', updatedAt: '-', usedIn: ['s1-3'] },
  {
    id: 'r4',
    name: '樱',
    type: 'character',
    status: 'ready',
    size: '4.8 MB',
    updatedAt: '2026-04-14',
    usedIn: ['s1-1', 's1-2', 's1-3'],
    variants: [
      { id: 'r4-1', name: 'neutral', status: 'ready' },
      { id: 'r4-2', name: 'happy', status: 'ready' },
      { id: 'r4-3', name: 'sad', status: 'ready' },
      { id: 'r4-4', name: 'surprised', status: 'ready' },
      { id: 'r4-5', name: 'angry', status: 'generating' },
    ],
  },
  {
    id: 'r5',
    name: '小林',
    type: 'character',
    status: 'ready',
    size: '3.6 MB',
    updatedAt: '2026-04-14',
    usedIn: ['s1-1'],
    variants: [
      { id: 'r5-1', name: 'neutral', status: 'ready' },
      { id: 'r5-2', name: 'happy', status: 'ready' },
      { id: 'r5-3', name: 'sad', status: 'ready' },
      { id: 'r5-4', name: 'surprised', status: 'missing' },
      { id: 'r5-5', name: 'angry', status: 'missing' },
    ],
  },
  { id: 'r8', name: 'bgm_peaceful.mp3', type: 'audio', status: 'ready', size: '4.5 MB', updatedAt: '2026-04-13', usedIn: ['s1-1'] },
  { id: 'r9', name: 'bgm_tension.mp3', type: 'audio', status: 'unused', size: '3.8 MB', updatedAt: '2026-04-10', usedIn: [] },
  { id: 'r10', name: 'main_menu_bg.jpg', type: 'ui', status: 'ready', size: '3.2 MB', updatedAt: '2026-04-12', usedIn: ['ui'] },
];

const typeConfig = {
  background: { label: '背景', icon: Image, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20' },
  character: { label: '角色', icon: User, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-900/20' },
  audio: { label: '音频', icon: Music, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
  ui: { label: 'UI', icon: LayoutTemplate, color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20' },
  video: { label: '视频', icon: Video, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/20' },
};

const statusConfig = {
  ready: { label: '就绪', icon: CheckCircle2, className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  generating: { label: '生成中', icon: Loader2, className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  missing: { label: '缺失', icon: AlertCircle, className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
  unused: { label: '未使用', icon: FolderOpen, className: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' },
};

export function ResourcesView() {
  const { selectedSceneId, chapters } = useAppStore();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null);
  const [variantDialogOpen, setVariantDialogOpen] = useState(false);
  const [variantDialogResource, setVariantDialogResource] = useState<ResourceItem | null>(null);

  let sceneName = '';
  for (const ch of chapters) {
    const scene = ch.scenes.find((s: Scene) => s.id === selectedSceneId);
    if (scene) {
      sceneName = scene.name;
      break;
    }
  }

  const baseResources = useMemo(() => {
    if (!selectedSceneId) return mockResources;
    return mockResources.filter((r) => r.usedIn?.includes(selectedSceneId) || r.usedIn?.includes('ui'));
  }, [selectedSceneId]);

  const filteredResources = useMemo(() => {
    return baseResources.filter((r) => {
      const matchesSearch = r.name.toLowerCase().includes(search.toLowerCase());
      const matchesType = typeFilter === 'all' || r.type === typeFilter;
      return matchesSearch && matchesType;
    });
  }, [baseResources, search, typeFilter]);

  const displayedSelectedResourceId = filteredResources.some((r) => r.id === selectedResourceId)
    ? selectedResourceId
    : null;

  const selectedResource = useMemo(() => {
    return filteredResources.find((r) => r.id === displayedSelectedResourceId) || null;
  }, [filteredResources, displayedSelectedResourceId]);

  const openVariantDialog = (resource: ResourceItem) => {
    setVariantDialogResource(resource);
    setVariantDialogOpen(true);
  };

  return (
    <div className="h-full flex">
      {/* Left: Resource List */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {selectedSceneId ? `${sceneName} 的资源` : '项目资源库'}
              </h3>
              <p className="text-xs text-gray-500">
                共 {filteredResources.length} 个资源
                {selectedSceneId && ' · 已按当前场景过滤'}
              </p>
            </div>
            <Button size="sm" variant="outline" className="gap-2" disabled title="功能开发中">
              <RefreshCw className="w-4 h-4" />
              批量生成缺失资源
            </Button>
          </div>

          {/* Filters */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索资源..."
                className="pl-9 h-9"
              />
            </div>
            <Tabs value={typeFilter} onValueChange={setTypeFilter}>
              <TabsList className="h-9">
                <TabsTrigger value="all" className="text-xs px-3">全部</TabsTrigger>
                <TabsTrigger value="background" className="text-xs px-3">背景</TabsTrigger>
                <TabsTrigger value="character" className="text-xs px-3">角色</TabsTrigger>
                <TabsTrigger value="audio" className="text-xs px-3">音频</TabsTrigger>
                <TabsTrigger value="ui" className="text-xs px-3">UI</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>

        {/* Resource Grid */}
        <div className="flex-1 overflow-y-auto p-5">
          {filteredResources.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <FolderOpen className="w-12 h-12 mb-3 text-gray-300" />
              <p>未找到符合条件的资源</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredResources.map((res) => (
                <ResourceCard
                  key={res.id}
                  resource={res}
                  selected={displayedSelectedResourceId === res.id}
                  onClick={() => setSelectedResourceId(res.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Resource Detail */}
      {selectedResource && (
        <div className="w-80 border-l border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50 p-5 flex flex-col">
          <h4 className="font-semibold text-gray-900 dark:text-white mb-4">资源详情</h4>

          {/* Preview */}
          <div className="rounded-xl bg-gray-200 dark:bg-gray-800 mb-4 flex items-center justify-center overflow-hidden">
            {selectedResource.type === 'character' ? (
              <div className="w-full p-4">
                <div className="aspect-[3/4] rounded-lg bg-gradient-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30 flex items-center justify-center mb-3">
                  <User className="w-16 h-16 text-purple-400" />
                </div>
                {selectedResource.variants && selectedResource.variants.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-gray-500">表情变体</p>
                      <Button
                        variant="link"
                        size="sm"
                        className="h-auto p-0 text-xs"
                        onClick={() => openVariantDialog(selectedResource)}
                      >
                        查看全部
                      </Button>
                    </div>
                    <div className="flex gap-1.5">
                      {selectedResource.variants.slice(0, 5).map((variant) => (
                        <div
                          key={variant.id}
                          className={cn(
                            "w-8 h-8 rounded border flex items-center justify-center flex-shrink-0",
                            variant.status === 'missing'
                              ? "bg-gray-100 border-gray-200"
                              : "bg-purple-50 border-purple-200"
                          )}
                          title={variant.name}
                        >
                          <User className={cn('w-4 h-4', variant.status === 'missing' ? 'text-gray-300' : 'text-purple-400')} />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="aspect-video w-full flex items-center justify-center">
                {selectedResource.type === 'background' && <div className="text-5xl">🖼️</div>}
                {selectedResource.type === 'audio' && <div className="text-5xl">🎵</div>}
                {selectedResource.type === 'ui' && <div className="text-5xl">🎨</div>}
                {selectedResource.type === 'video' && <div className="text-5xl">🎬</div>}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-xs text-gray-500 mb-1">文件名</p>
              <p className="text-sm font-medium text-gray-900 dark:text-white break-all">
                {selectedResource.name}
              </p>
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <p className="text-xs text-gray-500 mb-1">类型</p>
                <Badge variant="outline">
                  {typeConfig[selectedResource.type].label}
                </Badge>
              </div>
              <div className="flex-1">
                <p className="text-xs text-gray-500 mb-1">状态</p>
                <Badge className={cn(statusConfig[selectedResource.status].className, 'border-0')}>
                  {statusConfig[selectedResource.status].label}
                </Badge>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <p className="text-xs text-gray-500 mb-1">大小</p>
                <p className="text-sm text-gray-900 dark:text-white">{selectedResource.size}</p>
              </div>
              <div className="flex-1">
                <p className="text-xs text-gray-500 mb-1">更新时间</p>
                <p className="text-sm text-gray-900 dark:text-white">{selectedResource.updatedAt}</p>
              </div>
            </div>

            <div>
              <p className="text-xs text-gray-500 mb-1">使用场景</p>
              <div className="flex flex-wrap gap-2">
                {selectedResource.usedIn && selectedResource.usedIn.length > 0 ? (
                  selectedResource.usedIn.map((sceneId) => (
                    <Badge key={sceneId} variant="secondary" className="text-xs">
                      {sceneId === 'ui' ? 'UI 全局' : `Scene ${sceneId}`}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-gray-400">未使用</span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-auto pt-4 space-y-2">
            {selectedResource.type === 'character' && selectedResource.variants && selectedResource.variants.length > 0 && (
              <Button
                className="w-full"
                size="sm"
                variant="outline"
                onClick={() => openVariantDialog(selectedResource)}
              >
                查看全部 {selectedResource.variants.length} 个表情变体
              </Button>
            )}
            <Button className="w-full" size="sm" disabled title="功能开发中">
              <RefreshCw className="w-4 h-4 mr-2" />
              重新生成
            </Button>
            <Button variant="outline" className="w-full text-red-600 hover:text-red-700" size="sm" disabled title="功能开发中">
              <Trash2 className="w-4 h-4 mr-2" />
              删除资源
            </Button>
          </div>
        </div>
      )}

      {/* Variant Dialog */}
      <Dialog open={variantDialogOpen} onOpenChange={setVariantDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center">
                <User className="w-5 h-5 text-white" />
              </div>
              <div>
                <div>{variantDialogResource?.name}</div>
                <span className="text-xs text-gray-500 font-normal">表情变体一览</span>
              </div>
            </DialogTitle>
            <DialogDescription>
              共 {variantDialogResource?.variants?.length || 0} 个变体，缺失或生成中的变体可点击重新生成。
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-5 gap-4 py-2">
            {variantDialogResource?.variants?.map((variant) => (
              <div key={variant.id} className="flex flex-col items-center gap-2">
                <div className={cn(
                  "w-full aspect-square rounded-xl flex items-center justify-center border relative",
                  variant.status === 'missing'
                    ? "bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
                    : "bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800"
                )}>
                  <User className={cn(
                    "w-8 h-8",
                    variant.status === 'missing' ? "text-gray-300" : "text-purple-400"
                  )} />
                  {variant.status === 'generating' && (
                    <Loader2 className="w-4 h-4 text-blue-500 animate-spin absolute" />
                  )}
                  {variant.status === 'ready' && (
                    <CheckCircle2 className="w-4 h-4 text-green-500 absolute top-1 right-1" />
                  )}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{variant.name}</p>
                  <Badge className={cn('text-[10px] px-1.5 py-0 border-0 mt-1', statusConfig[variant.status].className)}>
                    {statusConfig[variant.status].label}
                  </Badge>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 flex gap-2">
            <Button className="flex-1" size="sm" disabled title="功能开发中">
              <RefreshCw className="w-4 h-4 mr-2" />
              重新生成缺失变体
            </Button>
            <Button variant="outline" className="flex-1" size="sm" onClick={() => setVariantDialogOpen(false)}>
              关闭
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ResourceCard({
  resource,
  selected,
  onClick,
}: {
  resource: ResourceItem;
  selected: boolean;
  onClick: () => void;
}) {
  const TypeIcon = typeConfig[resource.type].icon;
  const StatusIcon = statusConfig[resource.status].icon;

  return (
    <div
      onClick={onClick}
      className={cn(
        'group rounded-xl border p-0 cursor-pointer transition-all hover:shadow-sm overflow-hidden',
        selected
          ? 'border-blue-500 bg-blue-50/30 dark:bg-blue-900/10 ring-1 ring-blue-500'
          : 'border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950'
      )}
    >
      {resource.type === 'character' ? (
        <div className="p-4">
          {/* Character preview */}
          <div className="aspect-[3/4] rounded-lg bg-gradient-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30 mb-3 flex items-center justify-center relative">
            <User className="w-12 h-12 text-purple-400" />
            <div className="absolute top-2 right-2">
              <Badge className={cn('text-[10px] px-1.5 py-0 border-0', statusConfig[resource.status].className)}>
                <StatusIcon className={cn('w-3 h-3 mr-1', resource.status === 'generating' && 'animate-spin')} />
                {statusConfig[resource.status].label}
              </Badge>
            </div>
          </div>
          {/* Info */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate" title={resource.name}>
                {resource.name}
              </p>
              <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                <TypeIcon className={cn('w-3 h-3', typeConfig[resource.type].color)} />
                {resource.variants ? `${resource.variants.length} 个变体` : '角色'}
              </p>
            </div>
          </div>
          {/* Variant thumbnails strip */}
          {resource.variants && resource.variants.length > 0 && (
            <div className="mt-3 flex gap-1.5 overflow-hidden">
              {resource.variants.map((v) => (
                <div
                  key={v.id}
                  className={cn(
                    "w-6 h-6 rounded border flex items-center justify-center flex-shrink-0",
                    v.status === 'missing'
                      ? "bg-gray-100 border-gray-200"
                      : "bg-purple-50 border-purple-200"
                  )}
                  title={v.name}
                >
                  <User className={cn('w-3 h-3', v.status === 'missing' ? 'text-gray-300' : 'text-purple-400')} />
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Preview */}
          <div className="aspect-video bg-gray-100 dark:bg-gray-900 m-4 mb-3 rounded-lg flex items-center justify-center relative overflow-hidden">
            {resource.type === 'background' && <div className="text-4xl">🖼️</div>}
            {resource.type === 'audio' && <div className="text-4xl">🎵</div>}
            {resource.type === 'ui' && <div className="text-4xl">🎨</div>}
            {resource.type === 'video' && <div className="text-4xl">🎬</div>}

            <div className="absolute top-2 right-2">
              <Badge className={cn('text-[10px] px-1.5 py-0 border-0', statusConfig[resource.status].className)}>
                <StatusIcon className={cn('w-3 h-3 mr-1', resource.status === 'generating' && 'animate-spin')} />
                {statusConfig[resource.status].label}
              </Badge>
            </div>
          </div>

          {/* Info */}
          <div className="px-4 pb-4 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate" title={resource.name}>
                {resource.name}
              </p>
              <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                <TypeIcon className={cn('w-3 h-3', typeConfig[resource.type].color)} />
                {typeConfig[resource.type].label}
                {resource.size && resource.size !== '-' && <span>· {resource.size}</span>}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
