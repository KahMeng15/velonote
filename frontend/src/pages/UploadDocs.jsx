import { useState, useEffect } from 'react';
import { Box, Title, Text, Select, Button, Stack, Group, Progress, SimpleGrid, Card, SegmentedControl, Switch } from '@mantine/core';
import { IconUpload, IconFile, IconX } from '@tabler/icons-react';
import { Dropzone, PDF_MIME_TYPE, IMAGE_MIME_TYPE, MS_POWERPOINT_MIME_TYPE } from '@mantine/dropzone';
import { fetchApi, notifyTaskStarted } from '../lib/api';
import { useNavigate, useSearchParams } from 'react-router-dom';

export default function UploadDocs() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialGroupId = searchParams.get('group_id');
  const initialSubjectId = searchParams.get('subject_id');
  const initialType = searchParams.get('type') === 'exercise' ? 'exercise' : 'resource';

  const [groups, setGroups] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(initialGroupId || null);
  const [selectedSubject, setSelectedSubject] = useState(initialSubjectId || null);
  const [uploadType, setUploadType] = useState(initialType);
  const [files, setFiles] = useState([]);
  const [useAiPolish, setUseAiPolish] = useState(false);
  
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [groupsData, subjectsData] = await Promise.all([
          fetchApi('/groups'),
          fetchApi('/subjects')
        ]);
        
        const fetchedGroups = groupsData || [];
        const fetchedSubjects = subjectsData || [];
        
        setGroups(fetchedGroups);
        setSubjects(fetchedSubjects);
        
        // Auto-select subject's group if subject is pre-selected from URL
        if (initialSubjectId) {
          const match = fetchedSubjects.find(s => s.id.toString() === initialSubjectId);
          if (match && match.group_id) {
            setSelectedGroup(match.group_id.toString());
          }
        } else if (initialGroupId && fetchedSubjects.length > 0) {
          const groupSubjects = fetchedSubjects.filter(s => s.group_id && s.group_id.toString() === initialGroupId);
          if (groupSubjects.length > 0) {
            setSelectedSubject(groupSubjects[0].id.toString());
          }
        }
      } catch (err) {
        console.error("Failed to load data", err);
      }
    };
    loadData();
  }, [initialGroupId, initialSubjectId]);

  // Handle group change: clear subject if it's not in the new group
  const handleGroupChange = (newGroupId) => {
    setSelectedGroup(newGroupId);
    const subjectStillValid = subjects.some(s => s.id.toString() === selectedSubject && s.group_id?.toString() === newGroupId);
    if (!subjectStillValid) {
      setSelectedSubject(null);
    }
  };

  const filteredSubjects = selectedGroup 
    ? subjects.filter(s => s.group_id?.toString() === selectedGroup)
    : subjects;

  const handleUpload = async () => {
    if (!selectedSubject || files.length === 0) {
      setError("Please select a subject and at least one file.");
      return;
    }

    setUploading(true);
    setError(null);
    setProgress(20);

    try {
      if (uploadType === 'exercise') {
        const exerciseIds = [];
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          const formData = new FormData();
          formData.append('subject_id', selectedSubject);
          formData.append('file', file);

          const res = await fetchApi('/exercises/upload', {
            method: 'POST',
            body: formData,
          });
          notifyTaskStarted();
          if (res && res.id) exerciseIds.push(res.id);
          setProgress(Math.round(20 + (80 * (i + 1) / files.length)));
        }
        setProgress(100);
        setTimeout(() => {
          if (exerciseIds.length === 1) {
            navigate(`/exercises/${exerciseIds[0]}`);
          } else {
            navigate(`/subject/${selectedSubject}/exercise`);
          }
        }, 800);
      } else {
        const formData = new FormData();
        formData.append('subject_id', selectedSubject);
        formData.append('use_ai_polish', useAiPolish);
        files.forEach(file => {
          formData.append('files', file);
        });

        const res = await fetchApi('/resources/upload', {
          method: 'POST',
          body: formData,
        });
        notifyTaskStarted();

        setProgress(100);
        setTimeout(() => {
          if (res && res.length === 1 && res[0].id) {
            navigate(`/resource/${res[0].id}`);
          } else {
            navigate(`/subject/${selectedSubject}`);
          }
        }, 800);
      }

    } catch (err) {
      setError(err.message || 'Failed to upload document');
      setProgress(0);
    } finally {
      setUploading(false);
    }
  };

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  return (
    <Box h="100%" style={{ overflowX: 'hidden' }}>
      <Title order={2} mb="xs">Upload Files</Title>
      <Text c="dimmed" mb="lg">Upload study resources to generate smart notes, or worksheets to create interactive exercises.</Text>

      <Box>
        <Stack gap="lg">
          {error && <Text color="red" size="sm">{error}</Text>}

          <Box>
            <Text fw={500} size="sm" mb={5}>Upload As</Text>
            <SegmentedControl
              value={uploadType}
              onChange={setUploadType}
              data={[
                { label: 'Study Resource', value: 'resource' },
                { label: 'Exercise / Worksheet', value: 'exercise' },
              ]}
              fullWidth
            />
          </Box>
          
          <Stack gap="sm">
            <Select
              label="Group"
              placeholder="Filter by Group (Optional)"
              data={groups.map(g => ({ value: g.id.toString(), label: g.name }))}
              value={selectedGroup}
              onChange={handleGroupChange}
              searchable
              clearable
            />
            
            <Select
              label="Subject"
              placeholder="Choose a subject for this document"
              data={filteredSubjects.map(s => ({ value: s.id.toString(), label: s.name }))}
              value={selectedSubject}
              onChange={setSelectedSubject}
              searchable
              required
            />
          </Stack>

          <Box>
            <Text fw={500} size="sm" mb={3}>Files <Text component="span" c="red">*</Text></Text>
            <Dropzone
              onDrop={(acceptedFiles) => setFiles((curr) => [...curr, ...acceptedFiles])}
              onReject={() => setError("Some files were rejected. Ensure they are PDF, PPTX, or Images.")}
              accept={[...PDF_MIME_TYPE, ...IMAGE_MIME_TYPE, ...MS_POWERPOINT_MIME_TYPE]}
              mb="md"
            >
              <Group justify="center" gap="md" mih={120} style={{ pointerEvents: 'none', padding: 'clamp(16px, 4vw, 40px)' }}>
                <Dropzone.Accept>
                  <IconUpload size={40} color="var(--mantine-color-blue-6)" stroke={1.5} />
                </Dropzone.Accept>
                <Dropzone.Reject>
                  <IconX size={40} color="var(--mantine-color-red-6)" stroke={1.5} />
                </Dropzone.Reject>
                <Dropzone.Idle>
                  <IconFile size={40} color="var(--mantine-color-dimmed)" stroke={1.5} />
                </Dropzone.Idle>

                <div>
                  <Text size={{ base: 'md', sm: 'xl' }} inline>
                    Drag files here or click to select files
                  </Text>
                  <Text size="xs" c="dimmed" inline mt={7}>
                    {uploadType === 'exercise' ? "Attach PDFs, PPTXs, or Image files of worksheets/exams to process" : "Attach PDFs, PPTXs, or Image files to process"}
                  </Text>
                </div>
              </Group>
            </Dropzone>

            {files.length > 0 && (
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                {files.map((file, index) => (
                  <Card key={index} withBorder shadow="sm" radius="md" p="sm">
                    <Group justify="space-between" wrap="nowrap">
                      <Group wrap="nowrap" style={{ overflow: 'hidden' }}>
                        <IconFile size={24} color="gray" style={{ flexShrink: 0 }} />
                        <Text size="sm" truncate>{file.name}</Text>
                      </Group>
                      <Button variant="subtle" color="red" size="xs" onClick={() => removeFile(index)}>
                        Remove
                      </Button>
                    </Group>
                  </Card>
                ))}
              </SimpleGrid>
            )}
          </Box>

          {uploadType === 'resource' && (
            <Card withBorder radius="md" p="sm" bg="var(--mantine-color-default-hover)">
              <Switch
                label="AI Polish"
                description="Use AI to polish formatting and grammar. Off by default for fast, layout-accurate extraction."
                checked={useAiPolish}
                onChange={(e) => setUseAiPolish(e.currentTarget.checked)}
              />
            </Card>
          )}

          {uploading && (
            <Box mt="sm">
              <Text size="sm" mb={5}>Uploading...</Text>
              <Progress value={progress} animated striped />
            </Box>
          )}

          <Button 
            leftSection={<IconUpload size={16} />} 
            onClick={handleUpload}
            loading={uploading}
            disabled={!selectedSubject || files.length === 0}
            size="md"
            fullWidth
            mt="xl"
          >
            Upload
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}
