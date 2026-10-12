import { useState, useEffect, useMemo } from 'react';
import {
  Title,
  Text,
  Button,
  Group,
  TextInput,
  Select,
  Card,
  SimpleGrid,
  ActionIcon,
  Modal,
  ColorInput,
  Textarea,
  Stack,
  Box,
  Badge,
  Loader,
  Center,
  Menu,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconPlus,
  IconSearch,
  IconArrowsSort,
  IconEdit,
  IconTrash,
  IconFiles,
  IconDotsVertical,
  IconCheck,
  IconChevronLeft,
} from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { fetchApi } from '../lib/api';

export default function NotesManager() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState(
    localStorage.getItem('smartnotes_sort_pref') || 
    JSON.parse(localStorage.getItem('user') || '{}').sort_preference || 
    'name_asc'
  );
  
  const [groups, setGroups] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);

  // Modals
  const [groupModalOpened, { open: openGroupModal, close: closeGroupModal }] = useDisclosure(false);
  const [subjectModalOpened, { open: openSubjectModal, close: closeSubjectModal }] = useDisclosure(false);
  const [editGroupModalOpened, { open: openEditGroupModal, close: closeEditGroupModal }] = useDisclosure(false);
  const [deleteGroupModalOpened, { open: openDeleteGroupModal, close: closeDeleteGroupModal }] = useDisclosure(false);
  const [editingGroup, setEditingGroup] = useState(null);
  const [groupToDelete, setGroupToDelete] = useState(null);
  
  // Creation States
  const [newGroupName, setNewGroupName] = useState('');
  const [newSubjectName, setNewSubjectName] = useState('');
  const [newSubjectDesc, setNewSubjectDesc] = useState('');
  const [newSubjectColor, setNewSubjectColor] = useState('#593C8F');
  const [activeGroupId, setActiveGroupId] = useState(null);
  
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
    fetchApi('/auth/me').then(data => {
      if (data && data.sort_preference) {
        setSort(data.sort_preference);
        localStorage.setItem('smartnotes_sort_pref', data.sort_preference);
      }
    }).catch(err => console.error("Failed to load user preferences", err));
  }, []);

  const loadData = async () => {
    try {
      const [groupsData, subjectsData] = await Promise.all([
        fetchApi('/groups'),
        fetchApi('/subjects')
      ]);
      setGroups(groupsData || []);
      setSubjects(subjectsData || []);
    } catch (err) {
      console.error("Failed to load notes data", err);
    } finally {
      setLoading(false);
    }
  };

  const handleEditGroupClick = (group) => {
    setEditingGroup(group);
    setNewGroupName(group.name);
    openEditGroupModal();
  };

  const handleCreateOrEditGroup = async () => {
    if (!newGroupName.trim()) return;
    setSubmitting(true);
    try {
      if (editingGroup) {
        await fetchApi(`/groups/${editingGroup.id}`, {
          method: 'PUT',
          body: JSON.stringify({ name: newGroupName.trim() })
        });
        closeEditGroupModal();
      } else {
        await fetchApi('/groups', {
          method: 'POST',
          body: JSON.stringify({ name: newGroupName.trim() })
        });
        closeGroupModal();
      }
      setNewGroupName('');
      setEditingGroup(null);
      loadData();
    } catch (err) {
      alert("Failed to save group: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateSubject = async () => {
    if (!newSubjectName.trim()) return;
    setSubmitting(true);
    try {
      await fetchApi('/subjects', {
        method: 'POST',
        body: JSON.stringify({
          name: newSubjectName.trim(),
          description: newSubjectDesc.trim(),
          color: newSubjectColor,
          group_id: activeGroupId
        })
      });
      closeSubjectModal();
      loadData();
    } catch (err) {
      alert("Failed to create subject: " + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteClick = (group) => {
    setGroupToDelete(group);
    openDeleteGroupModal();
  };

  const executeDeleteGroup = async () => {
    if (!groupToDelete) return;
    setSubmitting(true);
    try {
      await fetchApi(`/groups/${groupToDelete.id}`, { method: 'DELETE' });
      closeDeleteGroupModal();
      setGroupToDelete(null);
      loadData();
    } catch (err) {
      alert('Failed to delete group: ' + err.message);
    } finally {
      setSubmitting(false);
    }
  };

  // Combine groups and subjects, filter, and sort
  const processedGroups = useMemo(() => {
    // 1. Combine
    let combined = groups.map(g => ({
      ...g,
      subjects: subjects.filter(s => s.group_id === g.id)
    }));

    // Add Ungrouped if there are subjects without a group
    const ungroupedSubjects = subjects.filter(s => !s.group_id);
    if (ungroupedSubjects.length > 0) {
      combined.push({
        id: 'ungrouped',
        name: 'Ungrouped Subjects',
        subjects: ungroupedSubjects
      });
    }

    // 2. Filter by search
    if (search.trim()) {
      const q = search.toLowerCase();
      combined = combined.map(g => ({
        ...g,
        subjects: g.subjects.filter(s => 
          s.name.toLowerCase().includes(q) || 
          (s.description && s.description.toLowerCase().includes(q))
        )
      })).filter(g => g.name.toLowerCase().includes(q) || g.subjects.length > 0);
    }

    // 3. Sort groups
    combined.sort((a, b) => {
      // Put ungrouped at the end
      if (a.id === 'ungrouped') return 1;
      if (b.id === 'ungrouped') return -1;
      
      if (sort === 'name_asc') return a.name.localeCompare(b.name);
      if (sort === 'name_desc') return b.name.localeCompare(a.name);
      if (sort === 'date_desc') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      if (sort === 'date_asc') return new Date(a.created_at || 0) - new Date(b.created_at || 0);
      return 0;
    });

    return combined;
  }, [groups, subjects, search, sort]);

  if (loading) {
    return (
      <Center h="50vh">
        <Loader size="lg" />
      </Center>
    );
  }

  return (
    <Box>
      {/* Sticky Header */}
      <Box py="xs" px="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)', backgroundColor: '#fff', zIndex: 20, margin: '-16px -16px 20px -16px' }}>
        <Group>
          <ActionIcon variant="subtle" color="gray" onClick={() => navigate(-1)}>
            <IconChevronLeft size={20} />
          </ActionIcon>
        </Group>
      </Box>

      {/* Desktop Header */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" visibleFrom="sm">
        <Title order={1} fw={800} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738', fontSize: 'clamp(1.5rem, 5vw, 2.5rem)' }}>My Notes</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => { setNewGroupName(''); openGroupModal(); }} size="sm">
          Create Group
        </Button>
      </Group>

      {/* Desktop Controls */}
      <Group mb="xl" align="flex-end" wrap="wrap" gap="sm" visibleFrom="sm">
        <TextInput
          placeholder="Search groups, subjects..."
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
        <Title order={1} fw={800} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738', fontSize: 'clamp(1.8rem, 7vw, 2.8rem)', marginBottom: 16 }}>My Notes</Title>
        <Group gap="xs" mb="md" justify="flex-start">
          <Button leftSection={<IconPlus size={16} />} onClick={() => { setNewGroupName(''); openGroupModal(); }} size="sm">
            Create
          </Button>
        </Group>
        <Group gap="xs" wrap="nowrap">
          <TextInput
            placeholder="Search groups, subjects..."
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

      {/* Groups Grid */}
      {processedGroups.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg">
          {processedGroups.map((group) => (
            <Card
              key={group.id}
              shadow="sm"
              padding="lg"
              radius="md"
              withBorder
              onClick={() => navigate(`/group/${group.id}`)}
              style={{ cursor: 'pointer', transition: 'transform 150ms ease', '&:hover': { transform: 'translateY(-2px)' } }}
            >
              <Group justify="space-between" wrap="nowrap" mb="xs">
                <Title order={3} fw={700} c="#171738" style={{ fontFamily: 'Instrument Sans, sans-serif' }}>
                  {group.name}
                </Title>
              </Group>

              <Text size="sm" c="dimmed" style={{ minHeight: '3rem' }}>
                {group.subjects.length} Subjects inside
              </Text>

              <Group mt="md" justify="space-between">
                <Badge leftSection={<IconFiles size={12} />} variant="light">
                  View Subjects
                </Badge>
                {group.id !== 'ungrouped' && (
                  <div onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon variant="subtle" color="gray" onClick={(e) => e.stopPropagation()}>
                          <IconDotsVertical size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => { handleEditGroupClick(group); }}>Edit Group</Menu.Item>
                        <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => { handleDeleteClick(group); }}>Delete Group</Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </div>
                )}
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      ) : (
        <Center h={200}>
          <Stack align="center">
            <IconFiles size={48} color="var(--mantine-color-gray-4)" />
            <Text c="dimmed">No groups found.</Text>
            <Button onClick={() => { setNewGroupName(''); openGroupModal(); }}>Create your first Group</Button>
          </Stack>
        </Center>
      )}

      {/* Modals */}
      <Modal opened={groupModalOpened} onClose={closeGroupModal} title="Create New Group" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleCreateOrEditGroup(); }}>
          <Stack>
            <TextInput required label="Group Name" placeholder="e.g. Semester 1, Year 2" value={newGroupName} onChange={(e) => setNewGroupName(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeGroupModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Create Group</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={editGroupModalOpened} onClose={closeEditGroupModal} title="Edit Group" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleCreateOrEditGroup(); }}>
          <Stack>
            <TextInput required label="Group Name" value={newGroupName} onChange={(e) => setNewGroupName(e.currentTarget.value)} data-autofocus />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeEditGroupModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Save Changes</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={subjectModalOpened} onClose={closeSubjectModal} title="Add New Subject" centered>
        <form onSubmit={(e) => { e.preventDefault(); handleCreateSubject(); }}>
          <Stack>
            <TextInput required label="Subject Name" placeholder="e.g. Calculus I" value={newSubjectName} onChange={(e) => setNewSubjectName(e.currentTarget.value)} data-autofocus />
            <Textarea label="Description (Optional)" placeholder="Brief overview" value={newSubjectDesc} onChange={(e) => setNewSubjectDesc(e.currentTarget.value)} rows={3} />
            <ColorInput label="Color Tag" value={newSubjectColor} onChange={setNewSubjectColor} format="hex" />
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeSubjectModal}>Cancel</Button>
              <Button type="submit" loading={submitting}>Add Subject</Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      <Modal opened={deleteGroupModalOpened} onClose={closeDeleteGroupModal} title="Confirm Delete" centered>
        <form onSubmit={(e) => { e.preventDefault(); executeDeleteGroup(); }}>
          <Stack>
            <Text size="sm">Are you sure you want to delete the group <b>{groupToDelete?.name}</b>? This action cannot be undone.</Text>
            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDeleteGroupModal}>Cancel</Button>
              <Button type="submit" color="red" loading={submitting} data-autofocus>Delete Group</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Box>
  );
}
