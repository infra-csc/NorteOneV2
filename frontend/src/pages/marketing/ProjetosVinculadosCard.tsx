import React from 'react';
import { useNavigate } from 'react-router-dom';

export interface ProjetoVinculado {
  id: number;
  nome: string;
  sku: string;
}

interface ProjetosVinculadosCardProps {
  projetosVinculados: ProjetoVinculado[];
  anosDisponiveis: number[];
  anoParam: number | undefined;
  eventId: string | undefined;
}

/**
 * Card "Projetos Vinculados" da visão consolidada (grupo).
 * Extraído de EventDetail.tsx sem mudança visual ou de comportamento.
 */
const ProjetosVinculadosCard: React.FC<ProjetosVinculadosCardProps> = ({
  projetosVinculados,
  anosDisponiveis,
  anoParam,
  eventId,
}) => {
  const navigate = useNavigate();
  if (projetosVinculados.length === 0) return null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 dark:text-white">
          Projetos Vinculados ({projetosVinculados.length})
        </h3>
        {anosDisponiveis.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Ano:</span>
            <select
              value={anoParam || new Date().getFullYear()}
              onChange={(e) => {
                navigate(`/marketing/evento/${eventId}?ano=${e.target.value}`);
              }}
              className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500"
            >
              {anosDisponiveis.map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {projetosVinculados.map((p) => (
          <span
            key={p.id}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg text-sm"
          >
            <span className="font-medium">{p.sku}</span>
            <span className="text-blue-500 dark:text-blue-400">-</span>
            <span>{p.nome || 'Sem nome'}</span>
          </span>
        ))}
      </div>
    </div>
  );
};

export default ProjetosVinculadosCard;
