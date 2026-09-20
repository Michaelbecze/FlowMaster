import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Without this, an uncaught render error anywhere in a page (e.g. a chart
 * given a bad color value) unmounts the *entire* React tree — including the
 * nav in Layout — leaving a blank page with no working links. Catching it
 * here keeps the nav alive so the user can navigate away from the broken
 * page instead of being stuck on a blank screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string }) {
    console.error("Unhandled error in page content:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="card">
          <p className="card-title">Something went wrong loading this page</p>
          <p style={{ color: "var(--text-secondary)", marginBottom: 16 }}>
            {this.state.error.message}
          </p>
          <button onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}
