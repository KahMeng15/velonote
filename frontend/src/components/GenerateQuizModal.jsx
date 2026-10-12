import { useState, useEffect } from 'react';
import { Modal, Tabs, Paper, Text, Stack, TextInput, Select, MultiSelect, NumberInput, Button, Textarea, FileInput, Checkbox, Group } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconBolt, IconFileImport } from '@tabler/icons-react';
import { fetchApi, notifyTaskStarted } from '../lib/api';

export default function GenerateQuizModal({ opened, onClose, onSuccess, initialQuizGroupId = null }) {
  const [groups, setGroups] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [notes, setNotes] = useState([]);
  const [quizGroups, setQuizGroups] = useState([]);

  const [quizTitle, setQuizTitle] = useState('');
  const [selectedGroup, setSelectedGroup] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('');
  const [selectedNote, setSelectedNote] = useState('');
  const [selectedQuizGroup, setSelectedQuizGroup] = useState('');
  
  const [questionTypes, setQuestionTypes] = useState(['mixed']);
  const [numQuestions, setNumQuestions] = useState(5);
  
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);

  // Import States
  const [importText, setImportText] = useState('');
  const [importFiles, setImportFiles] = useState([]);
  const [generateAnswers, setGenerateAnswers] = useState(true);
  const [importing, setImporting] = useState(false);

  // Nested Create Quiz Group Modal
  const [createQuizGroupOpened, { open: openCreateQuizGroup, close: closeCreateQuizGroup }] = useDisclosure(false);
  const [newQuizGroupName, setNewQuizGroupName] = useState('');
  const [creatingQuizGroup, setCreatingQuizGroup] = useState(false);

  useEffect(() => {
    if (opened) {
      // Reset form on open
      setQuizTitle('');
      setSelectedGroup('');
      setSelectedSubject('');
      setSelectedNote('');
      setSelectedQuizGroup(initialQuizGroupId || '');
      setQuestionTypes(['mixed']);
      setNumQuestions(5);
      setError(null);
      setImportText('');
      setImportFiles([]);

      // Load data
      const loadContextData = async () => {
        try {
          const [subjectsData, groupsData, notesData, quizGroupsData] = await Promise.all([
            fetchApi('/subjects').catch(() => []),
            fetchApi('/groups').catch(() => []),
            fetchApi('/resources').catch(() => []),
            fetchApi('/quizzes/groups').catch(() => [])
          ]);
          setSubjects(subjectsData || []);
          setGroups(groupsData || []);
          setNotes(notesData || []);
          setQuizGroups(quizGroupsData || []);
        } catch (err) {
          console.error("Failed to load context for quiz generation", err);
        }
      };
      loadContextData();
    }
  }, [opened, initialQuizGroupId]);

  const handleCreateQuizGroup = async () => {
    if (!newQuizGroupName.trim()) return;
    setCreatingQuizGroup(true);
    try {
      const response = await fetchApi('/quizzes/groups', {
        method: 'POST',
        body: JSON.stringify({ name: newQuizGroupName.trim() })
      });
      setQuizGroups(prev => [...prev, response]);
      setSelectedQuizGroup(response.id.toString());
      closeCreateQuizGroup();
      setNewQuizGroupName('');
    } catch(err) {
      setError("Failed to create quiz group");
    } finally {
      setCreatingQuizGroup(false);
    }
  };

  const handleQuestionTypeChange = (values) => {
    if (values.length === 0) {
      setQuestionTypes([]);
      return;
    }
    const hasMixed = values.includes('mixed');
    const prevHadMixed = questionTypes.includes('mixed');
    
    if (hasMixed && !prevHadMixed) {
      setQuestionTypes(['mixed']);
    } else if (hasMixed && values.length > 1) {
      setQuestionTypes(values.filter(v => v !== 'mixed'));
    } else {
      setQuestionTypes(values);
    }
  };

  const handleGenerateQuiz = async () => {
    let scopeType = '';
    let scopeId = '';

    if (selectedNote && selectedNote !== 'all') {
      scopeType = 'note';
      scopeId = selectedNote;
    } else if (selectedSubject && selectedSubject !== 'all') {
      scopeType = 'subject';
      scopeId = selectedSubject;
    } else if (selectedGroup && selectedGroup !== 'ungrouped' && selectedGroup !== 'all') {
      scopeType = 'group';
      scopeId = selectedGroup;
    } else {
      setError("Please select a group, subject or note to test.");
      return;
    }

    setGenerating(true);
    setError(null);

    try {
      const response = await fetchApi('/quizzes/generate', {
        method: 'POST',
        body: JSON.stringify({
          title: quizTitle.trim(),
          scope_type: scopeType,
          scope_id: scopeId,
          question_types: questionTypes.length > 0 ? questionTypes : ['mixed'],
          number_of_questions: numQuestions,
          quiz_group_id: selectedQuizGroup || null
        })
      });
      notifyTaskStarted();

      const pendingQuiz = { 
        id: response.quiz_id || response.task_id, 
        title: quizTitle.trim() || 'Generating AI Quiz...', 
        created_at: new Date().toISOString(), 
        questions: [],
        quiz_group_id: selectedQuizGroup || null,
        model: 'Generating...'
      };
      
      onSuccess(pendingQuiz);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to generate quiz');
    } finally {
      setGenerating(false);
    }
  };

  const handleImportQuiz = async () => {
    if (!importText.trim() && importFiles.length === 0) {
      setError("Please provide either text or file(s) to import.");
      return;
    }
    setImporting(true);
    setError(null);
    const formData = new FormData();
    if (quizTitle.trim()) formData.append('title', quizTitle.trim());
    if (importText.trim()) formData.append('text', importText.trim());
    if (selectedQuizGroup) formData.append('quiz_group_id', selectedQuizGroup);
    formData.append('generate_answers', generateAnswers);
    importFiles.forEach(file => formData.append('file', file));

    try {
      const response = await fetchApi('/quizzes/import', {
        method: 'POST',
        body: formData,
        headers: {} // Required to let browser set boundary
      });
      onSuccess(response);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to import quiz');
    } finally {
      setImporting(false);
    }
  };

  return (
    <>
      <Modal opened={opened} onClose={onClose} title="Create Quiz" centered size="lg">
        {error && <Text color="red" size="sm" mb="sm">{error}</Text>}
        <Tabs defaultValue="generate">
          <Tabs.List mb="md">
            <Tabs.Tab value="generate" leftSection={<IconBolt size={14} />}>Generate AI Quiz</Tabs.Tab>
            <Tabs.Tab value="import" leftSection={<IconFileImport size={14} />}>Import Quiz</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="generate">
            <Stack spacing="md">
              <Paper withBorder p="sm" radius="md">
                <Text size="sm" fw={500} mb="xs">Quiz Info</Text>
                <Stack spacing="sm">
                  <TextInput
                    label="Quiz Title (Optional)"
                    placeholder="Leave blank to auto-generate"
                    value={quizTitle}
                    onChange={(e) => setQuizTitle(e.currentTarget.value)}
                    data-autofocus
                  />
                  <Select
                    label="Save to Quiz Group (Optional)"
                    placeholder="Select a quiz group"
                    data={[
                      { value: 'new', label: '+ Create New Quiz Group' },
                      ...quizGroups.map(qg => ({ value: qg.id.toString(), label: qg.name }))
                    ]}
                    value={selectedQuizGroup}
                    onChange={(val) => {
                      if (val === 'new') {
                        openCreateQuizGroup();
                        return;
                      }
                      setSelectedQuizGroup(val);
                    }}
                    clearable
                  />
                </Stack>
              </Paper>

              <Paper withBorder p="sm" radius="md">
                <Text size="sm" fw={500} mb="xs">Quiz Context</Text>
                <Stack spacing="sm">
                  <Select
                    label="Select Group"
                    placeholder="Choose group"
                    data={groups
                      .map(g => ({ value: g.id.toString(), label: g.name }))
                      .sort((a, b) => a.label.localeCompare(b.label))
                    }
                    value={selectedGroup}
                    onChange={(val) => {
                      setSelectedGroup(val);
                      setSelectedSubject('');
                      setSelectedNote('');
                    }}
                  />
                  <Select
                    label="Select Subject"
                    placeholder="Whole Group or pick a Subject"
                    data={[
                      { value: 'all', label: 'Whole Group (All Subjects)' },
                      ...subjects
                         .filter(s => s.group_id?.toString() === selectedGroup)
                         .map(s => ({ value: s.id.toString(), label: s.name }))
                         .sort((a, b) => a.label.localeCompare(b.label))
                    ]}
                    value={selectedSubject}
                    onChange={(val) => {
                      setSelectedSubject(val);
                      setSelectedNote('');
                    }}
                    disabled={!selectedGroup}
                  />
                  <Select
                    label="Select Note"
                    placeholder="Whole Subject or pick a Note"
                    data={[
                      { value: 'all', label: 'Whole Subject (All Notes)' },
                      ...notes
                         .filter(n => n.subject_id?.toString() === selectedSubject)
                         .map(n => ({ value: n.id.toString(), label: n.title }))
                         .sort((a, b) => a.label.localeCompare(b.label))
                    ]}
                    value={selectedNote}
                    onChange={setSelectedNote}
                    disabled={!selectedSubject || selectedSubject === 'all'}
                  />
                </Stack>
              </Paper>

              <Paper withBorder p="sm" radius="md">
                <Text size="sm" fw={500} mb="xs">Question Parameters</Text>
                <Stack spacing="sm">
                  <MultiSelect
                    label="Question Types"
                    placeholder="Select types"
                    data={[
                      { value: 'mixed', label: 'Mixed' },
                      { value: 'objective', label: 'Multiple Choice' },
                      { value: 'subjective', label: 'Short Answer' },
                      { value: 'fill_in_the_blank', label: 'Fill in the Blank' },
                    ]}
                    value={questionTypes}
                    onChange={handleQuestionTypeChange}
                    clearable
                  />
                  <NumberInput
                    label="Number of Questions"
                    value={numQuestions}
                    onChange={setNumQuestions}
                    min={1}
                    max={50}
                  />
                </Stack>
              </Paper>

              <Button mt="md" fullWidth color="pink" onClick={handleGenerateQuiz} loading={generating} leftSection={<IconBolt size={16} />}>
                {generating ? 'Generating AI Quiz...' : 'Generate Quiz'}
              </Button>
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="import">
            <Stack spacing="md">
              <Paper withBorder p="sm" radius="md">
                <Text size="sm" fw={500} mb="xs">Quiz Info</Text>
                <Stack spacing="sm">
                  <TextInput
                    label="Quiz Title (Optional)"
                    placeholder="E.g. Biology Notes Quiz"
                    value={quizTitle}
                    onChange={(e) => setQuizTitle(e.currentTarget.value)}
                  />
                  <Select
                    label="Save to Quiz Group (Optional)"
                    placeholder="Select a quiz group"
                    data={[
                      { value: 'new', label: '+ Create New Quiz Group' },
                      ...quizGroups.map(qg => ({ value: qg.id.toString(), label: qg.name }))
                    ]}
                    value={selectedQuizGroup}
                    onChange={(val) => {
                      if (val === 'new') {
                        openCreateQuizGroup();
                        return;
                      }
                      setSelectedQuizGroup(val);
                    }}
                    clearable
                  />
                </Stack>
              </Paper>

              <Paper withBorder p="sm" radius="md">
                <Text size="sm" fw={500} mb="xs">Import Source</Text>
                <Stack spacing="sm">
                  <Textarea
                    label="Paste Text Content"
                    placeholder="Paste your questions and answers here..."
                    minRows={4}
                    value={importText}
                    onChange={(e) => setImportText(e.currentTarget.value)}
                  />
                  <FileInput
                    label="Upload Files (PDF, PPTX, Images)"
                    placeholder="Select files"
                    multiple
                    value={importFiles}
                    onChange={setImportFiles}
                  />
                  <Checkbox
                    label="Generate Missing Answers via AI"
                    checked={generateAnswers}
                    onChange={(event) => setGenerateAnswers(event.currentTarget.checked)}
                    mt="sm"
                  />
                </Stack>
              </Paper>

              <Button mt="md" fullWidth color="pink" onClick={handleImportQuiz} loading={importing} leftSection={<IconFileImport size={16} />}>
                {importing ? 'Importing Quiz...' : 'Import Quiz'}
              </Button>
            </Stack>
          </Tabs.Panel>
        </Tabs>
      </Modal>

      {/* Nested Create Quiz Group Modal */}
      <Modal opened={createQuizGroupOpened} onClose={closeCreateQuizGroup} title="Create Quiz Group" size="sm" zIndex={2000}>
        <Stack spacing="sm">
          <TextInput
            label="Group Name"
            placeholder="e.g., Final Exams 2026"
            value={newQuizGroupName}
            onChange={(e) => setNewQuizGroupName(e.currentTarget.value)}
            data-autofocus
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeCreateQuizGroup}>Cancel</Button>
            <Button color="pink" onClick={handleCreateQuizGroup} loading={creatingQuizGroup}>Create</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
