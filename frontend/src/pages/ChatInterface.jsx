import { useState, useRef, useEffect } from 'react';
import { Box, Title, Paper, ScrollArea, TextInput, ActionIcon, Group, Text, Stack, Loader, Flex, Divider, Center, Select, Badge, Menu, Modal, Button, Rating, Popover, Textarea, Drawer } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { 
  IconSend, IconPlus, IconClockHour4, IconMessageCircle2, IconAdjustmentsHorizontal,
  IconRobot, IconWorld, IconFolder, IconBook, IconFile,
  IconSchool, IconBolt, IconList, IconFileText, IconX,
  IconWand, IconBrain, IconBabyCarriage, IconListNumbers, IconTable,
  IconInfoCircle, IconRefresh, IconDotsVertical, IconPencil, IconPin, IconTrash, IconPinFilled, IconLayoutCards, IconStar,
  IconLayoutSidebarLeftCollapse, IconLayoutSidebarLeftExpand
} from '@tabler/icons-react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchApi, notifyTaskStarted } from '../lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkUnwrapImages from 'remark-unwrap-images';
import { LazyImage } from '../components/LazyImage';

const stepLabels = {
  step1: "1. Scope Identification",
  step2: "2. Conversation Detection",
  step3: "3. Intent Classification",
  step4: "4. Local Context Retrieval",
  step5: "5. Web Search Fallback",
  step6: "6. Prompt Building",
  step7: "7. AI Answer Generation",
  step9: "9. Save & Housekeeping"
};

const modeIcons = {
    quick: <IconBolt size={14} />,
    simple: <IconWand size={14} />,
    normal: <IconBrain size={14} />,
    elaborate: <IconSchool size={14} />,
    eli5: <IconBabyCarriage size={14} />
  };
  
const modeLabels = {
    quick: 'Quick',
    simple: 'Simple',
    normal: 'Normal',
    elaborate: 'Elaborate',
    eli5: 'ELI5'
  };

const formatIcons = {
    mix: <IconLayoutCards size={14} />,
    sentence: <IconFileText size={14} />,
    pointform: <IconList size={14} />,
    numbered_list: <IconListNumbers size={14} />,
    table: <IconTable size={14} />
  };
  
const formatLabels = {
    mix: 'Mix',
    sentence: 'Sentence',
    pointform: 'Pointform',
    numbered_list: 'Numbered List',
    table: 'Table'
  };

const parseAiMessage = (text) => {
  if (!text) return { reasoning: null, finalAnswer: null };
  
  let reasoning = null;
  let finalAnswer = text;
  
  let cleanText = text.trim();
  if (cleanText.startsWith('```json')) cleanText = cleanText.substring(7);
  else if (cleanText.startsWith('```')) cleanText = cleanText.substring(3);
  if (cleanText.endsWith('```')) cleanText = cleanText.substring(0, cleanText.length - 3);
  cleanText = cleanText.trim();
  
  try {
    const parsed = JSON.parse(cleanText);
    if (parsed) {
      if (parsed.reasoning) reasoning = parsed.reasoning;
      if (parsed.final_answer) finalAnswer = parsed.final_answer;
    }
  } catch(e) {
    const reasoningMatch = cleanText.match(/"reasoning"\s*:\s*"([\s\S]*?)(?:"\s*,|"$|$)/);
    if (reasoningMatch && reasoningMatch[1]) {
      reasoning = reasoningMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');
    }
    
    const answerMatch = cleanText.match(/"final_answer"\s*:\s*"([\s\S]*?)(?:"\s*}|"\s*,|"$|$)/);
    if (answerMatch && answerMatch[1]) {
      finalAnswer = answerMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');
    } else if (reasoningMatch) {
      finalAnswer = "*(The response was cut off before an answer could be generated. Please try again.)*"; 
    }
  }
  
  return { reasoning, finalAnswer };
};

