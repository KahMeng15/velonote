import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { fetchApi } from './api';

const TaskContext = createContext(null);

const POLL_INTERVAL = 3000;

export function TaskProvider({ children }) {
  const [tasks, setTasks] = useState([]);
  const pollRef = useRef(null);
  const pollGenRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    const gen = pollGenRef.current;
    try {
      const data = await fetchApi('/search/tasks/active');
      if (data && data.tasks) {
        setTasks(data.tasks);
        const hasActive = data.tasks.some(
          t => t.status === 'pending' || t.status === 'processing' || t.status === 'running'
        );
        if (!hasActive) {
          if (gen === pollGenRef.current) {
            stopPolling();
          }
          return false;
        }
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to fetch tasks', err);
      return false;
    }
  }, [stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollGenRef.current += 1;
    fetchTasks();
    pollRef.current = setInterval(fetchTasks, POLL_INTERVAL);
  }, [fetchTasks, stopPolling]);

  useEffect(() => {
    if (!localStorage.getItem('token')) return;

    let cancelled = false;

    fetchTasks().then(hasTasks => {
      if (cancelled) return;
      if (hasTasks) startPolling();
    });

    const handleTaskStarted = () => {
      startPolling();
    };
    window.addEventListener('task_started', handleTaskStarted);

    return () => {
      cancelled = true;
      stopPolling();
      window.removeEventListener('task_started', handleTaskStarted);
    };
  }, [fetchTasks, startPolling, stopPolling]);

  return (
    <TaskContext.Provider value={{ tasks, refreshTasks: fetchTasks }}>
      {children}
    </TaskContext.Provider>
  );
}

export function useTaskContext() {
  const ctx = useContext(TaskContext);
  if (!ctx) throw new Error('useTaskContext must be used within TaskProvider');
  return ctx;
}
