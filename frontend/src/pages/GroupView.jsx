import { useState, useEffect, useMemo } from 'react';
import { Box, Title, Text, Group, Card, Button, Badge, ActionIcon, Center, Loader, SimpleGrid, Modal, TextInput, Textarea, ColorInput, Stack, Menu, Select } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconTrash, IconEdit, IconUpload, IconPlus, IconFiles, IconDotsVertical, IconSearch, IconArrowsSort, IconChevronLeft, IconCheck } from '@tabler/icons-react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchApi } from '../lib/api';

const generateContrastingColor = () => {
  const h = Math.floor(Math.random() * 360) / 360;
  const s = (55 + Math.floor(Math.random() * 30)) / 100;
  const l = (35 + Math.floor(Math.random() * 25)) / 100;

  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs((h * 6) % 2 - 1));
  const m = l - c / 2;

  let r = 0, g = 0, b = 0;
  const hi = Math.floor(h * 6);
  if (hi === 0) { r = c; g = x; b = 0; }
  else if (hi === 1) { r = x; g = c; b = 0; }
  else if (hi === 2) { r = 0; g = c; b = x; }
  else if (hi === 3) { r = 0; g = x; b = c; }
  else if (hi === 4) { r = x; g = 0; b = c; }
  else { r = c; g = 0; b = x; }

  const hex = (v) => Math.round((v + m) * 255).toString(16).padStart(2, '0');
  return `#${hex(r)}${hex(g)}${hex(b)}`;
};