const MetadataBlock = ({ msg, messageIndex, setMessages, handleRepeat }) => {
  const { reasoning } = parseAiMessage(msg.text);
  if (!msg.id && !msg.detailed_sources && !msg.timings && !msg.ai_model && !reasoning) return null;
  
  const filteredSources = msg.detailed_sources ? msg.detailed_sources.filter(s => s.is_web || s.score >= 30) : [];
  const hasSources = filteredSources.length > 0;
  const isWebSearch = hasSources && filteredSources.some(s => s.is_web);
  
  const [activeTab, setActiveTab] = useState(null);
  const [rateOpened, setRateOpened] = useState(false);
  const [comment, setComment] = useState(msg.rating_comment || '');

  const handleRate = async (val, cmt = comment) => {
    try {
      if (!msg.id) return;
      await fetchApi(`/chat/${msg.id}/rate`, {
        method: 'PUT',
        body: JSON.stringify({ rating: val, comment: cmt })
      });
      
      // Update local state so it renders correctly
      setMessages(prev => prev.map((m, i) => i === messageIndex ? { ...m, rating: val, rating_comment: cmt } : m));
    } catch(e) {
      console.error("Failed to rate", e);
    }
  };
  
  const handleCommentSubmit = () => {
    handleRate(msg.rating || 0, comment);
    setRateOpened(false);
  };

  return (
    <Box mt="sm" pt="xs" style={{ fontSize: '12px' }}>
      <Group gap="md" style={{ color: '#888' }}>
        {reasoning && (
          <Button variant="light" size="compact-xs" leftSection={<IconBrain size={12} />} onClick={() => setActiveTab(prev => prev === 'brain' ? null : 'brain')}>
            {activeTab === 'brain' ? 'Hide Reasoning' : 'Show Reasoning'}
          </Button>
        )}

        {hasSources && (
          <Group gap={4} style={{ cursor: 'pointer', transition: 'color 0.2s' }} onClick={() => setActiveTab(prev => prev === 'sources' ? null : 'sources')} c={activeTab === 'sources' ? 'blue' : undefined}>
            <IconFileText size={14} />
            <Text size="xs" fw={500}>Sources</Text>
          </Group>
        )}

        {msg.id && (
          <Popover opened={rateOpened} onChange={setRateOpened} position="top" withArrow shadow="md">
            <Popover.Target>
              <Group gap={4} style={{ cursor: 'pointer', transition: 'color 0.2s' }} onClick={() => setRateOpened((o) => !o)} c={rateOpened ? 'yellow' : undefined}>
                <IconStar size={14} />
                <Text size="xs" fw={500}>Rate</Text>
              </Group>
            </Popover.Target>
            <Popover.Dropdown>
              <Stack gap="xs">
                <Text size="xs" fw={500}>Rate this answer</Text>
                <Rating value={msg.rating || 0} onChange={(val) => handleRate(val, comment)} size="sm" />
                <Textarea
                  placeholder="Leave a comment (optional)..."
                  size="xs"
                  value={comment}
                  onChange={(e) => setComment(e.currentTarget.value)}
                  minRows={2}
                />
                <Button size="compact-xs" fullWidth onClick={handleCommentSubmit}>Submit</Button>
              </Stack>
            </Popover.Dropdown>
          </Popover>
        )}

        <Group gap={4} style={{ cursor: 'pointer', transition: 'color 0.2s' }} onClick={() => setActiveTab(prev => prev === 'info' ? null : 'info')} c={activeTab === 'info' ? 'teal' : undefined}>
          <IconInfoCircle size={14} />
          <Text size="xs" fw={500}>Info</Text>
        </Group>

        <Group gap={4} style={{ cursor: 'pointer', transition: 'color 0.2s' }} onClick={() => handleRepeat(messageIndex)}>
          <IconRefresh size={14} />
          <Text size="xs" fw={500}>Retry</Text>
        </Group>
      </Group>

      {activeTab && (
        <Paper p="sm" mt="sm" withBorder bg="#f8f9fa" radius="md">
          {activeTab === 'brain' && reasoning && (
            <Box>
              <Text size="xs" fw={600} mb="xs"><IconBrain size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> AI Thought Process</Text>
              <Text size="xs" c="dimmed" style={{ fontStyle: 'italic', whiteSpace: 'pre-wrap' }}>{reasoning}</Text>
            </Box>
          )}

          {activeTab === 'info' && (
            <Box>
              <Text size="xs" fw={600} mb="xs" c="teal"><IconInfoCircle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Request Details</Text>
              
              <Text size="xs" mb={4}><IconRobot size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Model: {msg.ai_model || 'Unknown'}</Text>
              {msg.ai_mode && <Text size="xs" mb={4}><IconWand size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Mode: {modeLabels[msg.ai_mode] || msg.ai_mode}</Text>}
              {msg.output_format && <Text size="xs" mb={4}><IconFileText size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Format: {formatLabels[msg.output_format] || msg.output_format}</Text>}
              
              {(msg.note_id || msg.subject_id || msg.group_id) && (
                <Text size="xs" mb="xs">
                  <IconFolder size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> 
                  Context: {msg.note_id ? 'Specific Note' : msg.subject_id ? 'Subject Level' : msg.group_id ? 'Group Level' : 'Global Scope'}
                </Text>
              )}
              
              {msg.timings && msg.timings.step_times ? (
                <Box mt="xs">
                  <Text size="xs" fw={600} mb="xs"><IconListNumbers size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Process Timing (ms)</Text>
                  {Object.entries(msg.timings.step_times).map(([step, time]) => (
                    <Group key={step} justify="space-between" mb={2}>
                      <Text size="xs" c="dimmed">{stepLabels[step] || step}</Text>
                      <Text size="xs" fw={500}>{Number(time).toFixed(2)}ms</Text>
                    </Group>
                  ))}
                  <Divider my="xs" />
                  <Group justify="space-between">
                    <Text size="xs" fw={600}>Total Time</Text>
                    <Text size="xs" c="teal" fw={600}>{Number(msg.timings.total_ms).toFixed(2)}ms</Text>
                  </Group>
                </Box>
              ) : msg.timings ? (
                 <Box mt="xs">
                   <Text size="xs" fw={600} mb="xs"><IconClockHour4 size={12} style={{ verticalAlign: 'middle', marginRight: 4 }}/> Timing</Text>
                   <Group justify="space-between">
                     <Text size="xs" fw={600}>Total Time</Text>
                     <Text size="xs" c="teal" fw={600}>{Number(msg.timings.total_ms).toFixed(2)}ms</Text>
                   </Group>
                 </Box>
              ) : <Text size="xs" c="dimmed">No timing data available.</Text>}
            </Box>
          )}

          {activeTab === 'sources' && hasSources && (
            <Box>
              {isWebSearch && (
                <Badge mb="sm" leftSection={<IconWorld size={10}/>}>Included Web Search Results</Badge>
              )}
              <Stack spacing="xs">
                {filteredSources.map((src, idx) => (
                  <Paper 
                    key={idx} 
                    p="xs" 
                    withBorder 
                    bg="white"
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f1f3f5'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                    onClick={() => {
                      if (src.is_web) {
                        window.open(src.url, '_blank');
                      } else if (src.resource_id) {
                        const params = src.position !== undefined ? `ref=${src.position}` : `highlight=${encodeURIComponent(src.text_preview)}`;
                        window.open(`/resource/${src.resource_id}?${params}`, '_blank');
                      }
                    }}
                  >
                    {src.is_web ? (
                      <Box>
                        <Text size="xs" fw={600}><IconWorld size={10} style={{ verticalAlign: 'middle', marginRight: 4 }} /> [{idx + 1}] Web Reference</Text>
                        <Text size="xs" c="dimmed" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{src.url}</Text>
                      </Box>
                    ) : (
                      <Box>
                        <Text size="xs" fw={600}><IconFileText size={10} style={{ verticalAlign: 'middle', marginRight: 4 }} /> [{idx + 1}] Reference ({src.score}% match)</Text>
                        <Text size="xs" c="dimmed">"{src.text_preview}"</Text>
                      </Box>
                    )}
                  </Paper>
                ))}
              </Stack>
            </Box>
          )}
        </Paper>
      )}
    </Box>
  );
};

