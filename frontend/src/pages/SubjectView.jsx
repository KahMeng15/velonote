import { useState, useEffect, useMemo, useRef } from 'react';
import { Box, Title, Text, Group, Card, Button, Badge, ActionIcon, Menu, Center, Loader, Stack, Modal, TextInput, Textarea, ColorInput, Select, Code, Anchor, Tabs, Checkbox, Progress, ScrollArea, Divider, MultiSelect, SegmentedControl, NumberInput, Collapse, Switch, Paper } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDotsVertical, IconTrash, IconPencil, IconUpload, IconEdit, IconFile, IconChevronLeft, IconSearch, IconArrowsSort, IconInfoCircle, IconRefresh, IconClipboardList, IconSparkles, IconBolt, IconWand, IconBrain, IconSchool, IconBabyCarriage, IconFileText, IconList, IconListNumbers, IconTable, IconLayersLinked, IconCpu, IconBinaryTree, IconPlus, IconUser, IconUserEdit, IconX, IconCheck, IconCopy } from '@tabler/icons-react';
import * as TablerIcons from '@tabler/icons-react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchApi, getAuthToken, notifyTaskStarted } from '../lib/api';
import { useTaskContext } from '../lib/TaskContext';
import { formatParams } from '../lib/formatters';
import ProcessLoggerModal from '../components/ProcessLoggerModal';

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
  
  const formattedName = 'Icon' + iconName.split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()).join('');
  if (TablerIcons[formattedName]) return TablerIcons[formattedName];
  
  return TablerIcons.IconFileText;
};

const getFriendlyFileType = (mimeType) => {
  if (!mimeType) return 'DOCUMENT';
  const type = mimeType.toLowerCase();
  if (type.includes('pdf')) return 'PDF';
  if (type.includes('presentation') || type.includes('powerpoint') || type.includes('pptx') || type.includes('presentationml')) return 'PowerPoint';
  if (type.includes('image') || type.includes('png') || type.includes('jpeg') || type.includes('jpg')) return 'Image';
  if (type.includes('word') || type.includes('docx') || type.includes('wordprocessingml') || type.includes('document')) return 'Word';
  if (type.includes('spreadsheet') || type.includes('excel') || type.includes('xlsx') || type.includes('spreadsheetml')) return 'Excel';
  
  const part = type.includes('/') ? type.split('/')[1] : type;
  if (part.includes('presentation')) return 'PowerPoint';
  if (part.includes('wordprocessingml') || part.includes('document')) return 'Word';
  if (part.includes('spreadsheetml')) return 'Excel';
  return part.toUpperCase();
};

const parseRanges = (str) => {
  const nums = new Set();
  const parts = str.split(',');
  for (let p of parts) {
    p = p.trim();
    if (p.includes('-')) {
      const [start, end] = p.split('-').map(Number);
      if (!isNaN(start) && !isNaN(end)) {
        for (let i = start; i <= end; i++) nums.add(i);
      }
    } else if (p.includes('–')) {
      const [start, end] = p.split('–').map(Number);
      if (!isNaN(start) && !isNaN(end)) {
        for (let i = start; i <= end; i++) nums.add(i);
      }
    } else {
      const n = Number(p);
      if (!isNaN(n)) nums.add(n);
    }
  }
  return Array.from(nums).sort((a, b) => a - b);
};

const getRangeString = (nums) => {
  if (nums.length === 0) return '';
  const ranges = [];
  let start = nums[0];
  let end = nums[0];
  for (let i = 1; i < nums.length; i++) {
    if (nums[i] === end + 1) {
      end = nums[i];
    } else {
      ranges.push(start === end ? `${start}` : `${start}-${end}`);
      start = nums[i];
      end = nums[i];
    }
  }
  ranges.push(start === end ? `${start}` : `${start}-${end}`);
  return ranges.join(', ');
};

const formatNoteDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '';
  const day = date.getDate();
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const month = monthNames[date.getMonth()];
  const year = date.getFullYear();
  return `${day} ${month} ${year}`;
};

