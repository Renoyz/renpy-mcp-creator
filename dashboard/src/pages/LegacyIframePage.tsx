import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useProject } from "../context/ProjectContext";

interface LegacyIframePageProps {
  path: string;
  title: string;
}

export function LegacyIframePage({ path, title }: LegacyIframePageProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loading, setLoading] = useState(true);
  const { currentProject } = useProject();

  useEffect(() => {
    setLoading(true);
  }, [path]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-10 items-center justify-between border-b bg-card px-4">
        <span className="text-sm font-medium text-muted-foreground">{title}</span>
        {currentProject && (
          <span className="text-xs text-muted-foreground">
            {currentProject.name}
          </span>
        )}
      </div>
      <div className="relative flex-1">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}
        <iframe
          ref={iframeRef}
          src={path}
          title={title}
          className="h-full w-full border-0"
          onLoad={() => setLoading(false)}
        />
      </div>
    </div>
  );
}
