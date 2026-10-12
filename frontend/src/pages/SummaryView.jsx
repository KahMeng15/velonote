import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useDisclosure } from '@mantine/hooks';
import { Box, Container, Title, Text, Button, Center, Loader, Select, ScrollArea, Group, ActionIcon, Stack, Paper, Modal, Progress, Badge, Tooltip, NavLink as MantineNavLink, SegmentedControl, Textarea, TextInput, Menu, Code, Drawer, Card, Divider } from '@mantine/core';
import { IconRobot, IconAlertCircle, IconFileText, IconCheck, IconChevronLeft, IconLayoutSidebarRightCollapse, IconLayoutSidebarRightExpand, IconSparkles, IconBolt, IconWand, IconBrain, IconSchool, IconBabyCarriage, IconList, IconListNumbers, IconTable, IconFile, IconLayersLinked, IconBinaryTree, IconCpu, IconDeviceFloppy, IconPencil, IconX, IconH1, IconH2, IconH3, IconTypography, IconCode, IconEye, IconDownload, IconPhotoPlus } from '@tabler/icons-react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import { ResizableImageExtension } from '../lib/ResizableImageExtension';
import { ImageUploadExtension, handleImageUploadFlow } from '../lib/tiptapImageUpload';
import { LazyImage } from '../components/LazyImage';
import ProcessLoggerModal from '../components/ProcessLoggerModal';
import * as TablerIcons from '@tabler/icons-react';
import { formatParams } from '../lib/formatters';

const MODE_ICONS = {
  quick: <IconBolt size={14} />,
  simple: <IconWand size={14} />,
  normal: <IconBrain size={14} />,
  elaborate: <IconSchool size={14} />,
  eli5: <IconBabyCarriage size={14} />,
};

const FORMAT_ICONS = {
  sentence: <IconFileText size={14} />,
  pointform: <IconList size={14} />,
  numbered_list: <IconListNumbers size={14} />,
  table: <IconTable size={14} />,
};

const METHOD_ICONS = {
  whole: <IconFile size={14} />,
  section: <IconLayersLinked size={14} />,
  chunked: <IconCpu size={14} />,
  hierarchical: <IconBinaryTree size={14} />,
};

const getIconComponent = (iconName) => {
  if (!iconName) return TablerIcons.IconFileText;
  if (TablerIcons[iconName]) return TablerIcons[iconName];
  
  // Try to fix formatting: e.g. 'school' -> 'IconSchool', 'file-text' -> 'IconFileText'
  const formattedName = 'Icon' + iconName.split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()).join('');
  if (TablerIcons[formattedName]) return TablerIcons[formattedName];
  
  return TablerIcons.IconFileText;
};

const formatDate = (dateString) => {
  const d = new Date(dateString);
  let hours = d.getHours();
  const minutes = d.getMinutes().toString().padStart(2, '0');
  const ampm = hours >= 12 ? 'pm' : 'am';
  hours = hours % 12;
  hours = hours ? hours : 12;
  const day = d.getDate();
  const month = d.toLocaleString('en-US', { month: 'long' });
  const year = d.getFullYear();
  return `${hours}.${minutes}${ampm}, ${day} ${month} ${year}`;
};

import { useNavigate, useParams } from 'react-router-dom';
import { fetchApi } from '../lib/api';
import { useTaskContext } from '../lib/TaskContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkUnwrapImages from 'remark-unwrap-images';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

