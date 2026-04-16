import { useAppStore } from '@/store/useAppStore';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Play, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function TopBar() {
  const { currentProject } = useAppStore();
  const navigate = useNavigate();

  const handleBack = () => {
    navigate('/');
  };

  return (
    <div className="h-14 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 flex items-center justify-between px-4">
      {/* Left */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleBack}
          className="gap-2 text-gray-600 dark:text-gray-400"
        >
          <ArrowLeft className="w-4 h-4" />
          返回项目列表
        </Button>

        <div className="h-6 w-px bg-gray-200 dark:border-gray-800" />

        <h1 className="font-semibold text-gray-900 dark:text-white">
          {currentProject}
        </h1>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled
          title="功能开发中"
          className="gap-2"
        >
          <Wrench className="w-4 h-4" />
          Build
        </Button>

        <Button
          size="sm"
          disabled
          title="功能开发中"
          className="gap-2"
        >
          <Play className="w-4 h-4" />
          试玩
        </Button>
      </div>
    </div>
  );
}
