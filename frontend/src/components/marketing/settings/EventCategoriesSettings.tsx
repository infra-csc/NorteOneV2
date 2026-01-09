import React, { useState } from 'react';
import { Plus, Edit2, Trash2, Save, X, Tag, Users, DollarSign } from 'lucide-react';
import { EventCategory } from '../../../types/marketingSettings';
import { getEventCategories } from '../../../data/mockMarketingSettings';

const EventCategoriesSettings: React.FC = () => {
  const [categories, setCategories] = useState<EventCategory[]>(getEventCategories());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<EventCategory>>({});
  const [showNewForm, setShowNewForm] = useState(false);
  const [newCategory, setNewCategory] = useState<Partial<EventCategory>>({
    name: '',
    description: '',
    color: '#3b82f6',
    icon: 'tag',
    defaultCapacity: 5000,
    defaultTicketPrice: 150,
    isActive: true,
    eventCount: 0
  });

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('pt-BR').format(value);
  };

  const handleEdit = (category: EventCategory) => {
    setEditingId(category.id);
    setEditForm({ ...category });
  };

  const handleSave = () => {
    if (editingId && editForm) {
      setCategories(categories.map(c => 
        c.id === editingId ? { ...c, ...editForm } as EventCategory : c
      ));
      setEditingId(null);
      setEditForm({});
    }
  };

  const handleCancel = () => {
    setEditingId(null);
    setEditForm({});
  };

  const handleDelete = (id: string) => {
    setCategories(categories.filter(c => c.id !== id));
  };

  const handleToggleActive = (id: string) => {
    setCategories(categories.map(c => 
      c.id === id ? { ...c, isActive: !c.isActive } : c
    ));
  };

  const handleAddCategory = () => {
    if (newCategory.name && newCategory.description) {
      const existingIds = categories.map(c => Number(c.id));
      const newId = String(existingIds.length > 0 ? Math.max(...existingIds) + 1 : 1);
      setCategories([...categories, { ...newCategory, id: newId, eventCount: 0 } as EventCategory]);
      setNewCategory({
        name: '',
        description: '',
        color: '#3b82f6',
        icon: 'tag',
        defaultCapacity: 5000,
        defaultTicketPrice: 150,
        isActive: true,
        eventCount: 0
      });
      setShowNewForm(false);
    }
  };

  const colorOptions = [
    '#ef4444', '#f97316', '#eab308', '#22c55e', '#10b981',
    '#06b6d4', '#0ea5e9', '#3b82f6', '#6366f1', '#8b5cf6',
    '#a855f7', '#d946ef', '#ec4899', '#f43f5e'
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Gestão de Categorias de Eventos
          </h2>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Gerencie as categorias disponíveis para classificação de eventos
          </p>
        </div>
        <button
          onClick={() => setShowNewForm(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Nova Categoria
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <Tag className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-blue-600 dark:text-blue-400">Total de Categorias</p>
              <p className="text-2xl font-bold text-blue-800 dark:text-blue-200">{categories.length}</p>
            </div>
          </div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 dark:bg-green-900/40 rounded-lg">
              <Tag className="w-5 h-5 text-green-600 dark:text-green-400" />
            </div>
            <div>
              <p className="text-sm text-green-600 dark:text-green-400">Ativas</p>
              <p className="text-2xl font-bold text-green-800 dark:text-green-200">
                {categories.filter(c => c.isActive).length}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/40 rounded-lg">
              <Users className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <div>
              <p className="text-sm text-purple-600 dark:text-purple-400">Total de Eventos</p>
              <p className="text-2xl font-bold text-purple-800 dark:text-purple-200">
                {categories.reduce((sum, c) => sum + c.eventCount, 0)}
              </p>
            </div>
          </div>
        </div>
        <div className="bg-amber-50 dark:bg-amber-900/20 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-100 dark:bg-amber-900/40 rounded-lg">
              <DollarSign className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-sm text-amber-600 dark:text-amber-400">Ticket Médio</p>
              <p className="text-2xl font-bold text-amber-800 dark:text-amber-200">
                {formatCurrency(categories.reduce((sum, c) => sum + c.defaultTicketPrice, 0) / categories.length)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {showNewForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Nova Categoria</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nome</label>
              <input
                type="text"
                value={newCategory.name || ''}
                onChange={(e) => setNewCategory({ ...newCategory, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Nome da categoria"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Descrição</label>
              <input
                type="text"
                value={newCategory.description || ''}
                onChange={(e) => setNewCategory({ ...newCategory, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Descrição breve"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Cor</label>
              <div className="flex flex-wrap gap-2">
                {colorOptions.map((color) => (
                  <button
                    key={color}
                    onClick={() => setNewCategory({ ...newCategory, color })}
                    className={`w-6 h-6 rounded-full border-2 ${newCategory.color === color ? 'border-gray-800 dark:border-white' : 'border-transparent'}`}
                    style={{ backgroundColor: color }}
                  />
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Capacidade Padrão</label>
              <input
                type="number"
                value={newCategory.defaultCapacity || 0}
                onChange={(e) => setNewCategory({ ...newCategory, defaultCapacity: Number(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Preço Ticket Padrão</label>
              <input
                type="number"
                step="0.01"
                value={newCategory.defaultTicketPrice || 0}
                onChange={(e) => setNewCategory({ ...newCategory, defaultTicketPrice: Number(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={() => setShowNewForm(false)}
              className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              Cancelar
            </button>
            <button
              onClick={handleAddCategory}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Adicionar
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {categories.map((category) => (
          <div
            key={category.id}
            className={`bg-white dark:bg-gray-800 rounded-xl border-2 p-4 transition-all ${
              category.isActive
                ? 'border-gray-200 dark:border-gray-700'
                : 'border-gray-100 dark:border-gray-800 opacity-60'
            }`}
          >
            {editingId === category.id ? (
              <div className="space-y-3">
                <input
                  type="text"
                  value={editForm.name || ''}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
                <input
                  type="text"
                  value={editForm.description || ''}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
                <div className="flex flex-wrap gap-2">
                  {colorOptions.map((color) => (
                    <button
                      key={color}
                      onClick={() => setEditForm({ ...editForm, color })}
                      className={`w-6 h-6 rounded-full border-2 ${editForm.color === color ? 'border-gray-800 dark:border-white' : 'border-transparent'}`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={editForm.defaultCapacity || 0}
                    onChange={(e) => setEditForm({ ...editForm, defaultCapacity: Number(e.target.value) })}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                    placeholder="Capacidade"
                  />
                  <input
                    type="number"
                    step="0.01"
                    value={editForm.defaultTicketPrice || 0}
                    onChange={(e) => setEditForm({ ...editForm, defaultTicketPrice: Number(e.target.value) })}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                    placeholder="Ticket"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <button onClick={handleCancel} className="p-2 text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                    <X className="w-4 h-4" />
                  </button>
                  <button onClick={handleSave} className="p-2 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 rounded-lg">
                    <Save className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: category.color + '20' }}
                    >
                      <Tag className="w-5 h-5" style={{ color: category.color }} />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900 dark:text-white">{category.name}</h4>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{category.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleEdit(category)}
                      className="p-1.5 text-blue-600 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(category.id)}
                      className="p-1.5 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-lg"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2">
                    <p className="text-gray-500 dark:text-gray-400 text-xs">Eventos</p>
                    <p className="font-semibold text-gray-900 dark:text-white">{category.eventCount}</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2">
                    <p className="text-gray-500 dark:text-gray-400 text-xs">Capacidade</p>
                    <p className="font-semibold text-gray-900 dark:text-white">{formatNumber(category.defaultCapacity)}</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-2">
                    <p className="text-gray-500 dark:text-gray-400 text-xs">Ticket</p>
                    <p className="font-semibold text-gray-900 dark:text-white">{formatCurrency(category.defaultTicketPrice)}</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <button
                    onClick={() => handleToggleActive(category.id)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      category.isActive ? 'bg-green-600' : 'bg-gray-300 dark:bg-gray-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        category.isActive ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                  <span className={`text-sm ${category.isActive ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}>
                    {category.isActive ? 'Ativa' : 'Inativa'}
                  </span>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default EventCategoriesSettings;