export default function SubjectView() {
  const { id, tab } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  const [subject, setSubject] = useState(null);
  const subjectRef = useRef(null);
  subjectRef.current = subject;
  const [notes, setNotes] = useState([]);
  const [exercises, setExercises] = useState([]);
  const [generatedNotes, setGeneratedNotes] = useState([]);
  
  const [activeTab, setActiveTab] = useState(tab || 'resource');

  const [selectedResources, setSelectedResources] = useState([]);
  const [selectedExerciseNotes, setSelectedExerciseNotes] = useState([]);
  const [createNoteModalOpened, setCreateNoteModalOpened] = useState(false);
  
  const [createExerciseModalOpened, setCreateExerciseModalOpened] = useState(false);
  const [exerciseTitle, setExerciseTitle] = useState('');
  const [exerciseScope, setExerciseScope] = useState([]);
  const [exerciseQuestionTypes, setExerciseQuestionTypes] = useState(["Short answer", "Long answer", "Objective", "Fill in the blank"]);
  const [exerciseLengths, setExerciseLengths] = useState(["Short", "Medium", "Long"]);
  const [exerciseDifficulties, setExerciseDifficulties] = useState(["Easy", "Medium", "Hard"]);
  const [generatingExercise, setGeneratingExercise] = useState(false);

  const [exerciseNumQuestions, setExerciseNumQuestions] = useState(10);
  const [exerciseAdvanced, setExerciseAdvanced] = useState(false);
  const [exerciseEasy, setExerciseEasy] = useState(3);
  const [exerciseMedium, setExerciseMedium] = useState(4);
  const [exerciseHard, setExerciseHard] = useState(3);
  const [exerciseShort, setExerciseShort] = useState(4);
  const [exerciseMedLen, setExerciseMedLen] = useState(3);
  const [exerciseLong, setExerciseLong] = useState(3);
  const [exerciseTypeShort, setExerciseTypeShort] = useState(3);
  const [exerciseTypeLong, setExerciseTypeLong] = useState(3);
  const [exerciseTypeObj, setExerciseTypeObj] = useState(2);
  const [exerciseTypeFill, setExerciseTypeFill] = useState(2);

  useEffect(() => {
    if (exerciseNumQuestions > 0 && !exerciseAdvanced) {
      const q = exerciseNumQuestions;

      // Distribute difficulties
      const diffs = exerciseDifficulties.length > 0 ? exerciseDifficulties : ["Easy"];
      setExerciseEasy(diffs.includes("Easy") ? Math.floor(q / diffs.length) + (q % diffs.length > 0 ? 1 : 0) : 0);
      setExerciseMedium(diffs.includes("Medium") ? Math.floor(q / diffs.length) + (diffs.includes("Easy") ? (q % diffs.length > 1 ? 1 : 0) : (q % diffs.length > 0 ? 1 : 0)) : 0);
      setExerciseHard(diffs.includes("Hard") ? q - (diffs.includes("Easy") ? (Math.floor(q / diffs.length) + (q % diffs.length > 0 ? 1 : 0)) : 0) - (diffs.includes("Medium") ? (Math.floor(q / diffs.length) + (diffs.includes("Easy") ? (q % diffs.length > 1 ? 1 : 0) : (q % diffs.length > 0 ? 1 : 0))) : 0) : 0);
      
      // Simplify distribution logic by using a helper function
      const distribute = (options, mapping) => {
        const counts = {};
        options.forEach(o => counts[o] = 0);
        for(let i=0; i<q; i++) {
          if (options.length > 0) {
            counts[options[i % options.length]]++;
          }
        }
        return mapping.map(key => counts[key] || 0);
      };

      const [s, m, l] = distribute(exerciseLengths.length ? exerciseLengths : ["Short"], ["Short", "Medium", "Long"]);
      setExerciseShort(s); setExerciseMedLen(m); setExerciseLong(l);

      const [ts, tl, to, tf] = distribute(exerciseQuestionTypes.length ? exerciseQuestionTypes : ["Short answer"], ["Short answer", "Long answer", "Objective", "Fill in the blank"]);
      setExerciseTypeShort(ts); setExerciseTypeLong(tl); setExerciseTypeObj(to); setExerciseTypeFill(tf);
    }
  }, [exerciseNumQuestions, exerciseAdvanced, exerciseLengths, exerciseDifficulties, exerciseQuestionTypes]);

  const [noteMode, setNoteMode] = useState('elaborate');
  const [noteFormat, setNoteFormat] = useState('sentence');
  const [noteMethod, setNoteMethod] = useState('whole');
  const [noteCustomPrompt, setNoteCustomPrompt] = useState('');
  const [newNoteTitle, setNewNoteTitle] = useState('');
  const [generatingCombinedNote, setGeneratingCombinedNote] = useState(false);

  const [parameterType, setParameterType] = useState('multi'); // 'multi' or 'single'
  const [globalPrompts, setGlobalPrompts] = useState([]);
  const [selectedPromptId, setSelectedPromptId] = useState(null);
  const [userPrompts, setUserPrompts] = useState([]);
  const [createPromptModalOpened, setCreatePromptModalOpened] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [newPromptContent, setNewPromptContent] = useState('');
  const [savingNewPrompt, setSavingNewPrompt] = useState(false);
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

  const saveNewPrompt = async () => {
    if (!newPromptName.trim() || !newPromptContent.trim()) return;
    setSavingNewPrompt(true);
    try {
      const res = await fetchApi('/prompts', {
        method: 'POST',
        body: JSON.stringify({ name: newPromptName, content: newPromptContent })
      });
      if (res && res.id) {
        setUserPrompts(prev => [...prev, res]);
        setSelectedPromptId(`u_${res.id}`);
        setCreatePromptModalOpened(false);
        setNewPromptName('');
        setNewPromptContent('');
      }
    } catch (err) {
      console.error("Failed to save new prompt", err);
    } finally {
      setSavingNewPrompt(false);
    }
  };

  const generatePrompt = async () => {
    if (!newPromptInput.trim()) return;
    setGeneratingNewPrompt(true);
    try {
      const res = await fetchApi('/notes/generate-prompt', {
        method: 'POST',
        body: JSON.stringify({ user_input: newPromptInput })
      });
      if (res) {
        if (res.prompt) setNewPromptContent(res.prompt);
        if (res.name) setNewPromptName(res.name);
      }
    } catch (err) {
      console.error("Failed to generate prompt", err);
    } finally {
      setGeneratingNewPrompt(false);
    }
  };

  const handleCreateExercise = async () => {
    if (exerciseScope.length === 0) {
      showError("Selection Required", "Please select at least one resource or exercise.");
      return;
    }
    setGeneratingExercise(true);
    try {
      const resource_ids = exerciseScope.filter(id => !id.startsWith('ex_'));
      const exercise_ids = exerciseScope.filter(id => id.startsWith('ex_'));
      await fetchApi('/exercises/generate', {
        method: 'POST',
        body: JSON.stringify({
          subject_id: subject.id,
          resource_ids,
          exercise_ids,
          title: exerciseTitle,
          question_types: exerciseQuestionTypes,
          lengths: exerciseLengths,
          difficulties: exerciseDifficulties,
          num_questions: exerciseNumQuestions,
          advanced: exerciseAdvanced,
          distribution: {
            easy: exerciseEasy,
            medium: exerciseMedium,
            hard: exerciseHard,
            short: exerciseShort,
            medLen: exerciseMedLen,
            long: exerciseLong,
            typeShort: exerciseTypeShort,
            typeLong: exerciseTypeLong,
            typeObj: exerciseTypeObj,
            typeFill: exerciseTypeFill
          }
        })
      });
      notifyTaskStarted();
      setCreateExerciseModalOpened(false);
      setExerciseTitle('');
      setExerciseScope([]);
      window.location.reload(); // Refresh to show new background task
    } catch (e) {
      console.error(e);
      showError("Generation Failed", "Failed to generate exercise: " + e.message);
    } finally {
      setGeneratingExercise(false);
    }
  };

  const handleCreateNotes = async () => {
    if (selectedResources.length === 0 && selectedExerciseNotes.length === 0) return;
    setGeneratingCombinedNote(true);
    try {
      let bodyData = {
        resource_ids: selectedResources,
        exercise_ids: selectedExerciseNotes.length > 0 ? selectedExerciseNotes : undefined,
      };
      
      let finalPromptName = null;
      let finalPromptIcon = null;

      if (parameterType === 'single') {
        const gp = globalPrompts.find(p => `g_${p.id}` === selectedPromptId);
        const up = userPrompts.find(p => `u_${p.id}` === selectedPromptId);
        const name = gp ? gp.name : up ? up.name : 'Custom Note';
        const icon = gp ? gp.icon : up ? up.icon : 'IconFileText';
        const customPrompt = gp ? gp.content : up ? up.content : '';
        
        finalPromptName = name;
        finalPromptIcon = icon;
        bodyData = {
          ...bodyData,
          custom_prompt: customPrompt,
          prompt_name: name,
          prompt_icon: icon,
          mode: 'none',
          output_format: 'none',
        };
      } else {
        bodyData = {
          ...bodyData,
          mode: noteMode,
          output_format: noteFormat,
          processing_method: noteMethod,
          custom_prompt: noteCustomPrompt || undefined,
        };
      }

      let finalTitle = newNoteTitle.trim();
      if (!finalTitle) {
        let suffix = '';
        if (selectedResources.length > 0) {
          if (selectedResources.length === 1) {
            const resObj = notes.find(r => r.id === selectedResources[0]);
            suffix = resObj ? resObj.title : 'Note';
          } else {
            const labelSet = new Set();
            const allNums = new Set();
            let matchCount = 0;
            for (const id of selectedResources) {
              const resObj = notes.find(r => r.id === id);
              if (!resObj) continue;
              const match = resObj.title.match(/(Topic|Chapter|Lec|Lecture|Sec|Section)\s*(\d+(?:[-–,\s\d]+)*)/i);
              if (match) {
                labelSet.add(match[1].charAt(0).toUpperCase() + match[1].slice(1).toLowerCase());
                const parsed = parseRanges(match[2]);
                for (const n of parsed) allNums.add(n);
                matchCount++;
              }
            }
            
            if (labelSet.size === 1 && matchCount === selectedResources.length) {
              const label = Array.from(labelSet)[0];
              const sortedNums = Array.from(allNums).sort((a, b) => a - b);
              suffix = `${label} ${getRangeString(sortedNums)}`;
            } else {
              const resourcesOrdered = selectedResources.map(rid => notes.find(r => r.id === rid)).filter(Boolean);
              suffix = resourcesOrdered.slice(0, 3).map(r => r.title).join(', ');
              if (resourcesOrdered.length > 3) suffix += '...';
            }
          }
        } else if (selectedExerciseNotes.length > 0) {
          const exercisesOrdered = selectedExerciseNotes.map(eid => exercises.find(e => e.id === eid)).filter(Boolean);
          suffix = exercisesOrdered.slice(0, 3).map(e => e.title).join(', ');
          if (exercisesOrdered.length > 3) suffix += '...';
        } else {
          suffix = 'Note';
        }
        
        const parameterStr = parameterType === 'single'
          ? finalPromptName
          : formatParams(noteMode, noteFormat, noteMethod);
        
        finalTitle = `${parameterStr} - ${suffix}`;
      }

      bodyData.title = finalTitle;

      const res = await fetchApi('/notes/summary', {
        method: 'POST',
        body: JSON.stringify(bodyData)
      });
      notifyTaskStarted();
      
      if (res && res.task_id) {
        setPendingSummaryTasks(prev => ({ ...prev, [res.note_id]: res.task_id }));
        setActiveTab('notes');
        const placeholderNote = {
          id: res.note_id,
          version: 1,
          resource_id: selectedResources[0],
          note_id: selectedResources[0],
          title: finalTitle,
          summary_type: "summary",
          file_path: "",
          created_at: new Date().toISOString(),
          mode: parameterType === 'multi' ? noteMode : undefined,
          output_format: parameterType === 'multi' ? noteFormat : undefined,
          processing_method: parameterType === 'multi' ? noteMethod : undefined,
          prompt_name: parameterType === 'single' ? finalPromptName : undefined,
          prompt_icon: parameterType === 'single' ? finalPromptIcon : undefined,
          status: "pending"
        };
        setGeneratedNotes(prev => [placeholderNote, ...prev]);
      }
      
      setCreateNoteModalOpened(false);
      setSelectedResources([]);
      setSelectedExerciseNotes([]);
      setNewNoteTitle('');
    } catch (e) {
      alert("Failed to create notes: " + e.message);
    } finally {
      setGeneratingCombinedNote(false);
    }
  };

  useEffect(() => {
    if (tab && tab !== activeTab) {
      setActiveTab(tab);
    }
  }, [tab]);

  const handleTabChange = (val) => {
    setActiveTab(val);
    navigate(`/subject/${id}/${val}`);
  };
  const [selectedExercises, setSelectedExercises] = useState([]);
  const [merging, setMerging] = useState(false);

  const handleDownload = async (noteId, fileName) => {
    try {
      const token = getAuthToken();
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const response = await fetch(`/api/resources/${noteId}/download-file`, {
        headers
      });
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
    } catch (error) {
      console.error('Failed to download file:', error);
    }
  };
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState(
    localStorage.getItem('smartnotes_sort_pref') || 
    JSON.parse(localStorage.getItem('user') || '{}').sort_preference || 
    'name_asc'
  );

  useEffect(() => {
    fetchApi('/auth/me').then(data => {
      if (data && data.sort_preference) {
        setSort(data.sort_preference);
        localStorage.setItem('smartnotes_sort_pref', data.sort_preference);
      }
    }).catch(err => console.error("Failed to load user preferences", err));
  }, []);

  const filteredNotes = useMemo(() => {
    let result = [...notes];
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(n => 
        n.title.toLowerCase().includes(q) || 
        (n.file_name && n.file_name.toLowerCase().includes(q))
      );
    }
    
    result.sort((a, b) => {
      if (sort === 'name_asc') return a.title.localeCompare(b.title);
      if (sort === 'name_desc') return b.title.localeCompare(a.title);
      if (sort === 'date_desc') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      if (sort === 'date_asc') return new Date(a.created_at || 0) - new Date(b.created_at || 0);
      return 0;
    });
    
    return result;
  }, [notes, search, sort]);

  // Subject Edit Modals
  const [editSubjectModalOpened, { open: openEditSubjectModal, close: closeEditSubjectModal }] = useDisclosure(false);
  const [deleteSubjectModalOpened, { open: openDeleteSubjectModal, close: closeDeleteSubjectModal }] = useDisclosure(false);
  const [editSubjectName, setEditSubjectName] = useState('');
  const [editSubjectDesc, setEditSubjectDesc] = useState('');
  const [editSubjectColor, setEditSubjectColor] = useState('#593C8F');
  // Note Action Modals
  const [renameModalOpened, { open: openRenameModal, close: closeRenameModal }] = useDisclosure(false);
  const [deleteNoteModalOpened, { open: openDeleteNoteModal, close: closeDeleteNoteModal }] = useDisclosure(false);
  const [reprocessNoteModalOpened, { open: openReprocessNoteModal, close: closeReprocessNoteModal }] = useDisclosure(false);
  const [reprocessingNote, setReprocessingNote] = useState(null);
  const [reprocessUseAiPolish, setReprocessUseAiPolish] = useState(false);
  const [reprocessingNoteIds, setReprocessingNoteIds] = useState([]);
  const [exerciseProgress, setExerciseProgress] = useState({});
  const [failedExerciseIds, setFailedExerciseIds] = useState([]);
  const [completedExerciseIds, setCompletedExerciseIds] = useState([]);
  const [reprocessingExerciseIds, setReprocessingExerciseIds] = useState([]);
  const [generatedNoteProgress, setGeneratedNoteProgress] = useState({});
  const [failedGeneratedNoteIds, setFailedGeneratedNoteIds] = useState(() => JSON.parse(localStorage.getItem('failedGeneratedNoteIds') || '[]'));
  const [reprocessingGeneratedNoteIds, setReprocessingGeneratedNoteIds] = useState([]);
  // Maps summary id -> task_id for in-flight generations
  const [pendingSummaryTasks, setPendingSummaryTasks] = useState({});
  const [resourceTasks, setResourceTasks] = useState({});
  const [cancelledNoteIds, setCancelledNoteIds] = useState(() => JSON.parse(localStorage.getItem('cancelledNoteIds') || '[]'));
  const [cancelledGeneratedNoteIds, setCancelledGeneratedNoteIds] = useState(() => JSON.parse(localStorage.getItem('cancelledGeneratedNoteIds') || '[]'));
  
  const [exerciseTasks, setExerciseTasks] = useState({});
  const [cancelledExerciseIds, setCancelledExerciseIds] = useState(() => JSON.parse(localStorage.getItem('cancelledExerciseIds') || '[]'));

  useEffect(() => {
    localStorage.setItem('cancelledExerciseIds', JSON.stringify(cancelledExerciseIds));
  }, [cancelledExerciseIds]);
  useEffect(() => {
    localStorage.setItem('failedGeneratedNoteIds', JSON.stringify(failedGeneratedNoteIds));
  }, [failedGeneratedNoteIds]);

  useEffect(() => {
    localStorage.setItem('cancelledNoteIds', JSON.stringify(cancelledNoteIds));
  }, [cancelledNoteIds]);

  useEffect(() => {
    localStorage.setItem('cancelledGeneratedNoteIds', JSON.stringify(cancelledGeneratedNoteIds));
  }, [cancelledGeneratedNoteIds]);
  const [editingNote, setEditingNote] = useState(null);
  const [infoModalNote, setInfoModalNote] = useState(null);
  const [newTitle, setNewTitle] = useState('');
  const [deletingNote, setDeletingNote] = useState(null);

  const [renameExerciseModalOpened, { open: openRenameExerciseModal, close: closeRenameExerciseModal }] = useDisclosure(false);
  const [deleteExerciseModalOpened, { open: openDeleteExerciseModal, close: closeDeleteExerciseModal }] = useDisclosure(false);
  const [reprocessExerciseModalOpened, { open: openReprocessExerciseModal, close: closeReprocessExerciseModal }] = useDisclosure(false);
  const [mergeExerciseModalOpened, { open: openMergeExerciseModal, close: closeMergeExerciseModal }] = useDisclosure(false);
  
  const [editingExercise, setEditingExercise] = useState(null);
  const [newExerciseTitle, setNewExerciseTitle] = useState('');
  const [deletingExercise, setDeletingExercise] = useState(null);
  const [reprocessingExercise, setReprocessingExercise] = useState(null);
  const [infoModalExercise, setInfoModalExercise] = useState(null);

  // Summary Action Modals
  const [renameSummaryModalOpened, { open: openRenameSummaryModal, close: closeRenameSummaryModal }] = useDisclosure(false);
  const [deleteSummaryModalOpened, { open: openDeleteSummaryModal, close: closeDeleteSummaryModal }] = useDisclosure(false);
  const [editingSummary, setEditingSummary] = useState(null);
  const [deletingSummary, setDeletingSummary] = useState(null);
  const [infoModalSummary, setInfoModalSummary] = useState(null);
  const [newSummaryTitle, setNewSummaryTitle] = useState('');
  const [processLogEntityId, setProcessLogEntityId] = useState(null);

  // Processing Logs
  const [processingLogsModalOpened, { open: openProcessingLogsModal, close: closeProcessingLogsModal }] = useDisclosure(false);
  const [processingLogs, setProcessingLogs] = useState(null);
  const [processingLogsLoading, setProcessingLogsLoading] = useState(false);
  const [processingLogsNoteId, setProcessingLogsNoteId] = useState(null);

  // General Error Modal
  const [errorModalOpened, { open: openErrorModal, close: closeErrorModal }] = useDisclosure(false);
  const [errorModalData, setErrorModalData] = useState({ title: '', message: '' });

  const showError = (title, message) => {
    setErrorModalData({ title, message });
    openErrorModal();
  };

  const fetchProcessingLogs = async (noteId) => {
    setProcessingLogsNoteId(noteId);
    setProcessingLogsLoading(true);
    setProcessingLogs(null);
    openProcessingLogsModal();
    try {
      const data = await fetchApi(`/resources/${noteId}/processing-logs?limit=200`);
      setProcessingLogs(data);
    } catch (err) {
      setProcessingLogs({ error: err.message });
    } finally {
      setProcessingLogsLoading(false);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        const [subjectsData, allNotes, exercisesData, summariesData, activeTasksData] = await Promise.all([
          fetchApi('/subjects'),
          fetchApi('/resources'),
          fetchApi(`/exercises/subject/${id}`),
          fetchApi(`/notes?subject_id=${id}`),
          fetchApi('/search/tasks/active').catch(() => ({ tasks: [] }))
        ]);
        
        const currentSub = subjectsData.find(s => s.id == id);
        setSubject(currentSub);
        
        setNotes(allNotes.filter(l => l.subject_id == id));
        setExercises(exercisesData || []);
        setGeneratedNotes(summariesData || []);

        if (activeTasksData && activeTasksData.tasks) {
          const summaryTasks = {};
          const summaryProgress = {};
          const initialReprocessingNoteIds = [];
          const initialNoteProgress = {};

          activeTasksData.tasks.forEach(t => {
            const isActive = t.status !== 'completed' && t.status !== 'failed' && t.status !== 'cancelled';
            if (t.task_type === 'note_generation' && t.input_data && t.input_data.kwargs && t.input_data.kwargs.note_id) {
              const summaryId = t.input_data.kwargs.note_id;
              if (isActive) {
                summaryTasks[summaryId] = t.task_id;
              }
              if (t.progress !== undefined) {
                summaryProgress[summaryId] = t.progress;
              }
            } else if (t.task_type === 'resource_processing' || t.task_type === 'ocr') {
              const noteId = t.input_data?.kwargs?.resource_id || (t.task_id && t.task_id.startsWith('ocr_') ? t.task_id.split('_').slice(2).join('_') : null);
              if (noteId) {
                if (isActive) {
                  initialReprocessingNoteIds.push(noteId);
                }
                if (t.progress !== undefined) {
                  initialNoteProgress[noteId] = t.progress;
                }
                setResourceTasks(prev => ({ ...prev, [noteId]: t.task_id }));
                setNoteTaskStatus(prev => ({ ...prev, [noteId]: t.status }));
              }
            }
          });
          if (Object.keys(summaryTasks).length > 0) {
            setPendingSummaryTasks(prev => ({ ...prev, ...summaryTasks }));
            setGeneratedNoteProgress(prev => ({ ...prev, ...summaryProgress }));
          }
          if (initialReprocessingNoteIds.length > 0) {
            setReprocessingNoteIds(prev => [...new Set([...prev, ...initialReprocessingNoteIds])]);
          }
          if (Object.keys(initialNoteProgress).length > 0) {
            setNoteProgress(prev => ({ ...prev, ...initialNoteProgress }));
          }
        }
      } catch (err) {
        console.error("Failed to load subject data", err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [id]);

  useEffect(() => {
    if (loading || !subject) return;

    const createNote = searchParams.get('createNote');
    const createExercise = searchParams.get('createExercise');
    const resourceId = searchParams.get('resourceId');

    if (createNote === 'true' && resourceId) {
      setSelectedResources([resourceId]);
      setActiveTab('resource');
      setCreateNoteModalOpened(true);
      window.history.replaceState({}, '', `/subject/${id}`);
    } else if (createExercise === 'true' && resourceId) {
      setExerciseScope([resourceId]);
      setActiveTab('resource');
      setCreateExerciseModalOpened(true);
      window.history.replaceState({}, '', `/subject/${id}`);
    }
  }, [loading, subject, searchParams, id]);

  const [noteProgress, setNoteProgress] = useState({});
  const [noteTaskStatus, setNoteTaskStatus] = useState({});
  const [failedNoteIds, setFailedNoteIds] = useState([]);

  // Process task updates from shared TaskContext
  const { tasks } = useTaskContext();
  const knownTaskStatusRef = useRef({});

  useEffect(() => {
    for (const t of tasks) {
      const prevStatus = knownTaskStatusRef.current[t.task_id];
      if (prevStatus === t.status) continue;
      knownTaskStatusRef.current[t.task_id] = t.status;
      const kwargs = t.input_data?.kwargs || {};
      const task_type = t.task_type;
      const status = t.status;

      if (task_type === 'resource_processing') {
        const rid = kwargs.resource_id;
        if (!rid) continue;
        if (t.progress !== undefined) {
          setNoteProgress(prev => ({ ...prev, [rid]: t.progress }));
        }
        if (t.task_id) {
          setResourceTasks(prev => ({ ...prev, [rid]: t.task_id }));
        }
        setNoteTaskStatus(prev => ({ ...prev, [rid]: status }));
        if (status === 'completed') {
          setReprocessingNoteIds(prev => prev.filter(id => id !== rid));
          fetchApi(`/resources/${rid}?t=${Date.now()}`).then(updated => {
            if (updated) setNotes(prev => prev.map(n => n.id === rid ? updated : n));
          }).catch(err => console.log('Resource fetch failed, might be deleted', err));
        } else if (status === 'failed' || status === 'cancelled') {
          setReprocessingNoteIds(prev => prev.filter(id => id !== rid));
          if (t.error === 'Cancelled by user' || status === 'cancelled') {
            setCancelledNoteIds(prev => prev.includes(rid) ? prev : [...prev, rid]);
          } else {
            setFailedNoteIds(prev => prev.includes(rid) ? prev : [...prev, rid]);
          }
          fetchApi(`/resources/${rid}?t=${Date.now()}`).then(updated => {
            if (updated) setNotes(prev => prev.map(n => n.id === rid ? updated : n));
          }).catch(err => console.log('Resource fetch failed, might be deleted', err));
        }
      }

      if (task_type === 'exercise_extraction' || task_type === 'exercise_generation') {
        const eid = kwargs.exercise_id;
        if (!eid) continue;
        if (t.progress !== undefined) {
          setExerciseProgress(prev => ({ ...prev, [eid]: t.progress }));
        }
        if (t.task_id) {
          setExerciseTasks(prev => ({ ...prev, [eid]: t.task_id }));
        }
        if (status === 'completed') {
          setCompletedExerciseIds(prev => prev.includes(eid) ? prev : [...prev, eid]);
          setExerciseProgress(prev => { const n = { ...prev }; delete n[eid]; return n; });
          if (subjectRef.current?.id) {
            fetchApi(`/exercises/subject/${subjectRef.current.id}`).then(data => setExercises(data || []));
          }
        } else if (status === 'failed' || status === 'cancelled') {
          setFailedExerciseIds(prev => prev.includes(eid) ? prev : [...prev, eid]);
        }
      }

      if (task_type === 'note_generation') {
        const nid = kwargs.note_id;
        if (!nid) continue;
        if (t.progress !== undefined) {
          setGeneratedNoteProgress(prev => ({ ...prev, [nid]: t.progress }));
        }
        if (status === 'completed') {
          setReprocessingGeneratedNoteIds(prev => prev.filter(id => id !== nid));
          fetchApi(`/notes/${nid}?t=${Date.now()}`).then(refreshed => {
            if (refreshed) setGeneratedNotes(prev => prev.map(item => item.id === nid ? refreshed : item));
          });
          setPendingSummaryTasks(prev => { const n = { ...prev }; delete n[nid]; return n; });
          setGeneratedNoteProgress(prev => { const n = { ...prev }; delete n[nid]; return n; });
        } else if (status === 'failed' || status === 'cancelled') {
          setReprocessingGeneratedNoteIds(prev => prev.filter(id => id !== nid));
          if (t.error === 'Cancelled by user' || status === 'cancelled') {
            setCancelledGeneratedNoteIds(prev => prev.includes(nid) ? prev : [...prev, nid]);
          } else {
            setFailedGeneratedNoteIds(prev => prev.includes(nid) ? prev : [...prev, nid]);
          }
          setPendingSummaryTasks(prev => { const n = { ...prev }; delete n[nid]; return n; });
          setGeneratedNoteProgress(prev => { const n = { ...prev }; delete n[nid]; return n; });
        }
      }
    }
  }, [tasks]);

  const handleEditSubjectClick = () => {
    setEditSubjectName(subject.name);
    setEditSubjectDesc(subject.description || '');
    setEditSubjectColor(subject.color || '#593C8F');
    openEditSubjectModal();
  };

  const handleUpdateSubject = async () => {
    if (!editSubjectName.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetchApi(`/subjects/${subject.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: editSubjectName.trim(),
          description: editSubjectDesc.trim(),
          color: editSubjectColor
        })
      });
      setSubject(res);
      closeEditSubjectModal();
    } catch (err) {
      alert("Failed to update subject: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteSubject = async () => {
    setSubmitting(true);
    try {
      await fetchApi(`/subjects/${subject.id}`, { method: 'DELETE' });
      closeDeleteSubjectModal();
      navigate('/mynotes');
    } catch (err) {
      alert("Failed to delete subject: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const openRename = (note) => {
    setEditingNote(note);
    setNewTitle(note.title);
    openRenameModal();
  };

  const openDelete = (note) => {
    setDeletingNote(note);
    openDeleteNoteModal();
  };

  const openReprocess = (note) => {
    setReprocessingNote(note);
    openReprocessNoteModal();
  };

  const handleRenameSummary = async () => {
    if (!newSummaryTitle.trim() || !editingSummary) return;
    setSubmitting(true);
    try {
      await fetchApi(`/notes/${editingSummary.id}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ title: newSummaryTitle.trim() })
      });
      // The API saves this as a user-edited title, and we need to update state
      setGeneratedNotes(generatedNotes.map(gn => gn.id === editingSummary.id ? { ...gn, title: newSummaryTitle.trim(), is_user_edited: true } : gn));
      closeRenameSummaryModal();
    } catch (err) {
      alert("Failed to rename generated note: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteSummary = async () => {
    if (!deletingSummary) return;
    setSubmitting(true);
    try {
      await fetchApi(`/notes/${deletingSummary.id}`, { method: 'DELETE' });
      setGeneratedNotes(generatedNotes.filter(gn => gn.id !== deletingSummary.id));
      closeDeleteSummaryModal();
    } catch (err) {
      alert("Failed to delete generated note: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleRename = async () => {
    if (!newTitle.trim() || !editingNote) return;
    setSubmitting(true);
    try {
      await fetchApi(`/resources/${editingNote.id}`, {
        method: 'PUT',
        body: JSON.stringify({ title: newTitle.trim() })
      });
      setNotes(notes.map(l => l.id === editingNote.id ? { ...l, title: newTitle.trim() } : l));
      closeRenameModal();
    } catch (err) {
      alert("Failed to rename note: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteNote = async () => {
    if (!deletingNote) return;
    setSubmitting(true);
    try {
      await fetchApi(`/resources/${deletingNote.id}`, { method: 'DELETE' });
      setNotes(notes.filter(l => l.id !== deletingNote.id));
      closeDeleteNoteModal();
    } catch (err) {
      alert("Failed to delete note: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeReprocessNote = async () => {
    if (!reprocessingNote) return;
    const noteIdToReprocess = reprocessingNote.id;
    closeReprocessNoteModal();
    setFailedNoteIds(prev => prev.filter(id => id !== noteIdToReprocess));
    setCancelledNoteIds(prev => prev.filter(id => id !== noteIdToReprocess));
    setReprocessingNoteIds(prev => [...prev, noteIdToReprocess]);
    try {
      const res = await fetchApi(`/resources/${noteIdToReprocess}/reprocess?use_ai_polish=${reprocessUseAiPolish}`, {
        method: 'POST'
      });
      notifyTaskStarted();
      // The API returns the updated note
      setNotes(prevNotes => prevNotes.map(l => l.id === noteIdToReprocess ? res : l));
    } catch (err) {
      alert("Failed to reprocess note: " + err.message);
      setReprocessingNoteIds(prev => prev.filter(id => id !== noteIdToReprocess));
    }
  };

  const reprocessGeneratedNote = async (gn) => {
    const genId = gn.id;
    setFailedGeneratedNoteIds(prev => prev.filter(id => id !== genId));
    setCancelledGeneratedNoteIds(prev => prev.filter(id => id !== genId));
    setReprocessingGeneratedNoteIds(prev => [...prev, genId]);
    try {
      const res = await fetchApi(`/notes/${genId}/reprocess`, { method: 'POST' });
      notifyTaskStarted();
      if (res && res.task_id) {
        setPendingSummaryTasks(prev => ({ ...prev, [res.note_id]: res.task_id }));
      }
    } catch (err) {
      alert("Failed to reprocess note: " + err.message);
      setReprocessingGeneratedNoteIds(prev => prev.filter(id => id !== genId));
    }
  };

  const openRenameExercise = (ex) => {
    setEditingExercise(ex);
    setNewExerciseTitle(ex.title);
    openRenameExerciseModal();
  };

  const openDeleteExercise = (ex) => {
    setDeletingExercise(ex);
    openDeleteExerciseModal();
  };

  const openReprocessExercise = (ex) => {
    setReprocessingExercise(ex);
    openReprocessExerciseModal();
  };

  const openCreateSimilarExercise = (ex) => {
    setExerciseScope([ex.id]);
    if (ex.parameters) {
      setExerciseQuestionTypes(ex.parameters.question_types || ["Short answer", "Long answer", "Objective", "Fill in the blank"]);
      setExerciseLengths(ex.parameters.lengths || ["Short", "Medium", "Long"]);
      setExerciseDifficulties(ex.parameters.difficulties || ["Easy", "Medium", "Hard"]);
      setExerciseNumQuestions(ex.parameters.num_questions || ex.questions?.length || 10);
    } else if (ex.questions && ex.questions.length > 0) {
      const qTypes = [...new Set(ex.questions.map(q => q.question_type).filter(Boolean))];
      const qDiffs = [...new Set(ex.questions.map(q => q.difficulty).filter(Boolean))];
      setExerciseQuestionTypes(qTypes.length > 0 ? qTypes.map(t => t.charAt(0).toUpperCase() + t.replace(/_/g, ' ').slice(1)) : ["Short answer", "Long answer", "Objective", "Fill in the blank"]);
      setExerciseLengths(["Short", "Medium", "Long"]);
      setExerciseDifficulties(qDiffs.length > 0 ? qDiffs : ["Easy", "Medium", "Hard"]);
      setExerciseNumQuestions(ex.questions.length);
    } else {
      setExerciseQuestionTypes(["Short answer", "Long answer", "Objective", "Fill in the blank"]);
      setExerciseLengths(["Short", "Medium", "Long"]);
      setExerciseDifficulties(["Easy", "Medium", "Hard"]);
      setExerciseNumQuestions(10);
    }
    setExerciseTitle(`Similar ${ex.title}`);
    setExerciseAdvanced(false);
    setCreateExerciseModalOpened(true);
  };

  const handleRenameExercise = async () => {
    if (!newExerciseTitle.trim() || !editingExercise) return;
    setSubmitting(true);
    try {
      await fetchApi(`/exercises/${editingExercise.id}/rename`, {
        method: 'PATCH',
        body: JSON.stringify({ title: newExerciseTitle.trim() })
      });
      setExercises(exercises.map(e => e.id === editingExercise.id ? { ...e, title: newExerciseTitle.trim() } : e));
      closeRenameExerciseModal();
    } catch (err) {
      // fallback to put if patch is not supported
      try {
        await fetchApi(`/exercises/${editingExercise.id}`, {
          method: 'PUT',
          body: JSON.stringify({ title: newExerciseTitle.trim() })
        });
        setExercises(exercises.map(e => e.id === editingExercise.id ? { ...e, title: newExerciseTitle.trim() } : e));
        closeRenameExerciseModal();
      } catch (innerErr) {
        alert("Failed to rename exercise: " + err.message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteExercise = async () => {
    if (!deletingExercise) return;
    setSubmitting(true);
    try {
      await fetchApi(`/exercises/${deletingExercise.id}`, { method: 'DELETE' });
      setExercises(exercises.filter(e => e.id !== deletingExercise.id));
      closeDeleteExerciseModal();
    } catch (err) {
      alert("Failed to delete exercise: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeReprocessExercise = async () => {
    if (!reprocessingExercise) return;
    const exId = reprocessingExercise.id;
    closeReprocessExerciseModal();
    setFailedExerciseIds(prev => prev.filter(id => id !== exId));
    setCompletedExerciseIds(prev => prev.filter(id => id !== exId));
    setReprocessingExerciseIds(prev => [...prev, exId]);
    try {
      await fetchApi(`/exercises/${exId}/reprocess`, {
        method: 'POST'
      });
      notifyTaskStarted();
    } catch (err) {
      alert("Failed to reprocess exercise: " + err.message);
      setReprocessingExerciseIds(prev => prev.filter(id => id !== exId));
    }
  };

  const sortedProcessableNotes = useMemo(() => {
    return notes
      .filter(n => {
        const isProcessed = (n.processing_time_ms != null && n.processing_time_ms > 0) || 
                            (n.extracted_text != null && n.extracted_text.trim() !== '') || 
                            (n.extracted_content_structured != null && n.extracted_content_structured !== '[]' && n.extracted_content_structured !== '') || 
                            (n.output_pdf_path != null && n.output_pdf_path !== '');
        return isProcessed && !reprocessingNoteIds.includes(n.id) && !failedNoteIds.includes(n.id);
      })
      .sort((a, b) => a.title.localeCompare(b.title));
  }, [notes, reprocessingNoteIds, failedNoteIds]);

  if (loading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!subject) {
    return (
      <Center h="50vh">
        <Text c="dimmed">Subject not found.</Text>
      </Center>
    );
  }

  return (
    <Box>
      <style>{`
        .clickable-crumb {
          cursor: pointer;
        }
        .clickable-crumb:hover {
          text-decoration: underline;
        }
      `}</style>
      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20, margin: '-16px -16px 20px -16px' }}>
        <Group justify="space-between" wrap="wrap" gap="xs">
          <Group wrap="wrap" gap="xs">
            <ActionIcon variant="subtle" color="gray" onClick={() => navigate(-1)}>
              <IconChevronLeft size={20} />
            </ActionIcon>
            <Group gap="xs" ml="xs" wrap="wrap">
              <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate('/mynotes')} style={{ whiteSpace: 'nowrap' }}>Notes</Text>
              {subject.group && (
                <>
                  <Text size="sm" c="dimmed">/</Text>
                  <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/group/${subject.group.id}`)} style={{ whiteSpace: 'nowrap' }}>{subject.group.name}</Text>
                </>
              )}
            </Group>
          </Group>
        </Group>
      </Box>

      {/* Desktop Header */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" visibleFrom="sm">
        <Box style={{ minWidth: 200, flex: 1 }}>
          <Title order={1} style={{ fontSize: 'clamp(1.3rem, 4vw, 2rem)' }}>{subject.name}</Title>
          <Text c="dimmed">{subject.description || 'No description'}</Text>
        </Box>
        <Group gap="xs" wrap="wrap">
          <ActionIcon variant="light" color="gray" size="lg" title="Edit Subject" onClick={handleEditSubjectClick}>
            <IconEdit size={18} />
          </ActionIcon>
          <ActionIcon variant="light" color="red" size="lg" title="Delete Subject" onClick={openDeleteSubjectModal}>
            <IconTrash size={18} />
          </ActionIcon>
          <Menu shadow="md" width={200} position="bottom-end">
            <Menu.Target>
              <Button variant="light" leftSection={<IconSparkles size={16} />} size="sm">
                Create
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => setCreateNoteModalOpened(true)}>
                Study Notes
              </Menu.Item>
              <Menu.Item leftSection={<IconBrain size={14} />} onClick={() => setCreateExerciseModalOpened(true)}>
                Exercise
              </Menu.Item>
              <Menu.Item leftSection={<IconLayersLinked size={14} />} onClick={openMergeExerciseModal}>
                Merge Exercises
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <Menu shadow="md" width={200} position="bottom-end">
            <Menu.Target>
              <Button leftSection={<IconUpload size={16} />} size="sm">
                Upload
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => navigate(`/upload?subject_id=${subject.id}&type=resource`)}>
                Resource
              </Menu.Item>
              <Menu.Item leftSection={<IconBrain size={14} />} onClick={() => navigate(`/upload?subject_id=${subject.id}&type=exercise`)}>
                Exercise
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      {/* Desktop Controls */}
      <Group mb="xl" align="flex-end" wrap="wrap" gap="sm" visibleFrom="sm">
        <TextInput
          placeholder="Search notes..."
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          style={{ flexGrow: 1, minWidth: 200 }}
        />
        <Select
          value={sort}
          onChange={async (val) => {
             setSort(val);
             localStorage.setItem('smartnotes_sort_pref', val);
             try {
               await fetchApi('/auth/profile', {
                 method: 'PUT',
                 body: JSON.stringify({ sort_preference: val })
               });
               const user = JSON.parse(localStorage.getItem('user') || '{}');
               user.sort_preference = val;
               localStorage.setItem('user', JSON.stringify(user));
             } catch (e) {
               console.error("Failed to update sort preference in DB", e);
             }
          }}
          data={[
            { value: 'name_asc', label: 'Name (A-Z)' },
            { value: 'name_desc', label: 'Name (Z-A)' },
            { value: 'date_desc', label: 'Newest First' },
            { value: 'date_asc', label: 'Oldest First' },
          ]}
          leftSection={<IconArrowsSort size={16} />}
          style={{ width: 180 }}
          size="sm"
        />
      </Group>

      {/* Mobile Header */}
      <Box hiddenFrom="sm" mb="lg">
        <Title order={1} style={{ fontSize: 'clamp(1.8rem, 7vw, 2.8rem)', marginBottom: 16 }}>{subject.name}</Title>
        <Group gap="xs" mb="md" justify="flex-start">
          <Menu shadow="md" width={200} position="bottom-start">
            <Menu.Target>
              <Button variant="light" leftSection={<IconSparkles size={16} />} size="sm">
                Create
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => setCreateNoteModalOpened(true)}>
                Study Notes
              </Menu.Item>
              <Menu.Item leftSection={<IconBrain size={14} />} onClick={() => setCreateExerciseModalOpened(true)}>
                Exercise
              </Menu.Item>
              <Menu.Item leftSection={<IconLayersLinked size={14} />} onClick={openMergeExerciseModal}>
                Merge Exercises
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <Menu shadow="md" width={200} position="bottom-start">
            <Menu.Target>
              <Button leftSection={<IconUpload size={16} />} size="sm">
                Upload
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconFileText size={14} />} onClick={() => navigate(`/upload?subject_id=${subject.id}&type=resource`)}>
                Resource
              </Menu.Item>
              <Menu.Item leftSection={<IconBrain size={14} />} onClick={() => navigate(`/upload?subject_id=${subject.id}&type=exercise`)}>
                Exercise
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
          <ActionIcon variant="light" color="gray" size="lg" title="Edit Subject" onClick={handleEditSubjectClick}>
            <IconEdit size={18} />
          </ActionIcon>
          <ActionIcon variant="light" color="red" size="lg" title="Delete Subject" onClick={openDeleteSubjectModal}>
            <IconTrash size={18} />
          </ActionIcon>
        </Group>
        <Group gap="xs" wrap="nowrap">
          <TextInput
            placeholder="Search notes..."
            leftSection={<IconSearch size={16} />}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            style={{ flex: 1 }}
          />
          <Menu shadow="md" width={200}>
            <Menu.Target>
              <ActionIcon variant="light" color="gray" size="lg">
                <IconArrowsSort size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              {[
                { value: 'name_asc', label: 'Name (A-Z)' },
                { value: 'name_desc', label: 'Name (Z-A)' },
                { value: 'date_desc', label: 'Newest First' },
                { value: 'date_asc', label: 'Oldest First' },
              ].map(opt => (
                <Menu.Item
                  key={opt.value}
                  leftSection={sort === opt.value ? <IconCheck size={14} /> : <Box w={14} />}
                  onClick={async () => {
                    setSort(opt.value);
                    localStorage.setItem('smartnotes_sort_pref', opt.value);
                    try {
                      await fetchApi('/auth/profile', {
                        method: 'PUT',
                        body: JSON.stringify({ sort_preference: opt.value })
                      });
                      const user = JSON.parse(localStorage.getItem('user') || '{}');
                      user.sort_preference = opt.value;
                      localStorage.setItem('user', JSON.stringify(user));
                    } catch (e) {
                      console.error("Failed to update sort preference in DB", e);
                    }
                  }}
                >
                  {opt.label}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Box>

      <Tabs value={activeTab} onChange={handleTabChange} mb="md">
        <Tabs.List>
          <Tabs.Tab value="resource">Resources</Tabs.Tab>
          <Tabs.Tab value="exercise">Exercises</Tabs.Tab>
          <Tabs.Tab value="notes">Notes</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="resource" pt="xl">
          {filteredNotes.length > 0 ? (
            <Stack spacing="sm">
              {filteredNotes.map((note) => {
                const isProcessed = (note.processing_time_ms != null && note.processing_time_ms > 0) || 
                                    (note.extracted_text != null && note.extracted_text.trim() !== '') || 
                                    (note.extracted_content_structured != null && note.extracted_content_structured !== '[]' && note.extracted_content_structured !== '') || 
                                    (note.output_pdf_path != null && note.output_pdf_path !== '');
                const isReprocessing = reprocessingNoteIds.includes(note.id);
                const isCancelled = cancelledNoteIds.includes(note.id);
                // Also treat it as failed if it's not processed, has no active task, and is not reprocessing/cancelled
                const hasFailed = failedNoteIds.includes(note.id) || (!isProcessed && !resourceTasks[note.id] && !isReprocessing && !isCancelled);

                return (
                  <Card
                    key={note.id}
                    shadow="sm"
                    padding="md"
                    radius="md"
                    withBorder
                    style={{ cursor: 'pointer', position: 'relative', overflow: 'hidden' }}
                    onClick={() => navigate(`/resource/${note.id}`)}
                  >
                    <Group justify="space-between" wrap="nowrap" align="center">
                      <Box style={{ flex: 1, minWidth: 0 }}>
                        <Text fw={600} size="lg" lineClamp={2}>
                          {note.title}
                        </Text>
                        <Group gap="xs" mt={4}>
                          {(isReprocessing || !isProcessed || isCancelled) && (
                            <Badge color={(hasFailed || isCancelled) ? "red" : "orange"} variant="light" size="sm">
                              {isCancelled ? 'Cancelled' : hasFailed ? 'Failed' : isReprocessing && noteTaskStatus[note.id] === 'pending' ? 'In queue' : isReprocessing ? 'Reprocessing...' : 'Processing...'}
                            </Badge>
                          )}
                          <Text size="xs" c="dimmed">
                            {getFriendlyFileType(note.file_type)} • {formatNoteDate(note.created_at)}
                          </Text>
                        </Group>
                      </Box>

                      <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
                        <Menu position="bottom-end" withinPortal>
                          <Menu.Target>
                            <ActionIcon variant="subtle" color="gray" onClick={(e) => e.stopPropagation()}>
                              <IconDotsVertical size={16} />
                            </ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item leftSection={<IconPencil size={14} />} onClick={(e) => { e.stopPropagation(); openRename(note); }}>Rename</Menu.Item>
                            <Menu.Item leftSection={<IconRefresh size={14} />} onClick={(e) => { e.stopPropagation(); openReprocess(note); }}>Reprocess</Menu.Item>
                            <Menu.Item leftSection={<IconInfoCircle size={14} />} onClick={(e) => { e.stopPropagation(); setInfoModalNote(note); }}>System Info</Menu.Item>
                            {(isReprocessing || (!isProcessed && !hasFailed && !isCancelled)) ? (
                              <Menu.Item color="orange" leftSection={<IconX size={14} />} onClick={(e) => { e.stopPropagation(); (async () => {
                                const taskId = resourceTasks[note.id];
                                if (!taskId) {
                                  alert("Task ID not found, please wait a moment and try again.");
                                  return;
                                }
                                try {
                                  await fetchApi(`/search/tasks/${taskId}/cancel`, { method: 'POST' });
                                  setCancelledNoteIds(prev => [...prev, note.id]);
                                  setReprocessingNoteIds(prev => prev.filter(id => id !== note.id));
                                } catch(e) {
                                  alert("Failed to cancel: " + e.message);
                                }
                              })(); }}>Cancel Processing</Menu.Item>
                            ) : (
                              <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => { e.stopPropagation(); openDelete(note); }}>Delete</Menu.Item>
                            )}
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                    </Group>
                    {(isReprocessing || (!isProcessed && !hasFailed)) && (
                      <Progress 
                        value={noteProgress[note.id] ?? 10}
                        animated={isReprocessing || (noteProgress[note.id] === undefined || noteProgress[note.id] < 100)} 
                        size="xs" 
                        color="orange" 
                        style={{ position: 'absolute', bottom: 0, left: 0, right: 0 }} 
                      />
                    )}
                  </Card>
                );
              })}
            </Stack>
          ) : search.trim() ? (
            <Center h={200}>
              <Box ta="center">
                <IconSearch size={48} color="var(--mantine-color-gray-4)" />
                <Text c="dimmed" mt="md">No notes found matching "{search}"</Text>
              </Box>
            </Center>
          ) : (
            <Center h={200}>
              <Box ta="center">
                <IconFile size={48} color="var(--mantine-color-gray-4)" />
                <Text c="dimmed" mt="md">No notes uploaded to this subject yet.</Text>
                <Button mt="md" variant="light" onClick={() => navigate(`/upload?subject_id=${subject.id}`)}>
                  Upload your first file
                </Button>
              </Box>
            </Center>
          )}
        </Tabs.Panel>
        
        <Tabs.Panel value="exercise" pt="xl">
          {exercises.length > 0 ? (
            <Stack spacing="sm">
              {exercises.map((ex) => {
                const isProcessed = ex.questions && ex.questions.length > 0;
                const hasFailed = failedExerciseIds.includes(ex.id);
                const isCancelled = cancelledExerciseIds.includes(ex.id);
                const hasActiveTask = tasks.some(t =>
                    (t.task_type === 'exercise_extraction' || t.task_type === 'exercise_generation') &&
                    (t.task_id === `extract_${ex.id}` || t.task_id === `generate_${ex.id}`) &&
                    (t.status === 'pending' || t.status === 'processing' || t.status === 'running')
                );
                const isProcessing = !isProcessed && !hasFailed && !isCancelled && hasActiveTask;
                const qTypes = isProcessed ? [...new Set(ex.questions.map(q => q.question_type).filter(Boolean))] : [];
                const qDifficulties = isProcessed ? [...new Set(ex.questions.map(q => q.difficulty).filter(Boolean))] : [];
                
                return (
                <Card key={ex.id} shadow="sm" padding="md" radius="md" withBorder style={{ cursor: 'pointer', position: 'relative', overflow: 'hidden' }} onClick={() => navigate(`/exercises/${ex.id}`)}>
                  <Group justify="space-between" wrap="nowrap" align="center">
                    <Box style={{ flex: 1, minWidth: 0 }}>
                      <Text fw={600} size="lg" lineClamp={2}>
                        {ex.title}
                      </Text>
                      <Group gap="xs" mt={4}>
                        {(isProcessing || hasFailed || reprocessingExerciseIds.includes(ex.id)) && (
                          <Badge color={hasFailed ? "red" : "orange"} variant="light" size="sm">
                            {hasFailed ? 'Failed' : reprocessingExerciseIds.includes(ex.id) ? 'Reprocessing...' : 'Processing...'}
                          </Badge>
                        )}
                        <Text size="xs" c="dimmed">
                          {formatNoteDate(ex.created_at)}
                        </Text>
                      </Group>
                      {isProcessed && (
                        <Group gap="xs" mt="xs" wrap="wrap">
                          <Badge variant="light" size="xs" fw={500}>
                             {ex.questions.length} Questions
                          </Badge>
                          {(() => {
                            const totalMarks = ex.questions.reduce((s, q) => s + (q.max_marks || (q.sub_parts?.reduce((ss, sp) => ss + (sp.max_marks || 0), 0) || 1)), 0);
                            return totalMarks > 0 ? (
                              <Badge variant="light" color="blue" size="xs" fw={500}>
                                {totalMarks} total marks
                              </Badge>
                            ) : null;
                          })()}
                          {qTypes.length > 0 && (
                            <Badge variant="light" size="xs" fw={500}>
                              {qTypes.map(t => t.charAt(0).toUpperCase() + t.replace(/_/g, ' ').slice(1)).join(', ')}
                            </Badge>
                          )}
                          {qDifficulties.length > 0 && (
                            <Badge variant="light" color="red" size="xs" fw={500}>
                              {qDifficulties.join(', ')}
                            </Badge>
                          )}
                        </Group>
                      )}
                    </Box>
                    <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" color="gray" onClick={(e) => e.stopPropagation()}>
                            <IconDotsVertical size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item leftSection={<IconPencil size={14} />} onClick={(e) => { e.stopPropagation(); openRenameExercise(ex); }}>Rename</Menu.Item>
                          <Menu.Item leftSection={<IconCopy size={14} />} onClick={(e) => { e.stopPropagation(); openCreateSimilarExercise(ex); }}>Create Similar</Menu.Item>
                          <Menu.Item leftSection={<IconRefresh size={14} />} onClick={(e) => { e.stopPropagation(); openReprocessExercise(ex); }}>Reprocess</Menu.Item>
                          <Menu.Item leftSection={<IconInfoCircle size={14} />} onClick={(e) => { e.stopPropagation(); setInfoModalExercise(ex); }}>System Info</Menu.Item>
                          {(isProcessing || reprocessingExerciseIds.includes(ex.id)) ? (
                            <Menu.Item color="orange" leftSection={<IconX size={14} />} onClick={async (e) => {
                              e.stopPropagation();
                              const cancelTask = tasks.find(t =>
                                (t.task_type === 'exercise_extraction' || t.task_type === 'exercise_generation') &&
                                (t.task_id === `extract_${ex.id}` || t.task_id === `generate_${ex.id}`)
                              );
                              const taskId = exerciseTasks[ex.id] || cancelTask?.task_id;
                              if (!taskId) {
                                alert("No active task found to cancel");
                                return;
                              }
                              try {
                                await fetchApi(`/search/tasks/${taskId}/cancel`, { method: 'POST' });
                                setCancelledExerciseIds(prev => [...prev, ex.id]);
                                setReprocessingExerciseIds(prev => prev.filter(id => id !== ex.id));
                              } catch(e) {
                                alert("Failed to cancel: " + e.message);
                              }
                            }}>Cancel Processing</Menu.Item>
                          ) : (
                            <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => { e.stopPropagation(); openDeleteExercise(ex); }}>Delete</Menu.Item>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </Group>
                  {/* Progress bar for exercise processing */}
                  {(reprocessingExerciseIds.includes(ex.id) || (typeof exerciseProgress[ex.id] === 'number' && !completedExerciseIds.includes(ex.id))) && (
                    <Progress
                      value={exerciseProgress[ex.id] || undefined}
                      animated={true}
                      size="xs"
                      color="orange"
                      style={{ position: 'absolute', bottom: 0, left: 0, right: 0 }}
                    />
                  )}
                </Card>
              );
              })}
            </Stack>
          ) : (
            <Center h={200}>
              <Box ta="center">
                <Text c="dimmed">No exercises found.</Text>
                <Button mt="md" variant="light" onClick={() => navigate(`/upload?subject_id=${subject.id}&type=exercise`)}>
                  Upload an Exercise
                </Button>
              </Box>
            </Center>
          )}
        </Tabs.Panel>
        
        <Tabs.Panel value="notes" pt="xl">
          {generatedNotes.length > 0 ? (
            <Stack spacing="sm">
              {generatedNotes.map((gn) => {
                 const relatedNote = notes.find(n => n.id === gn.note_id);
                 const resourceName = relatedNote ? relatedNote.title : 'Unknown Resource';
                 const templateInfo = gn.prompt_name || formatParams(gn.mode, gn.output_format, gn.processing_method);
                 const displayTitle = gn.title || `${templateInfo} - ${resourceName}`;

                 const isProcessed = (gn.processing_time_ms != null && gn.processing_time_ms > 0) || 
                                     (gn.file_path != null && gn.file_path !== '') || 
                                     gn.status === 'completed';
                 const isReprocessing = reprocessingGeneratedNoteIds.includes(gn.id);
                 const isCancelled = cancelledGeneratedNoteIds.includes(gn.id);
                 const hasFailed = failedGeneratedNoteIds.includes(gn.id) || gn.status === 'failed' || (!isProcessed && !pendingSummaryTasks[gn.id] && !isReprocessing && !isCancelled);
                 const inProgressOrPending = !isProcessed && !hasFailed && !isCancelled;

                 return (
                  <Card key={gn.id} shadow="sm" padding="md" radius="md" withBorder style={{ cursor: 'pointer', position: 'relative', overflow: 'hidden' }} onClick={() => navigate(`/note/${gn.id}`)}>
                     <Group justify="space-between" wrap="nowrap" align="center">
                        <Box style={{ flex: 1, minWidth: 0 }}>
                          <Text fw={600} size="lg" lineClamp={2}>
                            {displayTitle}
                          </Text>
                        <Group gap="xs" mt={4}>
                          {(isReprocessing || inProgressOrPending || hasFailed || isCancelled) && (
                            <Badge color={(hasFailed || isCancelled) ? "red" : "orange"} variant="light" size="sm">
                              {isCancelled ? 'Cancelled' : hasFailed ? 'Failed' : isReprocessing ? 'Regenerating...' : 'Generating...'}
                            </Badge>
                          )}
                           <Text size="xs" c="dimmed">
                              {formatNoteDate(gn.created_at)}
                           </Text>
                        </Group>
                      </Box>
                       <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
                          <Menu position="bottom-end" withinPortal>
                          <Menu.Target>
                            <ActionIcon variant="subtle" color="gray" onClick={(e) => e.stopPropagation()}>
                              <IconDotsVertical size={20} />
                            </ActionIcon>
                          </Menu.Target>
                          <Menu.Dropdown>
                            <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => { setEditingSummary(gn); setNewSummaryTitle(displayTitle); openRenameSummaryModal(); }}>
                              Rename
                            </Menu.Item>
                            <Menu.Item leftSection={<IconRefresh size={14} />} onClick={(e) => { e.stopPropagation(); reprocessGeneratedNote(gn); }}>
                              Reprocess
                            </Menu.Item>
                            <Menu.Item leftSection={<IconInfoCircle size={14} />} onClick={() => setInfoModalSummary(gn)}>
                              System Info
                            </Menu.Item>
                            {(inProgressOrPending || isReprocessing) && pendingSummaryTasks[gn.id] ? (
                              <Menu.Item color="orange" leftSection={<IconX size={14} />} onClick={async () => {
                                try {
                                  await fetchApi(`/search/tasks/${pendingSummaryTasks[gn.id]}/cancel`, { method: 'POST' });
                                  setCancelledGeneratedNoteIds(prev => [...prev, gn.id]);
                                  setReprocessingGeneratedNoteIds(prev => prev.filter(id => id !== gn.id));
                                  setPendingSummaryTasks(prev => { const n = { ...prev }; delete n[gn.id]; return n; });
                                  setGeneratedNoteProgress(prev => { const n = { ...prev }; delete n[gn.id]; return n; });
                                } catch (e) {
                                  console.error("Failed to cancel task", e);
                                  alert("Failed to cancel task: " + e.message);
                                }
                              }}>
                                Cancel Generation
                              </Menu.Item>
                            ) : (
                              <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => { setDeletingSummary({ ...gn, displayTitle }); openDeleteSummaryModal(); }}>
                                Delete
                              </Menu.Item>
                            )}
                          </Menu.Dropdown>
                        </Menu>
                      </Group>
                   </Group>
                   {/* Progress bar for generated note processing */}
                   {(isReprocessing || inProgressOrPending) && (
                     <Progress
                       value={isReprocessing ? undefined : (generatedNoteProgress[gn.id] ?? 10)}
                       animated={isReprocessing || (generatedNoteProgress[gn.id] === undefined || generatedNoteProgress[gn.id] < 100)}
                       size="xs"
                       color="orange"
                       style={{ position: 'absolute', bottom: 0, left: 0, right: 0 }}
                     />
                   )}
                </Card>
                 );
              })}
            </Stack>
          ) : (
            <Center h={200}>
              <Text c="dimmed">No notes found.</Text>
            </Center>
          )}
        </Tabs.Panel>
      </Tabs>

      {/* Modals */}
      <Modal opened={errorModalOpened} onClose={closeErrorModal} title={<Text c="red" fw={500}>{errorModalData.title}</Text>} centered>
        <Stack>
          <Text size="sm">{errorModalData.message}</Text>
          <Group justify="flex-end" mt="md">
            <Button onClick={closeErrorModal}>Close</Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={editSubjectModalOpened} onClose={closeEditSubjectModal} title="Edit Subject" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleUpdateSubject(); }}>
          <Stack>
            <TextInput required label="Subject Name" value={editSubjectName} onChange={(e) => setEditSubjectName(e.currentTarget.value)} data-autofocus />
            <Textarea label="Description" value={editSubjectDesc} onChange={(e) => setEditSubjectDesc(e.currentTarget.value)} rows={3} />
            <ColorInput label="Color Tag" value={editSubjectColor} onChange={setEditSubjectColor} format="hex" />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeEditSubjectModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteSubjectModalOpened} onClose={closeDeleteSubjectModal} title="Confirm Delete Subject" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteSubject(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete <b>{subject.name}</b>? This will permanently remove all associated notes and quizzes.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteSubjectModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete Subject</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={renameModalOpened} onClose={closeRenameModal} title="Rename Note" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleRename(); }}>
          <Stack>
            <TextInput label="Note Title" value={newTitle} onChange={(e) => setNewTitle(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeRenameModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteNoteModalOpened} onClose={closeDeleteNoteModal} title="Confirm Delete" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteNote(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete the note <b>{deletingNote?.title}</b>? This action cannot be undone.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteNoteModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete Note</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={reprocessNoteModalOpened} onClose={closeReprocessNoteModal} title="Reprocess Note" centered>
        <Stack gap="md" mb="lg">
          <Text size="sm">
            Are you sure you want to reprocess <b>{reprocessingNote?.title}</b>? This will extract all content from the file again, completely replacing the current extraction and embeddings. Existing summaries will be kept.
          </Text>
          <Card withBorder radius="md" p="sm" bg="var(--mantine-color-default-hover)">
            <Switch
              label="AI Polish"
              description="Use AI to polish text and formatting. Off by default for fast, layout-accurate extraction."
              checked={reprocessUseAiPolish}
              onChange={(e) => setReprocessUseAiPolish(e.currentTarget.checked)}
            />
          </Card>
        </Stack>
        <Group justify="flex-end">
          <Button variant="default" onClick={closeReprocessNoteModal}>Cancel</Button>
          <Button color="orange" onClick={executeReprocessNote} loading={submitting}>Start Reprocessing</Button>
        </Group>
      </Modal>

      <Modal opened={createExerciseModalOpened} onClose={() => setCreateExerciseModalOpened(false)} title="Create Exercise" centered size="lg">
        <form onSubmit={(e) => { e.preventDefault(); handleCreateExercise(); }}>
          <Stack gap="md">
            <Text size="sm">Select resources or existing exercises and configure parameters to generate an exercise using AI.</Text>
            
            <TextInput
              label="Exercise Title (Optional)"
              placeholder="If empty, a name will be auto-generated"
              value={exerciseTitle}
              onChange={(e) => setExerciseTitle(e.currentTarget.value)}
            />
            
            <MultiSelect
              label="Scope (Select Resources or Exercises)"
              description="Choose resources and/or existing exercises to base the new exercise on."
              placeholder="Pick files or exercises"
              data={[
                { value: 'all', label: 'All Resources (Select/Deselect All)' },
                ...sortedProcessableNotes.map(n => ({ value: n.id, label: n.title })),
                { value: '---', label: '────────── Exercises ──────────', disabled: true },
                ...exercises.filter(ex => ex.questions && ex.questions.length > 0).map(ex => ({ value: ex.id, label: ex.title })),
              ]}
              value={exerciseScope}
              onChange={(values) => {
                const filtered = values.filter(v => v !== 'all' && v !== '---');
                const allSelected = values.includes('all');
                const exerciseIds = exerciseScope.filter(id => id.startsWith('ex_'));
                if (allSelected) {
                  const processableIds = sortedProcessableNotes.map(n => n.id);
                  const allResourcesSelected = processableIds.every(id => exerciseScope.includes(id));
                  if (allResourcesSelected) {
                    setExerciseScope(exerciseIds);
                  } else {
                    setExerciseScope([...processableIds, ...exerciseIds]);
                  }
                } else {
                  setExerciseScope(filtered);
                }
              }}
              searchable
              clearable
              required
            />

            <NumberInput
              label="Total Number of Questions"
              description="How many questions should the AI generate?"
              value={exerciseNumQuestions}
              onChange={setExerciseNumQuestions}
              min={1}
              max={100}
              required
            />

            <MultiSelect
              label="Question Type"
              description="Select types of questions to include."
              data={['Short answer', 'Long answer', 'Objective', 'Fill in the blank']}
              value={exerciseQuestionTypes}
              onChange={setExerciseQuestionTypes}
              required
            />

            <MultiSelect
              label="Question Length"
              description="Select lengths of questions."
              data={['Short', 'Medium', 'Long']}
              value={exerciseLengths}
              onChange={setExerciseLengths}
              required
            />

            <MultiSelect
              label="Difficulty"
              description="Select difficulties of questions."
              data={['Easy', 'Medium', 'Hard']}
              value={exerciseDifficulties}
              onChange={setExerciseDifficulties}
              required
            />

            <Switch
              label="Advanced Settings"
              checked={exerciseAdvanced}
              onChange={(e) => setExerciseAdvanced(e.currentTarget.checked)}
              mt="sm"
            />
            
            {exerciseAdvanced && (
              <Paper withBorder p="md" radius="md" mt="sm">
                <Text size="sm" fw={500} mb="xs">Question Difficulties Distribution</Text>
                <Group grow mb="md">
                  <NumberInput label="Easy" value={exerciseEasy} onChange={setExerciseEasy} min={0} />
                  <NumberInput label="Medium" value={exerciseMedium} onChange={setExerciseMedium} min={0} />
                  <NumberInput label="Hard" value={exerciseHard} onChange={setExerciseHard} min={0} />
                </Group>
                <Text size="sm" c="dimmed" mb="md">Sum: {exerciseEasy + exerciseMedium + exerciseHard} / {exerciseNumQuestions}</Text>

                <Text size="sm" fw={500} mb="xs">Question Lengths Distribution</Text>
                <Group grow mb="md">
                  <NumberInput label="Short" value={exerciseShort} onChange={setExerciseShort} min={0} />
                  <NumberInput label="Medium" value={exerciseMedLen} onChange={setExerciseMedLen} min={0} />
                  <NumberInput label="Long" value={exerciseLong} onChange={setExerciseLong} min={0} />
                </Group>
                <Text size="sm" c="dimmed" mb="md">Sum: {exerciseShort + exerciseMedLen + exerciseLong} / {exerciseNumQuestions}</Text>

                <Text size="sm" fw={500} mb="xs">Question Types Distribution</Text>
                <Group grow>
                  <NumberInput label="Short Ans" value={exerciseTypeShort} onChange={setExerciseTypeShort} min={0} />
                  <NumberInput label="Long Ans" value={exerciseTypeLong} onChange={setExerciseTypeLong} min={0} />
                  <NumberInput label="Multiple Choice" value={exerciseTypeObj} onChange={setExerciseTypeObj} min={0} />
                  <NumberInput label="Fill in Blank" value={exerciseTypeFill} onChange={setExerciseTypeFill} min={0} />
                </Group>
                <Text size="sm" c="dimmed" mt="xs">Sum: {exerciseTypeShort + exerciseTypeLong + exerciseTypeObj + exerciseTypeFill} / {exerciseNumQuestions}</Text>
              </Paper>
            )}

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => setCreateExerciseModalOpened(false)}>Cancel</Button>
              <Button type="submit" loading={generatingExercise} leftSection={<IconBrain size={16} />}>Generate Exercise</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={createNoteModalOpened} onClose={() => setCreateNoteModalOpened(false)} title="Create Note" centered size="lg">
        <form onSubmit={(e) => { e.preventDefault(); handleCreateNotes(); }}>
          <Stack gap="md">
            <Text size="sm">Select resources and configure parameters to generate smart study notes using AI.</Text>
            
            <MultiSelect
              label="Select Resources"
              description="Choose one or more uploaded files to process into your study note."
              placeholder="Pick files to include"
              data={[
                { value: 'all', label: 'All Resources (Select/Deselect All)' },
                ...sortedProcessableNotes.map(n => ({ value: n.id, label: n.title }))
              ]}
              value={selectedResources}
              onChange={(values) => {
                if (values.includes('all')) {
                  const processableIds = sortedProcessableNotes.map(n => n.id);
                  if (selectedResources.length === processableIds.length) {
                    setSelectedResources([]);
                  } else {
                    setSelectedResources(processableIds);
                  }
                } else {
                  setSelectedResources(values);
                }
              }}
              searchable
              clearable
            />

            <MultiSelect
              label="Select Exercises"
              description="Choose exercises to include as source content for your note."
              placeholder="Pick exercises to include"
              data={exercises
                .filter(ex => ex.questions && ex.questions.length > 0)
                .map(ex => ({ value: ex.id, label: ex.title }))}
              value={selectedExerciseNotes}
              onChange={setSelectedExerciseNotes}
              searchable
              clearable
            />

            <TextInput
              label="Note Name (Optional)"
              description="Give this note a custom name, or leave blank to auto-generate one."
              placeholder="e.g., Biology Midterm Prep"
              value={newNoteTitle}
              onChange={(e) => setNewNoteTitle(e.currentTarget.value)}
            />

            <SegmentedControl
              value={parameterType}
              onChange={setParameterType}
              data={[
                { label: 'Multi Parameters', value: 'multi' },
                { label: 'Single Parameter', value: 'single' },
              ]}
              fullWidth
              mb="xs"
            />

            {parameterType === 'multi' ? (
              <>
                <Select
                  label="Mode"
                  description="Controls the tone and elaboration level of the generated notes."
                  value={noteMode}
                  onChange={setNoteMode}
                  leftSection={MODE_ICONS[noteMode]}
                  renderOption={({ option }) => (
                    <Group gap="sm">
                      {MODE_ICONS[option.value]}
                      <Text size="sm">{option.label}</Text>
                    </Group>
                  )}
                  data={[
                    { value: 'quick', label: 'Quick' },
                    { value: 'simple', label: 'Simple' },
                    { value: 'normal', label: 'Normal' },
                    { value: 'elaborate', label: 'Elaborate' },
                    { value: 'eli5', label: 'Explain like I am 5' },
                  ]}
                />
                
                <Select
                  label="Output Format"
                  description="Format style of the study notes."
                  value={noteFormat}
                  onChange={setNoteFormat}
                  leftSection={FORMAT_ICONS[noteFormat]}
                  renderOption={({ option }) => (
                    <Group gap="sm">
                      {FORMAT_ICONS[option.value]}
                      <Text size="sm">{option.label}</Text>
                    </Group>
                  )}
                  data={[
                    { value: 'sentence', label: 'Sentence' },
                    { value: 'pointform', label: 'Pointform' },
                    { value: 'numbered_list', label: 'Numbered List' },
                    { value: 'table', label: 'Table' },
                  ]}
                />
                
                <Select
                  label="Processing Method"
                  description="How the AI analyzes the concatenated document text."
                  value={noteMethod}
                  onChange={setNoteMethod}
                  leftSection={METHOD_ICONS[noteMethod]}
                  renderOption={({ option }) => (
                    <Group gap="sm">
                      {METHOD_ICONS[option.value]}
                      <Text size="sm">{option.label}</Text>
                    </Group>
                  )}
                  data={[
                    { value: 'whole', label: 'Whole Document (Fast)' },
                    { value: 'section', label: 'Section by Section' },
                    { value: 'chunked', label: 'Chunked (Detailed)' },
                    { value: 'hierarchical', label: 'Hierarchical (Structured)' },
                  ]}
                />

                <Textarea
                  label="Custom Instruction (Optional)"
                  description="Add custom instructions to guide the note generation."
                  placeholder="e.g. Focus on vocabulary, write in french, explain the math equations step-by-step..."
                  value={noteCustomPrompt}
                  onChange={(e) => setNoteCustomPrompt(e.currentTarget.value)}
                  rows={3}
                />
              </>
            ) : (
              <Stack gap="sm">
                <Select
                  label="Prompt Template"
                  placeholder="Select a template..."
                  data={[
                    {
                      group: 'Global Templates',
                      items: globalPrompts.map(p => ({ value: `g_${p.id}`, label: p.name, icon: p.icon }))
                    },
                    {
                      group: 'Your Templates',
                      items: [
                        ...userPrompts.map(p => ({ value: `u_${p.id}`, label: p.name, icon: 'IconUserEdit' })),
                        { value: 'create_new', label: 'Create New Template...', icon: 'IconPlus' }
                      ]
                    }
                  ]}
                  value={selectedPromptId}
                  onChange={(val) => {
                    if (val === 'create_new') {
                      setNewPromptName('');
                      setNewPromptContent('');
                      setNewPromptInput('');
                      setCreatePromptModalOpened(true);
                    } else {
                      setSelectedPromptId(val);
                    }
                  }}
                  leftSection={(() => {
                    if (!selectedPromptId) return <IconFileText size={16} />;
                    if (selectedPromptId.startsWith('g_')) {
                      const id = selectedPromptId.replace('g_', '');
                      const gp = globalPrompts.find(p => p.id.toString() === id);
                      const IconComp = getIconComponent(gp?.icon);
                      return <IconComp size={16} />;
                    } else if (selectedPromptId.startsWith('u_')) {
                      const IconComp = getIconComponent('IconUserEdit');
                      return <IconComp size={16} />;
                    }
                    return <IconFileText size={16} />;
                  })()}
                  renderOption={({ option }) => {
                    const IconComp = getIconComponent(option.icon);
                    return (
                      <Group gap="sm">
                        <IconComp size={16} />
                        <Text size="sm">{option.label}</Text>
                      </Group>
                    );
                  }}
                  required
                />
              </Stack>
            )}

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => setCreateNoteModalOpened(false)}>Cancel</Button>
              <Button type="submit" loading={generatingCombinedNote} disabled={(selectedResources.length === 0 && selectedExerciseNotes.length === 0) || (parameterType === 'single' && !selectedPromptId)} leftSection={<IconSparkles size={16} />}>Create</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={createPromptModalOpened} onClose={() => setCreatePromptModalOpened(false)} title="Create Custom Template" centered size="lg">
        <form onSubmit={(e) => { e.preventDefault(); saveNewPrompt(); }}>
          <Stack gap="md">
            <TextInput
              label="Template Name"
              placeholder="e.g., Executive Summary"
              value={newPromptName}
              onChange={(e) => setNewPromptName(e.currentTarget.value)}
              required
              data-autofocus
            />
            <Textarea
              label="Prompt Content"
              placeholder="Instructions for the AI, e.g., Summarize key findings in bullet points..."
              value={newPromptContent}
              onChange={(e) => setNewPromptContent(e.currentTarget.value)}
              minRows={5}
              autosize
              required
            />
            
            <Divider label="AI Prompt Generator" labelPosition="center" my="sm" />
            
            <Text size="xs" c="dimmed">
              Describe what you want, and the AI will generate a structured template for you.
            </Text>
            
            <Group align="flex-end" gap="xs" style={{ flexWrap: 'nowrap' }}>
              <div style={{ flex: 1 }}>
                <Textarea
                  label="AI Instruction"
                  placeholder="e.g., focus on vocabulary, write a cheat sheet with formulas..."
                  value={newPromptInput}
                  onChange={(e) => setNewPromptInput(e.currentTarget.value)}
                  minRows={2}
                  autosize
                />
              </div>
              <Button 
                variant="light" 
                onClick={generatePrompt} 
                loading={generatingNewPrompt} 
                disabled={!newPromptInput.trim()}
                leftSection={<IconSparkles size={16} />}
                style={{ height: '56px' }}
              >
                Generate
              </Button>
            </Group>

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={() => setCreatePromptModalOpened(false)}>Cancel</Button>
              <Button type="submit" loading={savingNewPrompt} disabled={!newPromptName.trim() || !newPromptContent.trim()}>
                Create Template
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Summary Modals */}
      <Modal opened={renameSummaryModalOpened} onClose={closeRenameSummaryModal} title="Rename Generated Note" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleRenameSummary(); }}>
          <Stack>
            <TextInput label="Note Title" value={newSummaryTitle} onChange={(e) => setNewSummaryTitle(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeRenameSummaryModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteSummaryModalOpened} onClose={closeDeleteSummaryModal} title="Confirm Delete" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteSummary(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete <b>{deletingSummary?.displayTitle || deletingSummary?.title}</b>? This action cannot be undone.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteSummaryModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Exercise Modals */}
      <Modal opened={renameExerciseModalOpened} onClose={closeRenameExerciseModal} title="Rename Exercise" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleRenameExercise(); }}>
          <Stack>
            <TextInput label="Exercise Title" value={newExerciseTitle} onChange={(e) => setNewExerciseTitle(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeRenameExerciseModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteExerciseModalOpened} onClose={closeDeleteExerciseModal} title="Confirm Delete" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteExercise(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete <b>{deletingExercise?.title}</b>? This action cannot be undone.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteExerciseModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={reprocessExerciseModalOpened} onClose={closeReprocessExerciseModal} title="Reprocess Exercise" centered>
        <Text size="sm" mb="lg">
          Are you sure you want to reprocess <b>{reprocessingExercise?.title}</b>? This will regenerate the exercise using the same configuration. This operation might take a while.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={closeReprocessExerciseModal}>Cancel</Button>
          <Button color="orange" onClick={executeReprocessExercise} loading={submitting}>Start Reprocessing</Button>
        </Group>
      </Modal>

      <Modal opened={!!infoModalExercise} onClose={() => setInfoModalExercise(null)} title="System Info (Exercise)" centered>
        <Stack>
          <Text size="sm"><b>ID:</b> {infoModalExercise?.id}</Text>
          <Text size="sm"><b>Created:</b> {infoModalExercise?.created_at ? new Date(infoModalExercise.created_at).toLocaleString() : ''}</Text>
          {infoModalExercise?.model && (
            <Text size="sm"><b>Model:</b> {infoModalExercise.model}</Text>
          )}
          {infoModalExercise?.file_name && (
            <Text size="sm"><b>File Name:</b> {infoModalExercise.file_name}</Text>
          )}
          {infoModalExercise?.parameters && (
            <>
              <Divider label="Parameters" labelPosition="center" />
              {infoModalExercise.parameters.num_questions && (
                <Text size="sm"><b>Questions:</b> {infoModalExercise.parameters.num_questions}</Text>
              )}
              {infoModalExercise.parameters.question_types && (
                <Text size="sm"><b>Question Types:</b> {infoModalExercise.parameters.question_types.join(', ')}</Text>
              )}
              {infoModalExercise.parameters.difficulties && (
                <Text size="sm"><b>Difficulties:</b> {infoModalExercise.parameters.difficulties.join(', ')}</Text>
              )}
              {infoModalExercise.parameters.lengths && (
                <Text size="sm"><b>Lengths:</b> {infoModalExercise.parameters.lengths.join(', ')}</Text>
              )}
              {infoModalExercise.parameters.resource_ids && (
                <Text size="sm"><b>Source Resources:</b> {infoModalExercise.parameters.resource_ids.length}</Text>
              )}
            </>
          )}
          <Divider mt="md" />
          <Button
            variant="light"
            leftSection={<IconClipboardList size={16} />}
            onClick={() => { 
              const exId = infoModalExercise.id;
              setInfoModalExercise(null);
              setProcessLogEntityId(exId);
            }}
            fullWidth
          >
            Technical Info: Live Logs
          </Button>
        </Stack>
      </Modal>

      <Modal opened={mergeExerciseModalOpened} onClose={closeMergeExerciseModal} title="Merge Exercises" centered size="lg">
        <form onSubmit={async (e) => {
          e.preventDefault();
          if (selectedExercises.length < 2) {
            alert("Please select at least two exercises to merge.");
            return;
          }
          setMerging(true);
          try {
            const res = await fetchApi('/exercises/merge', {
              method: 'POST',
              body: JSON.stringify({ exercise_ids: selectedExercises, title: "Merged Exercises" })
            });
            setExercises([...exercises, res]);
            setSelectedExercises([]);
            closeMergeExerciseModal();
          } catch (err) {
            alert("Failed to merge exercises: " + err.message);
          } finally {
            setMerging(false);
          }
        }}>
          <Stack gap="md">
            <Text size="sm">Select multiple exercises to merge them into a single comprehensive exercise.</Text>
            <MultiSelect
              label="Select Exercises"
              placeholder="Pick exercises to merge"
              data={exercises.map(ex => ({ value: ex.id, label: ex.title }))}
              value={selectedExercises}
              onChange={setSelectedExercises}
              searchable
              clearable
              required
            />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeMergeExerciseModal}>Cancel</Button>
              <Button type="submit" loading={merging} leftSection={<IconLayersLinked size={16} />}>Merge Exercises</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={!!infoModalSummary} onClose={() => setInfoModalSummary(null)} title="System Info (Summary)" centered>
        <Stack>
          <Text size="sm"><b>ID:</b> {infoModalSummary?.id}</Text>
          <Text size="sm"><b>Created:</b> {infoModalSummary?.created_at}</Text>
          <Text size="sm"><b>Mode:</b> {infoModalSummary?.mode}</Text>
          <Text size="sm"><b>Format:</b> {infoModalSummary?.output_format}</Text>
          {infoModalSummary?.resource_ids && (() => {
            try { const ids = JSON.parse(infoModalSummary.resource_ids); return Array.isArray(ids) && ids.length > 0 ? <Text size="sm"><b>Source Resources:</b> {ids.length}</Text> : null; } catch { return null; }
          })()}
          {infoModalSummary?.exercise_ids && (() => {
            try { const ids = JSON.parse(infoModalSummary.exercise_ids); return Array.isArray(ids) && ids.length > 0 ? <Text size="sm"><b>Source Exercises:</b> {ids.length}</Text> : null; } catch { return null; }
          })()}
          {infoModalSummary?.processing_time_ms && (
            <Text size="sm"><b>Processing Time:</b> {(infoModalSummary.processing_time_ms / 1000).toFixed(2)}s</Text>
          )}
          {infoModalSummary?.model && (
            <Text size="sm"><b>Model:</b> {infoModalSummary.model}</Text>
          )}
        </Stack>
      </Modal>

      <Modal opened={!!infoModalNote} onClose={() => setInfoModalNote(null)} title="System Information" centered size="lg">
        {infoModalNote && (
          <Stack gap="sm">
            <Group justify="space-between">
              <Text size="sm" fw={500}>Note ID</Text>
              <Code>{infoModalNote.id}</Code>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Created</Text>
              <Text size="sm">{new Date(infoModalNote.created_at).toLocaleString()}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Uploaded</Text>
              <Text size="sm">{new Date(infoModalNote.created_at).toLocaleString()}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>Processing</Text>
              <Text size="sm">{new Date(infoModalNote.updated_at).toLocaleString()}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>File Name</Text>
              <Anchor 
                size="sm" 
                onClick={() => handleDownload(infoModalNote.id, infoModalNote.file_name)}
                style={{ cursor: 'pointer' }}
              >
                {infoModalNote.file_name || 'Download File'}
              </Anchor>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>File Type</Text>
              <Text size="sm">{infoModalNote.file_type || 'Unknown'}</Text>
            </Group>
            <Group justify="space-between">
              <Text size="sm" fw={500}>File Size</Text>
              <Text size="sm">
                {infoModalNote.file_size ? `${(infoModalNote.file_size / 1024 / 1024).toFixed(2)} MB` : 'Unknown'}
              </Text>
            </Group>
            {infoModalNote.page_count > 0 && (
              <Group justify="space-between">
                <Text size="sm" fw={500}>Page Count</Text>
                <Text size="sm">{infoModalNote.page_count}</Text>
              </Group>
            )}
            
            {infoModalNote.timings ? (
              <>
                <Text size="sm" fw={700} mt="md">Processing Timings</Text>
                {infoModalNote.timings.local_extraction && (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>Local Extraction</Text>
                    <Text size="sm" c="dimmed">{infoModalNote.timings.local_extraction.toFixed(2)}s</Text>
                  </Group>
                )}
                {infoModalNote.timings.ai_polish_total && (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>AI Polish (Total)</Text>
                    <Text size="sm" c="dimmed">{infoModalNote.timings.ai_polish_total.toFixed(2)}s</Text>
                  </Group>
                )}
                
                {/* Find chunk timings dynamically */}
                {Object.keys(infoModalNote.timings)
                  .filter(k => k.startsWith("chunk_"))
                  .sort()
                  .map(k => (
                  <Group key={k} justify="space-between" pl="md">
                    <Text size="xs" fw={500}>- {k.replace('chunk_', 'Chunk ')}</Text>
                    <Text size="xs" c="dimmed">{infoModalNote.timings[k].toFixed(2)}s</Text>
                  </Group>
                ))}

                {infoModalNote.timings.total_pipeline && (
                  <Group justify="space-between">
                    <Text size="sm" fw={500}>Total Pipeline Time</Text>
                    <Text size="sm" c="dimmed">{infoModalNote.timings.total_pipeline.toFixed(2)}s</Text>
                  </Group>
                )}
              </>
            ) : (
              <Text size="sm" c="dimmed" mt="md">No detailed timings available for this note.</Text>
            )}

            {infoModalNote.processing_time_ms && (
              <Group justify="space-between" mt="xs">
                <Text size="sm" fw={500}>Total Request Processing Time</Text>
                <Text size="sm" c="dimmed">{(infoModalNote.processing_time_ms / 1000).toFixed(2)}s</Text>
              </Group>
            )}

            <Divider mt="md" />
            <Button
              variant="light"
              leftSection={<IconClipboardList size={16} />}
              onClick={() => { setInfoModalNote(null); setProcessLogEntityId(infoModalNote.id); }}
              fullWidth
            >
              Technical Info: Live Logs
            </Button>
          </Stack>
        )}
      </Modal>

      {/* Processing Logs Modal */}
      <Modal
        opened={processingLogsModalOpened}
        onClose={closeProcessingLogsModal}
        title={
          <Group gap="xs">
            <IconClipboardList size={18} />
            <Text fw={600}>Processing Logs</Text>
            {processingLogsNoteId && <Code fz="xs">{processingLogsNoteId}</Code>}
          </Group>
        }
        centered
        size="xl"
      >
        {processingLogsLoading ? (
          <Center h={200}><Loader /></Center>
        ) : processingLogs?.error ? (
          <Text c="red" size="sm">{processingLogs.error}</Text>
        ) : processingLogs?.entries?.length === 0 ? (
          <Text c="dimmed" size="sm" ta="center" py="xl">No processing logs found for this note.</Text>
        ) : (
          <>
            <Text size="xs" c="dimmed" mb="sm">
              Showing {processingLogs?.entries?.length || 0} log entries
            </Text>
            <ScrollArea h={480} type="scroll">
              <Stack gap={4}>
                {processingLogs?.entries?.map((entry, i) => {
                  const levelColor = entry.level === 'ERROR' ? 'red' : entry.level === 'WARNING' ? 'orange' : 'teal';
                  const bgColor = entry.level === 'ERROR' ? 'var(--mantine-color-red-0)' : entry.level === 'WARNING' ? 'var(--mantine-color-orange-0)' : undefined;
                  return (
                    <Box
                      key={i}
                      p="xs"
                      style={{
                        borderRadius: 4,
                        backgroundColor: bgColor,
                        borderLeft: `3px solid var(--mantine-color-${levelColor}-5)`,
                        fontFamily: 'monospace',
                      }}
                    >
                      <Group gap="xs" wrap="nowrap" align="flex-start">
                        <Badge color={levelColor} size="xs" variant="filled" style={{ flexShrink: 0, marginTop: 2 }}>
                          {entry.level}
                        </Badge>
                        <Box style={{ flex: 1, minWidth: 0 }}>
                          <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>{entry.timestamp}</Text>
                          <Text size="xs" style={{ wordBreak: 'break-word', fontFamily: 'monospace' }}>{entry.message}</Text>
                          <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>{entry.logger}</Text>
                        </Box>
                      </Group>
                    </Box>
                  );
                })}
              </Stack>
            </ScrollArea>
          </>
        )}
      </Modal>
      
      <ProcessLoggerModal
        opened={!!processLogEntityId}
        onClose={() => setProcessLogEntityId(null)}
        entityId={processLogEntityId}
        tasks={tasks}
        entityType="resource"
      />
    </Box>
  );
}
