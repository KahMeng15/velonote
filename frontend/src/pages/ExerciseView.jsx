import { useState, useEffect, useRef } from 'react';
import { 
  Box, Title, Text, Group, Card, Button, Stack, Loader, Center, 
  Badge, ActionIcon, Textarea, Collapse, Radio, Paper, Alert, Menu,
  Grid, Select, SegmentedControl, TextInput, Divider, NumberInput, Switch,
  Container, ScrollArea, Tooltip, NavLink as MantineNavLink, Progress, RingProgress, Modal, Drawer, Rating, Popover
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useParams, useNavigate } from 'react-router-dom';
import { IconArrowLeft, IconCheck, IconX, IconBulb, IconBook, IconDownload, IconFileTypePdf, IconFileTypeDocx, IconEdit, IconTrash, IconPlus, IconClock, IconDeviceFloppy, IconChevronLeft, IconLayoutSidebarRightCollapse, IconLayoutSidebarRightExpand, IconPencil, IconEyeOff, IconEye, IconMessageDots, IconDotsVertical, IconRefresh, IconRobot, IconAlertCircle, IconArrowsShuffle, IconSortAscending, IconBolt, IconPhotoPlus, IconAdjustments, IconSend, IconWand, IconBrain, IconSchool, IconBabyCarriage, IconLayoutCards, IconFileText, IconList, IconListNumbers, IconTable, IconStar, IconInfoCircle, IconPin, IconPinFilled, IconMicrophone, IconCode } from '@tabler/icons-react';
import { fetchApi } from '../lib/api';
import { useTaskContext } from '../lib/TaskContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import { Link } from '@tiptap/extension-link';
import { Image } from '@tiptap/extension-image';
import { ResizableImageExtension } from '../lib/ResizableImageExtension';
import { ImageUploadExtension, handleImageUploadFlow } from '../lib/tiptapImageUpload';
import ProcessLoggerModal from '../components/ProcessLoggerModal';
import ConversationMode from '../components/ConversationMode';
export default function ExerciseView() {
  const { id, mode } = useParams();
  const navigate = useNavigate();
  const { tasks } = useTaskContext();
  const [exercise, setExercise] = useState(null);
  const [loading, setLoading] = useState(true);

  const urlToMode = {
    'hide-answers': 'hide',
    'show-answers': 'show',
    'interactive': 'interactive',
    'exam': 'exam',
    'conversation': 'conversation'
  };

  const modeToUrl = {
    'hide': 'hide-answers',
    'show': 'show-answers',
    'interactive': 'interactive',
    'exam': 'exam',
    'conversation': 'conversation'
  };

  // Layout & Mode state
  const [viewMode, setViewMode] = useState(mode && urlToMode[mode] ? urlToMode[mode] : 'hide');
  // Load initial exam state from localStorage if it exists
  const getInitialExamState = () => {
    try {
      const saved = localStorage.getItem(`exercise_exam_${id}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.examActive && parsed.savedAt) {
          const elapsedSeconds = Math.floor((Date.now() - parsed.savedAt) / 1000);
          const remaining = Math.max(0, parsed.examTimeRemaining - elapsedSeconds);
          return {
            ...parsed,
            examTimeRemaining: remaining,
            examActive: remaining > 0 ? parsed.examActive : false,
            examCompleted: remaining <= 0 ? true : parsed.examCompleted
          };
        }
        return parsed;
      }
    } catch (e) {
      console.error(e);
    }
    return null;
  };
  const initialExamState = getInitialExamState();

  const [currentConvIdx, setCurrentConvIdx] = useState(initialExamState?.currentConvIdx ?? 0);
  const [editMode, setEditMode] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try {
      const saved = localStorage.getItem(`exercise_chat_state_${id}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.sidebarOpen === 'boolean') return parsed.sidebarOpen;
      }
    } catch {}
    return true;
  });
  const [mobileActionsOpened, { open: openMobileActions, close: closeMobileActions }] = useDisclosure(false);

  useEffect(() => {
    if (mode && urlToMode[mode]) {
      const mappedMode = urlToMode[mode];
      setViewMode(mappedMode);
      setShowExplanations({});
      if (mappedMode !== 'exam') {
        setExamActive(false);
        if (timerRef.current) clearInterval(timerRef.current);
      }
    } else {
      navigate(`/exercises/${id}/hide-answers`, { replace: true });
    }
  }, [mode, id]);



  // Exam state
  const [examTimerMinutes, setExamTimerMinutes] = useState(15);
  const [examTimeRemaining, setExamTimeRemaining] = useState(initialExamState?.examTimeRemaining ?? null); // seconds
  const [examActive, setExamActive] = useState(initialExamState?.examActive ?? false);
  const [convActive, setConvActive] = useState(false);
  const [examCompleted, setExamCompleted] = useState(initialExamState?.examCompleted ?? false);
  const [showTimeUpModal, setShowTimeUpModal] = useState(initialExamState?.examActive && initialExamState?.examTimeRemaining <= 0);
  const [customMinutes, setCustomMinutes] = useState(5);
  const timerRef = useRef(null);
  const sidebarChatRef = useRef(null);

  // User input and feedback state
  const [userAnswers, setUserAnswers] = useState(initialExamState?.userAnswers ?? {});
  const [gradingResults, setGradingResults] = useState(initialExamState?.gradingResults ?? {});
  const [explanations, setExplanations] = useState(initialExamState?.explanations ?? {});
  const [gradingLoading, setGradingLoading] = useState({});
  const [explainLoading, setExplainLoading] = useState({});
  const [revealedAnswers, setRevealedAnswers] = useState(initialExamState?.revealedAnswers ?? {});
  const [showExplanations, setShowExplanations] = useState(initialExamState?.showExplanations ?? {});
  const [answerTimestamps, setAnswerTimestamps] = useState({});

  // Sync state to localStorage
  useEffect(() => {
    const stateToSave = {
      examActive,
      examCompleted,
      examTimeRemaining,
      userAnswers,
      gradingResults,
      explanations,
      revealedAnswers,
      showExplanations,
      currentConvIdx,
      savedAt: Date.now()
    };
    localStorage.setItem(`exercise_exam_${id}`, JSON.stringify(stateToSave));
  }, [id, examActive, examCompleted, examTimeRemaining, userAnswers, gradingResults, explanations, revealedAnswers, showExplanations, currentConvIdx]);

  // Question order
  const [questionOrder, setQuestionOrder] = useState('original');
  const [shuffledIndices, setShuffledIndices] = useState([]);

  const shuffleQuestions = () => {
    const n = exercise?.questions?.length || 0;
    const indices = Array.from({ length: n }, (_, i) => i);
    for (let i = indices.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [indices[i], indices[j]] = [indices[j], indices[i]];
    }
    setShuffledIndices(indices);
    setQuestionOrder('randomized');
  };

  const restoreQuestionOrder = () => {
    setShuffledIndices([]);
    setQuestionOrder('original');
  };

  // Chat param labels/icons
  const modeLabels = { quick: 'Quick', simple: 'Simple', normal: 'Normal', elaborate: 'Elaborate', eli5: 'ELI5' };
  const modeIcons = { quick: <IconBolt size={14} />, simple: <IconWand size={14} />, normal: <IconBrain size={14} />, elaborate: <IconSchool size={14} />, eli5: <IconBabyCarriage size={14} /> };
  const formatLabels = { sentence: 'Sentence', pointform: 'Pointform', numbered_list: 'Numbered List', table: 'Table', mix: 'Mix' };
  const formatIcons = { mix: <IconLayoutCards size={14} />, sentence: <IconFileText size={14} />, pointform: <IconList size={14} />, numbered_list: <IconListNumbers size={14} />, table: <IconTable size={14} /> };

  // Sidebar chat
  const getSavedChat = () => {
    try {
      const saved = localStorage.getItem(`exercise_chat_state_${id}`);
      if (saved) return JSON.parse(saved);
    } catch {}
    return {};
  };
  const savedChat = getSavedChat();
  const [sidebarChatActive, setSidebarChatActive] = useState(savedChat.sidebarChatActive ?? false);
  const [sidebarChatConversationId, setSidebarChatConversationId] = useState(savedChat.sidebarChatConversationId ?? null);
  const [sidebarChatMessages, setSidebarChatMessages] = useState(savedChat.sidebarChatMessages ?? []);
  const [sidebarChatInput, setSidebarChatInput] = useState(savedChat.sidebarChatInput ?? '');
  const [sidebarChatLoading, setSidebarChatLoading] = useState(false);
  const [sidebarChatTaskId, setSidebarChatTaskId] = useState(null);
  const [sidebarChatPollInterval, setSidebarChatPollInterval] = useState(null);
  const [exerciseConversations, setExerciseConversations] = useState([]);
  const [showConvList, setShowConvList] = useState(false);
  const [sidebarAiMode, setSidebarAiModeInner] = useState(() => {
    try {
      const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
      return ls.aiMode || 'quick';
    } catch { return 'quick'; }
  });
  const [sidebarOutputFormat, setSidebarOutputFormatInner] = useState(() => {
    try {
      const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
      return ls.outputFormat || 'sentence';
    } catch { return 'sentence'; }
  });
  const setSidebarAiMode = (mode) => {
    setSidebarAiModeInner(mode);
    try {
      const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
      ls.aiMode = mode;
      localStorage.setItem('lastChatSettings', JSON.stringify(ls));
    } catch {}
  };
  const setSidebarOutputFormat = (fmt) => {
    setSidebarOutputFormatInner(fmt);
    try {
      const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
      ls.outputFormat = fmt;
      localStorage.setItem('lastChatSettings', JSON.stringify(ls));
    } catch {}
  };
  const [sidebarSettingsOpen, setSidebarSettingsOpen] = useState(savedChat.sidebarSettingsOpen ?? false);

  useEffect(() => {
    localStorage.setItem(`exercise_chat_state_${id}`, JSON.stringify({
      sidebarOpen,
      sidebarChatActive,
      sidebarChatConversationId,
      sidebarChatMessages,
      sidebarChatInput,
      sidebarAiMode,
      sidebarOutputFormat,
      sidebarSettingsOpen,
    }));
  }, [id, sidebarOpen, sidebarChatActive, sidebarChatConversationId, sidebarChatMessages, sidebarChatInput, sidebarAiMode, sidebarOutputFormat, sidebarSettingsOpen]);

  useEffect(() => {
    if (sidebarChatRef.current) {
      sidebarChatRef.current.scrollTop = sidebarChatRef.current.scrollHeight;
    }
  }, [sidebarChatMessages]);

  // Sidebar chat action button state
  const [sidebarChatActiveTab, setSidebarChatActiveTab] = useState({});
  const [sidebarChatRateOpened, setSidebarChatRateOpened] = useState({});
  const [sidebarChatComment, setSidebarChatComment] = useState({});
  const handleSidebarRate = async (msgId, val, commentKey) => {
    const comment = sidebarChatComment[commentKey] || '';
    try {
      await fetchApi(`/chat/messages/${msgId}/rate`, {
        method: 'POST',
        body: JSON.stringify({ rating: val, comment }),
      });
    } catch {}
  };

  const openSidebarChat = async (conversationId = null) => {
    setSidebarChatActive(true);
    setShowConvList(false);
    setSidebarSettingsOpen(false);
    if (conversationId) {
      setSidebarChatConversationId(conversationId);
      try {
        const msgs = await fetchApi(`/chat/conversations/${conversationId}/messages`);
        setSidebarChatMessages(msgs || []);
      } catch (e) {
        setSidebarChatMessages([]);
      }
    } else {
      setSidebarChatConversationId(null);
      setSidebarChatMessages([]);
    }
  };

  const closeSidebarChat = () => {
    setSidebarChatActive(false);
    setSidebarChatConversationId(null);
    setSidebarChatMessages([]);
    setSidebarChatInput('');
    if (sidebarChatPollInterval) clearInterval(sidebarChatPollInterval);
    setSidebarChatTaskId(null);
  };

  const startNewSidebarChat = () => {
    setSidebarChatConversationId(null);
    setSidebarChatMessages([]);
    setSidebarChatActive(true);
    setShowConvList(false);
    setSidebarSettingsOpen(false);
  };

  const sendSidebarChatMessage = async (message, startNew = false, apiMessage) => {
    const msg = (message || sidebarChatInput).trim();
    if (!msg) return;
    if (startNew) {
      setSidebarChatActive(true);
      setShowConvList(false);
      setSidebarSettingsOpen(false);
    }
    setSidebarChatInput('');
    setSidebarChatMessages(prev => [...prev, { id: 'temp', message: msg, response: '', created_at: new Date().toISOString() }]);
    setSidebarChatLoading(true);
    const activeConvId = sidebarChatConversationId;
    const apiMsg = (apiMessage || msg).trim();
    try {
      const res = await fetchApi('/chat/ask', {
        method: 'POST',
        body: JSON.stringify({
          message: apiMsg,
          exercise_id: id,
          conversation_id: activeConvId,
          ai_mode: sidebarAiMode,
          output_format: sidebarOutputFormat,
          auto_detect_conversation: true,
        })
      });
      if (res.task_id) {
        setSidebarChatTaskId(res.task_id);
        const interval = setInterval(async () => {
          try {
            const statusRes = await fetchApi(`/search/tasks/${res.task_id}`);
            if (statusRes.status === 'completed') {
              clearInterval(interval);
              setSidebarChatLoading(false);
              setSidebarChatTaskId(null);
              const newConvId = statusRes.result?.conversation_id || activeConvId;
              if (newConvId) {
                setSidebarChatConversationId(newConvId);
                const msgs = await fetchApi(`/chat/conversations/${newConvId}/messages`);
                setSidebarChatMessages(msgs || []);
              }
            } else if (statusRes.status === 'failed') {
              clearInterval(interval);
              setSidebarChatLoading(false);
              setSidebarChatTaskId(null);
            }
          } catch (e) {
            clearInterval(interval);
            setSidebarChatLoading(false);
            setSidebarChatTaskId(null);
          }
        }, 2000);
        setSidebarChatPollInterval(interval);
      }
    } catch (e) {
      setSidebarChatLoading(false);
    }
  };

  const loadExerciseConversations = async () => {
    try {
      const convs = await fetchApi(`/chat/exercise/${id}/conversations`);
      setExerciseConversations(convs || []);
      setShowConvList(true);
    } catch (e) {
      setExerciseConversations([]);
    }
  };

  const buildExplanationContext = (q, explanation, userAnswer, correctAnswer, followUp) => {
    const qText = q.question || q.question_text || '';
    const ref = qText.length > 80 ? qText.slice(0, 80) + '...' : qText;
    return `[referring to explanation: ${ref}]\n${followUp}`;
  };

  const sendExplanationFollowUp = (q, explanation, userAnswer, correctAnswer, followUp) => {
    const displayMsg = buildExplanationContext(q, explanation, userAnswer, correctAnswer, followUp);
    sendSidebarChatMessage(displayMsg, true, followUp);
  };

  // History modal
  const [historyModalOpened, setHistoryModalOpened] = useState(false);
  const [historyModalQuestion, setHistoryModalQuestion] = useState(null);
  const [voiceSettingsOpened, setVoiceSettingsOpened] = useState(false);
  const [showProcessLog, setShowProcessLog] = useState(false);

  // Poll for exercise and note statuse
  const [editedQuestions, setEditedQuestions] = useState([]);
  const [savingEdits, setSavingEdits] = useState(false);

  // Processing state
  const [processingStatus, setProcessingStatus] = useState(null);
  const viewportRef = useRef(null);
  const [scrollProgress, setScrollProgress] = useState(0);

  const prevExerciseTaskStatus = useRef(null);

  // Fetch exercise data and check for existing task on mount (one-time, no 404s)
  useEffect(() => {
    let active = true;

    const fetchExercise = async () => {
      try {
        const data = await fetchApi(`/exercises/${id}`);
        if (!active) return;
        setExercise(data);
        setEditedQuestions(JSON.parse(JSON.stringify(data.questions || [])));
        setLoading(false);

        // Load saved state
        const stateData = await fetchApi(`/exercises/${id}/state`).catch(() => null);
        if (!active) return;
        if (stateData && Object.keys(stateData).length > 0) {
          if (stateData.userAnswers) setUserAnswers(stateData.userAnswers);
          if (stateData.gradingResults) setGradingResults(stateData.gradingResults);
          if (stateData.explanations) setExplanations(stateData.explanations);
          if (stateData.revealedAnswers) setRevealedAnswers(stateData.revealedAnswers);
          if (stateData.showExplanations) setShowExplanations(stateData.showExplanations);
          if (stateData.answerTimestamps) setAnswerTimestamps(stateData.answerTimestamps);
        }

        const taskData = await fetchApi(`/search/task?exercise_id=${id}`).catch(() => null);
        if (!active) return;
        if (taskData && taskData.status && taskData.status !== 'completed') {
          setProcessingStatus({
            status: taskData.status,
            progress: taskData.progress,
            message: taskData.message
          });
        }
      } catch (err) {
        if (!active) return;
        console.error(err);
        alert("Failed to load exercise");
        setLoading(false);
      }
    };

    fetchExercise();

    return () => { active = false; };
  }, [id]);

  // Auto-save exercise state on changes
  const saveTimeoutRef = useRef(null);
  useEffect(() => {
    if (!exercise) return;
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      fetchApi(`/exercises/${id}/state`, {
        method: 'PUT',
        body: JSON.stringify({
          userAnswers,
          gradingResults,
          explanations,
          revealedAnswers,
          showExplanations,
          answerTimestamps,
        })
      }).catch(() => {});
    }, 1000);
    return () => {
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    };
  }, [id, userAnswers, gradingResults, explanations, revealedAnswers, showExplanations, answerTimestamps]);

  // Watch TaskContext for task updates (replaces polling)
  useEffect(() => {
    if (!exercise || !id) return;

    const exerciseTask = tasks.find(t =>
      (t.task_type === 'exercise_extraction' || t.task_type === 'exercise_generation') &&
      (t.task_id === `extract_${id}` || t.task_id === `generate_${id}`)
    );

    if (!exerciseTask) return;

    const prevStatus = prevExerciseTaskStatus.current;
    prevExerciseTaskStatus.current = exerciseTask.status;

    setProcessingStatus({
      status: exerciseTask.status,
      progress: exerciseTask.progress,
      message: exerciseTask.message
    });

    // Only refetch on transition TO completed (avoids infinite refetch loop)
    if (exerciseTask.status === 'completed' && prevStatus !== 'completed') {
      fetchApi(`/exercises/${id}`).then(data => {
        setExercise(data);
        setEditedQuestions(JSON.parse(JSON.stringify(data.questions || [])));
      });
    }
  }, [tasks, exercise, id]);

  useEffect(() => {
    if (examActive && examTimeRemaining !== null) {
      if (examTimeRemaining <= 0) {
        clearInterval(timerRef.current);
        setExamActive(false);
        setShowTimeUpModal(true);
      } else {
        timerRef.current = setInterval(() => {
          setExamTimeRemaining(prev => prev - 1);
        }, 1000);
      }
    }
    return () => clearInterval(timerRef.current);
  }, [examActive, examTimeRemaining]);

  const handleGrade = async (qId) => {
    const answer = userAnswers[qId] || '';
    if (!answer.trim()) return;

    const question = exercise.questions.find(q => q.id === qId);
    if (!question) return;

    setAnswerTimestamps(prev => ({ ...prev, [qId]: Date.now() }));

    // Client-side auto-grade for objective only
    if (question.question_type === 'objective') {
      const correctAns = question.answer_text.trim().toLowerCase();
      const userAns = answer.trim().toLowerCase();
      const isCorrect = userAns === correctAns || correctAns.includes(userAns) || userAns.includes(correctAns);
      const maxM = question.max_marks || 1;
      setGradingResults(prev => ({ 
        ...prev, 
        [qId]: {
          total_awarded: isCorrect ? maxM : 0,
          total_max: maxM,
          criterion_results: [{
            criterion: "Correct answer",
            max_points: maxM,
            awarded_points: isCorrect ? maxM : 0,
            rationale: isCorrect ? "Answer matches the correct answer." : "Answer does not match the correct answer."
          }],
          feedback: isCorrect ? "Correct!" : "Incorrect.",
          correct_answer: question.answer_text
        }
      }));
      if (question.score_type === 'both') {
        handleExplain(qId);
      }
      return;
    }

    // AI grading for subjective
    setGradingLoading(prev => ({ ...prev, [qId]: true }));
    try {
      const res = await fetchApi(`/exercises/${id}/questions/${qId}/grade`, {
        method: 'POST',
        body: JSON.stringify({ user_answer: answer })
      });
      setGradingResults(prev => ({ ...prev, [qId]: res }));
      if (question.score_type === 'both') {
        handleExplain(qId);
      }
    } catch (e) {
      alert("Failed to grade answer: " + e.message);
    } finally {
      setGradingLoading(prev => ({ ...prev, [qId]: false }));
    }
  };

  const saveSession = async () => {
    try {
      const gradeEntries = Object.entries(gradingResults);
      if (gradeEntries.length === 0) return;
      const totalMax = gradeEntries.reduce((s, [, g]) => s + ((g.total_max || (g.is_correct !== undefined ? 1 : 0))), 0);
      const totalAwarded = gradeEntries.reduce((s, [, g]) => s + ((g.total_awarded !== undefined ? g.total_awarded : (g.is_correct ? 1 : 0))), 0);
      await fetchApi(`/exercises/${id}/submit`, {
        method: 'POST',
        body: JSON.stringify({
          awarded_marks: totalAwarded,
          total_marks: totalMax,
          question_scores: gradingResults,
          duration_minutes: examTimerMinutes - (examTimeRemaining !== null ? Math.floor(examTimeRemaining / 60) : 0),
        })
      });
    } catch (e) {
      console.error("Failed to save session:", e);
    }
  };

  const handleCheckAll = async () => {
    const promises = (exercise.questions || []).map(q => {
      if (!userAnswers[q.id]) return Promise.resolve();
      if (!gradingResults[q.id]) {
        return handleGrade(q.id);
      }
      return Promise.resolve();
    });
    await Promise.all(promises);
    saveSession();
  };

  const handleExplain = async (qId) => {
    setExplainLoading(prev => ({ ...prev, [qId]: true }));
    try {
      const res = await fetchApi(`/exercises/${id}/questions/${qId}/explain`, {
        method: 'POST',
        body: JSON.stringify({ 
          user_answer: userAnswers[qId] || null,
          view_mode: viewMode
        })
      });
      setExplanations(prev => ({ ...prev, [qId]: res.explanation }));
      setShowExplanations(prev => ({ ...prev, [qId]: true }));
    } catch (e) {
      alert("Failed to get explanation: " + e.message);
    } finally {
      setExplainLoading(prev => ({ ...prev, [qId]: false }));
    }
  };

  const handleDeleteExplanation = async (qId) => {
    try {
      await fetchApi(`/exercises/${id}/questions/${qId}/explain`, {
        method: 'DELETE'
      });
      setExplanations(prev => ({ ...prev, [qId]: null }));
      setShowExplanations(prev => ({ ...prev, [qId]: false }));
    } catch (e) {
      alert("Failed to delete explanation: " + e.message);
    }
  };

  const handleResetQuestion = (qId) => {
    setUserAnswers(prev => ({ ...prev, [qId]: "" }));
    setGradingResults(prev => {
      const newResults = { ...prev };
      delete newResults[qId];
      return newResults;
    });
    setShowExplanations(prev => {
      const newShow = { ...prev };
      delete newShow[qId];
      return newShow;
    });
  };

  const handleExport = async (format) => {
    setExporting(true);
    try {
      const res = await fetchApi(`/exercises/${id}/export`, {
        method: 'POST',
        body: JSON.stringify({ format, include_cover: true })
      });
      if (res && res.task_id) {
        const interval = setInterval(async () => {
          try {
            const statusRes = await fetchApi(`/exercises/${id}/export-status/${res.task_id}`);
            if (statusRes.status === 'complete') {
              clearInterval(interval);
              window.location.href = res.download_url;
              setExporting(false);
            } else if (statusRes.status === 'failed') {
              clearInterval(interval);
              alert("Export failed.");
              setExporting(false);
            }
          } catch (e) {
            clearInterval(interval);
            setExporting(false);
          }
        }, 2000);
      }
    } catch (e) {
      alert("Failed to start export: " + e.message);
      setExporting(false);
    }
  };

  const handleStartExam = () => {
    setExamTimeRemaining(examTimerMinutes * 60);
    setExamActive(true);
    setExamCompleted(false);
    setUserAnswers({});
    setGradingResults({});
    setExplanations({});
    setRevealedAnswers({});
  };

  const handleSubmitExam = async () => {
    setExamActive(false);
    setExamCompleted(true);
    clearInterval(timerRef.current);
    await handleCheckAll();
  };

  const toggleReveal = (qId) => {
    setRevealedAnswers(prev => ({ ...prev, [qId]: !prev[qId] }));
  };

  const handleResetExercise = () => {
    setUserAnswers({});
    setGradingResults({});
    setExplanations({});
    setRevealedAnswers({});
    setShowExplanations({});
    setExamActive(false);
    setExamCompleted(false);
    setExamTimeRemaining(null);
    if (timerRef.current) clearInterval(timerRef.current);
    localStorage.removeItem(`exercise_exam_${id}`);
    fetchApi(`/exercises/${id}/state`, { method: 'DELETE' }).catch(() => {});
  };

  const handleSaveEdits = async () => {
    setSavingEdits(true);
    try {
      const res = await fetchApi(`/exercises/${id}/content`, {
        method: 'PUT',
        body: JSON.stringify({ questions: editedQuestions })
      });
      setExercise(res);
      setEditMode(false);
    } catch (e) {
      alert("Failed to save exercise: " + e.message);
    } finally {
      setSavingEdits(false);
    }
  };

  if (loading) {
    return <Center h="50vh"><Loader size="lg" /></Center>;
  }

  if (!exercise) {
    return <Center h="50vh"><Text>Exercise not found.</Text></Center>;
  }

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  function QEditor({ value, onChange, label, placeholder, minRows = 2 }) {
    const editor = useEditor({
      extensions: [
        StarterKit,
        Markdown,
        Table.configure({ resizable: true }),
        TableRow,
        TableHeader,
        TableCell,
        Link,
        Image,
        ResizableImageExtension.configure({ inline: true, allowBase64: true }),
      ],
      content: value || '',
      onUpdate: ({ editor }) => {
        onChange(editor.getHTML());
      },
      editorProps: {
        attributes: { class: 'prose prose-sm max-w-none focus:outline-none' }
      }
    });

    return (
      <Box>
        {label && <Text size="sm" fw={500} mb={4}>{label}</Text>}
        <Box
          style={{
            border: '1px solid var(--mantine-color-gray-3)',
            borderRadius: 'var(--mantine-radius-sm)',
            overflow: 'hidden'
          }}
        >
          <Group gap={4} p={4} style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', background: 'var(--mantine-color-gray-0)' }}>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleBold().run()}>
              <Text fw={700} size="xs">B</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleItalic().run()}>
              <Text fs="italic" size="xs">I</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleBulletList().run()}>
              <Text size="xs">•</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleOrderedList().run()}>
              <Text size="xs">1.</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}>
              <Text size="xs" fw={700}>H2</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleHeading({ level: 3 }).run()}>
              <Text size="xs" fw={700}>H3</Text>
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => editor?.chain().focus().toggleCodeBlock().run()}>
              <IconCode size={16} />
            </ActionIcon>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={async () => {
              try {
                const fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.onchange = async () => {
                  const file = fileInput.files?.[0];
                  if (!file) return;
                  const url = await handleImageUploadFlow(file, id, 'exercises');
                  if (url) {
                    editor?.chain().focus().setImage({ src: url }).run();
                  }
                };
                fileInput.click();
              } catch (e) {
                console.error(e);
              }
            }}>
              <IconPhotoPlus size={16} />
            </ActionIcon>
          </Group>
          <Box p="sm" style={{ minHeight: minRows * 24 }}>
            <EditorContent editor={editor} />
          </Box>
        </Box>
      </Box>
    );
  }

  function HtmlContent({ html, ...props }) {
    if (!html) return null;
    return (
      <Box className="markdown-content" dangerouslySetInnerHTML={{ __html: html }} style={{ lineHeight: 1.65 }} {...props} />
    );
  }

  function SubPartRenderer({ part, userAnswers, setUserAnswers, gradingResults, gradingLoading, handleGrade, handleResetQuestion, isInteractive, isExam, examActive, hasGraded, viewMode, showAns, depth, explanations, explainLoading, handleExplain, showExplanations, setShowExplanations, revealedAnswers, toggleReveal }) {
    const spId = part.id;
    const partGrade = gradingResults[spId];
    const partHasGraded = !!partGrade;
    const partExplanation = explanations?.[spId] || part.explanation;
    const partShowAns = showAns || revealedAnswers?.[spId];
    const isLast = depth >= 2;

    let parsedPartOptions = [];
    try {
      parsedPartOptions = typeof part.options === 'string' ? JSON.parse(part.options) : (part.options || []);
    } catch(e) { parsedPartOptions = []; }

    return (
      <Box mb="md">
        <Group justify="space-between" wrap="nowrap" mb={4}>
          <Text fw={500} size="sm" c="dimmed">
            ({part.label || '?'})
          </Text>
          {part.max_marks > 0 && (
            <Badge size="xs" variant="light" color="blue" radius="sm" style={{ flexShrink: 0 }}>
              {part.max_marks} {part.max_marks === 1 ? 'mark' : 'marks'}
            </Badge>
          )}
        </Group>
        <HtmlContent html={part.question_text} mb="xs" />

        {/* Nested sub-parts */}
        {part.sub_parts?.length > 0 && (
          <Box ml="md" mt="sm" style={{borderLeft: '2px solid var(--mantine-color-gray-2)', paddingLeft: 14}}>
            {part.sub_parts.map(spp => (
              <SubPartRenderer
                key={spp.id}
                part={spp}
                {...{ userAnswers, setUserAnswers, gradingResults, gradingLoading, handleGrade, handleResetQuestion, isInteractive, isExam, examActive, hasGraded, viewMode, showAns, explanations, explainLoading, handleExplain, showExplanations, setShowExplanations, revealedAnswers, toggleReveal }}
                depth={depth + 1}
              />
            ))}
          </Box>
        )}

        {isInteractive && !isLast && (
          <Box mt="xs">
            {parsedPartOptions.length > 0 ? (
              <Radio.Group
                value={userAnswers[spId] || ''}
                onChange={(v) => setUserAnswers(prev => ({...prev, [spId]: v}))}
              >
                <Stack mt="xs">
                  {parsedPartOptions.map((opt, i) => (
                    <Radio key={i} value={opt} label={opt} disabled={partHasGraded || (isExam && !examActive)} size="xs" />
                  ))}
                </Stack>
              </Radio.Group>
            ) : (
              <Textarea
                placeholder="Type your answer here..."
                value={userAnswers[spId] || ''}
                onChange={(e) => setUserAnswers(prev => ({...prev, [spId]: e.currentTarget.value}))}
                minRows={1}
                autosize
                size="xs"
                disabled={partHasGraded || (isExam && !examActive)}
                autosize
                minRows={2}
              />
            )}

            {!isExam && (
              <Group mt="xs">
                {!partHasGraded ? (
                  <Button size="compact-sm" loading={gradingLoading[spId]} onClick={() => handleGrade(spId)} disabled={!userAnswers[spId]}>
                    Check
                  </Button>
                ) : (
                  <Button size="compact-sm" variant="light" color="gray" onClick={() => handleResetQuestion(spId)} leftSection={<IconRefresh size={12} />}>
                    Reset
                  </Button>
                )}
              </Group>
            )}

            {partHasGraded && partGrade && (
              <Box mt="sm">
                <GradeDisplay grade={partGrade} correctAnswer={part.answer_text} />
              </Box>
            )}
          </Box>
        )}

        {!isInteractive && (partShowAns || viewMode === 'hide') && (
          <Paper p="md" bg="var(--mantine-color-blue-0)" radius="sm" mt="xs"
            style={{
              cursor: !partShowAns ? 'pointer' : 'default',
              position: 'relative',
              overflow: 'hidden',
              transition: 'all 0.2s ease'
            }}
            onClick={() => {
              if (!partShowAns && viewMode === 'hide') {
                toggleReveal(spId);
              }
            }}
          >
            {!partShowAns && (
              <Center style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 10, background: 'rgba(231, 245, 255, 0.3)' }}>
                <Badge size="lg" variant="light" style={{ pointerEvents: 'none' }}>
                  Click to reveal answer
                </Badge>
              </Center>
            )}
            <Box style={{ filter: !partShowAns ? 'blur(6px)' : 'none', opacity: !partShowAns ? 0.5 : 1, transition: 'all 0.35s ease', userSelect: !partShowAns ? 'none' : 'auto', pointerEvents: !partShowAns ? 'none' : 'auto' }}>
              <Text fw={500} c="blue.9">Answer:</Text>
              <Box c="blue.9"><HtmlContent html={part.answer_text || "No answer provided."} /></Box>
              <Box mt="md">
                {partExplanation && showExplanations?.[spId] && (
                  <Paper p="md" bg="var(--mantine-color-white)" radius="sm" mb="sm">
                    {explainLoading?.[spId] ? (
                      <Group gap="xs"><Loader size="xs" color="grape" /><Text size="sm" c="dimmed">Regenerating explanation...</Text></Group>
                    ) : (
                      <>
                        <Group justify="space-between" align="center" wrap="nowrap" mb={8}>
                          <Text size="sm"><IconBulb size={14} style={{ marginRight: 5, verticalAlign: 'middle', color: 'var(--mantine-color-grape-6)' }}/><b>Explanation</b></Text>
                          <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => { e.stopPropagation(); setShowExplanations(prev => ({ ...prev, [spId]: false })); }}>
                            <IconEyeOff size={14} />
                          </ActionIcon>
                        </Group>
                        <Box className="markdown-content" size="sm">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{partExplanation}</ReactMarkdown>
                        </Box>
                      </>
                    )}
                  </Paper>
                )}
                <Group gap="xs">
                  {!partExplanation && (
                    <Button size="xs" variant="light" loading={explainLoading?.[spId]} onClick={(e) => { e.stopPropagation(); handleExplain(spId); }} leftSection={<IconBulb size={14} />}>
                      Ask AI to Explain
                    </Button>
                  )}
                  {partExplanation && !showExplanations?.[spId] && (
                    <Button size="xs" variant="light" onClick={(e) => { e.stopPropagation(); setShowExplanations(prev => ({ ...prev, [spId]: true })); }} leftSection={<IconBulb size={14} />}>
                      Show AI Explanation
                    </Button>
                  )}
                  {viewMode === 'hide' && (
                    <Button size="xs" variant="default" onClick={(e) => { e.stopPropagation(); toggleReveal(spId); }} leftSection={partShowAns ? <IconEyeOff size={14} /> : <IconEye size={14} />}>
                      {partShowAns ? "Re-hide Answer" : "Reveal Answer"}
                    </Button>
                  )}
                </Group>
              </Box>
            </Box>
          </Paper>
        )}
      </Box>
    );
  }

  function GradeDisplay({ grade, correctAnswer }) {
    if (!grade || grade.total_awarded === undefined) return null;
    const isLegacy = grade.is_correct !== undefined && grade.total_awarded === undefined;
    if (isLegacy) {
      return (
        <Alert color={grade.is_correct ? 'green' : 'red'} icon={grade.is_correct ? <IconCheck /> : <IconX />}>
          <Text fw={500}>{grade.feedback}</Text>
          {!grade.is_correct && <Box mt="xs" size="sm"><b>Correct Answer:</b> <HtmlContent html={grade.correct_answer} style={{ display: 'inline' }} /></Box>}
        </Alert>
      );
    }
    const isAiError = grade.feedback && grade.feedback.startsWith('AI grading unavailable');
    return (
      <Box>
        <Alert color={grade.total_awarded === grade.total_max ? 'green' : isAiError ? 'yellow' : grade.total_awarded > 0 ? 'yellow' : 'red'}
          icon={grade.total_awarded === grade.total_max ? <IconCheck /> : <IconX />}>
          <Box>
            <Group justify="space-between" wrap="wrap" gap="xs">
              <Box>
                <Text fw={600} size="sm">Score: {grade.total_awarded}/{grade.total_max}</Text>
              </Box>
              <Badge size="md" variant="filled" color={grade.total_awarded === grade.total_max ? 'green' : isAiError ? 'gray' : grade.total_awarded > 0 ? 'yellow' : 'red'} style={{ flexShrink: 0 }}>
                {isAiError ? 'Not graded' : grade.total_awarded === grade.total_max ? 'Perfect' : grade.total_awarded > 0 ? 'Partial' : 'Incorrect'}
              </Badge>
            </Group>
            {grade.feedback && <Text size="xs" mt={4}>{grade.feedback}</Text>}
          </Box>
        </Alert>
        {isAiError && correctAnswer && (
          <Paper mt="xs" p="sm" withBorder radius="md" bg="blue.0">
            <Text size="xs" fw={600} mb={2} c="dimmed">Correct Answer:</Text>
            <HtmlContent html={correctAnswer} />
          </Paper>
        )}
        {grade.criterion_results?.length > 0 && !isAiError && (
          <Paper mt="xs" p="sm" withBorder radius="md">
            <Text size="xs" fw={600} mb="xs" c="dimmed">Marking Breakdown</Text>
            {grade.criterion_results.map((cr, i) => (
              <Group key={i} justify="space-between" wrap="nowrap" py={4}
                style={{borderBottom: i < grade.criterion_results.length - 1 ? '1px solid #f0f0f0' : 'none'}}>
                <Box style={{flex: 1}}>
                  <Text size="xs" fw={500}>{cr.criterion}</Text>
                  {cr.rationale && <Text size="xs" c="dimmed">{cr.rationale}</Text>}
                </Box>
                <Badge size="sm" variant="light" color={cr.awarded_points === cr.max_points ? 'green' : cr.awarded_points > 0 ? 'yellow' : 'red'}>
                  {cr.awarded_points}/{cr.max_points}
                </Badge>
              </Group>
            ))}
          </Paper>
        )}
      </Box>
    );
  }

  function SubPartEditor({ part, onChange, onRemove, depth }) {
    if (depth >= 2) return null;
    return (
      <Paper p="xs" withBorder mb="xs" style={{marginLeft: depth * 16}}>
        <Group justify="space-between" mb="xs">
          <Text size="xs" fw={600} c="dimmed">Sub-part ({part.label || '?'})</Text>
          <ActionIcon color="red" variant="subtle" size="sm" onClick={onRemove}><IconX size={14} /></ActionIcon>
        </Group>
        <Stack gap="xs">
          <Group grow>
            <TextInput size="xs" label="Label" value={part.label || ''}
              onChange={(e) => onChange({...part, label: e.currentTarget.value})} />
            <NumberInput size="xs" label="Max Marks" value={part.max_marks ?? 1}
              onChange={(v) => onChange({...part, max_marks: v || 0})} min={0} />
            <Select size="xs" label="Type" data={['subjective', 'objective', 'fill_in_the_blank']}
              value={part.question_type}
              onChange={(v) => onChange({...part, question_type: v})} />
          </Group>
          <Textarea size="xs" label="Question" value={part.question_text}
            onChange={(e) => onChange({...part, question_text: e.currentTarget.value})} minRows={1} autosize />
          <Textarea size="xs" label="Answer" value={part.answer_text}
            onChange={(e) => onChange({...part, answer_text: e.currentTarget.value})} minRows={1} autosize />
          {part.question_type === 'objective' && (
            <Textarea size="xs" label="Options (one per line)" value={Array.isArray(part.options) ? part.options.join('\n') : ''}
              onChange={(e) => onChange({...part, options: e.currentTarget.value.split('\n').filter(Boolean)})} minRows={2} />
          )}

          {/* Nested sub-part editor */}
          <Box>
            <Group justify="space-between" mb={4}>
              <Text size="xs" fw={500} c="dimmed">Sub-parts</Text>
              <Button size="compact-xs" variant="light" onClick={() => {
                const subParts = [...(part.sub_parts || [])];
                const label = String.fromCharCode(97 + subParts.length);
                subParts.push({
                  id: `${part.id}${label}`,
                  label,
                  question_text: '',
                  answer_text: '',
                  max_marks: 1,
                  question_type: 'subjective',
                  options: null,
                  sub_parts: [],
                  marking_scheme: [],
                });
                onChange({...part, sub_parts: subParts});
              }} leftSection={<IconPlus size={10} />}>Add</Button>
            </Group>
            {(part.sub_parts || []).map((spp, sppIdx) => (
              <SubPartEditor
                key={spp.id || sppIdx}
                part={spp}
                onChange={(updated) => {
                  const subParts = [...(part.sub_parts || [])];
                  subParts[sppIdx] = updated;
                  onChange({...part, sub_parts: subParts});
                }}
                onRemove={() => {
                  const subParts = [...(part.sub_parts || [])];
                  subParts.splice(sppIdx, 1);
                  onChange({...part, sub_parts: subParts});
                }}
                depth={depth + 1}
              />
            ))}
          </Box>

          {/* Marking scheme for sub-part */}
          <Box>
            <Group justify="space-between" mb={4}>
              <Text size="xs" fw={500} c="dimmed">Marking Scheme</Text>
              <Button size="compact-xs" variant="light" onClick={() => {
                const ms = [...(part.marking_scheme || [])];
                ms.push({ criterion: '', max_points: 1, description: '' });
                onChange({...part, marking_scheme: ms});
              }} leftSection={<IconPlus size={10} />}>Add</Button>
            </Group>
            {(part.marking_scheme || []).map((mc, mcIdx) => (
              <Group key={mcIdx} gap={4} mb={2} wrap="nowrap">
                <TextInput size="xs" placeholder="Criterion" value={mc.criterion}
                  onChange={(e) => {
                    const ms = [...(part.marking_scheme || [])];
                    ms[mcIdx] = {...ms[mcIdx], criterion: e.currentTarget.value};
                    onChange({...part, marking_scheme: ms});
                  }} style={{flex: 2}} />
                <NumberInput size="xs" placeholder="Pts" value={mc.max_points}
                  onChange={(v) => {
                    const ms = [...(part.marking_scheme || [])];
                    ms[mcIdx] = {...ms[mcIdx], max_points: v || 1};
                    onChange({...part, marking_scheme: ms});
                  }} min={1} style={{width: 60}} />
                <ActionIcon color="red" variant="subtle" size="xs" onClick={() => {
                  const ms = [...(part.marking_scheme || [])];
                  ms.splice(mcIdx, 1);
                  onChange({...part, marking_scheme: ms});
                }}><IconX size={12} /></ActionIcon>
              </Group>
            ))}
          </Box>
        </Stack>
      </Paper>
    );
  }

  const taskActive = processingStatus && (processingStatus.status === 'pending' || processingStatus.status === 'processing' || processingStatus.status === 'running');
  const taskFailed = processingStatus && (processingStatus.status === 'failed' || processingStatus.status === 'cancelled');
  const hasQuestions = exercise?.questions?.length > 0;

  const isAiGenerated = !!exercise?.parameters;
  const coveredResources = (() => {
    if (!exercise || !exercise.questions) return [];
    const resourcesMap = new Map();
    exercise.questions.forEach(q => {
      if (q.reference_resource_title) {
        resourcesMap.set(q.reference_resource_title, q.reference_resource_id || null);
      }
    });
    return Array.from(resourcesMap.entries()).map(([title, id]) => ({ title, id }));
  })();
  const detectedQuestionTypes = (() => {
    if (!exercise?.questions) return [];
    const types = new Set();
    exercise.questions.forEach(q => {
      if (q.question_type) types.add(q.question_type);
    });
    return Array.from(types).map(t => {
      const formatted = t.replace(/_/g, ' ');
      return formatted.charAt(0).toUpperCase() + formatted.slice(1);
    });
  })();

  return (
    <Box h="100vh" style={{ display: 'flex', flexDirection: 'column', overflowX: 'hidden' }}>
      <style>{`
        .clickable-crumb {
          cursor: pointer;
        }
        .clickable-crumb:hover {
          text-decoration: underline;
        }
        .markdown-content img {
          max-width: 66%;
          height: auto;
          display: block;
          margin: 1rem 0;
          border-radius: 8px;
        }
        .markdown-content img[src$="#small"] {
          max-width: 33%;
        }
        .markdown-content img[src$="#large"] {
          max-width: 100%;
        }
      `}</style>
      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20 }}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Group wrap="nowrap" gap="xs" style={{ overflow: 'hidden', minWidth: 0 }}>
            <ActionIcon variant="subtle" color="gray" onClick={() => navigate(-1)}>
              <IconChevronLeft size={20} />
            </ActionIcon>
            {exercise?.subject && (
              <Group gap="xs" ml="xs" wrap="nowrap" visibleFrom="sm" style={{ overflow: 'hidden', minWidth: 0 }}>
                {exercise.subject.group && (
                  <>
                    <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/group/${exercise.subject.group.id}`)} style={{ whiteSpace: 'nowrap' }}>{exercise.subject.group.name}</Text>
                    <Text size="sm" c="dimmed">/</Text>
                  </>
                )}
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${exercise.subject.id}`)} style={{ whiteSpace: 'nowrap' }}>{exercise.subject.name}</Text>
                <Text size="sm" c="dimmed">/</Text>
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${exercise.subject.id}/exercise`)} style={{ whiteSpace: 'nowrap' }}>Exercise</Text>
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
        </Group>
      </Box>

      <Box style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <Box style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {!editMode && viewMode === 'exam' && !examActive && !examCompleted && (
            <Paper
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 100,
                background: 'rgba(255, 255, 255, 0.75)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                backdropFilter: 'blur(16px)',
                WebkitBackdropFilter: 'blur(16px)',
                padding: '40px',
                textAlign: 'center',
                userSelect: 'none',
              }}
            >
              <IconClock size={64} stroke={1.2} style={{ color: 'var(--mantine-color-indigo-5)', marginBottom: '16px' }} />
              <Title order={2} mb="xs" style={{ fontFamily: 'Instrument Sans, sans-serif' }}>Exam Mode Locked</Title>
              <Text c="dimmed" size="sm" style={{ maxWidth: '360px' }} mb="xl">
                The questions and answer choices are hidden to ensure a fair test. Start the exam to activate the timer and reveal the questions.
              </Text>
              <Button size="md" radius="md" onClick={handleStartExam} style={{ boxShadow: '0 4px 12px rgba(76, 110, 245, 0.2)' }}>
                Start Exam & Timer
              </Button>
            </Paper>
          )}

          {!editMode && viewMode === 'conversation' && !convActive && (
            <Paper
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 100,
                background: 'rgba(255, 255, 255, 0.75)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                backdropFilter: 'blur(16px)',
                WebkitBackdropFilter: 'blur(16px)',
                padding: '40px',
                textAlign: 'center',
                userSelect: 'none',
              }}
            >
              <IconMicrophone size={64} stroke={1.2} style={{ color: 'var(--mantine-color-teal-6)', marginBottom: '16px' }} />
              <Title order={2} mb="xs" style={{ fontFamily: 'Instrument Sans, sans-serif' }}>Conversation Mode</Title>
              <Text c="dimmed" size="sm" style={{ maxWidth: '360px' }} mb="xl">
                Ready to practice your knowledge out loud? You'll be asked questions verbally and can respond using your microphone.
              </Text>
              <Button size="md" radius="md" color="teal" onClick={() => setConvActive(true)} style={{ boxShadow: '0 4px 12px rgba(18, 184, 134, 0.2)' }}>
                Start Conversation
              </Button>
            </Paper>
          )}

          {examActive && (
            <Box
              style={{
                position: 'absolute',
                top: '20px',
                right: '24px',
                zIndex: 90,
                pointerEvents: 'none'
              }}
            >
              <Badge 
                color={examTimeRemaining < 60 ? "red" : "blue"} 
                size="lg" 
                variant="filled"
                leftSection={<IconClock size={16} />}
                style={{
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.12)',
                  height: '36px',
                  fontSize: '14px',
                  pointerEvents: 'auto',
                  display: 'inline-flex',
                  alignItems: 'center'
                }}
              >
                {formatTime(examTimeRemaining)}
              </Badge>
            </Box>
          )}

          <ScrollArea 
            style={{ flex: 1, backgroundColor: '#fff' }} 
            p={0}
            viewportRef={viewportRef}
            viewportProps={{ style: viewMode === 'conversation' ? { display: 'flex', flexDirection: 'column' } : {} }}
          >
          <Container size="md" p={0} pt={0} pb={viewMode === 'conversation' ? 0 : "xl"} style={viewMode === 'conversation' ? { display: 'flex', flexDirection: 'column', height: '100%', minHeight: '100%' } : {}}>
            <Box px="md" style={viewMode === 'conversation' ? { display: 'flex', flexDirection: 'column', flex: 1 } : {}}>
              {!taskActive && (
              <div className="summary-header" style={{ marginBottom: '1.5rem', marginTop: '1.5rem' }}>
                <Group justify="space-between">
                  <Title order={1} style={{ marginTop: 0, marginBottom: 0, paddingTop: '2rem', color: '#171738', fontWeight: 700 }}>
                    {exercise.title}
                  </Title>
                </Group>
              </div>
              )}

              {taskActive && (
                <Box mt={100} ta="center">
                  <IconRobot size={64} color="var(--mantine-color-blue-6)" stroke={1.5} style={{ opacity: 0.8 }} />
                  <Title order={2} mt="xl" mb="sm" fw={800} c="#171738">Generating Exercise...</Title>
                  <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                    Our AI is generating questions based on your resources. This usually takes a few seconds.
                  </Text>
                  
                  {processingStatus && (
                    <Box mx="auto" maw={400} mb="xl">
                      <Group justify="space-between" mb={5}>
                        <Text size="sm" fw={500}>{processingStatus.message || 'Processing...'}</Text>
                        <Text size="sm" fw={500}>{processingStatus.progress || 0}%</Text>
                      </Group>
                      <Progress value={processingStatus.progress || 0} size="xl" radius="xl" striped animated />
                      <Button variant="subtle" mt="sm" onClick={() => setShowProcessLog(true)}>
                        View Live Logs
                      </Button>
                    </Box>
                  )}
                </Box>
              )}

              {taskFailed && (
                <Box mt={100} ta="center">
                  <IconAlertCircle size={64} color="var(--mantine-color-red-6)" stroke={1.5} />
                  <Title order={2} mt="xl" mb="sm" fw={800} c="red">Processing Failed</Title>
                  <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                    {processingStatus.message || 'An unexpected error occurred while generating this exercise.'}
                  </Text>
                </Box>
              )}

              {!hasQuestions && !taskActive && !taskFailed && (
                <Box mb="xl">
                  <Card withBorder padding="xl" shadow="sm">
                    <Stack align="center" spacing="md">
                      <IconBook size={48} color="gray" />
                      <Title order={3}>No Questions Yet</Title>
                      <Text c="dimmed">This exercise has no questions. Generate questions from the subject view or upload a resource with questions.</Text>
                    </Stack>
                  </Card>
                </Box>
              )}

              {!taskActive && (
                <Stack 
                  spacing="xl"
                  style={{ 
                    filter: (!editMode && ((viewMode === 'exam' && !examActive && !examCompleted) || (viewMode === 'conversation' && !convActive))) ? 'blur(10px)' : 'none', 
                    pointerEvents: (!editMode && ((viewMode === 'exam' && !examActive && !examCompleted) || (viewMode === 'conversation' && !convActive))) ? 'none' : 'auto',
                    userSelect: (!editMode && ((viewMode === 'exam' && !examActive && !examCompleted) || (viewMode === 'conversation' && !convActive))) ? 'none' : 'auto',
                    transition: 'filter 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
                    display: viewMode === 'conversation' ? 'flex' : undefined,
                    flexDirection: viewMode === 'conversation' ? 'column' : undefined,
                    flex: viewMode === 'conversation' ? 1 : undefined
                  }}
                >
                  {editMode ? (
                  <Box>
                    <Text fw={600} mb="md">Edit Questions (Changes saved to JSON)</Text>
                    {editedQuestions.map((q, idx) => (
                      <Card key={idx} withBorder mb="sm" shadow="xs">
                        <Group justify="space-between" mb="xs">
                          <Text fw={500}>Question {idx + 1}</Text>
                          <Group gap={4}>
                            <ActionIcon variant="subtle" color="blue" size="sm" onClick={() => {
                              // Auto-fill topic and reference_quote using AI
                              const text = q.question_text?.replace(/<[^>]*>/g, '') || '';
                              const answer = q.answer_text?.replace(/<[^>]*>/g, '') || '';
                              if (text.length > 10) {
                                // Use basic extraction: first meaningful words
                                const words = text.split(/\s+/).filter(w => w.length > 2);
                                const topic = words.slice(0, 5).join(' ');
                                const newQs = [...editedQuestions];
                                if (!newQs[idx].topic) {
                                  newQs[idx].topic = topic;
                                }
                                if (!newQs[idx].reference_quote) {
                                  newQs[idx].reference_quote = text.slice(0, 200);
                                }
                                setEditedQuestions(newQs);
                              }
                            }}>
                              <IconBolt size={16} />
                            </ActionIcon>
                            <ActionIcon color="red" variant="subtle" onClick={() => {
                              const newQs = [...editedQuestions];
                              newQs.splice(idx, 1);
                              setEditedQuestions(newQs);
                            }}><IconTrash size={16} /></ActionIcon>
                          </Group>
                        </Group>
                        <Stack spacing="xs">
                          <Group grow>
                            <Select 
                              label="Type" 
                              data={['subjective', 'objective', 'fill_in_the_blank']} 
                              value={q.question_type} 
                              onChange={(v) => {
                                const newQs = [...editedQuestions];
                                newQs[idx].question_type = v;
                                setEditedQuestions(newQs);
                              }}
                            />
                            <NumberInput 
                              label="Max Marks" 
                              value={q.max_marks ?? 1} 
                              onChange={(v) => {
                                const newQs = [...editedQuestions];
                                newQs[idx].max_marks = v || 0;
                                setEditedQuestions(newQs);
                              }}
                              min={0}
                            />
                          </Group>
                          <QEditor
                            label="Question Text"
                            value={q.question_text || ''}
                            onChange={(html) => {
                              const newQs = [...editedQuestions];
                              newQs[idx].question_text = html;
                              setEditedQuestions(newQs);
                            }}
                          />
                          <QEditor
                            label="Correct Answer"
                            value={q.answer_text || ''}
                            onChange={(html) => {
                              const newQs = [...editedQuestions];
                              newQs[idx].answer_text = html;
                              setEditedQuestions(newQs);
                            }}
                          />

                          {/* Sub-part editor */}
                          <Box>
                            <Group justify="space-between" mb="xs">
                              <Text size="sm" fw={500}>Sub-parts</Text>
                              <Button size="compact-xs" variant="light" onClick={() => {
                                const newQs = [...editedQuestions];
                                if (!newQs[idx].sub_parts) newQs[idx].sub_parts = [];
                                const label = String.fromCharCode(97 + newQs[idx].sub_parts.length);
                                newQs[idx].sub_parts.push({
                                  id: `${q.id || idx}${label}`,
                                  label,
                                  question_text: '',
                                  answer_text: '',
                                  max_marks: 1,
                                  question_type: 'subjective',
                                  options: null,
                                  sub_parts: [],
                                  marking_scheme: [],
                                });
                                setEditedQuestions(newQs);
                              }} leftSection={<IconPlus size={12} />}>Add</Button>
                            </Group>
                            {(q.sub_parts || []).map((sp, spIdx) => (
                              <SubPartEditor
                                key={sp.id || spIdx}
                                part={sp}
                                onChange={(updated) => {
                                  const newQs = [...editedQuestions];
                                  newQs[idx].sub_parts[spIdx] = updated;
                                  setEditedQuestions(newQs);
                                }}
                                onRemove={() => {
                                  const newQs = [...editedQuestions];
                                  newQs[idx].sub_parts.splice(spIdx, 1);
                                  setEditedQuestions(newQs);
                                }}
                                depth={0}
                              />
                            ))}
                          </Box>

                          {/* Marking scheme editor */}
                          <Box>
                            <Group justify="space-between" mb="xs">
                              <Text size="sm" fw={500}>Marking Scheme</Text>
                              <Button size="compact-xs" variant="light" onClick={() => {
                                const newQs = [...editedQuestions];
                                if (!newQs[idx].marking_scheme) newQs[idx].marking_scheme = [];
                                newQs[idx].marking_scheme.push({
                                  criterion: '',
                                  max_points: 1,
                                  description: '',
                                });
                                setEditedQuestions(newQs);
                              }} leftSection={<IconPlus size={12} />}>Add Criterion</Button>
                            </Group>
                            {(q.marking_scheme || []).map((mc, mcIdx) => (
                              <Group key={mcIdx} gap="xs" mb={4} wrap="nowrap">
                                <TextInput
                                  size="xs"
                                  placeholder="Criterion name"
                                  value={mc.criterion}
                                  onChange={(e) => {
                                    const newQs = [...editedQuestions];
                                    newQs[idx].marking_scheme[mcIdx].criterion = e.currentTarget.value;
                                    setEditedQuestions(newQs);
                                  }}
                                  style={{ flex: 2 }}
                                />
                                <NumberInput
                                  size="xs"
                                  placeholder="Points"
                                  value={mc.max_points}
                                  onChange={(v) => {
                                    const newQs = [...editedQuestions];
                                    newQs[idx].marking_scheme[mcIdx].max_points = v || 1;
                                    setEditedQuestions(newQs);
                                  }}
                                  min={1}
                                  style={{ width: 80 }}
                                />
                                <TextInput
                                  size="xs"
                                  placeholder="Description"
                                  value={mc.description}
                                  onChange={(e) => {
                                    const newQs = [...editedQuestions];
                                    newQs[idx].marking_scheme[mcIdx].description = e.currentTarget.value;
                                    setEditedQuestions(newQs);
                                  }}
                                  style={{ flex: 3 }}
                                />
                                <ActionIcon color="red" variant="subtle" size="sm" onClick={() => {
                                  const newQs = [...editedQuestions];
                                  newQs[idx].marking_scheme.splice(mcIdx, 1);
                                  setEditedQuestions(newQs);
                                }}><IconX size={14} /></ActionIcon>
                              </Group>
                            ))}
                          </Box>

                          {q.question_type === 'objective' && (
                            <QEditor
                              label="Options (one per line)"
                              value={typeof q.options === 'string' ? q.options : (Array.isArray(q.options) ? q.options.join('\n') : '')}
                              onChange={(html) => {
                                const newQs = [...editedQuestions];
                                const text = html.replace(/<[^>]*>/g, '').trim();
                                newQs[idx].options = text ? text.split('\n').filter(Boolean) : [];
                                setEditedQuestions(newQs);
                              }}
                              minRows={3}
                            />
                          )}
                          <Box>
                            <Group gap="xs" align="flex-end">
                              <TextInput
                                label="Topic"
                                value={q.topic || ''}
                                onChange={(e) => {
                                  const newQs = [...editedQuestions];
                                  newQs[idx].topic = e.currentTarget.value;
                                  setEditedQuestions(newQs);
                                }}
                                style={{ flex: 1 }}
                                placeholder={q.question_text ? 'Auto-detected from question' : 'Enter topic'}
                              />
                            </Group>
                            <Text size="xs" c="dimmed" mt={2}>Leave empty to auto-detect. Click ⚡ to auto-fill topic and reference quote.</Text>
                          </Box>
                        </Stack>
                      </Card>
                    ))}
                    <Button variant="light" fullWidth leftSection={<IconPlus size={16} />} onClick={() => {
                      setEditedQuestions([...editedQuestions, { id: String(Date.now()), question_type: 'subjective', score_type: '', question_text: '', answer_text: '' }]);
                    }}>Add Question</Button>
                  </Box>
                ) : (
                  (() => {
                    const questions = exercise.questions || [];
                    const orderedQuestions = questionOrder === 'randomized'
                      ? shuffledIndices.map(i => ({ q: questions[i], displayIdx: i, orderIdx: i }))
                      : questions.map((q, i) => ({ q, displayIdx: i, orderIdx: i }));
                    const questionsToRender = viewMode === 'conversation' 
                      ? [orderedQuestions[currentConvIdx]].filter(Boolean) 
                      : orderedQuestions;
                    
                    return questionsToRender.map(({ q, displayIdx }, arrayIdx) => {
                    const idx = displayIdx;
                    const isExam = viewMode === 'exam';
                    const isInteractive = viewMode === 'interactive' || isExam;
                    const hasGraded = !!gradingResults[q.id];
                    const grade = gradingResults[q.id];
                    const explanation = explanations[q.id] || q.explanation;
                    
                    let showAns = false;
                    if (viewMode === 'show') showAns = true;
                    if (viewMode === 'hide' && revealedAnswers[q.id]) showAns = true;
                    if (isInteractive && hasGraded) showAns = true;

                    let parsedOptions = [];
                    try {
                      parsedOptions = typeof q.options === 'string' ? JSON.parse(q.options) : (q.options || []);
                    } catch(e) { parsedOptions = []; }

                    const totalMarks = q.max_marks || (q.sub_parts?.length > 0 ? q.sub_parts.reduce((s, sp) => s + (sp.max_marks || 0), 0) : 0);
                    
                    if (viewMode === 'conversation') {
                      return (
                        <ConversationMode 
                          key="conversation-mode"
                          exercise={exercise} 
                          question={q}
                          convActive={convActive}
                          currentConvIdx={currentConvIdx}
                          totalQuestions={orderedQuestions.length}
                          hasNext={currentConvIdx < orderedQuestions.length - 1}
                          hasPrev={currentConvIdx > 0}
                          onNext={() => setCurrentConvIdx(i => Math.min(i + 1, orderedQuestions.length - 1))}
                          onPrev={() => setCurrentConvIdx(i => Math.max(i - 1, 0))}
                          transcription={userAnswers[q.id] || ''}
                          setTranscription={(val) => setUserAnswers(prev => ({ ...prev, [q.id]: val }))}
                          evaluation={gradingResults[q.id] || null}
                          setEvaluation={(val) => {
                            if (!val) {
                               setGradingResults(prev => {
                                 const next = { ...prev };
                                 delete next[q.id];
                                 return next;
                               });
                               return;
                            }
                            // Evaluate overall status based on conversation if provided
                            let overallStatus = 'Inaccurate';
                            if (val.conversation) {
                               const correctTurn = val.conversation.find(t => t.status === 'Correct');
                               if (correctTurn) overallStatus = 'Correct';
                            } else {
                               overallStatus = val.status === 'Correct' ? 'Correct' : 'Inaccurate';
                            }

                            setGradingResults(prev => ({
                              ...prev,
                              [q.id]: {
                                ...val,
                                status: overallStatus,
                                total_awarded: val.awarded_marks !== undefined ? val.awarded_marks : (overallStatus === 'Correct' ? 1 : 0),
                                total_max: val.max_marks !== undefined ? val.max_marks : 1
                              }
                            }));
                            saveSession();
                          }}
                        />
                      );
                    }

                    return (
                      <Card key={q.id} shadow="sm" padding="lg" radius="md" withBorder>
                        <Group justify="space-between" align="center" mb="xs" wrap="nowrap">
                          <Group gap={8} wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                            {q.difficulty && (
                              <Text size="xs" c="dimmed" fw={500}>
                                {q.difficulty}
                              </Text>
                            )}
                            {q.difficulty && (q.topic || q.reference_resource_title) && (
                              <Text size="xs" c="dimmed" fw={500}>|</Text>
                            )}
                            {q.topic && (
                              <Text size="xs" c="dimmed" fw={500}>
                                {q.topic}
                              </Text>
                            )}
                            {q.topic && q.reference_resource_title && (
                              <Text size="xs" c="dimmed" fw={500}>|</Text>
                            )}
                            {q.reference_resource_title && (
                              <Text 
                                size="xs" 
                                c="dimmed" 
                                fw={500}
                                style={q.reference_resource_id ? { cursor: 'pointer', transition: 'color 0.2s' } : {}} 
                                onMouseEnter={(e) => { if (q.reference_resource_id) e.currentTarget.style.color = 'var(--mantine-color-blue-6)'; }}
                                onMouseLeave={(e) => { if (q.reference_resource_id) e.currentTarget.style.color = 'var(--mantine-color-dimmed)'; }}
                                onClick={() => {
                                  if (q.reference_resource_id) {
                                    let url = `/resource/${q.reference_resource_id}`;
                                    if (q.reference_chunk_position !== undefined && q.reference_chunk_position !== null) {
                                      url += `?ref=${q.reference_chunk_position}`;
                                    } else if (q.reference_quote) {
                                      url += `?highlight=${encodeURIComponent(q.reference_quote)}`;
                                    }
                                    window.open(url, '_blank');
                                  }
                                }}
                              >
                                {q.reference_resource_title}
                              </Text>
                            )}
                          </Group>
                          {totalMarks > 0 && (
                            <Badge 
                              size="xs" 
                              variant="light" 
                              color={grade?.total_awarded !== undefined ? (grade.total_awarded >= totalMarks ? "teal" : (grade.total_awarded > 0 ? "yellow" : "red")) : "blue"} 
                              radius="sm" 
                              ml="xs"
                              style={{ flexShrink: 0 }}
                            >
                              {grade?.total_awarded !== undefined ? `${grade.total_awarded} / ` : ''}{totalMarks} {totalMarks === 1 ? 'mark' : 'marks'}
                            </Badge>
                          )}
                        </Group>
                        <Group justify="space-between" align="flex-start" mb="sm" wrap="nowrap">
                          <Box style={{ flex: 1, minWidth: 0 }}>
                            <Box fw={600} size="lg">
                              <Text component="span" fw={600} size="lg">{idx + 1}. </Text>
                              <HtmlContent html={q.question_text} style={{ display: 'inline' }} />
                            </Box>
                          </Box>
                        </Group>

                        {q.sub_parts?.length > 0 && (
                          <Box ml="lg" mt="sm" style={{borderLeft: '2px solid var(--mantine-color-gray-2)', paddingLeft: 16}}>
                            {q.sub_parts.map(sp => (
                              <SubPartRenderer
                                key={sp.id}
                                part={sp}
                                userAnswers={userAnswers}
                                setUserAnswers={setUserAnswers}
                                gradingResults={gradingResults}
                                gradingLoading={gradingLoading}
                                handleGrade={handleGrade}
                                handleResetQuestion={handleResetQuestion}
                                isInteractive={isInteractive}
                                isExam={isExam}
                                examActive={examActive}
                                hasGraded={hasGraded}
                                viewMode={viewMode}
                                showAns={showAns}
                                explanations={explanations}
                                explainLoading={explainLoading}
                                handleExplain={handleExplain}
                                showExplanations={showExplanations}
                                setShowExplanations={setShowExplanations}
                                revealedAnswers={revealedAnswers}
                                toggleReveal={toggleReveal}
                                depth={0}
                              />
                            ))}
                          </Box>
                        )}



                        {isInteractive ? (
                          <Box mt="md">
                            {!q.sub_parts?.length && (
                              <>
                            {parsedOptions.length > 0 ? (
                               <Radio.Group
                                 value={userAnswers[q.id] || ''}
                                 onChange={(v) => setUserAnswers({...userAnswers, [q.id]: v})}
                               >
                                 <Stack mt="xs">
                                   {parsedOptions.map((opt, i) => (
                                     <Radio key={i} value={opt} label={opt} disabled={hasGraded || (isExam && !examActive)} />
                                   ))}
                                 </Stack>
                               </Radio.Group>
                            ) : (
                              <Textarea 
                                placeholder="Type your answer here..."
                                value={userAnswers[q.id] || ''}
                                onChange={(e) => setUserAnswers({...userAnswers, [q.id]: e.currentTarget.value})}
                                minRows={2}
                                disabled={hasGraded || (isExam && !examActive)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    if (userAnswers[q.id]) {
                                      handleGrade(q.id);
                                    }
                                  }
                                }}
                                autosize
                                minRows={2}
                              />
                            )}
                            
                            {!isExam && (
                              <Group mt="md">
                                {!hasGraded ? (
                                  <Button 
                                    loading={gradingLoading[q.id]} 
                                    onClick={() => handleGrade(q.id)}
                                    disabled={!userAnswers[q.id]}
                                  >
                                    Check Answer
                                  </Button>
                                ) : (
                                  <>
                                    <Button variant="light" color="gray" onClick={() => handleResetQuestion(q.id)} leftSection={<IconRefresh size={16} />}>
                                      Reset
                                    </Button>
                                    {!explanation && (
                                      <Button variant="light" loading={explainLoading[q.id]} onClick={() => handleExplain(q.id)} leftSection={<IconBulb size={16} />}>
                                        Ask AI to Explain
                                      </Button>
                                    )}
                                    {explanation && !showExplanations[q.id] && (
                                      <Button variant="light" onClick={() => setShowExplanations(prev => ({...prev, [q.id]: true}))} leftSection={<IconBulb size={16} />}>
                                        Show AI Explanation
                                      </Button>
                                    )}
                                  </>
                                )}
                              </Group>
                            )}

                            {hasGraded && (
                              <Box mt="md">
                                <GradeDisplay grade={grade} correctAnswer={q.answer_text} />
                              </Box>
                            )}
                            
                            {explanation && showExplanations[q.id] && (
                              <Paper mt="md" p="md" bg="var(--mantine-color-white)" radius="sm" withBorder>
                                {explainLoading[q.id] ? (
                                  <Group gap="xs"><Loader size="xs" color="grape" /><Text size="sm" c="dimmed">Regenerating explanation...</Text></Group>
                                ) : (
                                  <>
                                    <Group justify="space-between" align="center" wrap="nowrap" mb={8}>
                                      <Text size="sm"><IconBulb size={14} style={{ marginRight: 5, verticalAlign: 'middle', color: 'var(--mantine-color-grape-6)' }}/><b>Explanation</b></Text>
                                      <Menu position="bottom-end" shadow="sm">
                                        <Menu.Target>
                                          <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => e.stopPropagation()}>
                                            <IconDotsVertical size={14} />
                                          </ActionIcon>
                                        </Menu.Target>
                                        <Menu.Dropdown>
                                          <Menu.Item leftSection={<IconRefresh size={14} />} onClick={(e) => { e.stopPropagation(); handleExplain(q.id); }}>
                                            Regenerate Explanation
                                          </Menu.Item>
                                          <Menu.Item leftSection={<IconEyeOff size={14} />} onClick={(e) => { e.stopPropagation(); setShowExplanations(prev => ({ ...prev, [q.id]: false })); }}>
                                            Hide Explanation
                                          </Menu.Item>
                                          <Menu.Item leftSection={<IconMessageDots size={14} />} onClick={(e) => { e.stopPropagation(); sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, 'Can you elaborate on this explanation?'); }}>
                                            Ask Follow-up
                                          </Menu.Item>
                                          <Menu.Divider />
                                          <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => { e.stopPropagation(); handleDeleteExplanation(q.id); }}>
                                            Delete Explanation
                                          </Menu.Item>
                                        </Menu.Dropdown>
                                      </Menu>
                                    </Group>
                                    <Box className="markdown-content" size="sm">
                                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{explanation}</ReactMarkdown>
                                    </Box>
                                    <Group mt="sm" gap="xs" wrap="nowrap">
                                      <TextInput
                                        placeholder="Ask a follow-up question..."
                                        size="xs"
                                        style={{ flex: 1 }}
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter') {
                                            const val = e.currentTarget.value.trim();
                                            if (val) {
                                              e.currentTarget.value = '';
                                              sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, val);
                                            }
                                          }
                                        }}
                                      />
                                      <Button size="xs" variant="light" onClick={(e) => {
                                        const input = e.currentTarget.parentElement?.querySelector('input');
                                        if (input && input.value.trim()) {
                                          const val = input.value.trim();
                                          input.value = '';
                                          sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, val);
                                        }
                                      }}>Ask</Button>
                                    </Group>
                                  </>
                                )}
                              </Paper>
                            )}
                            </>
                            )}
                          </Box>
                        ) : (
                          <Box mt="md">
                            {!q.sub_parts?.length && (showAns || viewMode === 'hide') && (
                              <Box>
                                <Paper 
                                  p="md" 
                                  bg="var(--mantine-color-blue-0)" 
                                  radius="sm"
                                  style={{
                                    cursor: !showAns ? 'pointer' : 'default',
                                    position: 'relative',
                                    overflow: 'hidden',
                                    transition: 'all 0.2s ease'
                                  }}
                                  onClick={() => {
                                    if (!showAns && viewMode === 'hide') {
                                      toggleReveal(q.id);
                                    }
                                  }}
                                >
                                  {!showAns && (
                                    <Center style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 10, background: 'rgba(231, 245, 255, 0.3)' }}>
                                      <Badge size="lg" variant="light" style={{ pointerEvents: 'none' }}>
                                        Click to reveal answer
                                      </Badge>
                                    </Center>
                                  )}
                                  <Box style={{ filter: !showAns ? 'blur(6px)' : 'none', opacity: !showAns ? 0.5 : 1, transition: 'all 0.35s ease', userSelect: !showAns ? 'none' : 'auto', pointerEvents: !showAns ? 'none' : 'auto' }}>
                                    <Text fw={500} c="blue.9">Answer:</Text>
                                    <Box c="blue.9"><HtmlContent html={q.answer_text || "No answer provided."} /></Box>
                                    
                                      <Box mt="md">
                                        {explanation && showExplanations[q.id] && (
                                          <Paper p="md" bg="var(--mantine-color-white)" radius="sm" mb="sm">
                                            {explainLoading[q.id] ? (
                                              <Group gap="xs"><Loader size="xs" color="grape" /><Text size="sm" c="dimmed">Regenerating explanation...</Text></Group>
                                            ) : (
                                              <>
                                                <Group justify="space-between" align="center" wrap="nowrap" mb={8}>
                                                  <Text size="sm"><IconBulb size={14} style={{ marginRight: 5, verticalAlign: 'middle', color: 'var(--mantine-color-grape-6)' }}/><b>Explanation</b></Text>
                                                  <Menu position="bottom-end" shadow="sm">
                                                    <Menu.Target>
                                                      <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => e.stopPropagation()}>
                                                        <IconDotsVertical size={14} />
                                                      </ActionIcon>
                                                    </Menu.Target>
                                                    <Menu.Dropdown>
                                                      <Menu.Item leftSection={<IconRefresh size={14} />} onClick={(e) => { e.stopPropagation(); handleExplain(q.id); }}>
                                                        Regenerate
                                                      </Menu.Item>
                                                      <Menu.Item leftSection={<IconEyeOff size={14} />} onClick={(e) => { e.stopPropagation(); setShowExplanations(prev => ({ ...prev, [q.id]: false })); }}>
                                                        Hide
                                                      </Menu.Item>
                                          <Menu.Item leftSection={<IconMessageDots size={14} />} onClick={(e) => { e.stopPropagation(); sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, 'Can you elaborate on this explanation?'); }}>
                                                        Ask Follow-up
                                                      </Menu.Item>
                                                      <Menu.Divider />
                                                      <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => { e.stopPropagation(); handleDeleteExplanation(q.id); }}>
                                                        Delete
                                                      </Menu.Item>
                                                    </Menu.Dropdown>
                                                  </Menu>
                                                </Group>
                                                <Box className="markdown-content" size="sm">
                                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{explanation}</ReactMarkdown>
                                                </Box>
                                                <Group mt="sm" gap="xs" wrap="nowrap">
                                                  <TextInput
                                                    placeholder="Ask a follow-up question..."
                                                    size="xs"
                                                    style={{ flex: 1 }}
                                                    onKeyDown={(e) => {
                                                      if (e.key === 'Enter') {
                                                        const val = e.currentTarget.value.trim();
                                                        if (val) {
                                                          e.currentTarget.value = '';
                                                          sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, val);
                                                        }
                                                      }
                                                    }}
                                                  />
                                                  <Button size="xs" variant="light" onClick={(e) => {
                                                    const input = e.currentTarget.parentElement?.querySelector('input');
                                                    if (input && input.value.trim()) {
                                                      const val = input.value.trim();
                                                      input.value = '';
                                                      sendExplanationFollowUp(q, explanation, userAnswers[q.id], grade?.correct_answer, val);
                                                    }
                                                  }}>Ask</Button>
                                                </Group>
                                              </>
                                            )}
                                          </Paper>
                                        )}
                                      
                                      <Group gap="xs" mt="xs">
                                        {explanation && !showExplanations[q.id] && (
                                          <Button size="xs" variant="light" onClick={(e) => { e.stopPropagation(); setShowExplanations(prev => ({ ...prev, [q.id]: true })); }} leftSection={<IconBulb size={14} />}>
                                            Show AI Explanation
                                          </Button>
                                        )}
                                        {!explanation && (
                                          <Button size="xs" variant="light" loading={explainLoading[q.id]} onClick={(e) => { e.stopPropagation(); handleExplain(q.id); }} leftSection={<IconBulb size={14} />}>
                                            Ask AI to Explain
                                          </Button>
                                        )}
                                        {viewMode === 'hide' && (
                                          <Button size="xs" variant="default" onClick={(e) => { e.stopPropagation(); toggleReveal(q.id); }} leftSection={showAns ? <IconEyeOff size={14} /> : <IconEye size={14} />}>
                                            {showAns ? "Re-hide Answer" : "Reveal Answer"}
                                          </Button>
                                        )}
                                      </Group>
                                    </Box>
                                  </Box>
                                </Paper>
                              </Box>
                            )}
                          </Box>
                        )}
                      </Card>
                    );
                  });
                })()
                )}

                {(() => {
                  const gradeEntries = Object.entries(gradingResults);
                  if (gradeEntries.length === 0 || viewMode === 'conversation') return null;
                  const totalMax = gradeEntries.reduce((s, [, g]) => s + ((g.total_max || (g.is_correct !== undefined ? 1 : 0))), 0);
                  const totalAwarded = gradeEntries.reduce((s, [, g]) => s + ((g.total_awarded !== undefined ? g.total_awarded : (g.is_correct ? 1 : 0))), 0);
                  const pct = totalMax > 0 ? Math.round((totalAwarded / totalMax) * 100) : 0;
                  return (
                    <Paper p="lg" withBorder mb="xl" radius="md" bg="gray.0">
                      <Group justify="space-between" wrap="nowrap">
                        <Box>
                          <Title order={4}>Score Summary</Title>
                          <Text size="xl" fw={700} mt={4}>{totalAwarded} / {totalMax}</Text>
                          <Text size="sm" c="dimmed">{exercise.questions?.length || 0} question{(exercise.questions?.length || 0) !== 1 ? 's' : ''}</Text>
                        </Box>
                        <RingProgress
                          size={90} thickness={10}
                          sections={[{ value: pct, color: pct === 100 ? 'green' : pct >= 50 ? 'blue' : 'red' }]}
                          label={<Text ta="center" size="sm" fw={700}>{pct}%</Text>}
                        />
                      </Group>
                    </Paper>
                  );
                })()}

                {!editMode && viewMode === 'interactive' && exercise.questions?.length > 0 && (
                  <Button size="lg" onClick={handleCheckAll} mb="xl">
                    Check All Answers
                  </Button>
                )}
                
                {!editMode && viewMode === 'exam' && exercise.questions?.length > 0 && examActive && (
                  <Button size="lg" color="red" onClick={handleSubmitExam} mb="xl">
                    Submit Exam
                  </Button>
                )}
              </Stack>
            )}
            </Box>
          </Container>
        </ScrollArea>
        {/* Removed Progress bar to prevent scroll-induced re-renders */}
      </Box>

        {/* Right Sidebar */}
        {!taskActive && (
        <Box w={sidebarOpen ? 280 : 80} visibleFrom="sm" style={{ borderLeft: '1px solid #eaeaea', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', transition: 'width 200ms ease, min-width 200ms ease', minWidth: sidebarOpen ? 280 : 80, overflow: 'hidden' }} p="md">
          <Box style={{ flex: 1, overflowY: 'auto' }}>
            {sidebarChatActive && sidebarOpen ? (
              showConvList ? (
                /* Conversation List View */
                <Box style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                  <Group mb="sm">
                    <ActionIcon variant="subtle" color="gray" size="sm" onClick={() => setShowConvList(false)}>
                      <IconArrowLeft size={16} />
                    </ActionIcon>
                    <Text fw={600} size="sm">Conversations</Text>
                  </Group>
                  <Divider mb="sm" />
                  <Box style={{ flex: 1, overflowY: 'auto' }}>
                    {exerciseConversations.length === 0 ? (
                      <Center h={100}>
                        <Text size="sm" c="dimmed">No past conversations</Text>
                      </Center>
                    ) : (
                      <Stack gap={2}>
                        {exerciseConversations.map((conv) => (
                          <Paper key={conv.conversation_id} p={6} radius="sm"
                            style={{
                              cursor: 'pointer',
                              backgroundColor: sidebarChatConversationId === conv.conversation_id ? '#eef2ff' : 'transparent',
                              border: sidebarChatConversationId === conv.conversation_id ? '1px solid #c7d2fe' : '1px solid transparent',
                              transition: 'all 0.2s'
                            }}
                            onClick={() => { setShowConvList(false); openSidebarChat(conv.conversation_id); }}
                          >
                            <Group justify="space-between" wrap="nowrap">
                              <Group gap="xs" style={{ flex: 1, overflow: 'hidden' }} wrap="nowrap">
                                {conv.is_pinned && <IconPinFilled size={12} style={{ flexShrink: 0, color: '#f59f00' }} />}
                                <Text size="sm" fw={sidebarChatConversationId === conv.conversation_id ? 600 : 500} lineClamp={1}>
                                  {conv.title}
                                </Text>
                              </Group>
                              <Menu shadow="md" width={150} position="bottom-end" withinPortal>
                                <Menu.Target>
                                  <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => e.stopPropagation()}>
                                    <IconDotsVertical size={16} />
                                  </ActionIcon>
                                </Menu.Target>
                                <Menu.Dropdown>
                                  <Menu.Item leftSection={<IconPencil size={14} />} onClick={(e) => { e.stopPropagation(); }}>
                                    Rename
                                  </Menu.Item>
                                  <Menu.Item leftSection={<IconPin size={14} />} onClick={(e) => { e.stopPropagation(); }}>
                                    {conv.is_pinned ? 'Unpin' : 'Pin'}
                                  </Menu.Item>
                                  <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => { e.stopPropagation(); }}>
                                    Delete
                                  </Menu.Item>
                                </Menu.Dropdown>
                              </Menu>
                            </Group>
                          </Paper>
                        ))}
                      </Stack>
                    )}
                  </Box>
                </Box>
              ) : (
              <Box style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <Group justify="space-between" mb="sm">
                  <Group gap={4}>
                    <ActionIcon variant="subtle" color="gray" size="sm" onClick={closeSidebarChat}>
                      <IconArrowLeft size={16} />
                    </ActionIcon>
                    <Text fw={600} size="sm">Quick Chat</Text>
                  </Group>
                  <Group gap={4}>
                    <ActionIcon variant="subtle" color="gray" size="sm" onClick={startNewSidebarChat}>
                      <IconPlus size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="gray" size="sm" onClick={loadExerciseConversations}>
                      <IconMessageDots size={16} />
                    </ActionIcon>
                  </Group>
                </Group>
                <Divider mb="sm" />
                <Box style={{ flex: 1, overflowY: 'auto' }} mb="sm" ref={sidebarChatRef}>
                  {sidebarChatMessages.length === 0 ? (
                    <Text size="sm" c="dimmed" ta="center" mt="xl">Ask a question about this exercise.</Text>
                  ) : (
                    <Stack spacing="md">
                      {sidebarChatMessages.map((m, i) => {
                        const hasSources = m.detailed_sources?.length > 0;
                        const isWebSearch = m.detailed_sources?.some(s => s.is_web);
                        const filteredSources = m.detailed_sources?.filter(s => s.is_web || s.score >= 30) || [];
                        const msgKey = m.id || i;
                        const activeTab = sidebarChatActiveTab[msgKey];
                        const refMatch = m.message?.match(/^\[referring to explanation: ([^\]]+)\]\n([\s\S]*)$/);
                        return (
                        <Box key={msgKey} mb="md">
                          <Group align="flex-start" justify="flex-end" wrap="nowrap">
                             <Paper p={refMatch ? 'sm' : 'md'} radius="xl" style={{ backgroundColor: '#171738', color: '#fff', maxWidth: '80%', borderBottomRightRadius: '4px' }}>
                              {refMatch ? (
                                <Box>
                                  <Box style={{
                                    borderLeft: '3px solid #6c757d',
                                    paddingLeft: 10,
                                    marginBottom: 4,
                                    fontSize: 12,
                                    color: '#adb5bd',
                                    lineHeight: 1.3
                                  }}>
                                    {refMatch[1]}
                                  </Box>
                                  <Text size="sm" style={{ lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{refMatch[2]}</Text>
                                </Box>
                              ) : (
                                <Box className="markdown-content" size="sm" style={{ color: '#fff', lineHeight: 1.6 }}>
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.message}</ReactMarkdown>
                                </Box>
                              )}
                            </Paper>
                          </Group>
                          {m.response && (
                            <Box mt="xs" style={{ width: '100%', fontSize: '14px', lineHeight: 1.5, color: '#171738' }}>
                              <Box className="markdown-content" style={{ fontSize: '14px', lineHeight: 1.5 }}>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.response}</ReactMarkdown>
                              </Box>
                              <Group gap="md" mt="xs" pt="xs" style={{ fontSize: '12px', color: '#888' }}>
                                {m.reasoning && (
                                  <Group gap={4} style={{ cursor: 'pointer' }} onClick={() => setSidebarChatActiveTab(prev => ({ ...prev, [msgKey]: activeTab === 'brain' ? null : 'brain' }))}>
                                    <IconBrain size={12} />
                                    <Text size="xs" fw={500}>{activeTab === 'brain' ? 'Hide Reasoning' : 'Show Reasoning'}</Text>
                                  </Group>
                                )}
                                {hasSources && (
                                  <Group gap={4} style={{ cursor: 'pointer' }} onClick={() => setSidebarChatActiveTab(prev => ({ ...prev, [msgKey]: activeTab === 'sources' ? null : 'sources' }))}>
                                    <IconFileText size={12} />
                                    <Text size="xs" fw={500}>Sources</Text>
                                  </Group>
                                )}
                                {m.id && (
                                  <Popover opened={sidebarChatRateOpened[msgKey]} onChange={(o) => setSidebarChatRateOpened(prev => ({ ...prev, [msgKey]: o }))} position="top" withArrow shadow="md">
                                    <Popover.Target>
                                      <Group gap={4} style={{ cursor: 'pointer' }} onClick={() => setSidebarChatRateOpened(prev => ({ ...prev, [msgKey]: !prev[msgKey] }))}>
                                        <IconStar size={12} />
                                        <Text size="xs" fw={500}>Rate</Text>
                                      </Group>
                                    </Popover.Target>
                                    <Popover.Dropdown>
                                      <Stack gap="xs">
                                        <Text size="xs" fw={500}>Rate this answer</Text>
                                        <Rating value={m.rating || 0} onChange={(val) => handleSidebarRate(m.id, val, msgKey)} size="sm" />
                                        <Textarea placeholder="Leave a comment..." size="xs" value={sidebarChatComment[msgKey] || ''} onChange={(e) => setSidebarChatComment(prev => ({ ...prev, [msgKey]: e.currentTarget.value }))} minRows={2} />
                                        <Button size="compact-xs" fullWidth onClick={() => handleSidebarRate(m.id, m.rating || 5, msgKey)}>Submit</Button>
                                      </Stack>
                                    </Popover.Dropdown>
                                  </Popover>
                                )}
                                <Group gap={4} style={{ cursor: 'pointer' }} onClick={() => setSidebarChatActiveTab(prev => ({ ...prev, [msgKey]: activeTab === 'info' ? null : 'info' }))}>
                                  <IconInfoCircle size={12} />
                                  <Text size="xs" fw={500}>Info</Text>
                                </Group>
                                <Group gap={4} style={{ cursor: 'pointer' }} onClick={() => { const prevMsg = sidebarChatMessages[i - 1]; if (prevMsg) sendSidebarChatMessage(prevMsg.message); }}>
                                  <IconRefresh size={12} />
                                  <Text size="xs" fw={500}>Retry</Text>
                                </Group>
                              </Group>
                              {activeTab === 'brain' && m.reasoning && (
                                <Box mt="xs" p="xs" bg="gray.0" style={{ borderRadius: 4, fontSize: '12px', color: '#666', lineHeight: 1.5 }}>
                                  <Text size="xs" fw={600} mb={4}><IconBrain size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Reasoning</Text>
                                  <Text size="xs">{m.reasoning}</Text>
                                </Box>
                              )}
                              {activeTab === 'info' && (
                                <Box mt="xs" p="xs" bg="gray.0" style={{ borderRadius: 4, fontSize: '12px' }}>
                                  <Text size="xs" fw={600} mb="xs" c="teal"><IconInfoCircle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Request Details</Text>
                                  {m.ai_mode && <Text size="xs" mb={2}><IconWand size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Mode: {modeLabels[m.ai_mode] || m.ai_mode}</Text>}
                                  {m.output_format && <Text size="xs" mb={2}><IconFileText size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Format: {formatLabels[m.output_format] || m.output_format}</Text>}
                                  {m.ai_model && <Text size="xs" mb={2}><IconRobot size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Model: {m.ai_model}</Text>}
                                  {m.timings?.total_ms && <Text size="xs"><IconClock size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Total: {Number(m.timings.total_ms).toFixed(0)}ms</Text>}
                                </Box>
                              )}
                              {activeTab === 'sources' && hasSources && (
                                <Box mt="xs">
                                  {isWebSearch && <Badge mb="xs" size="xs" leftSection={<IconWorld size={10}/>}>Included Web Search Results</Badge>}
                                  <Stack spacing="xs">
                                    {filteredSources.map((src, idx) => (
                                      <Paper key={idx} p="xs" withBorder bg="white" style={{ cursor: 'pointer' }}
                                        onClick={() => { if (src.is_web && src.url) window.open(src.url, '_blank'); }}>
                                        {src.is_web ? (
                                          <Box>
                                            <Text size="xs" fw={600}><IconWorld size={10} style={{ verticalAlign: 'middle', marginRight: 4 }}/> [{idx + 1}] Web Reference</Text>
                                            <Text size="xs" c="dimmed" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{src.url}</Text>
                                          </Box>
                                        ) : (
                                          <Box>
                                            <Text size="xs" fw={600}><IconFileText size={10} style={{ verticalAlign: 'middle', marginRight: 4 }}/> [{idx + 1}] Reference ({src.score}% match)</Text>
                                            <Text size="xs" c="dimmed">"{src.text_preview}"</Text>
                                          </Box>
                                        )}
                                      </Paper>
                                    ))}
                                  </Stack>
                                </Box>
                              )}
                            </Box>
                          )}
                        </Box>
                      );})}
                      {sidebarChatLoading && (
                        <Group gap="xs">
                          <Loader size="xs" type="dots" />
                          <Text size="sm" c="dimmed" style={{ fontStyle: 'italic' }}>Thinking...</Text>
                        </Group>
                      )}
                    </Stack>
                  )}
                </Box>
                {sidebarSettingsOpen ? (
                  <Box mb="xs">
                    <Text size="xs" fw={600} c="dimmed" mb={4}>AI Mode</Text>
                    <Group gap={4} mb="xs" wrap="wrap">
                      {['quick', 'simple', 'normal', 'elaborate', 'eli5'].map(mode => (
                        <Badge key={mode} component="button" onClick={() => { setSidebarAiMode(mode); setSidebarSettingsOpen(false); }}
                          variant={sidebarAiMode === mode ? "filled" : "light"} size="sm" fw={600}
                          style={{ cursor: 'pointer' }} tt="none"
                          leftSection={modeIcons[mode]}>
                          {modeLabels[mode]}
                        </Badge>
                      ))}
                    </Group>
                    <Text size="xs" fw={600} c="dimmed" mb={4}>Output Format</Text>
                    <Group gap={4} mb="xs" wrap="wrap">
                      {['sentence', 'pointform', 'numbered_list', 'table', 'mix'].map(fmt => (
                        <Badge key={fmt} color="teal" component="button" onClick={() => { setSidebarOutputFormat(fmt); setSidebarSettingsOpen(false); }}
                          variant={sidebarOutputFormat === fmt ? "filled" : "light"} size="sm" fw={600}
                          style={{ cursor: 'pointer' }} tt="none"
                          leftSection={formatIcons[fmt]}>
                          {formatLabels[fmt]}
                        </Badge>
                      ))}
                    </Group>
                  </Box>
                ) : (
                  <Group gap={4} mb="xs" wrap="wrap">
                    <Badge variant="light" size="sm" fw={600} tt="none"
                      style={{ cursor: 'pointer' }} onClick={() => setSidebarSettingsOpen(true)}
                      leftSection={modeIcons[sidebarAiMode]}>
                      {modeLabels[sidebarAiMode]}
                    </Badge>
                    <Badge color="teal" variant="light" size="sm" fw={600} tt="none"
                      style={{ cursor: 'pointer' }} onClick={() => setSidebarSettingsOpen(true)}
                      leftSection={formatIcons[sidebarOutputFormat]}>
                      {formatLabels[sidebarOutputFormat]}
                    </Badge>
                  </Group>
                )}
                <Group gap={4} align="stretch">
                  <Textarea
                    placeholder="Ask a follow-up..."
                    value={sidebarChatInput}
                    onChange={(e) => setSidebarChatInput(e.currentTarget.value)}
                    minRows={1}
                    maxRows={3}
                    style={{ flex: 1 }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendSidebarChatMessage();
                      }
                    }}
                    disabled={sidebarChatLoading}
                  />
                  <ActionIcon variant="filled" color="blue"
                    onClick={sendSidebarChatMessage}
                    disabled={!sidebarChatInput.trim() || sidebarChatLoading}
                    loading={sidebarChatLoading}
                    style={{ height: '100%', width: 36, minHeight: 36 }}
                  >
                    <IconSend size={16} />
                  </ActionIcon>
                </Group>
              </Box>
              )
            ) : (
              <Stack gap={0} align="stretch">
              {sidebarOpen && (
                <Box mb="md">
                  <Title order={5} fw={600} c="dimmed" mb="xs">Exercise Info</Title>
                  <Card p="sm" radius="md" withBorder bg="var(--mantine-color-gray-0)" mb="md">
                    <Stack gap="xs">
                      <Group justify="space-between" wrap="nowrap">
                        <Text size="xs" fw={600} c="dimmed">Type</Text>
                        <Badge size="xs" color={isAiGenerated ? 'blue' : 'green'} variant="light">
                          {isAiGenerated ? 'AI Generated' : 'Imported'}
                        </Badge>
                      </Group>
                      
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
                                onClick={() => res.id && window.open(`/resource/${res.id}`, '_blank')}
                              >
                                • {res.title}
                              </Text>
                            ))}
                          </Stack>
                        ) : (
                          <Text size="xs" c="dimmed" fs="italic">No resources linked</Text>
                        )}
                      </Box>
                      
                      {detectedQuestionTypes.length > 0 && (
                        <>
                          <Divider my={4} />
                          <Group justify="space-between" wrap="nowrap">
                            <Text size="xs" fw={600} c="dimmed">Question Types</Text>
                            <Text size="xs" fw={500} ta="right">
                              {detectedQuestionTypes.join(', ')}
                            </Text>
                          </Group>
                        </>
                      )}

                      {exercise.questions?.length > 0 && (
                        <Group justify="space-between" wrap="nowrap">
                          <Text size="xs" fw={600} c="dimmed">Questions</Text>
                          <Text size="xs" fw={500}>
                            {exercise.questions.length}
                          </Text>
                        </Group>
                      )}

                      {exercise.questions?.length > 0 && (() => {
                        const totalMarks = exercise.questions.reduce((s, q) => s + (q.max_marks || (q.sub_parts?.reduce((ss, sp) => ss + (sp.max_marks || 0), 0) || 1)), 0);
                        return (
                          <Group justify="space-between" wrap="nowrap">
                            <Text size="xs" fw={600} c="dimmed">Total Marks</Text>
                            <Text size="xs" fw={500}>{totalMarks}</Text>
                          </Group>
                        );
                      })()}

                      {Object.keys(gradingResults).length > 0 && (() => {
                        const entries = Object.entries(gradingResults);
                        const totalMax = entries.reduce((s, [, g]) => s + ((g.total_max || (g.is_correct !== undefined ? 1 : 0))), 0);
                        const totalAwarded = entries.reduce((s, [, g]) => s + ((g.total_awarded !== undefined ? g.total_awarded : (g.is_correct ? 1 : 0))), 0);
                        const pct = totalMax > 0 ? Math.round((totalAwarded / totalMax) * 100) : 0;
                        return (
                          <>
                            <Divider my={4} />
                            <Group justify="space-between" wrap="nowrap">
                              <Text size="xs" fw={600} c="dimmed">Session Score</Text>
                              <Text size="xs" fw={700}>{totalAwarded}/{totalMax}</Text>
                            </Group>
                            <Group justify="space-between" wrap="nowrap">
                              <Text size="xs" fw={600} c="dimmed">Percentage</Text>
                              <Text size="xs" fw={700} c={pct >= 80 ? 'green' : pct >= 50 ? 'yellow' : 'red'}>{pct}%</Text>
                            </Group>
                          </>
                        );
                      })()}
                    </Stack>
                  </Card>
                </Box>
              )}

              {sidebarOpen && <Title order={5} fw={600} c="dimmed" mb="xs">Smart Actions</Title>}

              {!editMode ? (
                <>
                  <Tooltip label="Edit Questions" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Edit Questions" : ""}
                      leftSection={<IconPencil size="1.2rem" stroke={1.5} />}
                      onClick={() => setEditMode(true)}
                    />
                  </Tooltip>

                  <Tooltip label="Quick Chat" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Quick Chat" : ""}
                      leftSection={<IconMessageDots size="1.2rem" stroke={1.5} color="var(--mantine-color-grape-6)" />}
                      onClick={() => openSidebarChat()}
                    />
                  </Tooltip>

                  <Tooltip label="Reset Exercise" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Reset Exercise" : ""}
                      leftSection={<IconRefresh size="1.2rem" stroke={1.5} color="var(--mantine-color-orange-6)" />}
                      onClick={handleResetExercise}
                    />
                  </Tooltip>

                  {questionOrder === 'original' ? (
                    <Tooltip label="Randomize Question Order" disabled={sidebarOpen} position="left">
                      <MantineNavLink
                        label={sidebarOpen ? "Randomize Order" : ""}
                        leftSection={<IconArrowsShuffle size="1.2rem" stroke={1.5} />}
                        onClick={shuffleQuestions}
                      />
                    </Tooltip>
                  ) : (
                    <Tooltip label="Restore Original Order" disabled={sidebarOpen} position="left">
                      <MantineNavLink
                        label={sidebarOpen ? "Restore Order" : ""}
                        leftSection={<IconSortAscending size="1.2rem" stroke={1.5} color="var(--mantine-color-blue-6)" />}
                        onClick={restoreQuestionOrder}
                      />
                    </Tooltip>
                  )}

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
                      <Menu.Item leftSection={<IconFileTypePdf size={14} color="red" />} onClick={() => handleExport('pdf')}>
                        Export as PDF
                      </Menu.Item>
                      <Menu.Item leftSection={<IconFileTypeDocx size={14} />} onClick={() => handleExport('docx')}>
                        Export as DOCX
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>

                  {sidebarOpen && (
                    <Box mt="md">
                      <Divider my="sm" />
                      <Text fw={500} size="sm" mb="xs">View Mode</Text>
                      <SegmentedControl
                        orientation="vertical"
                        fullWidth
                        value={viewMode}
                        onChange={(v) => {
                          navigate(`/exercises/${id}/${modeToUrl[v]}`);
                        }}
                        data={[
                          { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEyeOff size={16} stroke={1.5} /><Text size="sm">Hide Answers</Text></Group>, value: 'hide' },
                          { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEye size={16} stroke={1.5} /><Text size="sm">Show All Answers</Text></Group>, value: 'show' },
                          { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEdit size={16} stroke={1.5} /><Text size="sm">Interactive</Text></Group>, value: 'interactive' },
                          { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconClock size={16} stroke={1.5} /><Text size="sm">Exam Mode</Text></Group>, value: 'exam' },
                          { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconMessageDots size={16} stroke={1.5} /><Text size="sm">Conversation</Text></Group>, value: 'conversation' }
                        ]}
                      />
                    </Box>
                  )}

                  {sidebarOpen && viewMode === 'exam' && (
                    <Box mt="md">
                      <Divider my="sm" />
                      <Text fw={500} size="sm" mb="xs">Exam Settings</Text>
                      <NumberInput 
                        label="Time Limit (Minutes)" 
                        value={examTimerMinutes} 
                        onChange={setExamTimerMinutes} 
                        min={1} 
                        max={120} 
                        disabled={examActive}
                      />
                      {!examActive ? (
                        <Button fullWidth mt="md" onClick={handleStartExam}>
                          Start Exam
                        </Button>
                      ) : (
                        <Button fullWidth mt="md" color="red" variant="light" onClick={() => {
                          setExamActive(false);
                          clearInterval(timerRef.current);
                        }}>
                          Cancel Exam
                        </Button>
                      )}
                    </Box>
                  )}

                  {sidebarOpen && (
                    <Box mt="md">
                      <Divider my="sm" />
                      <Text fw={500} size="sm" mb="xs">Recent Activity</Text>
                      {(() => {
                        const questions = exercise.questions || [];
                        const answeredQuestions = questions
                          .map((q, idx) => ({
                            q,
                            idx,
                            hasAnswer: !!userAnswers[q.id],
                            grade: gradingResults[q.id],
                            answerTime: answerTimestamps[q.id] || 0,
                          }))
                          .filter(a => a.hasAnswer || a.grade)
                          .sort((a, b) => (b.answerTime || 0) - (a.answerTime || 0))
                          .slice(0, 5);
                        if (answeredQuestions.length === 0) {
                          return <Text size="xs" c="dimmed" fs="italic">No questions attempted yet.</Text>;
                        }
                        return answeredQuestions.map(({ q, idx, hasAnswer, grade }) => {
                          let statusColor = 'gray';
                          let statusLabel = '';
                          if (grade) {
                            const awarded = grade.total_awarded !== undefined ? grade.total_awarded : (grade.is_correct ? 1 : 0);
                            const maxM = grade.total_max !== undefined ? grade.total_max : 1;
                            statusColor = awarded === maxM ? 'green' : awarded > 0 ? 'yellow' : 'red';
                            statusLabel = `${awarded}/${maxM}`;
                          } else if (hasAnswer) {
                            statusColor = 'yellow';
                            statusLabel = 'Pending';
                          }
                          return (
                            <Paper
                              key={q.id}
                              p="xs"
                              withBorder
                              bg="white"
                              mb={4}
                              style={{ cursor: 'pointer' }}
                              onClick={() => {
                                setHistoryModalQuestion({ ...q, idx, userAnswer: userAnswers[q.id], grade });
                                setHistoryModalOpened(true);
                              }}
                            >
                              <Group justify="space-between" wrap="nowrap">
                                <Text size="xs" lineClamp={1} style={{ flex: 1 }}>Q{idx + 1}. {q.question_text}</Text>
                                {statusLabel && <Badge size="xs" color={statusColor} variant="light">{statusLabel}</Badge>}
                              </Group>
                            </Paper>
                          );
                        });
                      })()}
                    </Box>
                  )}
                </>
              ) : (
                <>
                  {sidebarOpen && <Box mt="md" mb="xs" px="sm"><Text size="xs" fw={600} c="dimmed" tt="uppercase">Actions</Text></Box>}
                  <Tooltip label="Save Changes" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Save Changes" : ""}
                      leftSection={<IconDeviceFloppy size="1.2rem" stroke={1.5} color="var(--mantine-color-blue-6)" />}
                      onClick={handleSaveEdits}
                    />
                  </Tooltip>
                  <Tooltip label="Cancel Edit" disabled={sidebarOpen} position="left">
                    <MantineNavLink
                      label={sidebarOpen ? "Cancel Edit" : ""}
                      leftSection={<IconX size="1.2rem" stroke={1.5} color="var(--mantine-color-red-6)" />}
                      onClick={() => setEditMode(false)}
                    />
                  </Tooltip>
                </>
              )}
            </Stack>
            )}
          </Box>
          <Box mt="auto" pt="sm">
            <Tooltip label={sidebarOpen ? "Hide Sidebar" : "Show Sidebar"} position="left">
              <ActionIcon variant="subtle" color="gray" size="lg" onClick={() => setSidebarOpen(!sidebarOpen)}>
                {sidebarOpen ? <IconLayoutSidebarRightCollapse size={20} /> : <IconLayoutSidebarRightExpand size={20} />}
              </ActionIcon>
            </Tooltip>
          </Box>
        </Box>
        )}
      </Box>

      <Modal
        opened={showTimeUpModal}
        onClose={() => {}}
        withCloseButton={false}
        closeOnClickOutside={false}
        closeOnEscape={false}
        title={<Text fw={700} size="lg" style={{ fontFamily: 'Instrument Sans, sans-serif' }}>Time's Up!</Text>}
        centered
        radius="md"
        padding="xl"
      >
        <Stack spacing="md" align="center">
          <IconClock size={48} color="var(--mantine-color-red-6)" stroke={1.5} />
          <Text size="sm" ta="center" c="dimmed">
            Your exam time has expired. Would you like to add more time or submit and grade your answers now?
          </Text>
          
          <Group grow style={{ width: '100%' }} mt="xs">
            <Button 
              variant="outline" 
              onClick={() => {
                setExamTimeRemaining(5 * 60);
                setExamActive(true);
                setShowTimeUpModal(false);
              }}
            >
              Add 5 Mins
            </Button>
            
            <Button 
              color="green" 
              onClick={() => {
                handleSubmitExam();
                setShowTimeUpModal(false);
              }}
            >
              Grade Now
            </Button>
          </Group>
          
          <Divider label="Or Custom Time" labelPosition="center" style={{ width: '100%' }} my="xs" />
          
          <Group align="flex-end" gap="xs" style={{ width: '100%' }}>
            <NumberInput 
              style={{ flex: 1 }}
              placeholder="Minutes"
              min={1}
              max={120}
              value={customMinutes}
              onChange={(val) => setCustomMinutes(val || 5)}
            />
            <Button 
              onClick={() => {
                setExamTimeRemaining((customMinutes || 5) * 60);
                setExamActive(true);
                setShowTimeUpModal(false);
              }}
            >
              Add Time
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* History Modal */}
      <Modal
        opened={historyModalOpened}
        onClose={() => setHistoryModalOpened(false)}
        title={<Text fw={700} size="lg">Question Review</Text>}
        size="lg"
        radius="md"
        padding="xl"
      >
        {historyModalQuestion && (
          <Stack spacing="md">
            <Box fw={600} size="lg">
              <Text component="span" fw={600} size="lg">Q{historyModalQuestion.idx + 1}. </Text>
              <HtmlContent html={historyModalQuestion.question_text} style={{ display: 'inline' }} />
            </Box>

            {historyModalQuestion.userAnswer ? (
              <Box>
                <Text fw={500} size="sm" c="dimmed">Your Answer:</Text>
                <Paper p="sm" bg="var(--mantine-color-gray-0)" radius="sm" withBorder>
                  <Text style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', whiteSpace: 'pre-wrap', fontSize: '13px' }}>{historyModalQuestion.userAnswer}</Text>
                </Paper>
              </Box>
            ) : (
              <Text size="sm" c="dimmed" fs="italic">You did not answer this question.</Text>
            )}

            <Box>
              <Text fw={500} size="sm" c="dimmed">Correct Answer:</Text>
              <Paper p="sm" bg="var(--mantine-color-blue-0)" radius="sm" withBorder>
                <HtmlContent html={historyModalQuestion.answer_text || "No answer provided."} />
              </Paper>
            </Box>

            {historyModalQuestion.grade && (
              <Box>
                <GradeDisplay grade={historyModalQuestion.grade} correctAnswer={historyModalQuestion.answer_text} />
              </Box>
            )}

            {(historyModalQuestion.explanation || explanations[historyModalQuestion.id]) && (
              <Box>
                <Text fw={500} size="sm" c="dimmed" mb={4}>Explanation:</Text>
                <Paper p="md" bg="var(--mantine-color-white)" radius="sm" withBorder>
                  <Box className="markdown-content">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {historyModalQuestion.explanation || explanations[historyModalQuestion.id]}
                    </ReactMarkdown>
                  </Box>
                </Paper>
              </Box>
            )}
          </Stack>
        )}
      </Modal>

      {/* Mobile Smart Actions Drawer */}
      <Drawer
        opened={mobileActionsOpened}
        onClose={closeMobileActions}
        title="Exercise"
        padding={0}
        size="85%"
        position="right"
        hiddenFrom="sm"
        zIndex={1000}
        styles={{ header: { padding: '16px' } }}
      >
        <Box style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <ScrollArea style={{ flex: 1 }} px="md">
            <Stack gap={0} align="stretch" py="sm">
              {/* Exercise Info */}
              <Card p="sm" radius="md" withBorder bg="var(--mantine-color-gray-0)" mb="md" mx="sm">
                <Stack gap="xs">
                  <Group justify="space-between" wrap="nowrap">
                    <Text size="xs" fw={600} c="dimmed">Type</Text>
                    <Badge size="xs" color={isAiGenerated ? 'blue' : 'green'} variant="light">
                      {isAiGenerated ? 'AI Generated' : 'Imported'}
                    </Badge>
                  </Group>
                  <Box>
                    <Text size="xs" fw={600} c="dimmed" mb={4}>Resources Covered</Text>
                    {coveredResources.length > 0 ? (
                      <Stack gap={4}>
                        {coveredResources.map((res, idx) => (
                          <Text key={idx} size="xs" c={res.id ? "blue.6" : "dark"} style={res.id ? { cursor: 'pointer', textDecoration: 'underline' } : {}} onClick={() => res.id && window.open(`/resource/${res.id}`, '_blank')}>
                            • {res.title}
                          </Text>
                        ))}
                      </Stack>
                    ) : (
                      <Text size="xs" c="dimmed" fs="italic">No resources linked</Text>
                    )}
                  </Box>
                  {detectedQuestionTypes.length > 0 && (
                    <>
                      <Divider my={4} />
                      <Group justify="space-between" wrap="nowrap">
                        <Text size="xs" fw={600} c="dimmed">Question Types</Text>
                        <Text size="xs" fw={500} ta="right">{detectedQuestionTypes.join(', ')}</Text>
                      </Group>
                    </>
                  )}
                  {exercise?.questions?.length > 0 && (
                    <Group justify="space-between" wrap="nowrap">
                      <Text size="xs" fw={600} c="dimmed">Questions</Text>
                      <Text size="xs" fw={500}>{exercise.questions.length}</Text>
                    </Group>
                  )}
                  {exercise?.questions?.length > 0 && (() => {
                    const totalMarks = exercise.questions.reduce((s, q) => s + (q.max_marks || (q.sub_parts?.reduce((ss, sp) => ss + (sp.max_marks || 0), 0) || 1)), 0);
                    return (
                      <Group justify="space-between" wrap="nowrap">
                        <Text size="xs" fw={600} c="dimmed">Total Marks</Text>
                        <Text size="xs" fw={500}>{totalMarks}</Text>
                      </Group>
                    );
                  })()}
                  {Object.keys(gradingResults).length > 0 && (() => {
                    const entries = Object.entries(gradingResults);
                    const totalMax = entries.reduce((s, [, g]) => s + ((g.total_max || (g.is_correct !== undefined ? 1 : 0))), 0);
                    const totalAwarded = entries.reduce((s, [, g]) => s + ((g.total_awarded !== undefined ? g.total_awarded : (g.is_correct ? 1 : 0))), 0);
                    const pct = totalMax > 0 ? Math.round((totalAwarded / totalMax) * 100) : 0;
                    return (
                      <>
                        <Divider my={4} />
                        <Group justify="space-between" wrap="nowrap">
                          <Text size="xs" fw={600} c="dimmed">Session Score</Text>
                          <Text size="xs" fw={700}>{totalAwarded}/{totalMax}</Text>
                        </Group>
                        <Group justify="space-between" wrap="nowrap">
                          <Text size="xs" fw={600} c="dimmed">Percentage</Text>
                          <Text size="xs" fw={700} c={pct >= 80 ? 'green' : pct >= 50 ? 'yellow' : 'red'}>{pct}%</Text>
                        </Group>
                      </>
                    );
                  })()}
                </Stack>
              </Card>

              {!editMode ? (
                <>
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="sm">Smart Actions</Text>
                  <MantineNavLink
                    label="Edit Questions"
                    leftSection={<IconPencil size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); setEditMode(true); }}
                  />
                  <MantineNavLink
                    label="Quick Chat"
                    leftSection={<IconMessageDots size="1.2rem" stroke={1.5} color="var(--mantine-color-grape-6)" />}
                    onClick={() => { closeMobileActions(); openSidebarChat(); }}
                  />
                  <MantineNavLink
                    label="Reset Exercise"
                    leftSection={<IconRefresh size="1.2rem" stroke={1.5} color="var(--mantine-color-orange-6)" />}
                    onClick={() => { closeMobileActions(); handleResetExercise(); }}
                  />
                  {questionOrder === 'original' ? (
                    <MantineNavLink
                      label="Randomize Order"
                      leftSection={<IconArrowsShuffle size="1.2rem" stroke={1.5} />}
                      onClick={() => { closeMobileActions(); shuffleQuestions(); }}
                    />
                  ) : (
                    <MantineNavLink
                      label="Restore Order"
                      leftSection={<IconSortAscending size="1.2rem" stroke={1.5} color="var(--mantine-color-blue-6)" />}
                      onClick={() => { closeMobileActions(); restoreQuestionOrder(); }}
                    />
                  )}
                  <Menu position="right-start" withArrow>
                    <Menu.Target>
                      <MantineNavLink
                        label="Export"
                        leftSection={<IconDownload size="1.2rem" stroke={1.5} />}
                      />
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item leftSection={<IconFileTypePdf size={14} color="red" />} onClick={() => { closeMobileActions(); handleExport('pdf'); }}>
                        Export as PDF
                      </Menu.Item>
                      <Menu.Item leftSection={<IconFileTypeDocx size={14} />} onClick={() => { closeMobileActions(); handleExport('docx'); }}>
                        Export as DOCX
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>

                  <Divider my="sm" mx="sm" />
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="sm">View Mode</Text>
                  <Box px="sm">
                    <SegmentedControl
                      orientation="vertical"
                      fullWidth
                      value={viewMode}
                      onChange={(v) => {
                        closeMobileActions();
                        navigate(`/exercises/${id}/${modeToUrl[v]}`);
                      }}
                      data={[
                        { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEyeOff size={16} stroke={1.5} /><Text size="sm">Hide Answers</Text></Group>, value: 'hide' },
                        { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEye size={16} stroke={1.5} /><Text size="sm">Show All Answers</Text></Group>, value: 'show' },
                        { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconEdit size={16} stroke={1.5} /><Text size="sm">Interactive</Text></Group>, value: 'interactive' },
                        { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconClock size={16} stroke={1.5} /><Text size="sm">Exam Mode</Text></Group>, value: 'exam' },
                        { label: <Group gap="xs" justify="flex-start" wrap="nowrap"><IconMessageDots size={16} stroke={1.5} /><Text size="sm">Conversation</Text></Group>, value: 'conversation' }
                      ]}
                    />
                  </Box>

                  {viewMode === 'exam' && (
                    <Box px="sm" mt="md">
                      <Divider my="sm" />
                      <Text fw={500} size="sm" mb="xs">Exam Settings</Text>
                      <NumberInput
                        label="Time Limit (Minutes)"
                        value={examTimerMinutes}
                        onChange={setExamTimerMinutes}
                        min={1}
                        max={120}
                        disabled={examActive}
                      />
                      {!examActive ? (
                        <Button fullWidth mt="md" onClick={() => { closeMobileActions(); handleStartExam(); }}>
                          Start Exam
                        </Button>
                      ) : (
                        <Button fullWidth mt="md" color="red" variant="light" onClick={() => { setExamActive(false); clearInterval(timerRef.current); }}>
                          Cancel Exam
                        </Button>
                      )}
                    </Box>
                  )}

                  <Divider my="sm" mx="sm" />
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="sm">Recent Activity</Text>
                  <Box px="sm">
                    {(() => {
                      const questions = exercise.questions || [];
                      const answeredQuestions = questions
                        .map((q, idx) => ({
                          q, idx,
                          hasAnswer: !!userAnswers[q.id],
                          grade: gradingResults[q.id],
                          answerTime: answerTimestamps[q.id] || 0,
                        }))
                        .filter(a => a.hasAnswer || a.grade)
                        .sort((a, b) => (b.answerTime || 0) - (a.answerTime || 0))
                        .slice(0, 5);
                      if (answeredQuestions.length === 0) {
                        return <Text size="xs" c="dimmed" fs="italic">No questions attempted yet.</Text>;
                      }
                      return answeredQuestions.map(({ q, idx, hasAnswer, grade }) => {
                        let statusColor = 'gray';
                        let statusLabel = '';
                        if (grade) {
                          const awarded = grade.total_awarded !== undefined ? grade.total_awarded : (grade.is_correct ? 1 : 0);
                          const maxM = grade.total_max !== undefined ? grade.total_max : 1;
                          statusColor = awarded === maxM ? 'green' : awarded > 0 ? 'yellow' : 'red';
                          statusLabel = `${awarded}/${maxM}`;
                        } else if (hasAnswer) {
                          statusColor = 'yellow';
                          statusLabel = 'Pending';
                        }
                        return (
                          <Paper
                            key={q.id}
                            p="xs"
                            withBorder
                            bg="white"
                            mb={4}
                            style={{ cursor: 'pointer' }}
                            onClick={() => {
                              closeMobileActions();
                              setHistoryModalQuestion({ ...q, idx, userAnswer: userAnswers[q.id], grade });
                              setHistoryModalOpened(true);
                            }}
                          >
                            <Group justify="space-between" wrap="nowrap">
                              <Text size="xs" lineClamp={1} style={{ flex: 1 }}>Q{idx + 1}. {q.question_text}</Text>
                              {statusLabel && <Badge size="xs" color={statusColor} variant="light">{statusLabel}</Badge>}
                            </Group>
                          </Paper>
                        );
                      });
                    })()}
                  </Box>
                </>
              ) : (
                <>
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="sm">Actions</Text>
                  <MantineNavLink
                    label="Save Changes"
                    leftSection={<IconDeviceFloppy size="1.2rem" stroke={1.5} color="var(--mantine-color-blue-6)" />}
                    onClick={() => { closeMobileActions(); handleSaveEdits(); }}
                  />
                  <MantineNavLink
                    label="Cancel Edit"
                    leftSection={<IconX size="1.2rem" stroke={1.5} color="var(--mantine-color-red-6)" />}
                    onClick={() => { closeMobileActions(); setEditMode(false); }}
                  />
                </>
              )}
            </Stack>
          </ScrollArea>
        </Box>
      </Drawer>
      <ProcessLoggerModal
        opened={showProcessLog}
        onClose={() => setShowProcessLog(false)}
        entityId={id}
        tasks={tasks}
      />
    </Box>
  );
}
