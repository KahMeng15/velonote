import { useState } from 'react';
import { useMediaQuery } from '@mantine/hooks';
import { Card, Text, Group, Progress, ActionIcon, ScrollArea, Stack, CloseButton, Portal, Center, RingProgress, Paper, Loader } from '@mantine/core';
import { IconX, IconCheck, IconAlertCircle, IconChevronUp, IconChevronDown } from '@tabler/icons-react';
import { fetchApi } from '../lib/api';
import { useTaskContext } from '../lib/TaskContext';

export default function TaskQueueModal() {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const { tasks, refreshTasks } = useTaskContext();
  const [dismissedTaskIds, setDismissedTaskIds] = useState(new Set());
  const [isMinimized, setIsMinimized] = useState(false);

  // active tasks minus dismissed minus chat
  const visibleTasks = tasks.filter(t => !dismissedTaskIds.has(t.task_id) && t.task_type !== 'chat_response');

  if (visibleTasks.length === 0) return null;

  const handleCancel = async (taskId) => {
    try {
      await fetchApi(`/search/tasks/${taskId}/cancel`, { method: 'POST' });
      refreshTasks();
    } catch (err) {
      console.error('Failed to cancel task', err);
    }
  };

  const handleDismiss = async (taskId) => {
    try {
      await fetchApi(`/search/tasks/${taskId}/dismiss`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to dismiss task', err);
    }
    setDismissedTaskIds(prev => new Set(prev).add(taskId));
  };

  const getTaskIcon = (status) => {
    if (status === 'completed') return <IconCheck size={16} color="green" />;
    if (status === 'failed') return <IconAlertCircle size={16} color="red" />;
    if (status === 'pending') return <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#fcc419' }} />;
    return <Loader size={14} />;
  };

  const activeTasksForProgress = visibleTasks.filter(t => t.status === 'pending' || t.status === 'processing' || t.status === 'running');
  const overallProgress = activeTasksForProgress.length > 0
    ? activeTasksForProgress.reduce((sum, t) => sum + (t.progress || 0), 0) / activeTasksForProgress.length
    : 0;
  const hasActiveTasks = activeTasksForProgress.length > 0;

  if (isMobile && isMinimized) {
    return (
      <Portal>
        <div
          style={{ position: 'fixed', bottom: 80, right: 20, zIndex: 100, cursor: 'pointer' }}
          onClick={() => setIsMinimized(false)}
        >
          <Paper shadow="xl" radius="xl" p={2} withBorder bg="white">
            <RingProgress
              size={48}
              thickness={3}
              roundCaps
              sections={hasActiveTasks
                ? [{ value: overallProgress, color: 'blue' }]
                : [{ value: 100, color: 'green' }]
              }
              label={
                <Center>
                  {hasActiveTasks ? (
                    <Text size="xs" fw={700}>{Math.round(overallProgress)}%</Text>
                  ) : (
                    <IconCheck size={18} color="green" />
                  )}
                </Center>
              }
            />
          </Paper>
        </div>
      </Portal>
    );
  }

  return (
    <Portal>
      <div style={{ position: 'fixed', bottom: isMobile ? 80 : 20, right: 20, zIndex: 100, width: 350, transition: 'all 0.3s ease' }}>
        <Card shadow="xl" padding="md" radius="md" withBorder style={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', backdropFilter: 'blur(10px)' }}>
          <Group justify="space-between" mb={(isMinimized && !hasActiveTasks) ? 0 : "sm"}>
            <Text fw={600} size="sm">Tasks ({visibleTasks.length})</Text>
            <Group gap="xs">
              <ActionIcon variant="subtle" size="sm" onClick={() => setIsMinimized(!isMinimized)}>
                {isMinimized ? <IconChevronUp size={16} /> : <IconChevronDown size={16} />}
              </ActionIcon>
            </Group>
          </Group>

          {!isMobile && isMinimized && hasActiveTasks && (
            <Progress 
              value={overallProgress} 
              size="xs" 
              animated 
              striped 
            />
          )}

          {!isMinimized && (
            <Card.Section withBorder>
              <ScrollArea.Autosize mah={300} py="xs">
                <Stack gap="xs">
                  {visibleTasks.map((task, index) => {
                    let title = task.task_type;
                    if (task.input_data && task.input_data.kwargs) {
                      if (task.input_data.kwargs.title) {
                        title = task.input_data.kwargs.title;
                      } else if (task.input_data.kwargs.file_name) {
                        title = task.input_data.kwargs.file_name;
                      } else if (task.input_data.kwargs.file_path) {
                        title = task.input_data.kwargs.file_path.split('/').pop();
                      }
                    }
                    
                    // Hide common file extensions from the title
                    title = title.replace(/\.[^/.]+$/, "");

                    let typeLabel = task.task_type;
                    if (typeLabel === 'resource_processing' || typeLabel === 'ocr') typeLabel = 'Processing resource';
                    if (typeLabel === 'exercise_extraction') typeLabel = 'Extracting exercise';
                    if (typeLabel === 'exercise_generation') typeLabel = 'Generating exercise';
                    if (typeLabel === 'note_generation') typeLabel = 'Generating note';
                    if (typeLabel === 'embedding') typeLabel = 'Indexing resource';

                    const isRunning = task.status === 'pending' || task.status === 'processing' || task.status === 'running';
                    let statusFormatted = task.status.charAt(0).toUpperCase() + task.status.slice(1);
                    if (task.status === 'failed' && task.error === 'Cancelled by user') {
                      statusFormatted = 'Cancelled';
                    }
                    const displaySubtitle = `${typeLabel} (${isRunning ? 'Running' : statusFormatted})`;

                    return (
                      <div key={task.task_id} style={{ 
                        paddingBottom: '8px', 
                        paddingTop: index === 0 ? '4px' : '8px',
                        paddingLeft: '16px',
                        paddingRight: '16px',
                        borderBottom: index < visibleTasks.length - 1 ? '1px solid #eaeaea' : 'none' 
                      }}>
                        <Group justify="space-between" wrap="nowrap" align="flex-start" w="100%">
                          <Group gap="xs" wrap="nowrap" style={{ flex: 1, overflow: 'hidden' }}>
                            {getTaskIcon(task.status)}
                            <div style={{ flex: 1, overflow: 'hidden' }}>
                              <Text size="sm" fw={500} lineClamp={2} style={{ wordBreak: 'break-word' }}>{title}</Text>
                              <Text size="xs" c="dimmed" truncate>{displaySubtitle}</Text>
                            </div>
                          </Group>
                          <Group gap={4}>
                            {isRunning && (
                              <ActionIcon color="red" variant="subtle" size="sm" onClick={() => handleCancel(task.task_id)} title="Cancel task">
                                <IconX size={14} />
                              </ActionIcon>
                            )}
                            {!isRunning && (
                              <CloseButton size="sm" onClick={() => handleDismiss(task.task_id)} title="Dismiss" />
                            )}
                          </Group>
                        </Group>
                        
                        {isRunning && (
                          <Progress 
                            value={task.progress || 0} 
                            size="xs" 
                            mt={8} 
                            animated={task.status === 'processing' || task.status === 'running'} 
                            striped
                          />
                        )}
                        
                        {task.status === 'failed' && task.error && (
                          <Text size="xs" c="red" mt={4} truncate>{task.error}</Text>
                        )}
                      </div>
                    );
                  })}
                </Stack>
              </ScrollArea.Autosize>
            </Card.Section>
          )}
        </Card>
      </div>
    </Portal>
  );
}
