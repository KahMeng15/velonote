import { useState, useEffect, useRef, useMemo } from 'react';
import { useDisclosure } from '@mantine/hooks';
import { Box, Container, Title, Textarea, Group, Badge, Center, Loader, Text, ActionIcon, ScrollArea, Progress, Drawer, Stack, Tooltip, NavLink as MantineNavLink, Modal, Button, Menu, Divider, Card } from '@mantine/core';
import { IconDeviceFloppy, IconRobot, IconCards, IconChevronLeft, IconPencil, IconX, IconMessageChatbot, IconFileText, IconAlertCircle, IconLayoutSidebarRightCollapse, IconLayoutSidebarRightExpand, IconH1, IconH2, IconH3, IconTypography, IconList, IconListNumbers, IconTable, IconCode, IconEye, IconDownload, IconBolt, IconPhotoPlus } from '@tabler/icons-react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { fetchApi } from '../lib/api';
import { useTaskContext } from '../lib/TaskContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkUnwrapImages from 'remark-unwrap-images';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

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

export default function NoteView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const highlightText = searchParams.get('highlight');
  const refPosition = searchParams.get('ref');
  
  const [note, setNote] = useState(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  const { tasks } = useTaskContext();
  const [isEditing, setIsEditing] = useState(false);
  const [isRawMode, setIsRawMode] = useState(false);
  const [showProcessLog, setShowProcessLog] = useState(false);

  const [taskStatus, setTaskStatus] = useState(null);
  const [chatOpened, setChatOpened] = useState(false);
  const [mobileActionsOpened, { open: openMobileActions, close: closeMobileActions }] = useDisclosure(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [saveModalOpened, setSaveModalOpened] = useState(false);
  const [cancelModalOpened, setCancelModalOpened] = useState(false);
  const scrollFrameRef = useRef(null);

  const [relatedNotes, setRelatedNotes] = useState([]);
  const [relatedExercises, setRelatedExercises] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);

  const contentForRender = useMemo(() => {
    if (!content || !refPosition) return content;
    const pos = parseInt(refPosition, 10);
    if (isNaN(pos) || pos < 0 || pos > content.length) return content;
    return content.slice(0, pos) + '<span id="ref-target"></span>' + content.slice(pos);
  }, [content, refPosition]);

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
      ImageUploadExtension.configure({ id, endpointPrefix: 'resources' }),
    ],
    content: content,
  });

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

  const viewportRef = useRef(null);
  const markdownRef = useRef(null);
  const textareaRef = useRef(null);

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
      const before = content.substring(0, start);
      const selected = content.substring(start, end);
      const after = content.substring(end);

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
      setContent(newContent);
      
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
    const url = await handleImageUploadFlow(file, id, 'resources');
    if (url) {
      if (!isRawMode && editor) {
        editor.chain().focus().setImage({ src: url }).run();
      } else {
        const el = textareaRef.current;
        if (el) {
          const start = el.selectionStart;
          const before = content.substring(0, start);
          const after = content.substring(el.selectionEnd);
          const inserted = `![image](${url})`;
          setContent(before + inserted + after);
          setTimeout(() => {
            el.focus();
            el.setSelectionRange(start + inserted.length, start + inserted.length);
          }, 0);
        }
      }
    }
    e.target.value = '';
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
          const rect = el.getBoundingClientRect();
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
          if (el === activeEl) {
            el.style.opacity = 1;
            el.style.pointerEvents = 'auto';
          } else if (el.getBoundingClientRect().top <= viewportTop + currentAccumulatedTop + 5) {
            el.style.opacity = 0;
            el.style.pointerEvents = 'none';
          } else {
            el.style.opacity = 1;
            el.style.pointerEvents = 'auto';
          }
        }

        let h = 0;
        if (activeEl) {
          h = activeEl.offsetHeight;
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
  }, [content, isEditing, isRawMode]);

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

  useEffect(() => {
    if (loading || !markdownRef.current || isEditing || isRawMode) return;

    if (refPosition) {
      const scrollTimer = setTimeout(() => {
        const anchor = document.getElementById('ref-target');
        if (!anchor) return;
        const parent = anchor.parentElement;
        if (parent) {
          parent.style.backgroundColor = '#fff3e0';
          parent.style.borderRadius = '4px';
          parent.style.padding = '4px 0';
        }
        const rect = anchor.getBoundingClientRect();
        if (rect && rect.top && viewportRef.current) {
          const viewportRect = viewportRef.current.getBoundingClientRect();
          const scrollTop = viewportRef.current.scrollTop + (rect.top - viewportRect.top) - (viewportRect.height / 2);
          viewportRef.current.scrollTo({ top: scrollTop, behavior: 'smooth' });
        }
      }, 600);
      return () => clearTimeout(scrollTimer);
    }

    if (!highlightText) return;

    const highlightTimer = setTimeout(() => {
      const root = markdownRef.current;
      const cleanSearch = highlightText.replace(/[*_#`~\[\]()]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
      if (!cleanSearch) return;

      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
      const textNodes = [];
      let fullText = '';
      let node;
      while ((node = walker.nextNode())) {
        textNodes.push(node);
        fullText += node.textContent;
      }

      const matchIdx = fullText.toLowerCase().indexOf(cleanSearch);
      if (matchIdx === -1) return;

      let startNode = null, startOffset = 0, endNode = null, endOffset = 0;
      let accumulated = 0;

      for (const tn of textNodes) {
        const len = tn.textContent.length;
        const nodeEnd = accumulated + len;

        if (startNode === null && matchIdx < nodeEnd) {
          startNode = tn;
          startOffset = matchIdx - accumulated;
        }

        if (endNode === null && matchIdx + cleanSearch.length <= nodeEnd) {
          endNode = tn;
          endOffset = matchIdx + cleanSearch.length - accumulated;
          break;
        }

        accumulated = nodeEnd;
      }

      if (!startNode || !endNode) return;

      const range = document.createRange();
      range.setStart(startNode, startOffset);
      range.setEnd(endNode, endOffset);

      try {
        const mark = document.createElement('mark');
        mark.style.backgroundColor = '#ffd8a8';
        mark.style.color = 'inherit';
        mark.style.borderRadius = '2px';
        mark.style.padding = '0 2px';
        range.surroundContents(mark);
      } catch (e) {
        try {
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
        } catch (e2) {}
      }

      const targetRect = range.getBoundingClientRect();
      if (targetRect && targetRect.top && viewportRef.current) {
        const viewportRect = viewportRef.current.getBoundingClientRect();
        const scrollTop = viewportRef.current.scrollTop + (targetRect.top - viewportRect.top) - (viewportRect.height / 2);
        viewportRef.current.scrollTo({ top: scrollTop, behavior: 'smooth' });
      }
    }, 600);

    return () => clearTimeout(highlightTimer);
  }, [refPosition, highlightText, loading, content, isEditing, isRawMode]);

  useEffect(() => {
    const loadNote = async () => {
      try {
        const data = await fetchApi(`/resources/${id}?t=${Date.now()}`);
        setNote(data);
        setContent(data.extracted_text || '');
      } catch (err) {
        console.error("Failed to load note", err);
      } finally {
        setLoading(false);
      }
    };
    loadNote();
  }, [id]);

  useEffect(() => {
    if (!note) return;
    if (isProcessedCheck(note)) return;

    let interval;
    const pollTask = async () => {
      try {
        const statusData = await fetchApi(`/search/task?resource_id=${id}`);
        setTaskStatus(statusData);

        if (statusData && statusData.status === 'completed') {
          const data = await fetchApi(`/resources/${id}?t=${Date.now()}`);
          setNote(data);
          setContent(data.extracted_text || '');
          clearInterval(interval);
        } else if (statusData && statusData.status === 'failed') {
          clearInterval(interval);
        }
      } catch (e) {
        console.error("Failed to poll task status", e);
      }
    };

    pollTask();
    interval = setInterval(pollTask, 2000);

    return () => clearInterval(interval);
  }, [id, note?.processing_time_ms, note?.extracted_text, note?.output_pdf_path]);

  useEffect(() => {
    if (!note || !note.id) return;
    setLoadingRelated(true);
    fetchApi(`/resources/${note.id}/related`)
      .then(data => {
        setRelatedNotes(data.notes || []);
        setRelatedExercises(data.exercises || []);
      })
      .catch(err => console.error("Failed to load related content", err))
      .finally(() => setLoadingRelated(false));
  }, [note?.id]);

  const startEditing = () => {
    if (editor) {
      editor.commands.setContent(content);
    }
    setIsEditing(true);
    setIsRawMode(false);
  };

  const handleToggleRaw = () => {
    if (isRawMode) {
      editor?.commands.setContent(content);
      setIsRawMode(false);
    } else {
      if (editor) {
        setContent(editor.storage.markdown.getMarkdown());
      }
      setIsRawMode(true);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    let finalContent = content;
    if (!isRawMode && editor) {
      finalContent = editor.storage.markdown.getMarkdown();
    }

    try {
      await fetchApi(`/resources/${id}/content`, {
        method: 'PUT',
        body: JSON.stringify({ extracted_text: finalContent })
      });
      setIsEditing(false);
      setIsRawMode(false);
      setContent(finalContent);
      setNote({ ...note, extracted_text: finalContent });
    } catch (err) {
      console.error("Failed to save", err);
    } finally {
      setSaving(false);
    }
  };

  const isProcessedCheck = (lec) => {
    return (lec.processing_time_ms != null && lec.processing_time_ms > 0) || 
           (lec.extracted_text != null && lec.extracted_text.trim() !== '') || 
           (lec.extracted_content_structured != null && lec.extracted_content_structured !== '[]' && lec.extracted_content_structured !== '') || 
           (lec.output_pdf_path != null && lec.output_pdf_path !== '');
  };

  if (loading && !note) {
    return <Center h="50vh"><Loader size="lg" /></Center>;
  }

  if (!note) {
    return <Center h="50vh"><Text c="dimmed">Note not found.</Text></Center>;
  }

  const isCurrentlyProcessing = taskStatus && (taskStatus.status === 'pending' || taskStatus.status === 'processing' || taskStatus.status === 'running');
  const isProcessed = (isProcessedCheck(note) || taskStatus?.status === 'completed') && !isCurrentlyProcessing;
  const isFailed = taskStatus?.status === 'failed';
  const processingProgress = taskStatus?.progress || 10;

  const handleExportMarkdown = () => {
    const textToExport = content || note?.content;
    if (!textToExport) return;
    const blob = new Blob([textToExport], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${note?.title || 'Export'}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Box h="100vh" style={{ display: 'flex', flexDirection: 'column', overflowX: 'hidden' }}>
      <style>{`
        .sticky-markdown {
          font-family: 'Instrument Sans', sans-serif;
          color: #171738;
          line-height: 1.0;
          font-size: 16px;
        }
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
        .sticky-markdown .ProseMirror {
          min-height: 50vh;
          white-space: pre-wrap;
          word-wrap: break-word;
        }
        .sticky-markdown .ProseMirror:focus {
          outline: none;
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
        .clickable-crumb {
          cursor: pointer;
        }
        .clickable-crumb:hover {
          text-decoration: underline;
        }
        .related-card:hover {
          background-color: var(--mantine-color-gray-0);
        }
      `}</style>

      <input 
        type="file" 
        accept="image/*" 
        style={{ display: 'none' }} 
        ref={hiddenFileInput} 
        onChange={handleFileChange} 
      />

      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20 }}>
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
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${note.subject.id}/resource`)} style={{ whiteSpace: 'nowrap' }}>Resource</Text>
              </Group>
            )}
            {!isProcessed && (
              <Badge ml="md" color={isFailed ? 'red' : 'orange'} variant="light">
                {isFailed ? 'Failed' : 'Processing...'}
              </Badge>
            )}
          </Group>
          {isProcessed && (
            <ActionIcon
              variant="default"
              size="md"
              onClick={openMobileActions}
              hiddenFrom="sm"
            >
              <IconLayoutSidebarRightExpand size={20} />
            </ActionIcon>
          )}
        </Group>
      </Box>

      {/* Main Area with Sidebar */}
      <Box style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Content Area */}
        <ScrollArea
          viewportRef={viewportRef}
          onScrollPositionChange={handleScroll}
          style={{ flex: 1, backgroundColor: '#fff' }}
          p={0}
        >
          <Container size="md" py={0} px={0} w="100%">
            {isFailed ? (
              <Box mt={100} ta="center">
                <IconAlertCircle size={64} color="var(--mantine-color-red-6)" stroke={1.5} />
                <Title order={2} mt="xl" mb="sm" fw={800} c="red">Processing Failed</Title>
                <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                  {taskStatus?.error || 'An unexpected error occurred while processing this document.'}
                </Text>
              </Box>
            ) : !isProcessed ? (
              <Box mt={100} ta="center">
                <IconRobot size={64} color="var(--mantine-color-blue-6)" stroke={1.5} style={{ opacity: 0.8 }} />
                <Title order={2} mt="xl" mb="sm" fw={800} c="#171738">Processing Document...</Title>
                <Text c="dimmed" mb="xl" size="lg" maw={500} mx="auto">
                  Our AI is currently extracting text, analyzing the content, and preparing your smart notes. This usually takes a few seconds.
                </Text>
                
                <Box mx="auto" maw={400} mb="xl">
                  <Group justify="space-between" mb={5}>
                    <Text size="sm" fw={500}>Processing...</Text>
                    <Text size="sm" fw={500}>{processingProgress}%</Text>
                  </Group>
                  <Progress value={processingProgress} size="xl" radius="xl" striped animated />
                  <Button variant="subtle" mt="sm" onClick={() => setShowProcessLog(true)}>
                    View Live Logs
                  </Button>
                </Box>
              </Box>
            ) : (
              <Box px="md" pb="xl">
                {isEditing && isRawMode ? (
                  <Textarea
                    ref={textareaRef}
                    minRows={30}
                    autosize
                    value={content}
                    onChange={(e) => setContent(e.currentTarget.value)}
                    variant="unstyled"
                    styles={{ input: { fontFamily: 'monospace', fontSize: '14px', lineHeight: 1.6 } }}
                  />
                ) : (
                  <Box ref={markdownRef} className="sticky-markdown" style={{ color: '#171738', fontSize: '16px', lineHeight: 1.8 }}>
                    {isEditing && !isRawMode ? (
                      <EditorContent editor={editor} />
                    ) : content ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkUnwrapImages]}
                        rehypePlugins={[rehypeRaw]}
                        urlTransform={(uri) => uri}
                        components={markdownComponents}
                      >
                        {contentForRender || content}
                      </ReactMarkdown>
                    ) : (
                      <Center h={200}><Text c="dimmed">No content extracted.</Text></Center>
                    )}
                  </Box>
                )}
              </Box>
            )}
          </Container>
        </ScrollArea>

        {/* Right Sidebar */}
        {isProcessed && (
          <Box w={sidebarOpen ? 250 : 80} visibleFrom="sm" style={{ borderLeft: '1px solid #eaeaea', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', transition: 'width 200ms ease, min-width 200ms ease', minWidth: sidebarOpen ? 250 : 80, overflow: 'hidden' }} p="md">
            <Box style={{ flex: 1, overflowY: 'auto' }}>
              <Stack gap={0} align="stretch">
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
                    <Tooltip label="Create Note" disabled={sidebarOpen} position="left">
                      <MantineNavLink
                        label={sidebarOpen ? "Create Note" : ""}
                        leftSection={<IconFileText size="1.2rem" stroke={1.5} />}
                        onClick={() => navigate(`/subject/${note.subject.id}?createNote=true&resourceId=${note.id}`)}
                      />
                    </Tooltip>
                    <Tooltip label="Create Exercise" disabled={sidebarOpen} position="left">
                      <MantineNavLink
                        label={sidebarOpen ? "Create Exercise" : ""}
                        leftSection={<IconBolt size="1.2rem" stroke={1.5} />}
                        onClick={() => navigate(`/subject/${note.subject.id}?createExercise=true&resourceId=${note.id}`)}
                      />
                    </Tooltip>
                    <Tooltip label="Quick Chat" disabled={sidebarOpen} position="left">
                      <MantineNavLink
                        label={sidebarOpen ? "Quick Chat" : ""}
                        leftSection={<IconMessageChatbot size="1.2rem" stroke={1.5} />}
                        onClick={() => setChatOpened(true)}
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

              {sidebarOpen && !isEditing && isProcessed && (
                <>
                  <Divider my="sm" />
                  <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs">Related</Text>
                  {loadingRelated ? (
                    <Center py="sm"><Loader size="sm" /></Center>
                  ) : relatedNotes.length === 0 && relatedExercises.length === 0 ? (
                    <Text size="xs" c="dimmed" py="sm">No related content</Text>
                  ) : (
                    <Stack gap={4}>
                      {relatedNotes.map(rn => (
                        <Card
                          key={rn.id}
                          withBorder
                          padding="sm"
                          radius="sm"
                          style={{ cursor: 'pointer', transition: 'background-color 0.15s' }}
                          className="related-card"
                          onClick={() => navigate(`/note/${rn.id}?resourceId=${rn.resource_id}`)}
                        >
                          <Group gap="xs" wrap="nowrap" align="center">
                            <Text size="sm" fw={500} lineClamp={1} style={{ flex: 1 }}>{rn.title}</Text>
                            <Badge size="sm" variant="light">Note</Badge>
                          </Group>
                        </Card>
                      ))}
                      {relatedExercises.map(re => (
                        <Card
                          key={re.id}
                          withBorder
                          padding="sm"
                          radius="sm"
                          style={{ cursor: 'pointer', transition: 'background-color 0.15s' }}
                          className="related-card"
                          onClick={() => navigate(`/exercises/${re.id}`)}
                        >
                          <Group gap="xs" wrap="nowrap" align="center">
                            <Text size="sm" fw={500} lineClamp={1} style={{ flex: 1 }}>{re.title}</Text>
                            <Badge size="sm" color="teal" variant="light">Exercise</Badge>
                          </Group>
                        </Card>
                      ))}
                    </Stack>
                  )}
                </>
              )}
            </Box>

            <Box mt="auto" pt="sm">
              <Tooltip label={sidebarOpen ? "Hide Sidebar" : "Show Sidebar"} position="left">
                <ActionIcon variant="subtle" color="gray" size="lg" onClick={toggleSidebar}>
                  {sidebarOpen ? <IconLayoutSidebarRightCollapse size={20} /> : <IconLayoutSidebarRightExpand size={20} />}
                </ActionIcon>
              </Tooltip>
            </Box>
          </Box>
        )}
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
                  <MantineNavLink
                    label="Create Note"
                    leftSection={<IconFileText size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); navigate(`/subject/${note.subject.id}?createNote=true&resourceId=${note.id}`); }}
                  />
                  <MantineNavLink
                    label="Create Exercise"
                    leftSection={<IconBolt size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); navigate(`/subject/${note.subject.id}?createExercise=true&resourceId=${note.id}`); }}
                  />
                  <MantineNavLink
                    label="Quick Chat"
                    leftSection={<IconMessageChatbot size="1.2rem" stroke={1.5} />}
                    onClick={() => { closeMobileActions(); setChatOpened(true); }}
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
            </Stack>

            {!isEditing && isProcessed && (
              <>
                <Divider my="sm" />
                <Text size="xs" fw={600} c="dimmed" tt="uppercase" mb="xs" px="sm">Related</Text>
                {loadingRelated ? (
                  <Center py="sm"><Loader size="sm" /></Center>
                ) : relatedNotes.length === 0 && relatedExercises.length === 0 ? (
                  <Text size="xs" c="dimmed" py="sm" px="sm">No related content</Text>
                ) : (
                  <Stack gap={4} px="sm">
                    {relatedNotes.map(rn => (
                      <Card
                        key={rn.id}
                        withBorder
                        padding="sm"
                        radius="sm"
                        style={{ cursor: 'pointer', transition: 'background-color 0.15s' }}
                        className="related-card"
                        onClick={() => { closeMobileActions(); navigate(`/note/${rn.id}?resourceId=${rn.resource_id}`); }}
                      >
                        <Group gap="xs" wrap="nowrap" align="center">
                          <Text size="sm" fw={500} lineClamp={1} style={{ flex: 1 }}>{rn.title}</Text>
                          <Badge size="sm" variant="light">Note</Badge>
                        </Group>
                      </Card>
                    ))}
                    {relatedExercises.map(re => (
                      <Card
                        key={re.id}
                        withBorder
                        padding="sm"
                        radius="sm"
                        style={{ cursor: 'pointer', transition: 'background-color 0.15s' }}
                        className="related-card"
                        onClick={() => { closeMobileActions(); navigate(`/exercises/${re.id}`); }}
                      >
                        <Group gap="xs" wrap="nowrap" align="center">
                          <Text size="sm" fw={500} lineClamp={1} style={{ flex: 1 }}>{re.title}</Text>
                          <Badge size="sm" color="teal" variant="light">Exercise</Badge>
                        </Group>
                      </Card>
                    ))}
                  </Stack>
                )}
              </>
            )}
          </ScrollArea>
        </Box>
      </Drawer>

      {/* Modals */}
      <Modal opened={saveModalOpened} onClose={() => setSaveModalOpened(false)} title="Save Changes" centered withCloseButton={false}>
        <form onSubmit={(e) => { e.preventDefault(); setSaveModalOpened(false); handleSave(); }}>
          <Text size="sm" mb="md">Are you sure you want to save these changes?</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setSaveModalOpened(false)}>Cancel</Button>
            <Button type="submit" data-autofocus>Confirm Save</Button>
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

      {/* Quick Chat Drawer */}
      <Drawer
        opened={chatOpened}
        onClose={() => setChatOpened(false)}
        title="Quick Chat"
        position="right"
        size="md"
      >
        <Center h="70vh">
          <Text c="dimmed">Chat interface loading...</Text>
        </Center>
      </Drawer>
      <ProcessLoggerModal
        opened={showProcessLog}
        onClose={() => setShowProcessLog(false)}
        entityId={id}
        tasks={tasks}
        entityType="resource"
      />
    </Box>
  );
}