export default function GroupView() {
  const { id } = useParams();
  const navigate = useNavigate();
  
  const [group, setGroup] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Group Edit Modals
  const [editGroupModalOpened, { open: openEditGroupModal, close: closeEditGroupModal }] = useDisclosure(false);
  const [deleteGroupModalOpened, { open: openDeleteGroupModal, close: closeDeleteGroupModal }] = useDisclosure(false);
  const [editGroupName, setEditGroupName] = useState('');

  // Add Subject Modal
  const [subjectModalOpened, { open: openSubjectModal, close: closeSubjectModal }] = useDisclosure(false);
  const [deleteSubjectModalOpened, { open: openDeleteSubjectModal, close: closeDeleteSubjectModal }] = useDisclosure(false);
  const [newSubjectName, setNewSubjectName] = useState('');
  const [newSubjectDesc, setNewSubjectDesc] = useState('');
  const [newSubjectColor, setNewSubjectColor] = useState(generateContrastingColor());
  const [editingSubject, setEditingSubject] = useState(null);
  const [subjectToDelete, setSubjectToDelete] = useState(null);

  const [search, setSearch] = useState('');
  const [sort, setSort] = useState(
    localStorage.getItem('smartnotes_sort_pref') || 
    JSON.parse(localStorage.getItem('user') || '{}').sort_preference || 
    'name_asc'
  );

  const filteredSubjects = useMemo(() => {
    let result = [...subjects];
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(s => 
        s.name.toLowerCase().includes(q) || 
        (s.description && s.description.toLowerCase().includes(q))
      );
    }
    
    result.sort((a, b) => {
      if (sort === 'name_asc') return a.name.localeCompare(b.name);
      if (sort === 'name_desc') return b.name.localeCompare(a.name);
      if (sort === 'date_desc') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      if (sort === 'date_asc') return new Date(a.created_at || 0) - new Date(b.created_at || 0);
      return 0;
    });
    
    return result;
  }, [subjects, search, sort]);

  const loadData = async () => {
    try {
      const [groupsData, allSubjects] = await Promise.all([
        fetchApi('/groups'),
        fetchApi('/subjects')
      ]);
      
      let currentGroup;
      if (id === 'ungrouped') {
        currentGroup = { id: 'ungrouped', name: 'Ungrouped Subjects' };
      } else {
        currentGroup = (groupsData || []).find(g => g.id.toString() === id);
      }
      setGroup(currentGroup);
      
      if (id === 'ungrouped') {
        setSubjects((allSubjects || []).filter(s => !s.group_id));
      } else {
        setSubjects((allSubjects || []).filter(s => s.group_id?.toString() === id));
      }
    } catch (err) {
      console.error("Failed to load group data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    fetchApi('/auth/me').then(data => {
      if (data && data.sort_preference) {
        setSort(data.sort_preference);
        localStorage.setItem('smartnotes_sort_pref', data.sort_preference);
      }
    }).catch(err => console.error("Failed to load user preferences", err));
  }, [id]);

  const handleEditGroupClick = () => {
    setEditGroupName(group.name);
    openEditGroupModal();
  };

  const handleUpdateGroup = async () => {
    if (!editGroupName.trim() || id === 'ungrouped') return;
    setSubmitting(true);
    try {
      const res = await fetchApi(`/groups/${group.id}`, {
        method: 'PUT',
        body: JSON.stringify({ name: editGroupName.trim() })
      });
      setGroup(res);
      closeEditGroupModal();
    } catch (err) {
      alert("Failed to update group: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteGroup = async () => {
    if (id === 'ungrouped') return;
    setSubmitting(true);
    try {
      await fetchApi(`/groups/${group.id}`, { method: 'DELETE' });
      closeDeleteGroupModal();
      navigate('/mynotes');
    } catch (err) {
      alert("Failed to delete group: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddSubjectClick = () => {
    setEditingSubject(null);
    setNewSubjectName('');
    setNewSubjectDesc('');
    setNewSubjectColor(generateContrastingColor());
    openSubjectModal();
  };

  const handleEditSubjectClick = (subject) => {
    setEditingSubject(subject);
    setNewSubjectName(subject.name);
    setNewSubjectDesc(subject.description || '');
    setNewSubjectColor(subject.color || '#593C8F');
    openSubjectModal();
  };

  const handleDeleteSubjectClick = (subject) => {
    setSubjectToDelete(subject);
    openDeleteSubjectModal();
  };

  const handleCreateOrUpdateSubject = async () => {
    if (!newSubjectName.trim()) return;
    setSubmitting(true);
    try {
      if (editingSubject) {
        await fetchApi(`/subjects/${editingSubject.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: newSubjectName.trim(),
            description: newSubjectDesc.trim(),
            color: newSubjectColor
          })
        });
      } else {
        await fetchApi('/subjects', {
          method: 'POST',
          body: JSON.stringify({
            name: newSubjectName.trim(),
            description: newSubjectDesc.trim(),
            color: newSubjectColor,
            group_id: id === 'ungrouped' ? null : id
          })
        });
      }
      closeSubjectModal();
      loadData();
    } catch (err) {
      alert("Failed to save subject: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const executeDeleteSubject = async () => {
    if (!subjectToDelete) return;
    setSubmitting(true);
    try {
      await fetchApi(`/subjects/${subjectToDelete.id}`, { method: 'DELETE' });
      closeDeleteSubjectModal();
      setSubjectToDelete(null);
      loadData();
    } catch (err) {
      alert("Failed to delete subject: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!group) {
    return (
      <Center h="50vh">
        <Text c="dimmed">Group not found.</Text>
      </Center>
    );
  }

  return (
    <Box>
      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20, margin: '-16px -16px 20px -16px' }}>
        <Group justify="space-between">
          <Group>
            <ActionIcon variant="subtle" color="gray" onClick={() => navigate(-1)}>
              <IconChevronLeft size={20} />
            </ActionIcon>
            <Group gap="xs" ml="xs">
              <Text size="sm" fw={500} c="dimmed" style={{ cursor: 'pointer' }} onClick={() => navigate('/mynotes')}>Notes</Text>
            </Group>
          </Group>
        </Group>
      </Box>

      {/* Desktop Header */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" visibleFrom="sm">
        <Box>
          <Title order={1} style={{ fontSize: 'clamp(1.3rem, 4vw, 2rem)' }}>{group.name}</Title>
          <Text c="dimmed">{subjects.length} Subjects</Text>
        </Box>
        <Group gap="xs" wrap="wrap">
          {id !== 'ungrouped' && (
            <>
              <ActionIcon variant="light" color="gray" size="lg" title="Edit Group" onClick={handleEditGroupClick}>
                <IconEdit size={18} />
              </ActionIcon>
              <ActionIcon variant="light" color="red" size="lg" title="Delete Group" onClick={openDeleteGroupModal}>
                <IconTrash size={18} />
              </ActionIcon>
            </>
          )}
          <Button leftSection={<IconPlus size={16} />} onClick={handleAddSubjectClick} variant="light" size="sm">
            Add Subject
          </Button>
        </Group>
      </Group>

      {/* Desktop Controls */}
      <Group mb="xl" align="flex-end" wrap="wrap" gap="sm" visibleFrom="sm">
        <TextInput
          placeholder="Search subjects..."
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
        <Title order={1} style={{ fontSize: 'clamp(1.8rem, 7vw, 2.8rem)', marginBottom: 16 }}>{group.name}</Title>
        <Group gap="xs" mb="md" justify="flex-start">
          <Button leftSection={<IconPlus size={16} />} onClick={handleAddSubjectClick} variant="light" size="sm">
            Create
          </Button>
          {id !== 'ungrouped' && (
            <>
              <ActionIcon variant="light" color="gray" size="lg" title="Edit Group" onClick={handleEditGroupClick}>
                <IconEdit size={18} />
              </ActionIcon>
              <ActionIcon variant="light" color="red" size="lg" title="Delete Group" onClick={openDeleteGroupModal}>
                <IconTrash size={18} />
              </ActionIcon>
            </>
          )}
        </Group>
        <Group gap="xs" wrap="nowrap">
          <TextInput
            placeholder="Search subjects..."
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

      {filteredSubjects.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
          {filteredSubjects.map((subject) => (
            <Card
              key={subject.id}
              shadow="sm"
              padding="md"
              radius="md"
              withBorder
              onClick={() => navigate(`/subject/${subject.id}`)}
              style={{ cursor: 'pointer', borderLeft: `4px solid ${subject.color || '#228be6'}`, transition: 'transform 150ms ease', '&:hover': { transform: 'translateX(2px)' } }}
            >
              <Group justify="space-between" wrap="nowrap" align="center">
                <Box style={{ flex: 1 }}>
                  <Text fw={600} size="lg" c="#171738">
                    {subject.name}
                  </Text>
                  <Text size="sm" c="dimmed" mt={4}>
                    {subject.description || 'No description'}
                  </Text>
                </Box>
                
                <div onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon variant="subtle" color="gray" onClick={(e) => e.stopPropagation()}>
                          <IconDotsVertical size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => { handleEditSubjectClick(subject); }}>Edit Subject</Menu.Item>
                        <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => { handleDeleteSubjectClick(subject); }}>Delete Subject</Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </div>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      ) : (
        <Center h={200}>
          <Box ta="center">
            <IconFiles size={48} stroke={1.5} color="var(--mantine-color-gray-4)" />
            <Text c="dimmed" mt="sm">No subjects found in this group.</Text>
          </Box>
        </Center>
      )}

      {/* Modals */}
      <Modal opened={editGroupModalOpened} onClose={closeEditGroupModal} title="Edit Group" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleUpdateGroup(); }}>
          <Stack>
            <TextInput required label="Group Name" value={editGroupName} onChange={(e) => setEditGroupName(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeEditGroupModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteGroupModalOpened} onClose={closeDeleteGroupModal} title="Confirm Delete Group" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteGroup(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete <b>{group.name}</b>? This will permanently remove all associated subjects, notes, and quizzes.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteGroupModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete Group</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={subjectModalOpened} onClose={closeSubjectModal} title={editingSubject ? "Edit Subject" : "Add New Subject"} centered>
        <form onSubmit={(e) => { e.preventDefault(); handleCreateOrUpdateSubject(); }}>
          <Stack>
            <TextInput required label="Subject Name" placeholder="e.g. Mathematics" value={newSubjectName} onChange={(e) => setNewSubjectName(e.currentTarget.value)} data-autofocus />
            <Textarea label="Description" placeholder="Optional details..." value={newSubjectDesc} onChange={(e) => setNewSubjectDesc(e.currentTarget.value)} rows={3} />
            <ColorInput label="Color Tag" value={newSubjectColor} onChange={setNewSubjectColor} format="hex" />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeSubjectModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>{editingSubject ? "Save Changes" : "Create Subject"}</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteSubjectModalOpened} onClose={closeDeleteSubjectModal} title="Confirm Delete Subject" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteSubject(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete the subject <b>{subjectToDelete?.name}</b>? This will permanently remove all associated notes and quizzes.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteSubjectModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete Subject</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Box>
  );
}