export default function ChatInterface() {
  const { cvid } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messageQueue, setMessageQueue] = useState([]);
  const scrollRef = useRef(null);

  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);

  // Task Polling State
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);

  // Settings State
  const [settingsOpened, { toggle: toggleSettings, close: closeSettings }] = useDisclosure(false);
  const [mobileDrawerOpened, { open: openMobileDrawer, close: closeMobileDrawer }] = useDisclosure(false);
  
  // Context Selection State
  const [contextType, setContextType] = useState('global');
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [selectedSubjectId, setSelectedSubjectId] = useState(null);
  const [selectedNoteId, setSelectedNoteId] = useState(null);
  
  // AI Parameters
  const [aiMode, setAiMode] = useState('normal');
  const [outputFormat, setOutputFormat] = useState('mix');
  
  const saveSettingsLocally = (updates) => {
    const globalSettings = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
    const newGlobal = { ...globalSettings, ...updates };
    localStorage.setItem('lastChatSettings', JSON.stringify(newGlobal));

    if (currentConversationIdRef.current) {
      const convSettings = JSON.parse(localStorage.getItem('convSettings') || '{}');
      convSettings[currentConversationIdRef.current] = { ...(convSettings[currentConversationIdRef.current] || {}), ...updates };
      localStorage.setItem('convSettings', JSON.stringify(convSettings));
    }
  };

  const handleAiModeChange = (mode) => {
    setAiMode(mode);
    fetchApi('/auth/profile', { method: 'PUT', body: JSON.stringify({ last_chat_ai_mode: mode }) }).catch(console.error);
    saveSettingsLocally({ aiMode: mode });
  };
  
  const handleOutputFormatChange = (format) => {
    setOutputFormat(format);
    fetchApi('/auth/profile', { method: 'PUT', body: JSON.stringify({ last_chat_output_format: format }) }).catch(console.error);
    saveSettingsLocally({ outputFormat: format });
  };

  const handleContextTypeChange = (scope) => {
    setContextType(scope);
    fetchApi('/auth/profile', { method: 'PUT', body: JSON.stringify({ last_chat_context: scope }) }).catch(console.error);
    saveSettingsLocally({ contextType: scope });
  };
  
  // Data for context dropdowns
  const [groups, setGroups] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [notes, setNotes] = useState([]);

  // Sidebar sizing
  const [sidebarWidth, setSidebarWidth] = useState(300);
  const [sidebarOpened, setSidebarOpened] = useState(() => {
    const saved = localStorage.getItem('chatSidebarOpened');
    return saved !== null ? JSON.parse(saved) : true;
  });

  useEffect(() => {
    localStorage.setItem('chatSidebarOpened', JSON.stringify(sidebarOpened));
  }, [sidebarOpened]);

  const [renameModalOpened, setRenameModalOpened] = useState(false);
  const [conversationToRename, setConversationToRename] = useState(null);
  const [newTitle, setNewTitle] = useState('');

  const [deleteModalOpened, setDeleteModalOpened] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState(null);

  const handleRename = async () => {
    if (!conversationToRename || !newTitle.trim()) return;
    try {
      await fetchApi(`/chat/conversations/${conversationToRename.conversation_id}/title`, {
        method: 'PUT',
        body: JSON.stringify({ title: newTitle.trim() })
      });
      setRenameModalOpened(false);
      fetchConversations();
    } catch (e) {
      console.error(e);
    }
  };

  const handlePin = async (conv, e) => {
    e.stopPropagation();
    try {
      await fetchApi(`/chat/conversations/${conv.conversation_id}/pin`, { method: 'PUT' });
      fetchConversations();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteClick = (conv, e) => {
    e.stopPropagation();
    setConversationToDelete(conv);
    setDeleteModalOpened(true);
  };

  const executeDelete = async () => {
    if (!conversationToDelete) return;
    try {
      await fetchApi(`/chat/conversations/${conversationToDelete.conversation_id}`, { method: 'DELETE' });
      setDeleteModalOpened(false);
      setConversationToDelete(null);
      if (currentConversationId === conversationToDelete.conversation_id) {
        navigate('/chat');
      } else {
        fetchConversations();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchConversations = async () => {
    try {
      const data = await fetchApi('/chat/conversations');
      setConversations(data || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (cvid) {
      if (cvid !== currentConversationId) {
        loadConversation(cvid);
      }
    } else {
      if (currentConversationId !== null) {
        setCurrentConversationId(null);
        setMessages([]);
        setCurrentTaskId(null);
        setLoading(false);
        const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
        fetchApi('/auth/me').then(profileData => {
           if (ls.contextType) setContextType(ls.contextType);
           else if (profileData && profileData.last_chat_context) setContextType(profileData.last_chat_context);
           
           if (ls.aiMode) setAiMode(ls.aiMode);
           else if (profileData && profileData.last_chat_ai_mode) setAiMode(profileData.last_chat_ai_mode);
           
           if (ls.outputFormat) setOutputFormat(ls.outputFormat);
           else if (profileData && profileData.last_chat_output_format) setOutputFormat(profileData.last_chat_output_format);
           
           if (ls.selectedGroupId) setSelectedGroupId(ls.selectedGroupId);
           if (ls.selectedSubjectId) setSelectedSubjectId(ls.selectedSubjectId);
           if (ls.selectedNoteId) setSelectedNoteId(ls.selectedNoteId);
        }).catch(console.error);
      }
    }
  }, [cvid]);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [grpData, subjData, lectData, profileData] = await Promise.all([
          fetchApi('/groups').catch(() => []),
          fetchApi('/subjects').catch(() => []),
          fetchApi('/resources').catch(() => []),
          fetchApi('/auth/me').catch(() => null)
        ]);
        
        setGroups((grpData || []).sort((a, b) => a.name.localeCompare(b.name)));
        setSubjects((subjData || []).sort((a, b) => a.name.localeCompare(b.name)));
        setNotes((lectData || []).sort((a, b) => a.title.localeCompare(b.title)));
        
        const ls = JSON.parse(localStorage.getItem('lastChatSettings') || '{}');
        if (!cvid) {
           if (ls.contextType) setContextType(ls.contextType);
           else if (profileData && profileData.last_chat_context) setContextType(profileData.last_chat_context);
           
           if (ls.aiMode) setAiMode(ls.aiMode);
           else if (profileData && profileData.last_chat_ai_mode) setAiMode(profileData.last_chat_ai_mode);
           
           if (ls.outputFormat) setOutputFormat(ls.outputFormat);
           else if (profileData && profileData.last_chat_output_format) setOutputFormat(profileData.last_chat_output_format);
           
           if (ls.selectedGroupId) setSelectedGroupId(ls.selectedGroupId);
           if (ls.selectedSubjectId) setSelectedSubjectId(ls.selectedSubjectId);
           if (ls.selectedNoteId) setSelectedNoteId(ls.selectedNoteId);
        }
      } catch (err) {
        console.error("Failed to load context data", err);
      }
    };
    loadData();
    fetchConversations();
  }, []);

  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, taskStatus]);

  // Fix stale closures by keeping track of the latest conversation id
  const currentConversationIdRef = useRef(currentConversationId);
  useEffect(() => {
    currentConversationIdRef.current = currentConversationId;
  }, [currentConversationId]);

  // Task Polling Effect
  useEffect(() => {
    let interval;
    if (loading && currentTaskId) {
      interval = setInterval(checkTaskStatus, 500);
    }
    return () => clearInterval(interval);
  }, [loading, currentTaskId]);

  const checkTaskStatus = async () => {
    if (!currentTaskId) return;
    try {
      const statusData = await fetchApi(`/search/tasks/${currentTaskId}`);
      if (statusData) {
        setTaskStatus(statusData);
        if (statusData.status === 'completed' || statusData.status === 'failed') {
          setCurrentTaskId(null);
          setLoading(false);
          
          if (statusData.status === 'completed') {
             const latestConvId = currentConversationIdRef.current;
             if (!latestConvId && statusData.result?.conversation_id) {
               setCurrentConversationId(statusData.result.conversation_id);
               navigate(`/chat/${statusData.result.conversation_id}`, { replace: true });
             }
             fetchConversations();
             
             const answer = statusData.result?.response || statusData.result?.answer || "Done, but no answer found.";
             setMessages(prev => [...prev, { 
               role: 'ai', 
               id: statusData.result?.id,
               rating: statusData.result?.rating,
               text: answer,
               detailed_sources: statusData.result?.detailed_sources,
               timings: statusData.result?.timings,
               ai_model: statusData.result?.ai_model,
               ai_mode: statusData.result?.ai_mode,
               output_format: statusData.result?.output_format,
               note_id: statusData.result?.note_id,
               subject_id: statusData.result?.subject_id,
               group_id: statusData.result?.group_id
             }]);
          } else {
             setMessages(prev => [...prev, { role: 'ai', text: `Failed: ${statusData.error || 'Unknown error'}` }]);
          }
        }
      }
    } catch (e) {
      console.error("Failed to fetch task status", e);
    }
  };

  const loadConversation = async (convId) => {
    try {
      setLoading(true);
      setCurrentConversationId(convId);
      const msgs = await fetchApi(`/chat/conversations/${convId}/messages`);
      
      const formattedMsgs = [];
      for (const m of msgs) {
        formattedMsgs.push({ role: 'user', text: m.message });
        formattedMsgs.push({ 
          role: 'ai', 
          id: m.id,
          rating: m.rating,
          text: m.response,
          detailed_sources: m.detailed_sources,
          timings: m.timings,
          ai_model: m.ai_model,
          ai_mode: m.ai_mode,
          output_format: m.output_format,
          note_id: m.note_id,
          subject_id: m.subject_id,
          group_id: m.group_id
        });
      }
      setMessages(formattedMsgs);
      if (formattedMsgs.length > 0) {
        const lastMsg = formattedMsgs[formattedMsgs.length - 1];
        if (lastMsg.ai_mode) setAiMode(lastMsg.ai_mode);
        if (lastMsg.output_format) setOutputFormat(lastMsg.output_format);
        if (lastMsg.note_id) {
          setContextType('note');
          setSelectedNoteId(lastMsg.note_id);
        } else if (lastMsg.subject_id) {
          setContextType('subject');
          setSelectedSubjectId(lastMsg.subject_id);
        } else if (lastMsg.group_id) {
          setContextType('group');
          setSelectedGroupId(lastMsg.group_id);
        } else {
          setContextType('global');
        }
        
        const convSettings = JSON.parse(localStorage.getItem('convSettings') || '{}');
        if (convSettings[convId]) {
          const s = convSettings[convId];
          if (s.aiMode) setAiMode(s.aiMode);
          if (s.outputFormat) setOutputFormat(s.outputFormat);
          if (s.contextType) setContextType(s.contextType);
          if (s.selectedGroupId) setSelectedGroupId(s.selectedGroupId);
          if (s.selectedSubjectId) setSelectedSubjectId(s.selectedSubjectId);
          if (s.selectedNoteId) setSelectedNoteId(s.selectedNoteId);
        }
      }
      setLoading(false);
    } catch (err) {
      console.error("Failed to load conversation", err);
      setLoading(false);
    }
  };

  const startNewChat = () => {
    setCurrentConversationId(null);
    setMessages([]);
    setCurrentTaskId(null);
    setLoading(false);
    navigate('/chat');
  };

  const handleSend = async (overrideText = null, isFromQueue = false) => {
    const textToSend = typeof overrideText === 'string' ? overrideText : input.trim();
    if (!textToSend) return;
    
    if (settingsOpened) closeSettings();

    if (loading && !isFromQueue) {
      setMessageQueue(prev => [...prev, textToSend]);
      if (typeof overrideText !== 'string') setInput('');
      return;
    }

    if (typeof overrideText !== 'string') setInput('');
    setMessages(prev => [...prev, { role: 'user', text: textToSend }]);
    setLoading(true);
    setTaskStatus(null);

    try {
      let note_id = null;
      let subject_id = null;
      let group_id = null;
      
      if (contextType === 'note') note_id = selectedNoteId;
      if (contextType === 'subject') subject_id = selectedSubjectId;
      if (contextType === 'group') group_id = selectedGroupId;

      const response = await fetchApi('/chat/ask', {
        method: 'POST',
        body: JSON.stringify({
          message: textToSend,
          note_id: note_id ? String(note_id) : null,
          subject_id: subject_id ? String(subject_id) : null,
          group_id: group_id ? String(group_id) : null,
          ai_mode: aiMode,
          output_format: outputFormat,
          conversation_id: currentConversationId,
        })
      });

      if (response.task_id) {
        setCurrentTaskId(response.task_id);
        setTaskStatus({ status: 'pending', progress_message: 'Initializing search...' });
        notifyTaskStarted();
      } else {
        if (!currentConversationId && response.conversation_id) {
          setCurrentConversationId(response.conversation_id);
          navigate(`/chat/${response.conversation_id}`, { replace: true });
        }
        fetchConversations();
        
        const answer = response.answer || response.response || "I couldn't generate an answer.";
        setMessages(prev => [...prev, { 
          role: 'ai', 
          id: response.id,
          rating: response.rating,
          text: answer,
          detailed_sources: response.detailed_sources,
          timings: response.timings,
          ai_model: response.ai_model,
          ai_mode: response.ai_mode,
          output_format: response.output_format,
          note_id: response.note_id,
          subject_id: response.subject_id,
          group_id: response.group_id
        }]);
        setLoading(false);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'ai', text: `Error: ${err.message}` }]);
      setLoading(false);
    }
  };

  const handleRepeat = (index) => {
    let userText = "";
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userText = messages[i].text;
        break;
      }
    }
    if (userText) {
      handleSend(userText);
    }
  };

  const handleSendRef = useRef();
  useEffect(() => {
    handleSendRef.current = handleSend;
  });

  useEffect(() => {
    if (!loading && messageQueue.length > 0) {
      const nextMsg = messageQueue[0];
      setMessageQueue(prev => prev.slice(1));
      handleSendRef.current(nextMsg, true);
    }
  }, [loading, messageQueue]);

  // Icons for mapping
  const contextIcons = {
    global: <IconWorld size={14} />,
    group: <IconFolder size={14} />,
    subject: <IconBook size={14} />,
    note: <IconFile size={14} />
  };


  const getContextPillText = () => {
    if (contextType === 'global') return 'Global Scope';
    
    if (contextType === 'group') {
      const g = groups.find(x => x.id.toString() === selectedGroupId);
      return g ? `Group: ${g.name}` : 'Select Group...';
    }
    if (contextType === 'subject') {
      const s = subjects.find(x => x.id.toString() === selectedSubjectId);
      return s ? `Subject: ${s.name}` : 'Select Subject...';
    }
    if (contextType === 'note') {
      const n = notes.find(x => x.id.toString() === selectedNoteId);
      return n ? `Note: ${n.title}` : 'Select Note...';
    }
    
    return `${contextType} Scope`;
  };

  const renderMessageContent = (text, sources) => {
    let { finalAnswer } = parseAiMessage(text);
    if (!finalAnswer) {
      finalAnswer = text || "*(No response provided)*";
    }

    let processedAnswer = finalAnswer;
    const citationBlockPattern = /(?:\[|【)(?:\s*source\s*)?\d+(?:\s*,\s*(?:\s*source\s*)?\d+)*\s*(?:\]|】)/gi;
    processedAnswer = processedAnswer.replace(citationBlockPattern, (match) => {
      const numbers = match.match(/\d+/g);
      if (!numbers) return match;
      return numbers.map(num => `[${num}](#source-${num})`).join(' ');
    });
    const bareSourcePattern = /\bSource\s+(\d+)\b/gi;
    processedAnswer = processedAnswer.replace(bareSourcePattern, (match, num) => {
      return `[${num}](#source-${num})`;
    });
    const supPattern = /<sup>\s*(\d+)\s*<\/sup>/gi;
    processedAnswer = processedAnswer.replace(supPattern, (match, num) => {
      return `<sup>[${num}](#source-${num})</sup>`;
    });

    const LinkRenderer = (props) => {
      const { href, children } = props;
      if (href && href.startsWith('#source-')) {
        const sourceIndex = parseInt(href.replace('#source-', ''), 10) - 1;
        return (
          <sup style={{ margin: '0 2px' }}>
            <a 
              href={href}
              onClick={(e) => {
                e.preventDefault();
                if (sources && sources[sourceIndex]) {
                  const src = sources[sourceIndex];
                  if (src.is_web) {
                    window.open(src.url, '_blank');
                  } else if (src.resource_id) {
                    const params = src.position !== undefined ? `ref=${src.position}` : `highlight=${encodeURIComponent(src.text_preview)}`;
                    window.open(`/resource/${src.resource_id}?${params}`, '_blank');
                  }
                }
              }}
              style={{ textDecoration: 'none', color: '#1c7ed6', fontWeight: 'bold' }}
            >
              {children}
            </a>
          </sup>
        );
      }
      return <a {...props}>{children}</a>;
    };

    return (
      <Box className="markdown-content">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm, remarkUnwrapImages]} 
          urlTransform={(uri) => uri}
          components={{ 
            a: LinkRenderer,
            img(props) {
              if (!props.src) return null;
              const src = props.src;
              let maxWidth = '66%';
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
          }}
        >
          {processedAnswer}
        </ReactMarkdown>
      </Box>
    );
  };


  return (
    <>
      <Modal opened={renameModalOpened} onClose={() => setRenameModalOpened(false)} title="Rename Conversation" centered>
        <TextInput
          label="New Title"
          value={newTitle}
          onChange={(e) => setNewTitle(e.currentTarget.value)}
          data-autofocus
          onKeyDown={(e) => { if (e.key === 'Enter') handleRename(); }}
        />
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setRenameModalOpened(false)}>Cancel</Button>
          <Button onClick={handleRename}>Save</Button>
        </Group>
      </Modal>

      <Modal opened={deleteModalOpened} onClose={() => setDeleteModalOpened(false)} title="Confirm Delete Conversation" centered>
        <Text size="sm" mb="lg">Are you sure you want to delete this conversation?</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setDeleteModalOpened(false)}>Cancel</Button>
          <Button color="red" onClick={executeDelete}>Delete</Button>
        </Group>
      </Modal>

    <Flex style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
      {/* Sidebar: Conversations */}
      {sidebarOpened && (
        <Box visibleFrom="sm"
          style={{ 
            width: sidebarWidth, 
            minWidth: '200px', 
            maxWidth: '500px', 
            resize: 'horizontal', 
            overflow: 'auto', 
            display: 'flex', 
            flexDirection: 'column', 
            borderRight: '1px solid #eaeaea',
            backgroundColor: '#fafafa'
          }}
        >
          <Box px={16} py="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', height: '60px', display: 'flex', alignItems: 'center' }}>
            <Group justify="space-between" style={{ width: '100%' }}>
              <Title order={4} fw={700} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Conversations</Title>
              <Group gap="xs" wrap="nowrap">
                <ActionIcon variant="default" size="sm" onClick={startNewChat}>
                  <IconPlus size={16} />
                </ActionIcon>
                <ActionIcon variant="default" size="sm" onClick={() => setSidebarOpened(false)}>
                  <IconLayoutSidebarLeftCollapse size={16} />
                </ActionIcon>
              </Group>
            </Group>
          </Box>
        <ScrollArea style={{ flex: 1, display: 'block' }} p="xs">
        {conversations.length === 0 ? (
          <Center h={100}>
            <Text size="sm" c="dimmed">No past conversations</Text>
          </Center>
        ) : (
          <Stack gap={2}>
            {[...conversations].sort((a, b) => b.is_pinned - a.is_pinned).map(conv => (
              <Paper 
                key={conv.conversation_id} 
                p={6} 
                radius="sm" 
                style={{ 
                  cursor: 'pointer', 
                  backgroundColor: currentConversationId === conv.conversation_id ? '#eef2ff' : 'transparent',
                  border: currentConversationId === conv.conversation_id ? '1px solid #c7d2fe' : '1px solid transparent',
                  transition: 'all 0.2s'
                }}
                onClick={() => navigate(`/chat/${conv.conversation_id}`)}
                >
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="xs" style={{ flex: 1, overflow: 'hidden' }} wrap="nowrap">
                      {conv.is_pinned && <IconPinFilled size={12} style={{ flexShrink: 0, color: '#f59f00' }} />}
                      <Text size="sm" fw={currentConversationId === conv.conversation_id ? 600 : 500} lineClamp={1}>
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
                        <Menu.Item leftSection={<IconPencil size={14} />} onClick={(e) => { e.stopPropagation(); setConversationToRename(conv); setNewTitle(conv.title); setRenameModalOpened(true); }}>
                          Rename
                        </Menu.Item>
                        <Menu.Item leftSection={<IconPin size={14} />} onClick={(e) => handlePin(conv, e)}>
                          {conv.is_pinned ? 'Unpin' : 'Pin'}
                        </Menu.Item>
                        <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => handleDeleteClick(conv, e)}>
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}
        </ScrollArea>
      </Box>
      )}

      {/* Mobile Conversations Drawer */}
      <Drawer
        opened={mobileDrawerOpened}
        onClose={closeMobileDrawer}
        title={
          <Group justify="space-between" style={{ width: '100%' }}>
            <Title order={4} fw={700} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738' }}>Conversations</Title>
            <ActionIcon variant="default" size="sm" onClick={() => { closeMobileDrawer(); startNewChat(); }}>
              <IconPlus size={16} />
            </ActionIcon>
          </Group>
        }
        padding={0}
        size="85%"
        hiddenFrom="sm"
        zIndex={1000}
        styles={{ header: { padding: '16px' } }}
      >
        <Box style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <ScrollArea style={{ flex: 1 }} px="xs">
        {conversations.length === 0 ? (
          <Center h={100}>
            <Text size="sm" c="dimmed">No past conversations</Text>
          </Center>
        ) : (
          <Stack gap={2}>
            {[...conversations].sort((a, b) => b.is_pinned - a.is_pinned).map(conv => (
              <Paper 
                key={conv.conversation_id} 
                p={6} 
                radius="sm" 
                style={{ 
                  cursor: 'pointer', 
                  backgroundColor: currentConversationId === conv.conversation_id ? '#eef2ff' : 'transparent',
                  border: currentConversationId === conv.conversation_id ? '1px solid #c7d2fe' : '1px solid transparent',
                  transition: 'all 0.2s'
                }}
                onClick={() => { closeMobileDrawer(); navigate(`/chat/${conv.conversation_id}`); }}
              >
                <Group justify="space-between" wrap="nowrap">
                  <Group gap="xs" style={{ flex: 1, overflow: 'hidden' }} wrap="nowrap">
                    {conv.is_pinned && <IconPinFilled size={12} style={{ flexShrink: 0, color: '#f59f00' }} />}
                    <Text size="sm" fw={currentConversationId === conv.conversation_id ? 600 : 500} lineClamp={1}>
                      {conv.title}
                    </Text>
                  </Group>
                  <Menu shadow="md" width={150} position="bottom-end" zIndex={1010}>
                    <Menu.Target>
                      <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => e.stopPropagation()}>
                        <IconDotsVertical size={16} />
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item leftSection={<IconPencil size={14} />} onClick={(e) => { e.stopPropagation(); setConversationToRename(conv); setNewTitle(conv.title); setRenameModalOpened(true); }}>
                        Rename
                      </Menu.Item>
                      <Menu.Item leftSection={<IconPin size={14} />} onClick={(e) => handlePin(conv, e)}>
                        {conv.is_pinned ? 'Unpin' : 'Pin'}
                      </Menu.Item>
                      <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={(e) => handleDeleteClick(conv, e)}>
                        Delete
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Group>
              </Paper>
            ))}
          </Stack>
        )}
      </ScrollArea>
      </Box>
      </Drawer>

      {/* Main Chat Area */}
      <Box style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, backgroundColor: '#fff', position: 'relative' }}>
        
        {/* Floating Sidebar Toggle Button */}
        {!sidebarOpened && (
          <ActionIcon 
            variant="default" 
            size="md" 
            onClick={() => setSidebarOpened(true)}
            style={{ position: 'absolute', top: 16, left: 16, zIndex: 100 }}
            visibleFrom="sm"
          >
            <IconLayoutSidebarLeftExpand size={20} />
          </ActionIcon>
        )}
        <ActionIcon 
          variant="default" 
          size="md" 
          onClick={openMobileDrawer}
          style={{ position: 'absolute', top: 16, left: 16, zIndex: 100 }}
          hiddenFrom="sm"
        >
          <IconLayoutSidebarLeftExpand size={20} />
        </ActionIcon>
        
        {/* Header Removed */}

        {/* Chat Messages */}
        {loading && messages.length === 0 ? (
          <Flex flex={1} align="center" justify="center" direction="column" style={{ minHeight: 0 }}>
            <Loader size="md" type="dots" />
            <Text mt="md" size="sm" c="dimmed">Loading conversation...</Text>
          </Flex>
        ) : messages.length === 0 ? (
          <Flex flex={1} align="center" justify="center" direction="column" px="md" style={{ minHeight: 0, opacity: 0.6 }}>
            <IconMessageCircle2 size={60} color="#ccc" style={{ marginBottom: 16 }} />
            <Title order={3} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#666' }}>Ready to dive in?</Title>
            <Text c="dimmed" mt="xs" maw={400} ta="center">
              Select a scope and uncover the insights hidden in your notes!
            </Text>
          </Flex>
        ) : (
          <Box style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
          <ScrollArea style={{ position: 'absolute', inset: 0 }} px="xl" viewportRef={scrollRef}>
            <Stack spacing="xl" style={{ maxWidth: '800px', margin: '0 auto', padding: '24px 0' }}>
              {messages.map((msg, i) => (
                <Group key={i} align="flex-start" justify={msg.role === 'user' ? 'flex-end' : 'flex-start'} wrap="nowrap" mt="md">
                  {msg.role === 'user' ? (
                    <Paper 
                      p="md" 
                      radius="xl" 
                      style={{ 
                        backgroundColor: '#171738',
                        color: '#fff',
                        maxWidth: '80%',
                        borderBottomRightRadius: '4px'
                      }}
                    >
                      <Text size="sm" style={{ lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{msg.text}</Text>
                    </Paper>
                  ) : (
                    <Box style={{ width: '100%', padding: '0 8px' }}>
                      {msg.detailed_sources?.some(s => s.is_web) && (
                        <Badge variant="light" mb="sm" size="sm" style={{ textTransform: 'none' }} leftSection={<IconWorld size={12}/>}>
                          Used Web Search
                        </Badge>
                      )}
                      <Box style={{ fontSize: '15px', lineHeight: 1.6, color: '#171738' }}>
                        {renderMessageContent(msg.text, msg.detailed_sources)}
                      </Box>
                      <MetadataBlock msg={msg} messageIndex={i} setMessages={setMessages} handleRepeat={handleRepeat} />
                    </Box>
                  )}
                </Group>
              ))}
              {messageQueue.map((msg, index) => (
                <Group key={`queue-${index}`} align="flex-start" justify="flex-end" wrap="nowrap" mb="md">
                  <Paper p="md" radius="lg" style={{ backgroundColor: '#eef2ff', color: '#333', maxWidth: '85%', alignSelf: 'flex-end', borderBottomRightRadius: 4, opacity: 0.7 }}>
                    <Group gap="sm" mb={4}>
                      <Text size="sm" fw={600}>You (Queued)</Text>
                      <Loader size="xs" type="dots" />
                    </Group>
                    <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{msg}</Text>
                  </Paper>
                </Group>
              ))}
              {loading && (
                <Group align="flex-start" wrap="nowrap" mt="md">
                  <Box style={{ padding: '0 8px' }}>
                    <Group gap="xs">
                      <Loader size="xs" type="dots" />
                      <Text size="sm" c="dimmed" style={{ fontStyle: 'italic' }}>
                        {taskStatus?.progress_message || 'Thinking...'}
                      </Text>
                    </Group>
                  </Box>
                </Group>
              )}
            </Stack>
          </ScrollArea>
          </Box>
        )}

        {/* Input & Parameters Area */}
        <Box p="md" style={{ borderTop: '1px solid #eaeaea', backgroundColor: '#fdfdfd' }}>
          <Box style={{ maxWidth: '800px', margin: '0 auto' }}>
            
            {/* Action Pills to toggle settings - Hidden when settings open */}
            {!settingsOpened && (
              <Group justify="space-between" mb="sm" align="flex-start">
                <Box style={{ flex: 1, minWidth: 0 }} hiddenFrom="sm">
                  <Stack gap={4}>
                    <Badge 
                      component="button" 
                      onClick={toggleSettings} 
                      variant="light" size="sm" fw={600} tt="none"
                      leftSection={contextIcons[contextType]}
                      style={{ cursor: 'pointer', transition: 'transform 0.1s', whiteSpace: 'normal', overflow: 'visible', alignSelf: 'flex-start' }}
                    >
                      {getContextPillText()}
                    </Badge>
                    <Group gap="xs">
                      <Badge 
                        component="button" 
                        onClick={toggleSettings} 
                        variant="light" size="sm" fw={600} tt="none"
                        leftSection={modeIcons[aiMode]}
                        style={{ cursor: 'pointer', transition: 'transform 0.1s', whiteSpace: 'normal', overflow: 'visible' }}
                      >
                        {modeLabels[aiMode]}
                      </Badge>
                      <Badge 
                        component="button" 
                        onClick={toggleSettings} 
                        variant="light" color="teal" size="sm" fw={600} tt="none"
                        leftSection={formatIcons[outputFormat]}
                        style={{ cursor: 'pointer', transition: 'transform 0.1s', whiteSpace: 'normal', overflow: 'visible' }}
                      >
                        {formatLabels[outputFormat]}
                      </Badge>
                    </Group>
                  </Stack>
                </Box>
                <Group gap="xs" wrap="wrap" visibleFrom="sm">
                  <Badge 
                    component="button" 
                    onClick={toggleSettings} 
                    variant="light" size="sm" fw={600} tt="none"
                    leftSection={contextIcons[contextType]}
                    style={{ cursor: 'pointer', transition: 'transform 0.1s' }}
                  >
                    {getContextPillText()}
                  </Badge>
                  <Badge 
                    component="button" 
                    onClick={toggleSettings} 
                    variant="light" size="sm" fw={600} tt="none"
                    leftSection={modeIcons[aiMode]}
                    style={{ cursor: 'pointer', transition: 'transform 0.1s' }}
                  >
                    {modeLabels[aiMode]}
                  </Badge>
                  <Badge 
                    component="button" 
                    onClick={toggleSettings} 
                    variant="light" color="teal" size="sm" fw={600} tt="none"
                    leftSection={formatIcons[outputFormat]}
                    style={{ cursor: 'pointer', transition: 'transform 0.1s' }}
                  >
                    {formatLabels[outputFormat]}
                  </Badge>
                </Group>
                <ActionIcon variant="subtle" color="gray" radius="xl" onClick={toggleSettings} style={{ flexShrink: 0 }}>
                  <IconAdjustmentsHorizontal size={18} />
                </ActionIcon>
              </Group>
            )}

            {/* Animated Settings/Parameters Configuration - Desktop */}
            <Box style={{ 
              maxHeight: settingsOpened ? '800px' : '0', 
              opacity: settingsOpened ? 1 : 0, 
              overflow: 'visible', 
              transition: 'all 0.3s ease' 
            }}>
              {settingsOpened && (
                <Paper p="md" withBorder radius="md" mb="md" bg="#f8f9fa" style={{ position: 'relative' }}>
                  <ActionIcon onClick={toggleSettings} variant="subtle" color="gray" style={{ position: 'absolute', top: 10, right: 10, zIndex: 5 }}>
                    <IconX size={18} />
                  </ActionIcon>

                  <Stack spacing="md">
                    {/* Context Selector Options */}
                    <Box>
                      <Text size="sm" fw={600} mb="xs" c="dimmed">Context Scope</Text>
                      <Group gap="xs" wrap="wrap">
                        {[
                          { value: 'global', label: 'Global' },
                          { value: 'group', label: 'Group' },
                          { value: 'subject', label: 'Subject' },
                          { value: 'note', label: 'Note' }
                        ].map(({ value, label }) => (
                          <Badge 
                            key={value}
                            component="button"
                            onClick={() => {
                              handleContextTypeChange(value);
                              setSelectedGroupId(null);
                              setSelectedSubjectId(null);
                              setSelectedNoteId(null);
                            }}
                            variant={contextType === value ? "filled" : "light"}
                            size="md"
                            fw={600} tt="none"
                            style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                            leftSection={contextIcons[value]}
                          >
                            {label}
                          </Badge>
                        ))}
                      </Group>
                      
                      {/* Cascading Context Dropdowns */}
                      {contextType !== 'global' && (
                        <Box style={{ animation: 'fadeIn 0.3s' }} mt="md">
                          <Stack spacing="sm">
                            {['group', 'subject', 'note'].includes(contextType) && (
                              <Select
                                label="Select Group"
                                size="sm"
                                placeholder="Choose a group..."
                                data={groups.map(g => ({ value: g.id.toString(), label: g.name }))}
                                value={selectedGroupId}
                                onChange={(val) => {
                                  setSelectedGroupId(val);
                                  setSelectedSubjectId(null);
                                  setSelectedNoteId(null);
                                  saveSettingsLocally({ selectedGroupId: val, selectedSubjectId: null, selectedNoteId: null });
                                }}
                                searchable
                                maxDropdownHeight={200}
                              />
                            )}
                            
                            {['subject', 'note'].includes(contextType) && (
                              <Select
                                label="Select Subject"
                                size="sm"
                                placeholder="Choose a subject..."
                                data={subjects.filter(s => s.group_id?.toString() === selectedGroupId).map(s => ({ value: s.id.toString(), label: s.name }))}
                                value={selectedSubjectId}
                                onChange={(val) => {
                                  setSelectedSubjectId(val);
                                  setSelectedNoteId(null);
                                  saveSettingsLocally({ selectedSubjectId: val, selectedNoteId: null });
                                }}
                                searchable
                                maxDropdownHeight={200}
                                disabled={!selectedGroupId}
                              />
                            )}
                            
                            {contextType === 'note' && (
                              <Select
                                label="Select Note"
                                size="sm"
                                placeholder="Choose a note..."
                                data={notes.filter(n => n.subject_id?.toString() === selectedSubjectId).map(n => ({ value: n.id.toString(), label: n.title }))}
                                value={selectedNoteId}
                                onChange={(val) => {
                                  setSelectedNoteId(val);
                                  saveSettingsLocally({ selectedNoteId: val });
                                }}
                                searchable
                                maxDropdownHeight={200}
                                disabled={!selectedSubjectId}
                              />
                            )}
                          </Stack>
                        </Box>
                      )}
                    </Box>
                    
                    <Divider />

                    <Group grow align="flex-start" visibleFrom="sm">
                      {/* AI Mode Options */}
                      <Box>
                        <Text size="sm" fw={600} mb="xs" c="dimmed">AI Mode</Text>
                        <Group gap="xs" wrap="wrap">
                           {['quick', 'simple', 'normal', 'elaborate', 'eli5'].map(mode => (
                            <Badge 
                              key={mode}
                              component="button"
                              onClick={() => handleAiModeChange(mode)}
                              variant={aiMode === mode ? "filled" : "light"}
                              size="md"
                              fw={600} tt="none"
                              style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                              leftSection={modeIcons[mode]}
                            >
                              {modeLabels[mode]}
                            </Badge>
                          ))}
                        </Group>
                      </Box>
                      
                      {/* Output Format Options */}
                      <Box>
                        <Text size="sm" fw={600} mb="xs" c="dimmed">Output Format</Text>
                        <Group gap="xs" wrap="wrap">
                          {[
                            { value: 'sentence', label: 'Sentence' }, 
                            { value: 'pointform', label: 'Pointform' },
                            { value: 'numbered_list', label: 'Numbered List' },
                            { value: 'table', label: 'Table' },
                            { value: 'mix', label: 'Mix' }
                          ].map(format => (
                            <Badge 
                              key={format.value}
                              component="button"
                              onClick={() => handleOutputFormatChange(format.value)}
                              variant={outputFormat === format.value ? "filled" : "light"}
                              color="teal"
                              size="md"
                              fw={600} tt="none"
                              style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                              leftSection={formatIcons[format.value]}
                            >
                              {format.label}
                            </Badge>
                          ))}
                        </Group>
                      </Box>
                    </Group>
                    <Stack gap="md" hiddenFrom="sm">
                      <Box>
                        <Text size="sm" fw={600} mb="xs" c="dimmed">AI Mode</Text>
                        <Group gap="xs" wrap="wrap">
                          {['quick', 'simple', 'normal', 'elaborate', 'eli5'].map(mode => (
                            <Badge 
                              key={mode}
                              component="button"
                              onClick={() => handleAiModeChange(mode)}
                              variant={aiMode === mode ? "filled" : "light"}
                              size="md"
                              fw={600} tt="none"
                              style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                              leftSection={modeIcons[mode]}
                            >
                              {modeLabels[mode]}
                            </Badge>
                          ))}
                        </Group>
                      </Box>
                      <Box>
                        <Text size="sm" fw={600} mb="xs" c="dimmed">Output Format</Text>
                        <Group gap="xs" wrap="wrap">
                          {[
                            { value: 'sentence', label: 'Sentence' }, 
                            { value: 'pointform', label: 'Pointform' },
                            { value: 'numbered_list', label: 'Numbered List' },
                            { value: 'table', label: 'Table' },
                            { value: 'mix', label: 'Mix' }
                          ].map(format => (
                            <Badge 
                              key={format.value}
                              component="button"
                              onClick={() => handleOutputFormatChange(format.value)}
                              variant={outputFormat === format.value ? "filled" : "light"}
                              color="teal"
                              size="md"
                              fw={600} tt="none"
                              style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                              leftSection={formatIcons[format.value]}
                            >
                              {format.label}
                            </Badge>
                          ))}
                        </Group>
                      </Box>
                    </Stack>
                  </Stack>
                </Paper>
              )}
            </Box>

            {/* Full-screen Drawer for mobile */}
            <Drawer
              opened={settingsOpened}
              onClose={closeSettings}
              position="bottom"
              size="100%"
              hiddenFrom="sm"
              zIndex={1000}
              styles={{
                header: { padding: '16px 16px 0' },
                body: { padding: '16px', overflowY: 'auto' },
                content: { borderRadius: '16px 16px 0 0' }
              }}
              title={
                <Group justify="space-between" style={{ width: '100%' }}>
                  <Text fw={700} size="lg">Chat Parameters</Text>
                </Group>
              }
            >
              <Stack spacing="md">
                {/* Context Selector Options */}
                <Box>
                  <Text size="sm" fw={600} mb="xs" c="dimmed">Context Scope</Text>
                  <Group gap="xs" wrap="wrap">
                      {[
                        { value: 'global', label: 'Global Scope' },
                        { value: 'group', label: 'Group' },
                        { value: 'subject', label: 'Subject' },
                        { value: 'note', label: 'Note' }
                      ].map(({ value, label }) => (
                        <Badge 
                          key={value}
                          component="button"
                          onClick={() => {
                            handleContextTypeChange(value);
                            setSelectedGroupId(null);
                            setSelectedSubjectId(null);
                            setSelectedNoteId(null);
                          }}
                          variant={contextType === value ? "filled" : "light"}
                          size="md"
                          fw={600} tt="none"
                          style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                          leftSection={contextIcons[value]}
                        >
                          {label}
                        </Badge>
                      ))}
                  </Group>
                  
                  {/* Cascading Context Dropdowns */}
                  {contextType !== 'global' && (
                    <Box style={{ animation: 'fadeIn 0.3s' }} mt="md">
                      <Stack spacing="sm">
                        {['group', 'subject', 'note'].includes(contextType) && (
                          <Select
                            label="Select Group"
                            size="sm"
                            placeholder="Choose a group..."
                            data={groups.map(g => ({ value: g.id.toString(), label: g.name }))}
                            value={selectedGroupId}
                            onChange={(val) => {
                              setSelectedGroupId(val);
                              setSelectedSubjectId(null);
                              setSelectedNoteId(null);
                              saveSettingsLocally({ selectedGroupId: val, selectedSubjectId: null, selectedNoteId: null });
                            }}
                            searchable
                            maxDropdownHeight={200}
                            comboboxProps={{ zIndex: 1200 }}
                          />
                        )}
                        
                        {['subject', 'note'].includes(contextType) && (
                          <Select
                            label="Select Subject"
                            size="sm"
                            placeholder="Choose a subject..."
                            data={subjects.filter(s => s.group_id?.toString() === selectedGroupId).map(s => ({ value: s.id.toString(), label: s.name }))}
                            value={selectedSubjectId}
                            onChange={(val) => {
                              setSelectedSubjectId(val);
                              setSelectedNoteId(null);
                              saveSettingsLocally({ selectedSubjectId: val, selectedNoteId: null });
                            }}
                            searchable
                            maxDropdownHeight={200}
                            disabled={!selectedGroupId}
                            comboboxProps={{ zIndex: 1200 }}
                          />
                        )}
                        
                        {contextType === 'note' && (
                          <Select
                            label="Select Note"
                            size="sm"
                            placeholder="Choose a note..."
                            data={notes.filter(n => n.subject_id?.toString() === selectedSubjectId).map(n => ({ value: n.id.toString(), label: n.title }))}
                            value={selectedNoteId}
                            onChange={(val) => {
                              setSelectedNoteId(val);
                              saveSettingsLocally({ selectedNoteId: val });
                            }}
                            searchable
                            maxDropdownHeight={200}
                            disabled={!selectedSubjectId}
                            comboboxProps={{ zIndex: 1200 }}
                          />
                        )}
                      </Stack>
                    </Box>
                  )}
                </Box>
                
                <Divider />

                {/* AI Mode Options */}
                <Box>
                  <Text size="sm" fw={600} mb="xs" c="dimmed">AI Mode</Text>
                  <Group gap="xs" wrap="wrap">
                    {['quick', 'simple', 'normal', 'elaborate', 'eli5'].map(mode => (
                      <Badge 
                        key={mode}
                        component="button"
                        onClick={() => handleAiModeChange(mode)}
                        variant={aiMode === mode ? "filled" : "light"}
                        size="md"
                        fw={600} tt="none"
                        style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                        leftSection={modeIcons[mode]}
                      >
                        {modeLabels[mode]}
                      </Badge>
                    ))}
                  </Group>
                </Box>

                {/* Output Format Options */}
                <Box>
                  <Text size="sm" fw={600} mb="xs" c="dimmed">Output Format</Text>
                  <Group gap="xs" wrap="wrap">
                    {[
                      { value: 'sentence', label: 'Sentence' }, 
                      { value: 'pointform', label: 'Pointform' },
                      { value: 'numbered_list', label: 'Numbered List' },
                      { value: 'table', label: 'Table' },
                      { value: 'mix', label: 'Mix' }
                    ].map(format => (
                      <Badge 
                        key={format.value}
                        component="button"
                        onClick={() => handleOutputFormatChange(format.value)}
                        variant={outputFormat === format.value ? "filled" : "light"}
                        color="teal"
                        size="md"
                        fw={600} tt="none"
                        style={{ cursor: 'pointer', whiteSpace: 'normal', overflow: 'visible' }}
                        leftSection={formatIcons[format.value]}
                      >
                        {format.label}
                      </Badge>
                    ))}
                  </Group>
                </Box>
              </Stack>
            </Drawer>

            {/* Chat Input */}
            <TextInput
              placeholder="Ask anything about your notes..."
              size="md"
              radius="xl"
              value={input}
              onChange={(e) => {
                setInput(e.currentTarget.value);
                if (settingsOpened) {
                  closeSettings();
                }
              }}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
              rightSection={
                <ActionIcon size="md" variant="filled" radius="xl" onClick={() => handleSend()} disabled={!input.trim()} mr="sm">
                  <IconSend size={16} />
                </ActionIcon>
              }
              styles={{ input: { fontSize: 'var(--mantine-font-size-sm)', paddingRight: '50px', backgroundColor: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.05)' } }}
            />
            <Text size="xs" ta="center" c="dimmed" mt={{ base: 2, sm: 'md' }} fz={10}>
              AI can make mistakes. Verify important information from your original notes.
            </Text>
          </Box>
        </Box>
      </Box>
    </Flex>
    </>
  );
}
