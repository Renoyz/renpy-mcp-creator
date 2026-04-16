import { useState } from 'react';
import { RefreshCw, Check, Image } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ResourceCandidateCardProps {
  data: {
    type: 'background' | 'character';
    sceneId: string;
    urls: string[];
  };
}

export function ResourceCandidateCard({ data }: ResourceCandidateCardProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const handleConfirm = () => {
    if (selectedIndex !== null) {
      alert(`已选择方案 ${selectedIndex + 1}`);
    }
  };

  const handleRegenerate = () => {
    alert('重新生成候选...');
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <Image className="w-4 h-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {data.type === 'background' ? '背景候选' : '角色候选'}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Image Grid */}
        <div className="grid grid-cols-2 gap-2">
          {[1, 2, 3, 4].map((index) => (
            <button
              key={index}
              onClick={() => setSelectedIndex(index - 1)}
              className={cn(
                "aspect-square rounded-lg border-2 transition-all relative overflow-hidden",
                selectedIndex === index - 1
                  ? "border-blue-500 ring-2 ring-blue-500/20"
                  : "border-gray-200 dark:border-gray-700 hover:border-gray-300"
              )}
            >
              <div className="w-full h-full bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-700 flex items-center justify-center">
                <span className="text-2xl">
                  {data.type === 'background' ? '🖼️' : '👤'}
                </span>
              </div>
              {selectedIndex === index - 1 && (
                <div className="absolute inset-0 bg-blue-500/10 flex items-center justify-center">
                  <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center">
                    <Check className="w-5 h-5 text-white" />
                  </div>
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            onClick={handleRegenerate}
            variant="outline"
            className="flex-1 gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            重新生成
          </Button>
          <Button
            onClick={handleConfirm}
            className="flex-1"
            disabled={selectedIndex === null}
          >
            确认选择
          </Button>
        </div>
      </div>
    </div>
  );
}
