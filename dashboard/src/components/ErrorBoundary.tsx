import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center p-6 text-center">
          <h1 className="text-2xl font-bold text-destructive">出错了</h1>
          <p className="mt-2 text-muted-foreground">
            Dashboard 遇到了意外错误，请刷新页面重试。
          </p>
          <pre className="mt-4 max-w-lg rounded-md bg-muted p-4 text-left text-xs text-muted-foreground">
            {this.state.error?.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-6 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