export default function SummaryView() {
  const { summaryId } = useParams();
  const navigate = useNavigate();

  const [note, setNote] = useState(null);
  const [summaries, setSummaries] = useState([]);
  const [selectedSummary, setSelectedSummary] = useState(null);
  const [summaryContent, setSummaryContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalOpened, setModalOpened] = useState(false);
  const [deleteModalSummary, setDeleteModalSummary] = useState(null);
  const [renameModalSummary, setRenameModalSummary] = useState(null);
  const [infoModalSummary, setInfoModalSummary] = useState(null);
  const [renameInput, setRenameInput] = useState('');
  const [taskStatus, setTaskStatus] = useState(null);
  const [showProcessLog, setShowProcessLog] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileActionsOpened, { open: openMobileActions, close: closeMobileActions }] = useDisclosure(false);

  const [isEditing, setIsEditing] = useState(false);
  const [isRawMode, setIsRawMode] = useState(false);
  const [saveModalOpened, setSaveModalOpened] = useState(false);
  const [cancelModalOpened, setCancelModalOpened] = useState(false);
  const [saving, setSaving] = useState(false);
  const [coveredResources, setCoveredResources] = useState([]);
  const [coveredExercises, setCoveredExercises] = useState([]);
  const [exerciseReferencedResources, setExerciseReferencedResources] = useState([]);

  const markdownComponents = useMemo(() => ({
    pre(props) {
      return <>{props.children}</>;
    },
    code(props) {
      const {children, className, node, ...rest} = props;
      const match = /language-(\w+)/.exec(className || '');
      const isInline = !match && !String(children).includes('\n');
      return !isInline ? (
        <SyntaxHighlighter
          {...rest}
          PreTag="div"
          children={String(children).replace(/\n$/, '')}
          language={match ? match[1] : 'text'}
          style={oneLight}
          customStyle={{
            margin: '1rem 0',
            padding: '1rem',
            borderRadius: '6px',
            border: '1px solid #e9ecef',
            backgroundColor: '#f8f9fa',
            fontSize: '0.9em',
            maxWidth: '100%',
            overflowX: 'auto'
          }}
        />
      ) : (
        <code {...rest} className={className}>
          {children}
        </code>
      );
    },
    img(props) {
      if (!props.src) return null;
      const src = props.src;
      let maxWidth = '66%'; // default medium
      if (src.endsWith('#small')) maxWidth = '33%';
      if (src.endsWith('#large')) maxWidth = '100%';
      return (
        <LazyImage
          src={src}
          alt={props.alt}
          title={props.title}
          maxWidth={maxWidth}
        />
      );
    }
  }), []);

  const viewportRef = useRef(null);
  const markdownRef = useRef(null);
  const scrollFrameRef = useRef(null);
  const textareaRef = useRef(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      Markdown,
      ResizableImageExtension.configure({
        inline: true,
        allowBase64: true,
      }),
      ImageUploadExtension.configure({ id: summaryId, endpointPrefix: 'resources' }),
    ],
    content: summaryContent,
  });

  const [mode, setMode] = useState('normal');
  const [outputFormat, setOutputFormat] = useState('sentence');
  const [processingMethod, setProcessingMethod] = useState('whole');
  
  const [parameterType, setParameterType] = useState('multi'); // 'multi' or 'single'
  const [globalPrompts, setGlobalPrompts] = useState([]);
  const [selectedPromptId, setSelectedPromptId] = useState(null);
  const [userPrompts, setUserPrompts] = useState([]);
  const [createPromptModalOpened, setCreatePromptModalOpened] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptContent, setNewPromptContent] = useState('');
  const [newPromptInput, setNewPromptInput] = useState('');
  const [generatingNewPrompt, setGeneratingNewPrompt] = useState(false);

  useEffect(() => {
    fetchApi('/admin/global-prompts').then(data => {
      setGlobalPrompts(data || []);
    }).catch(err => console.error("Failed to load global prompts", err));
    fetchApi('/prompts').then(data => {
      setUserPrompts(data || []);
    }).catch(err => console.error("Failed to load user prompts", err));
  }, []);

  useEffect(() => {
    fetchApi('/auth/me').then(data => {
      if (data && data.action_sidebar_open !== undefined) {
        setSidebarOpen(data.action_sidebar_open);
      }
    }).catch(err => console.error("Failed to load user preferences", err));
  }, []);

  const toggleSidebar = async () => {
    const newState = !sidebarOpen;
    setSidebarOpen(newState);
    try {
      await fetchApi('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({ action_sidebar_open: newState })
      });
    } catch (e) {
      console.error("Failed to save sidebar state", e);
    }
  };

  useEffect(() => {
    if (!summaryId) {
      navigate('/dashboard');
      return;
    }
    
    const init = async () => {
      try {
        setLoading(true);
        const summaryData = await fetchApi(`/notes/${summaryId}`);
        setSelectedSummary(summaryData);
        setSummaryContent(summaryData.content);
        
        if (summaryData.resource_id) {
          const noteData = await fetchApi(`/resources/${summaryData.resource_id}`);
          setNote(noteData);
        } else if (summaryData.exercise_ids) {
          try {
            const exIds = JSON.parse(summaryData.exercise_ids);
            if (Array.isArray(exIds) && exIds.length > 0) {
              const exData = await fetchApi(`/exercises/${exIds[0]}?t=${Date.now()}`);
              if (exData?.subject) {
                setNote({ subject: exData.subject });
              }
            }
          } catch (e) {}
        }
        setLoading(false);
      } catch (err) {
        console.error("Failed to load data", err);
        setError("Failed to load summary");
        setLoading(false);
      }
    };
    init();
  }, [summaryId]);

  useEffect(() => {
    if (!selectedSummary) return;
    const loadResources = async () => {
      const directIds = new Set();
      if (selectedSummary.resource_ids) {
        try {
          const parsed = JSON.parse(selectedSummary.resource_ids);
          if (Array.isArray(parsed)) parsed.forEach(id => directIds.add(id));
        } catch (e) {}
      }
      if (directIds.size === 0 && selectedSummary.resource_id) {
        directIds.add(selectedSummary.resource_id);
      }

      const directResources = await Promise.all(
        [...directIds].map(async (rid) => {
          try {
            const data = await fetchApi(`/resources/${rid}?t=${Date.now()}`);
            return { id: data.id, title: data.title };
          } catch (e) {
            return { id: rid, title: rid };
          }
        })
      );
      setCoveredResources(directResources);

      // Collect resource IDs referenced by exercise questions (info only)
      const exRefIds = new Set();
      if (selectedSummary.exercise_ids) {
        try {
          const exIds = JSON.parse(selectedSummary.exercise_ids);
          if (Array.isArray(exIds)) {
            const exData = await Promise.all(
              exIds.map(async (eid) => {
                try {
                  return await fetchApi(`/exercises/${eid}?t=${Date.now()}`);
                } catch { return null; }
              })
            );
            for (const ex of exData) {
              if (ex?.questions) {
                for (const q of ex.questions) {
                  if (q.reference_resource_id) {
                    exRefIds.add(q.reference_resource_id);
                  }
                }
              }
            }
          }
        } catch (e) {}
      }

      // Remove any that are already directly covered
      exRefIds.forEach(id => directIds.has(id) && exRefIds.delete(id));

      const exRefResources = await Promise.all(
        [...exRefIds].map(async (rid) => {
          try {
            const data = await fetchApi(`/resources/${rid}?t=${Date.now()}`);
            return { id: data.id, title: data.title };
          } catch (e) {
            return { id: rid, title: rid };
          }
        })
      );
      setExerciseReferencedResources(exRefResources);
    };
    loadResources();

    const loadExercises = async () => {
      if (!selectedSummary.exercise_ids) {
        setCoveredExercises([]);
        return;
      }
      let exIds = [];
      try {
        const parsed = JSON.parse(selectedSummary.exercise_ids);
        if (Array.isArray(parsed)) exIds = parsed;
      } catch (e) {}
      const uniqueIds = [...new Set(exIds)];
      const exercises = await Promise.all(
        uniqueIds.map(async (eid) => {
          try {
            const data = await fetchApi(`/exercises/${eid}?t=${Date.now()}`);
            return { id: data.id, title: data.title };
          } catch (e) {
            return { id: eid, title: eid };
          }
        })
      );
      setCoveredExercises(exercises);
    };
    loadExercises();
  }, [selectedSummary]);

  const handleRename = (summary, e) => {
    e.stopPropagation();
    const details = summary.prompt_name || formatParams(summary.mode, summary.output_format, summary.processing_method);
    const defaultTitle = details || `Version ${summary.version}`;
    const currentName = summary.is_user_edited ? summary.title : defaultTitle;
    
    setRenameInput(currentName);
    setRenameModalSummary(summary);
  };

  const confirmRename = async () => {
    if (!renameModalSummary || !renameInput.trim()) return;
    
    const details = renameModalSummary.prompt_name || formatParams(renameModalSummary.mode, renameModalSummary.output_format, renameModalSummary.processing_method);
    const currentName = renameModalSummary.is_user_edited ? renameModalSummary.title : (details || `Version ${renameModalSummary.version}`);
    
    if (renameInput === currentName) {
      setRenameModalSummary(null);
      return;
    }
    
    try {
      await fetchApi(`/notes/${renameModalSummary.id}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ title: renameInput })
      });
      setSummaries(summaries.map(s => s.id === renameModalSummary.id ? { ...s, title: renameInput, is_user_edited: true } : s));
      if (selectedSummary?.id === renameModalSummary.id) {
        setSelectedSummary({ ...selectedSummary, title: renameInput, is_user_edited: true });
      }
      setRenameModalSummary(null);
    } catch (err) {
      console.error('Failed to rename', err);
    }
  };

  // Track note generation task via shared TaskContext
  const { tasks } = useTaskContext();

  useEffect(() => {
    if (!selectedSummary) return;
    const isProcessedCheck = (selectedSummary.processing_time_ms != null && selectedSummary.processing_time_ms > 0) || 
                             (selectedSummary.file_path != null && selectedSummary.file_path !== '');
    if (isProcessedCheck) return;

    const task = tasks.find(t => t.task_type === 'note_generation' && t.input_data?.kwargs?.note_id === summaryId);
    if (task) {
      setTaskStatus(task);
      if (task.status === 'completed') {
        fetchApi(`/notes/${summaryId}`).then(data => {
          setSelectedSummary(data);
          setSummaryContent(data.content || '');
        });
      }
    }
  }, [tasks, summaryId, selectedSummary]);

  const handlePin = async (summary, e) => {
    e.stopPropagation();
    try {
      await fetchApi(`/notes/${summary.id}/pin`, { method: 'PATCH' });
      const updated = summaries.map(s => s.id === summary.id ? { ...s, is_pinned: !s.is_pinned } : s);
      setSummaries(updated.sort((a, b) => {
        if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
        return b.version - a.version;
      }));
    } catch (err) {
      console.error('Failed to pin', err);
    }
  };

  const handleDelete = (summary, e) => {
    e.stopPropagation();
    setDeleteModalSummary(summary);
  };

  const confirmDelete = async () => {
    if (!deleteModalSummary) return;
    try {
      await fetchApi(`/notes/${deleteModalSummary.id}`, { method: 'DELETE' });
      setSummaries(summaries.filter(s => s.id !== deleteModalSummary.id));
      if (selectedSummary?.id === deleteModalSummary.id) {
        setSelectedSummary(null);
        navigate('/mynotes', { replace: true });
      }
      setDeleteModalSummary(null);
    } catch (err) {
      console.error('Failed to delete', err);
    }
  };

  const generateCustomPrompt = async () => {
    if (!promptInput.trim()) return;
    try {
      setGeneratingPrompt(true);
      const res = await fetchApi('/notes/generate-prompt', {
        method: 'POST',
        body: JSON.stringify({ user_input: promptInput })
      });
      if (res && res.prompt) {
        setCustomPromptText(res.prompt);
      }
    } catch (err) {
      console.error("Failed to generate prompt", err);
    } finally {
      setGeneratingPrompt(false);
    }
  };

  const handleGenerateNewPromptAI = async () => {
    if (!newPromptInput.trim()) return;
    try {
      setGeneratingNewPrompt(true);
      const res = await fetchApi('/notes/generate-prompt', {
        method: 'POST',
        body: JSON.stringify({ user_input: newPromptInput })
      });
      if (res && res.prompt) {
        setNewPromptContent(res.prompt);
        if (res.name) {
          setNewPromptName(res.name);
        }
      }
    } catch (err) {
      console.error("Failed to generate prompt", err);
    } finally {
      setGeneratingNewPrompt(false);
    }
  };

  const saveNewPrompt = async () => {
    if (!newPromptName.trim() || !newPromptContent.trim()) return;
    try {
      const res = await fetchApi('/prompts', {
        method: 'POST',
        body: JSON.stringify({ name: newPromptName, content: newPromptContent })
      });
      if (res && res.id) {
        setUserPrompts(prev => [...prev, res]);
        setSelectedPromptId(`u_${res.id}`);
        setCreatePromptModalOpened(false);
        setModalOpened(true);
        setNewPromptName('');
        setNewPromptContent('');
        setNewPromptInput('');
      }
    } catch (err) {
      console.error("Failed to save new prompt", err);
    }
  };

  const handleScroll = () => {
    if (scrollFrameRef.current) return;
    
    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      if (!viewportRef.current || !markdownRef.current) return;
      const viewportRect = viewportRef.current.getBoundingClientRect();
      const viewportTop = viewportRect.top;

      let activeEls = [];
      let currentAccumulatedTop = 0;

      for (let i = 1; i <= 6; i++) {
        const tag = `h${i}`;
        const elements = Array.from(markdownRef.current.querySelectorAll(tag));
        let activeEl = null;

        for (const el of elements) {
          const targetEl = el.closest('.summary-header') || el;
          const rect = targetEl.getBoundingClientRect();
          if (rect.top <= viewportTop + currentAccumulatedTop + 5) {
            activeEl = el;
          }
        }

        if (activeEl) {
          for (let j = 1; j < i; j++) {
            if (activeEls[j]) {
              if (activeEl.compareDocumentPosition(activeEls[j]) & Node.DOCUMENT_POSITION_FOLLOWING) {
                activeEl = null;
                break;
              }
            }
          }
        }
        
        activeEls[i] = activeEl;

        for (const el of elements) {
          const targetEl = el.closest('.summary-header') || el;
          if (el === activeEl) {
            targetEl.style.opacity = 1;
            targetEl.style.pointerEvents = 'auto';
          } else if (targetEl.getBoundingClientRect().top <= viewportTop + currentAccumulatedTop + 5) {
            targetEl.style.opacity = 0;
            targetEl.style.pointerEvents = 'none';
          } else {
            targetEl.style.opacity = 1;
            targetEl.style.pointerEvents = 'auto';
          }
        }

        let h = 0;
        if (activeEl) {
          const targetActiveEl = activeEl.closest('.summary-header') || activeEl;
          h = targetActiveEl.offsetHeight;
        }

        currentAccumulatedTop += h;
        if (i < 6) {
          markdownRef.current.style.setProperty(`--h${i + 1}-top`, `${currentAccumulatedTop}px`);
        }
      }
    });
  };

  useEffect(() => {
    setTimeout(handleScroll, 100);
  }, [summaryContent, isEditing, isRawMode]);

  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isEditing) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    
    if (isEditing) {
      window.addEventListener('beforeunload', handleBeforeUnload);
    }
    
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [isEditing]);

  const startEditing = () => {
    if (editor) {
      editor.commands.setContent(summaryContent || '');
    }
    setIsEditing(true);
    setIsRawMode(false);
  };

  const handleToggleRaw = () => {
    if (isRawMode) {
      editor?.commands.setContent(summaryContent || '');
      setIsRawMode(false);
    } else {
      if (editor) {
        setSummaryContent(editor.storage.markdown.getMarkdown());
      }
      setIsRawMode(true);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    let finalContent = summaryContent;
    if (!isRawMode && editor) {
      finalContent = editor.storage.markdown.getMarkdown();
    }

    try {
      await fetchApi(`/notes/${selectedSummary.id}`, {
        method: 'PUT',
        body: JSON.stringify({ content: finalContent })
      });
      setIsEditing(false);
      setIsRawMode(false);
      setSummaryContent(finalContent);
      setSummaries(summaries.map(s => s.id === selectedSummary.id ? { ...s, content: finalContent, is_user_edited: true } : s));
      setSelectedSummary({ ...selectedSummary, content: finalContent, is_user_edited: true });
    } catch (err) {
      console.error("Failed to save", err);
    } finally {
      setSaving(false);
    }
  };

  const handleFormat = (type) => {
    if (!isRawMode) {
      if (!editor) return;
      switch(type) {
        case 'paragraph': editor.chain().focus().setParagraph().run(); break;
        case 'h1': editor.chain().focus().toggleHeading({ level: 1 }).run(); break;
        case 'h2': editor.chain().focus().toggleHeading({ level: 2 }).run(); break;
        case 'h3': editor.chain().focus().toggleHeading({ level: 3 }).run(); break;
        case 'bullet': editor.chain().focus().toggleBulletList().run(); break;
        case 'ordered': editor.chain().focus().toggleOrderedList().run(); break;
        case 'table': editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(); break;
      }
    } else {
      if (!textareaRef.current) return;
      const el = textareaRef.current;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const before = summaryContent.substring(0, start);
      const selected = summaryContent.substring(start, end);
      const after = summaryContent.substring(end);

      let inserted = '';
      switch(type) {
        case 'paragraph': inserted = selected.replace(/^[#\-\*]*\s*/, ''); break;
        case 'h1': inserted = '# ' + selected; break;
        case 'h2': inserted = '## ' + selected; break;
        case 'h3': inserted = '### ' + selected; break;
        case 'bullet': inserted = '- ' + selected; break;
        case 'ordered': inserted = '1. ' + selected; break;
        case 'table': inserted = `\n| Column 1 | Column 2 | Column 3 |\n| -------- | -------- | -------- |\n| Cell 1   | Cell 2   | Cell 3   |\n| Cell 4   | Cell 5   | Cell 6   |\n`; break;
      }

      const newContent = before + inserted + after;
      setSummaryContent(newContent);
      
      setTimeout(() => {
        el.focus();
        if (type !== 'table') {
           el.setSelectionRange(start, start + inserted.length);
        } else {
           el.setSelectionRange(start + inserted.length, start + inserted.length);
        }
      }, 0);
    }
  };

  const hiddenFileInput = useRef(null);

  const handleUploadClick = () => {
    hiddenFileInput.current.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = await handleImageUploadFlow(file, summaryId, 'notes');
    if (url) {
      if (!isRawMode && editor) {
        editor.chain().focus().setImage({ src: url }).run();
      } else {
        const el = textareaRef.current;
        if (el) {
          const start = el.selectionStart;
          const before = summaryContent.substring(0, start);
          const after = summaryContent.substring(el.selectionEnd);
          const inserted = `![image](${url})`;
          setSummaryContent(before + inserted + after);
          setTimeout(() => {
            el.focus();
            el.setSelectionRange(start + inserted.length, start + inserted.length);
          }, 0);
        }
      }
    }
    e.target.value = '';
  };

  if (!summaryId) return null;

  const isCurrentlyProcessing = taskStatus && (taskStatus.status === 'pending' || taskStatus.status === 'processing' || taskStatus.status === 'running');
  const isProcessed = ((selectedSummary?.processing_time_ms != null && selectedSummary.processing_time_ms > 0) || 
                      (selectedSummary?.file_path != null && selectedSummary.file_path !== '') || taskStatus?.status === 'completed') && !isCurrentlyProcessing;
  const isFailed = taskStatus?.status === 'failed';
  const processingProgress = taskStatus?.progress || 10;

  const handleExportMarkdown = () => {
    const textToExport = summaryContent || '';
    if (!textToExport) return;
    const blob = new Blob([textToExport], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${note?.title || 'Export'}_Summary.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Box h="100vh" style={{ display: 'flex', flexDirection: 'column', overflowX: 'hidden' }}>
      <style>{`
        .clickable-crumb {
          cursor: pointer;
        }
        .clickable-crumb:hover {
          text-decoration: underline;
        }
        .sticky-markdown {
          font-family: 'Instrument Sans', sans-serif;
          color: #171738;
          line-height: 1.0;
          font-size: 16px;
        }
        .sticky-markdown .summary-header,
        .sticky-markdown h1,
        .sticky-markdown h2,
        .sticky-markdown h3,
        .sticky-markdown h4,
        .sticky-markdown h5,
        .sticky-markdown h6 {
          position: sticky;
          background-color: #ffffff;
          margin-top: 0;
          padding-top: 0.3rem;
          padding-bottom: 0.1rem;
          line-height: 1.1;
          z-index: 10;
          border-bottom: 1px solid #eaeaea;
        }
        .sticky-markdown .summary-header { top: 0; z-index: 16; }
        .sticky-markdown .summary-header h1 {
          position: static;
          background-color: transparent;
          border-bottom: none;
          padding-top: 2rem;
          padding-bottom: 0;
          font-size: 2.2rem;
          margin: 0;
        }
        .sticky-markdown h1 { top: 0; z-index: 16; font-size: 2.2rem; padding-top: 2rem; }
        .sticky-markdown h2 { top: var(--h2-top, 3.5rem); z-index: 15; font-size: 1.8rem; }
        .sticky-markdown h3 { top: var(--h3-top, 6.5rem); z-index: 14; font-size: 1.5rem; }
        .sticky-markdown h4 { top: var(--h4-top, 9rem); z-index: 13; font-size: 1.25rem; }
        .sticky-markdown h5 { top: var(--h5-top, 11rem); z-index: 12; font-size: 1.1rem; }
        .sticky-markdown h6 { top: var(--h6-top, 13rem); z-index: 11; font-size: 1rem; }
        .sticky-markdown p { margin-bottom: 0.5rem; }
        .sticky-markdown ul, .sticky-markdown ol { margin-top: 0; margin-bottom: 0.5rem; padding-left: 1.5rem; }
        .sticky-markdown li { margin-bottom: 0.2rem; }
        .sticky-markdown li p { margin: 0; }
        .sticky-markdown strong { font-weight: 700; }
        .sticky-markdown blockquote {
          border-left: 4px solid #3b82f6;
          margin: 1.5rem 0;
          padding: 0.5rem 0 0.5rem 1.5rem;
          background-color: #f8f9fa;
          color: #4b5563;
        }
        .sticky-markdown :not(pre) > code {
          background-color: #f1f3f5;
          padding: 0.2rem 0.4rem;
          border-radius: 4px;
          font-family: monospace;
          font-size: 0.9em;
        }
        .sticky-markdown pre {
          background-color: #f8f9fa;
          color: #212529;
          padding: 1rem;
          border-radius: 6px;
          overflow-x: auto;
          max-width: 100%;
          margin: 1rem 0;
          border: 1px solid #e9ecef;
        }
        .sticky-markdown pre code {
          background-color: transparent;
          padding: 0;
          border-radius: 0;
          font-family: monospace;
          font-size: 0.9em;
          color: inherit;
          white-space: pre;
          word-break: normal;
          word-wrap: normal;
        }
        .sticky-markdown img {
          max-width: 66%;
          height: auto;
          display: block;
          margin: 1rem 0;
          border-radius: 8px;
        }
        .sticky-markdown img[src$="#small"] {
          max-width: 33%;
        }
        .sticky-markdown img[src$="#large"] {
          max-width: 100%;
        }
        .sticky-markdown table {
          border-collapse: collapse;
          width: 100%;
          margin-bottom: 1rem;
        }
        .sticky-markdown th, .sticky-markdown td {
          border: 1px solid #dee2e6;
          padding: 0.5rem;
        }
        .sticky-markdown th {
          background-color: #f8f9fa;
        }
        .sticky-markdown .ProseMirror {
          min-height: 50vh;
          white-space: pre-wrap;
          word-wrap: break-word;
        }
        .sticky-markdown .ProseMirror:focus {
          outline: none;
        }
      `}</style>
      
      <Modal opened={saveModalOpened} onClose={() => setSaveModalOpened(false)} title="Save Changes" centered withCloseButton={false}>
        <form onSubmit={(e) => { e.preventDefault(); setSaveModalOpened(false); handleSave(); }}>
          <Text size="sm" mb="md">Are you sure you want to save these changes?</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setSaveModalOpened(false)}>Cancel</Button>
            <Button type="submit" data-autofocus loading={saving}>Confirm Save</Button>
          </Group>
        </form>
      </Modal>

      <Modal opened={cancelModalOpened} onClose={() => setCancelModalOpened(false)} title="Cancel Editing" centered withCloseButton={false}>
        <form onSubmit={(e) => { e.preventDefault(); setCancelModalOpened(false); setIsEditing(false); setIsRawMode(false); }}>
          <Text size="sm" mb="md">Are you sure you want to cancel? Any unsaved changes will be lost.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setCancelModalOpened(false)}>Go Back</Button>
            <Button type="submit" color="red" data-autofocus>Discard Changes</Button>
          </Group>
        </form>
      </Modal>

      <Modal opened={!!deleteModalSummary} onClose={() => setDeleteModalSummary(null)} title="Delete Summary" centered>
        <Text size="sm" mb="lg">
          Are you sure you want to delete <b>{deleteModalSummary?.title || (deleteModalSummary && `Version ${deleteModalSummary.version}`) || 'this summary'}</b>? This action cannot be undone.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setDeleteModalSummary(null)}>Cancel</Button>
          <Button color="red" onClick={confirmDelete} data-autofocus>Delete</Button>
        </Group>
      </Modal>

      <Modal opened={!!renameModalSummary} onClose={() => setRenameModalSummary(null)} title="Rename Summary" centered>
        <TextInput
          label="Summary Name"
          placeholder="Enter a new name"
          value={renameInput}
          onChange={(e) => setRenameInput(e.currentTarget.value)}
          data-autofocus
          mb="lg"
          onKeyDown={(e) => e.key === 'Enter' && confirmRename()}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setRenameModalSummary(null)}>Cancel</Button>
          <Button onClick={confirmRename}>Save</Button>
        </Group>
      </Modal>

      <Modal opened={!!infoModalSummary} onClose={() => setInfoModalSummary(null)} title="System Information" centered size="lg">
        {infoModalSummary && (
          <Stack gap="sm">
            <Group justify="space-between">
              <Text size="sm" fw={500}>Note ID</Text>
              <Code>{infoModalSummary.note_id}</Code>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Summary ID</Text>
              <Code>{infoModalSummary.id}</Code>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Type</Text>
              <Badge color={infoModalSummary.prompt_name ? "grape" : "blue"}>{infoModalSummary.prompt_name ? "Single Parameter" : "Multi Parameter"}</Badge>
            </Group>
            
            {infoModalSummary.prompt_name ? (
              <Group justify="space-between">
                <Text size="sm" fw={500}>Prompt Name</Text>
                <Text size="sm">{infoModalSummary.prompt_name}</Text>
              </Group>
            ) : (
              <>
                <Group justify="space-between">
                  <Text size="sm" fw={500}>Mode</Text>
                  <Text size="sm" tt="capitalize">{infoModalSummary.mode || 'N/A'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" fw={500}>Output Format</Text>
                  <Text size="sm" tt="capitalize">{infoModalSummary.output_format?.replace('_', ' ') || 'N/A'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" fw={500}>Processing Method</Text>
                  <Text size="sm" tt="capitalize">{infoModalSummary.processing_method || 'N/A'}</Text>
                </Group>
                {infoModalSummary.split_level && (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>Split Level</Text>
                    <Text size="sm" tt="uppercase">{infoModalSummary.split_level}</Text>
                  </Group>
                )}
              </>
            )}
            
            {infoModalSummary.resource_ids && (() => {
              try {
                const ids = JSON.parse(infoModalSummary.resource_ids);
                return Array.isArray(ids) && ids.length > 0 ? (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>Source Resources</Text>
                    <Text size="sm">{ids.length} resource{ids.length !== 1 ? 's' : ''}</Text>
                  </Group>
                ) : null;
              } catch { return null; }
            })()}
            {infoModalSummary.exercise_ids && (() => {
              try {
                const ids = JSON.parse(infoModalSummary.exercise_ids);
                return Array.isArray(ids) && ids.length > 0 ? (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>Source Exercises</Text>
                    <Text size="sm">{ids.length} exercise{ids.length !== 1 ? 's' : ''}</Text>
                  </Group>
                ) : null;
              } catch { return null; }
            })()}
            <Group justify="space-between">
              <Text size="sm" fw={500}>AI Model</Text>
              <Text size="sm" c="dimmed">{infoModalSummary.model || 'Unknown'}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Processing Time</Text>
              <Text size="sm" c="dimmed">
                {infoModalSummary.processing_time_ms ? `${(infoModalSummary.processing_time_ms / 1000).toFixed(2)}s` : 
                 infoModalSummary.processing_time ? `${infoModalSummary.processing_time.toFixed(2)}s` : 'Unknown'}
              </Text>
            </Group>
          </Stack>
        )}
      </Modal>



      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20 }}>
        <input 
          type="file" 
          accept="image/*" 
          style={{ display: 'none' }} 
          ref={hiddenFileInput} 
          onChange={handleFileChange} 
        />
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Group wrap="nowrap" gap="xs" style={{ overflow: 'hidden', minWidth: 0 }}>
            <ActionIcon variant="subtle" color="gray" onClick={() => isEditing ? setCancelModalOpened(true) : navigate(-1)}>
              <IconChevronLeft size={20} />
            </ActionIcon>
            {note?.subject && (
              <Group gap="xs" ml="xs" wrap="nowrap" visibleFrom="sm" style={{ overflow: 'hidden', minWidth: 0 }}>
                {note.subject.group && (
                  <>
                    <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/group/${note.subject.group.id}`)} style={{ whiteSpace: 'nowrap' }}>{note.subject.group.name}</Text>
                    <Text size="sm" c="dimmed">/</Text>
                  </>
                )}
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${note.subject.id}`)} style={{ whiteSpace: 'nowrap' }}>{note.subject.name}</Text>
                <Text size="sm" c="dimmed">/</Text>
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${note.subject.id}/notes`)} style={{ whiteSpace: 'nowrap' }}>Note</Text>
              </Group>
            )}
          </Group>
          <ActionIcon
            variant="default"
            size="md"
            onClick={openMobileActions}
            hiddenFrom="sm"
          >
            <IconLayoutSidebarRightExpand size={20} />
          </ActionIcon>
          {sidebarOpen && (
            <ActionIcon variant="subtle" color="gray" size="sm" onClick={toggleSidebar} visibleFrom="sm">
              {sidebarOpen ? <IconLayoutSidebarRightCollapse size={20} /> : <IconLayoutSidebarRightExpand size={20} />}
            </ActionIcon>
          )}
        </Group>
      </Box>

      <Box style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <ScrollArea 
          viewportRef={viewportRef}
          onScrollPositionChange={handleScroll}
          style={{ flex: 1, backgroundColor: '#fff' }} 
          p={0}
        >
          <Container size="md" p={0} pt={0} pb="xl">
            {loading ? (
              <Center h="50vh"><Loader size="lg" /></Center>
            ) : error ? (
              <Center h="50vh">
                <Stack align="center">
                  <IconAlertCircle size={48} color="red" />
                  <Text c="red">{error}</Text>
                </Stack>
              </Center>
            ) : !selectedSummary ? (
              <Center h="50vh">
                <Stack align="center">
                  <IconFileText size={64} color="var(--mantine-color-gray-3)" />
                  <Title order={3} c="dimmed">Summary Not Found</Title>
                </Stack>
              </Center>
            ) : isFailed ? (
              <Box mt={100} ta="center">
                <IconAlertCircle size={64} color="var(--mantine-color-red-6)" stroke={1.5} />
                <Title order={2} mt="xl" mb="sm" fw={800} c="red">Generation Failed</Title>
                <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                  {taskStatus?.error || 'An unexpected error occurred while generating this note.'}
                </Text>
              </Box>
            ) : !isProcessed ? (
              <Box mt={100} ta="center">
                <IconRobot size={64} color="var(--mantine-color-blue-6)" stroke={1.5} style={{ opacity: 0.8 }} />
                <Title order={2} mt="xl" mb="sm" fw={800} c="#171738">Generating Note...</Title>
                <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                  Our AI is currently analyzing the document and generating your smart notes. This usually takes a few seconds.
                </Text>
                <Box mx="auto" maw={400} mb="xl">
                  <Group justify="space-between" mb={5}>
                    <Text size="sm" fw={500}>Processing...</Text>
                    <Text size="sm" fw={500}>{processingProgress}%</Text>
                  </Group>
                  <Progress value={processingProgress} animated striped color="orange" size="xl" radius="xl" />
                  <Button variant="subtle" mt="sm" onClick={() => setShowProcessLog(true)}>
                    View Live Logs
                  </Button>
                </Box>
              </Box>
            ) : (
              <Box px="md">
                <Box mb="md" pt="md">
                  <Group gap="xs">
                    {selectedSummary?.prompt_name ? (() => {
                      const IconComp = getIconComponent(selectedSummary.prompt_icon);
                      return (
                        <Badge leftSection={<IconComp size={12} />} variant="light" size="md" tt="capitalize" fw={600}>
                          {selectedSummary.prompt_name}
                        </Badge>
                      );
                    })() : (
                      <>
                        {selectedSummary?.mode && (
                          <Badge leftSection={MODE_ICONS[selectedSummary.mode] || <IconBrain size={12} />} variant="light" size="md" tt="capitalize" fw={600}>
                            {selectedSummary.mode}
                          </Badge>
                        )}
                        {selectedSummary?.output_format && (
                          <Badge leftSection={FORMAT_ICONS[selectedSummary.output_format] || <IconFileText size={12} />} variant="light" color="teal" size="md" tt="capitalize" fw={600}>
                            {selectedSummary.output_format}
                          </Badge>
                        )}
                        {selectedSummary?.processing_method && (
                          <Badge leftSection={METHOD_ICONS[selectedSummary.processing_method] || <IconCpu size={12} />} variant="light" size="md" tt="capitalize" fw={600}>
                            {selectedSummary.processing_method}
                          </Badge>
                        )}
                      </>
                    )}
                  </Group>
                </Box>
                {(() => {
                  let displayContent = summaryContent || '';
                  let extractedTitle = selectedSummary?.title || 'Summary';

                  const h1Regex = /^\s*#\s+(.+)$/m;
                  const match = displayContent.match(h1Regex);
                  if (match) {
                    extractedTitle = match[1].trim();
                    displayContent = displayContent.replace(h1Regex, '').trim();
                  }

                  return (
                    <>
                      <div className="summary-header" style={{ marginBottom: '1.5rem' }}>
                        <Title order={1} style={{ marginTop: 0, marginBottom: 0, color: '#171738', fontWeight: 700 }}>
                          {extractedTitle}
                        </Title>
                      </div>
                      {isEditing && isRawMode ? (
                        <Textarea
                          ref={textareaRef}
                          minRows={30}
                          autosize
                          value={summaryContent}
                          onChange={(e) => setSummaryContent(e.currentTarget.value)}
                          variant="unstyled"
                          styles={{ input: { fontFamily: 'monospace', fontSize: '14px', lineHeight: 1.6 } }}
                        />
                      ) : (
                        <Box ref={markdownRef} className="sticky-markdown" style={{ color: '#171738', fontSize: '16px', lineHeight: 1.8 }}>
                          {isEditing && !isRawMode ? (
                            <EditorContent editor={editor} />
                          ) : (
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm, remarkUnwrapImages]}
                              urlTransform={(uri) => uri}
                              components={markdownComponents}
                            >
                              {displayContent}
                            </ReactMarkdown>
                          )}
                        </Box>
                      )}
                    </>
                  );
                })()}
              </Box>
            )}
          </Container>
        </ScrollArea>

        {/* Right Sidebar */}
        <Box w={sidebarOpen ? 280 : 80} visibleFrom="sm" style={{ borderLeft: '1px solid #eaeaea', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', transition: 'width 200ms ease, min-width 200ms ease', minWidth: sidebarOpen ? 280 : 80, overflow: 'hidden' }} p="md">
          <Box style={{ flex: 1, overflowY: 'auto' }}>
            <Stack gap={0} align="stretch">
              {sidebarOpen && isProcessed && !isEditing && (
                <Box mb="md">
                  <Title order={5} fw={600} c="dimmed" mb="xs">Note Info</Title>
                  <Card p="sm" radius="md" withBorder bg="var(--mantine-color-gray-0)">
                    <Stack gap="xs">
                      <Box>
                        <Text size="xs" fw={600} c="dimmed" mb={4}>Resources Covered</Text>
                        {coveredResources.length > 0 ? (
                          <Stack gap={4}>
                            {coveredResources.map((res, idx) => (
                              <Text
                                key={idx}
                                size="xs"
                                c={res.id ? "blue.6" : "dark"}
                                style={res.id ? { cursor: 'pointer', textDecoration: 'underline' } : {}}
                                onClick={() => res.id && navigate(`/resource/${res.id}`)}
                              >
                                • {res.title}
                              </Text>
                            ))}
                          </Stack>
                        ) : (
                          <Text size="xs" c="dimmed" fs="italic">No resources linked</Text>
                        )}
                      </Box>
                      {coveredExercises.length > 0 && (
                        <Box>
                          <Text size="xs" fw={600} c="dimmed" mb={4}>Exercises Covered</Text>
                          <Stack gap={4}>
                            {coveredExercises.map((ex, idx) => (
                              <Text
                                key={idx}
                                size="xs"
                                c="blue.6"
                                style={{ cursor: 'pointer', textDecoration: 'underline' }}
                                onClick={() => ex.id && navigate(`/exercises/${ex.id}`)}
                              >
                                • {ex.title}
                              </Text>
                            ))}
                          </Stack>
                        </Box>
                      )}
                      {exerciseReferencedResources.length > 0 && (
                        <Box>
                          <Text size="xs" fw={600} c="dimmed" mb={4}>Referenced in Exercises</Text>
                          <Stack gap={4}>
                            {exerciseReferencedResources.map((res, idx) => (
                              <Text
                                key={idx}
                                size="xs"
                                c="blue.6"
                                style={{ cursor: 'pointer', textDecoration: 'underline' }}
                                onClick={() => res.id && navigate(`/resource/${res.id}`)}
                              >
                                • {res.title} <Text component="span" size="xs" c="dimmed">[from exercise]</Text>
                              </Text>
                            ))}
                          </Stack>
                        </Box>
                      )}
                    </Stack>
                  </Card>
                </Box>
              )}

              {sidebarOpen && <Title order={5} fw={600} c="dimmed" mb="xs">Smart Actions</Title>}

              {!isEditing ? (
                <>
                  <Tooltip label="Edit" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Edit" : ""}
                      leftSection={<IconPencil size="1.2rem" stroke={1.5} />}
                      onClick={startEditing}
                    />
                  </Tooltip>

                    <Menu position="left-start" withArrow>
                      <Menu.Target>
                        <Tooltip label="Export" disabled={sidebarOpen} position="left">
                          <MantineNavLink
                            label={sidebarOpen ? "Export" : ""}
                            leftSection={<IconDownload size="1.2rem" stroke={1.5} />}
                          />
                        </Tooltip>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconDownload size="0.9rem" />} onClick={handleExportMarkdown}>
                          Download as Markdown (.md)
                        </Menu.Item>
                        <Menu.Item disabled>
                          Other formats coming soon...
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </>
              ) : (
                <>
                  {sidebarOpen && <Box mt="md" mb="xs" px="sm"><Text size="xs" fw={600} c="dimmed" tt="uppercase">Actions</Text></Box>}
                  <Tooltip label="Save Changes" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Save Changes" : ""}
                      leftSection={<IconDeviceFloppy size="1.2rem" stroke={1.5} />}
                      onClick={() => setSaveModalOpened(true)}
                      variant="filled"
                      active
                    />
                  </Tooltip>
                  <Tooltip label="Cancel Editing" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Cancel Editing" : ""}
                      leftSection={<IconX size="1.2rem" stroke={1.5} />}
                      onClick={() => setCancelModalOpened(true)}
                      color="red"
                    />
                  </Tooltip>
                  {sidebarOpen && <Box mt="md" mb="xs" px="sm"><Text size="xs" fw={600} c="dimmed" tt="uppercase">Formatting</Text></Box>}
                  <Tooltip label="Paragraph" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Paragraph" : ""}
                      leftSection={<IconTypography size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('paragraph')}
                      active={!isRawMode && editor?.isActive('paragraph')}
                    />
                  </Tooltip>
                  <Tooltip label="Heading 1" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Heading 1" : ""}
                      leftSection={<IconH1 size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('h1')}
                      active={!isRawMode && editor?.isActive('heading', { level: 1 })}
                    />
                  </Tooltip>
                  <Tooltip label="Heading 2" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Heading 2" : ""}
                      leftSection={<IconH2 size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('h2')}
                      active={!isRawMode && editor?.isActive('heading', { level: 2 })}
                    />
                  </Tooltip>
                  <Tooltip label="Heading 3" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Heading 3" : ""}
                      leftSection={<IconH3 size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('h3')}
                      active={!isRawMode && editor?.isActive('heading', { level: 3 })}
                    />
                  </Tooltip>
                  <Tooltip label="Bullet List" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Bullet List" : ""}
                      leftSection={<IconList size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('bullet')}
                      active={!isRawMode && editor?.isActive('bulletList')}
                    />
                  </Tooltip>
                  <Tooltip label="Ordered List" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Ordered List" : ""}
                      leftSection={<IconListNumbers size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('ordered')}
                      active={!isRawMode && editor?.isActive('orderedList')}
                    />
                  </Tooltip>
                  <Tooltip label="Table" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Table" : ""}
                      leftSection={<IconTable size="1.2rem" stroke={1.5} />}
                      onClick={() => handleFormat('table')}
                    />
                  </Tooltip>
                  <Tooltip label="Raw Mode" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? (isRawMode ? "Visual Mode" : "Raw Mode") : ""}
                      leftSection={isRawMode ? <IconEye size="1.2rem" stroke={1.5} /> : <IconCode size="1.2rem" stroke={1.5} />}
                      onClick={handleToggleRaw}
                      active={isRawMode}
                    />
                  </Tooltip>
                  <Tooltip label="Insert Image" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Insert Image" : ""}
                      leftSection={<IconPhotoPlus size="1.2rem" stroke={1.5} />}
                      onClick={handleUploadClick}
                    />
                  </Tooltip>

                </>
              )}

            </Stack>
          </Box>

          <Box mt="auto" pt="sm">
            <Tooltip label={sidebarOpen ? "Hide Sidebar" : "Show Sidebar"} position="left">
              <ActionIcon variant="subtle" color="gray" size="lg" onClick={toggleSidebar}>
                {sidebarOpen ? <IconLayoutSidebarRightCollapse size={20} /> : <IconLayoutSidebarRightExpand size={20} />}
              </ActionIcon>
            </Tooltip>
          </Box>
        </Box>

      {isEditing && (
        <Box hiddenFrom="sm" style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 56, zIndex: 150, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', borderTop: '1px solid var(--mantine-color-gray-2)', boxShadow: '0 -2px 8px rgba(0,0,0,0.06)' }}>
          <Group gap={4} justify="center" wrap="nowrap">
            <ActionIcon variant={!isRawMode && editor?.isActive('paragraph') ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('paragraph') ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('paragraph')}><IconTypography size={18} /></ActionIcon>
            <ActionIcon variant={!isRawMode && editor?.isActive('heading', { level: 1 }) ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('heading', { level: 1 }) ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('h1')}><IconH1 size={18} /></ActionIcon>
            <ActionIcon variant={!isRawMode && editor?.isActive('heading', { level: 2 }) ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('heading', { level: 2 }) ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('h2')}><IconH2 size={18} /></ActionIcon>
            <ActionIcon variant={!isRawMode && editor?.isActive('heading', { level: 3 }) ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('heading', { level: 3 }) ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('h3')}><IconH3 size={18} /></ActionIcon>
            <ActionIcon variant={!isRawMode && editor?.isActive('bulletList') ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('bulletList') ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('bullet')}><IconList size={18} /></ActionIcon>
            <ActionIcon variant={!isRawMode && editor?.isActive('orderedList') ? 'light' : 'subtle'} color={!isRawMode && editor?.isActive('orderedList') ? 'blue' : 'gray'} size="md" onClick={() => handleFormat('ordered')}><IconListNumbers size={18} /></ActionIcon>
            <ActionIcon variant="subtle" color="gray" size="md" onClick={() => handleFormat('table')}><IconTable size={18} /></ActionIcon>
            <ActionIcon variant={isRawMode ? 'light' : 'subtle'} color={isRawMode ? 'blue' : 'gray'} size="md" onClick={handleToggleRaw}>{isRawMode ? <IconEye size={18} /> : <IconCode size={18} />}</ActionIcon>
            <Box w={2} />
            <ActionIcon variant="filled" size="md" onClick={() => setSaveModalOpened(true)}><IconDeviceFloppy size={18} /></ActionIcon>
            <ActionIcon variant="outline" color="red" size="md" onClick={() => setCancelModalOpened(true)}><IconX size={18} /></ActionIcon>
          </Group>
        </Box>
      )}

      {/* Mobile Smart Actions Drawer */}
      <Drawer
        opened={mobileActionsOpened}
        onClose={closeMobileActions}
        title="Smart Actions"
        padding={0}
        size="80%"
        position="right"
        hiddenFrom="sm"
        zIndex={1000}
        styles={{ header: { padding: '16px' } }}
      >
        <Box style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <ScrollArea style={{ flex: 1 }} px="md">
            <Stack gap={0} align="stretch" py="sm">
              {!isEditing ? (
                <>
                  <MantineNavLink
                    label="Edit"
                    leftSection={<IconPencil size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); startEditing(); }}
                  />
                  <Menu position="right-start" withArrow>
                    <Menu.Target>
                      <MantineNavLink
                        label="Export"
                        leftSection={<IconDownload size="1.2rem" stroke={1.5} />}
                      />
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item leftSection={<IconDownload size="0.9rem" />} onClick={() => { closeMobileActions(); handleExportMarkdown(); }}>
                        Download as Markdown (.md)
                      </Menu.Item>
                      <Menu.Item disabled>
                        Other formats coming soon...
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </>
              ) : (
                <>
                  <MantineNavLink
                    label="Save Changes"
                    leftSection={<IconDeviceFloppy size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); setSaveModalOpened(true); }}
                    variant="filled"
                    active
                  />
                  <MantineNavLink
                    label="Cancel Editing"
                    leftSection={<IconX size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); setCancelModalOpened(true); }}
                    color="red"
                  />
                </>
              )}
              {!isEditing && isProcessed && (
                <>
                  <Divider my="sm" />
                  <Box px="sm">
                    <Text size="xs" fw={600} c="dimmed" mb={6}>Resources Covered</Text>
                    {coveredResources.length > 0 ? (
                      <Stack gap={4}>
                        {coveredResources.map((res, idx) => (
                          <Text
                            key={idx}
                            size="xs"
                            c="blue.6"
                            style={{ cursor: 'pointer', textDecoration: 'underline' }}
                            onClick={() => { closeMobileActions(); navigate(`/resource/${res.id}`); }}
                          >
                            • {res.title}
                          </Text>
                        ))}
                      </Stack>
                    ) : (
                      <Text size="xs" c="dimmed" fs="italic">No resources linked</Text>
                    )}
                    {coveredExercises.length > 0 && (
                      <>
                        <Text size="xs" fw={600} c="dimmed" mb={6} mt="sm">Exercises Covered</Text>
                        <Stack gap={4}>
                          {coveredExercises.map((ex, idx) => (
                            <Text
                              key={idx}
                              size="xs"
                              c="blue.6"
                              style={{ cursor: 'pointer', textDecoration: 'underline' }}
                              onClick={() => { closeMobileActions(); navigate(`/exercises/${ex.id}`); }}
                            >
                              • {ex.title}
                            </Text>
                          ))}
                        </Stack>
                      </>
                    )}
                    {exerciseReferencedResources.length > 0 && (
                      <>
                        <Text size="xs" fw={600} c="dimmed" mb={6} mt="sm">Referenced in Exercises</Text>
                        <Stack gap={4}>
                          {exerciseReferencedResources.map((res, idx) => (
                            <Text
                              key={idx}
                              size="xs"
                              c="blue.6"
                              style={{ cursor: 'pointer', textDecoration: 'underline' }}
                              onClick={() => { closeMobileActions(); navigate(`/resource/${res.id}`); }}
                            >
                              • {res.title} <Text component="span" size="xs" c="dimmed">[from exercise]</Text>
                            </Text>
                          ))}
                        </Stack>
                      </>
                    )}
                  </Box>
                </>
              )}
            </Stack>
          </ScrollArea>
        </Box>
      </Drawer>
      <ProcessLoggerModal
        opened={showProcessLog}
        onClose={() => setShowProcessLog(false)}
        entityId={summaryId}
        tasks={tasks}
        entityType="summary"
      />
      </Box>
    </Box>
  );
}
