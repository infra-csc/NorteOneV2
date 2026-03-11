import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, ArrowLeft, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackNavigate?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  handleNavigateBack = () => {
    window.location.href = this.props.fallbackNavigate || '/marketing';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6">
          <div className="flex items-center gap-2 mb-6">
            <button
              onClick={this.handleNavigateBack}
              className="flex items-center gap-2 text-blue-600 dark:text-blue-400 hover:underline"
            >
              <ArrowLeft className="w-5 h-5" />
              Voltar ao Dashboard
            </button>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-8 text-center">
            <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-2">
              Ocorreu um erro ao carregar esta página
            </h2>
            <p className="text-gray-500 dark:text-gray-400 mb-4">
              Tente recarregar ou voltar ao dashboard.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReset}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <RotateCcw className="w-4 h-4" />
                Tentar novamente
              </button>
              <button
                onClick={this.handleNavigateBack}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Voltar ao Dashboard
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
