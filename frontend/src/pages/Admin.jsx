import { useState, useEffect } from 'react';
import { Container, Title, Tabs, Table, Button, Group, Badge, Modal, Select, TextInput, NumberInput, Switch, Stack, Paper, Text, ScrollArea, Box, Radio, Divider, Textarea, SimpleGrid, Tooltip } from '@mantine/core';
import { useNavigate } from 'react-router-dom';
import { useMediaQuery } from '@mantine/hooks';
import { fetchApi, notifyTaskStarted } from '../lib/api';
import { IconShieldCheck, IconUsers, IconMail, IconStack2, IconSettings, IconClock, IconServer, IconListDetails, IconDatabase, IconActivity, IconMessages, IconTrash, IconRefresh, IconEye, IconUserCheck, IconDownload, IconFileDatabase } from '@tabler/icons-react';

const sectionTabsConfig = [
  { value: 'groups', label: 'Groups' },
  { value: 'subjects', label: 'Subjects' },
  { value: 'resources', label: 'Resources' },
  { value: 'exercises', label: 'Exercises' },
  { value: 'notes', label: 'Notes' },
  { value: 'conversations', label: 'Conversations' },
  { value: 'tasks', label: 'Tasks' },
];

function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tierModalOpen, setTierModalOpen] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [newTier, setNewTier] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [resetting, setResetting] = useState(null);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await fetchApi('/admin/users');
      setUsers(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadUsers(); }, []);

  const handleAction = async (userId, action, value = null) => {
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, action, value })
      });
      loadUsers();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleTierChange = async () => {
    if (!newTier || !selectedUser) return;
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: selectedUser.id, action: 'tier', value: newTier })
      });
      setTierModalOpen(false);
      loadUsers();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleSendResetLink = async (user) => {
    if (!confirm(`Send password reset email to ${user.email}?`)) return;
    setResetting(user.id);
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: user.id, action: 'send_reset_link' })
      });
      alert(`Reset link sent to ${user.email}`);
    } catch (e) {
      alert(e.message);
    } finally {
      setResetting(null);
    }
  };

  const handleEmailChange = async () => {
    if (!newEmail || !selectedUser) return;
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: selectedUser.id, action: 'change_email', value: newEmail })
      });
      setEmailModalOpen(false);
      setNewEmail('');
      loadUsers();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleDelete = async () => {
    if (!selectedUser) return;
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: selectedUser.id, action: 'delete' })
      });
      setDeleteModalOpen(false);
      loadUsers();
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <Stack>
      <Title order={3}>Users Management</Title>
      <ScrollArea>
        <Table striped highlightOnHover horizontalSpacing={isMobile ? 'xs' : 'sm'}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Notes/Subj/Grp</Table.Th>
              <Table.Th>Tier</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.map(u => (
              <Table.Tr key={u.id}>
                <Table.Td>{u.id}</Table.Td>
                <Table.Td>{u.email}</Table.Td>
                <Table.Td>{u.notes_count} / {u.subjects_count} / {u.groups_count}</Table.Td>
                <Table.Td><Badge color={u.tier === 'pro' ? 'blue' : u.tier === 'unlimited' ? 'grape' : 'gray'}>{u.tier}</Badge></Table.Td>
                <Table.Td>
                  {u.is_active ? <Text c="green" size="sm">Active</Text> : <Text c="red" size="sm">Inactive</Text>}
                  {u.is_admin && <Text size="xs">Admin</Text>}
                  {!u.is_approved && <Badge color="yellow" size="sm" mt={2}>Pending</Badge>}
                  {u.google_oauth_id && <Badge size="sm" mt={2} variant="outline">Google</Badge>}
                </Table.Td>
                <Table.Td>
                  <Group gap={isMobile ? 4 : 'xs'} wrap="wrap">
                    <Button size="xs" variant="outline" onClick={() => { setSelectedUser(u); setNewTier(u.tier); setTierModalOpen(true); }}>Tier</Button>
                    {u.is_active ? (
                      <Button size="xs" color="red" variant="light" onClick={() => handleAction(u.id, 'deactivate')}>Deactivate</Button>
                    ) : (
                      <Button size="xs" color="green" variant="light" onClick={() => handleAction(u.id, 'activate')}>Activate</Button>
                    )}
                    {u.is_approved ? (
                      <Button size="xs" color="yellow" variant="light" onClick={() => handleAction(u.id, 'unapprove')}>Unapprove</Button>
                    ) : null}
                    <Button size="xs" variant="light" loading={resetting === u.id} onClick={() => handleSendResetLink(u)}>Reset Pwd</Button>
                    <Button size="xs" variant="light" onClick={() => { setSelectedUser(u); setNewEmail(''); setEmailModalOpen(true); }}>Email</Button>
                    <Button size="xs" color="red" variant="subtle" onClick={() => { setSelectedUser(u); setDeleteModalOpen(true); }}>Delete</Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <Modal opened={tierModalOpen} onClose={() => setTierModalOpen(false)} title="Change User Tier" fullScreen={isMobile}>
        <Stack>
          <TextInput label="User Email" value={selectedUser?.email || ''} disabled />
          <Select label="New Tier" value={newTier} onChange={setNewTier} data={[
            {value: 'unlimited', label: 'Unlimited'},
            {value: 'pro', label: 'Pro'},
            {value: 'early_tester', label: 'Early Testers'},
            {value: 'free', label: 'Free'}
          ]} />
          <Button onClick={handleTierChange}>Update Tier</Button>
        </Stack>
      </Modal>

      <Modal opened={emailModalOpen} onClose={() => setEmailModalOpen(false)} title="Change Email Address" fullScreen={isMobile}>
        <Stack>
          <TextInput label="Current Email" value={selectedUser?.email || ''} disabled />
          <TextInput
            label="New Email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.currentTarget.value)}
            placeholder="new@email.com"
            required
          />
          <Button onClick={handleEmailChange}>Update Email</Button>
        </Stack>
      </Modal>

      <Modal opened={deleteModalOpen} onClose={() => setDeleteModalOpen(false)} title="Delete User Account" fullScreen={isMobile}>
        <Stack>
          <Text size="sm" c="red" fw={600}>This action cannot be undone.</Text>
          <TextInput label="User Email" value={selectedUser?.email || ''} disabled />
          <Text size="sm" c="dimmed">This will permanently delete the user account and all associated data.</Text>
          <Group>
            <Button color="gray" variant="outline" onClick={() => setDeleteModalOpen(false)}>Cancel</Button>
            <Button color="red" onClick={handleDelete}>Delete Account</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function AdminPendingApprovals() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(null);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadPending = async () => {
    setLoading(true);
    try {
      const data = await fetchApi('/admin/users');
      setUsers(data.filter(u => !u.is_approved));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadPending(); }, []);

  const handleApprove = async (userId) => {
    setApproving(userId);
    try {
      await fetchApi('/admin/users/action', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, action: 'approve' })
      });
      loadPending();
    } catch (e) {
      alert(e.message);
    } finally {
      setApproving(null);
    }
  };

  return (
    <Stack>
      <Title order={3}>Pending Approvals</Title>
      {loading ? (
        <Text c="dimmed" size="sm">Loading...</Text>
      ) : users.length === 0 ? (
        <Text c="dimmed" size="sm">No pending approval requests.</Text>
      ) : (
        <ScrollArea>
          <Table striped highlightOnHover horizontalSpacing={isMobile ? 'xs' : 'sm'}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>ID</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Name</Table.Th>
                <Table.Th>Nickname</Table.Th>
                <Table.Th>Verified</Table.Th>
                <Table.Th>Actions</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {users.map(u => (
                <Table.Tr key={u.id}>
                  <Table.Td>{u.id}</Table.Td>
                  <Table.Td>{u.email}</Table.Td>
                  <Table.Td>{u.full_name || '-'}</Table.Td>
                  <Table.Td>{u.nickname || '-'}</Table.Td>
                  <Table.Td>
                    <Badge color={u.is_verified ? 'green' : 'yellow'} size="sm">
                      {u.is_verified ? 'Verified' : 'Not verified'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Button
                      size="xs"
                      color="green"
                      loading={approving === u.id}
                      onClick={() => handleApprove(u.id)}
                    >
                      Approve
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </Stack>
  );
}

function AdminInvitations() {
  const [invites, setInvites] = useState([]);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [resultLink, setResultLink] = useState('');
  const [resultMessage, setResultMessage] = useState('');
  const [labelModalOpen, setLabelModalOpen] = useState(false);
  const [editingInvite, setEditingInvite] = useState(null);
  const [editLabel, setEditLabel] = useState('');
  const [inviteMethod, setInviteMethod] = useState('email');
  const [email, setEmail] = useState('');
  const [tier, setTier] = useState('free');
  const [inviteLabel, setInviteLabel] = useState('');
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadInvites = async () => {
    try {
      const data = await fetchApi('/admin/invitations');
      setInvites(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => { loadInvites(); }, []);

  const [revoking, setRevoking] = useState(null);

  const sendInvite = async () => {
    try {
      const sendEmail = inviteMethod === 'email';
      const payload = { tier, send_email: sendEmail, label: inviteLabel || undefined };
      if (sendEmail) payload.email = email;
      const res = await fetchApi('/admin/invitations', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setCreateModalOpen(false);
      setResultLink(res.invitation_link);
      if (sendEmail) {
        setResultMessage(`Invitation email sent to ${email}`);
      } else {
        setResultMessage('Shareable invitation link created');
      }
      setResultModalOpen(true);
      setInviteLabel('');
      setEmail('');
      loadInvites();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(resultLink).then(() => {
      alert('Link copied to clipboard');
    }).catch(() => {
      prompt('Copy this link:', resultLink);
    });
  };

  const handleRevoke = async (token) => {
    if (!confirm('Revoke this invitation? It will no longer be usable.')) return;
    setRevoking(token);
    try {
      await fetchApi(`/admin/invitations/${token}`, { method: 'DELETE' });
      loadInvites();
    } catch (e) {
      alert(e.message);
    } finally {
      setRevoking(null);
    }
  };

  const handleSaveLabel = async () => {
    if (!editingInvite) return;
    try {
      await fetchApi(`/admin/invitations/${editingInvite.token}`, {
        method: 'PUT',
        body: JSON.stringify({ label: editLabel || null })
      });
      setLabelModalOpen(false);
      setEditingInvite(null);
      loadInvites();
    } catch (e) {
      alert(e.message);
    }
  };

  const openLabelModal = (invite) => {
    setEditingInvite(invite);
    setEditLabel(invite.label || '');
    setLabelModalOpen(true);
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>Pending Invitations</Title>
        <Button onClick={() => setCreateModalOpen(true)}>New Invitation</Button>
      </Group>
      <ScrollArea>
        <Table striped horizontalSpacing={isMobile ? 'xs' : 'sm'}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Email</Table.Th>
              <Table.Th>Method</Table.Th>
              <Table.Th>Label</Table.Th>
              <Table.Th>Token</Table.Th>
              <Table.Th>Tier</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Used By</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {invites.map(i => (
              <Table.Tr key={i.token}>
                <Table.Td>{i.send_email ? i.email : 'Link only'}</Table.Td>
                <Table.Td>{i.send_email ? 'Email' : 'Link'}</Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    <Text size="sm" lineClamp={1}>{i.label || '—'}</Text>
                    <Button size="xs" variant="subtle" compact onClick={() => openLabelModal(i)}>
                      {i.label ? 'Edit' : 'Add'}
                    </Button>
                  </Group>
                </Table.Td>
                <Table.Td><Text size="xs" ff="mono">{i.token.substring(0, 8)}...</Text></Table.Td>
                <Table.Td>{i.tier}</Table.Td>
                <Table.Td>{i.is_used ? 'Used' : 'Pending'}</Table.Td>
                <Table.Td>
                  {i.is_used && i.accepted_by_email ? (
                    <Text size="sm" lineClamp={1}>{i.accepted_by_email}</Text>
                  ) : (
                    <Text size="sm" c="dimmed">—</Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    {!i.is_used && (
                      <Button size="xs" color="red" variant="subtle" loading={revoking === i.token} onClick={() => handleRevoke(i.token)}>Revoke</Button>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <Modal opened={createModalOpen} onClose={() => { setCreateModalOpen(false); setInviteLabel(''); }} title="Invite User" fullScreen={isMobile}>
        <Stack>
          <Radio.Group value={inviteMethod} onChange={setInviteMethod} label="Method">
            <Group>
              <Radio value="email" label="Send Email" />
              <Radio value="link" label="Shareable Link" />
            </Group>
          </Radio.Group>
          {inviteMethod === 'email' && (
            <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
          )}
          <Select label="Tier" value={tier} onChange={setTier} data={[
            {value: 'unlimited', label: 'Unlimited'},
            {value: 'pro', label: 'Pro'},
            {value: 'early_tester', label: 'Early Testers'},
            {value: 'free', label: 'Free'}
          ]} />
          <TextInput label="Label (optional)" value={inviteLabel} onChange={(e) => setInviteLabel(e.currentTarget.value)} placeholder="e.g. John's invite" />
          <Button onClick={sendInvite}>Create Invitation</Button>
        </Stack>
      </Modal>

      <Modal opened={resultModalOpen} onClose={() => setResultModalOpen(false)} title="Invitation Created" fullScreen={isMobile}>
        <Stack>
          <Text size="sm">{resultMessage}</Text>
          <TextInput label="Invitation Link" value={resultLink} readOnly />
          <Button onClick={handleCopyLink}>Copy Link</Button>
        </Stack>
      </Modal>

      <Modal opened={labelModalOpen} onClose={() => setLabelModalOpen(false)} title="Edit Invitation Label" fullScreen={isMobile}>
        <Stack>
          <TextInput label="Email" value={editingInvite?.email || ''} disabled />
          <TextInput label="Label" value={editLabel} onChange={(e) => setEditLabel(e.currentTarget.value)} placeholder="Optional label" />
          <Button onClick={handleSaveLabel}>Save</Button>
        </Stack>
      </Modal>
    </Stack>
  );
}

function AdminTiers() {
  const [tiers, setTiers] = useState([]);
  const [editValues, setEditValues] = useState({});
  const isMobile = useMediaQuery('(max-width: 48em)');
  
  const loadTiers = async () => {
    try {
      const data = await fetchApi('/admin/tiers');
      setTiers(data);
    } catch(e) {}
  };
  
  useEffect(() => { loadTiers(); }, []);

  const getEdit = (tierId, field) => {
    const key = `${tierId}_${field}`;
    if (key in editValues) return editValues[key];
    const t = tiers.find(t => t.id === tierId);
    if (!t) return 0;
    if (field === 'items_processed') return t.max_resources ?? 0;
    if (field === 'chat_messages') return t.max_conversations ?? 0;
    if (field === 'chat_reset_period') return t.conversations_reset_period || '';
    return t[field] ?? 0;
  };

  const setEdit = (tierId, field, value) => {
    setEditValues(prev => ({ ...prev, [`${tierId}_${field}`]: value }));
  };

  const saveTier = async (tierData) => {
    const payload = { ...tierData };
    const editableFields = ['max_resources', 'max_notes', 'max_subjects', 'max_groups', 'max_conversations', 'max_messages', 'max_storage_gb', 'max_exercises', 'notes_reset_period'];
    for (const field of editableFields) {
      const key = `${tierData.id}_${field}`;
      if (key in editValues) payload[field] = editValues[key];
    }
    // Items processed sets resources, notes, and exercises
    const ipKey = `${tierData.id}_items_processed`;
    if (ipKey in editValues) {
      const v = editValues[ipKey];
      payload.max_resources = v; payload.max_notes = v; payload.max_exercises = v;
    }
    // Chat messages numeric sets conversations and messages
    const cmKey = `${tierData.id}_chat_messages`;
    if (cmKey in editValues) {
      const v = editValues[cmKey];
      payload.max_conversations = v; payload.max_messages = v;
    }
    // Chat messages reset period -> both conversations and messages periods
    const crKey = `${tierData.id}_chat_reset_period`;
    if (crKey in editValues) {
      const v = editValues[crKey];
      payload.conversations_reset_period = v;
      payload.messages_reset_period = v;
    }
    try {
      await fetchApi(`/admin/tiers/${payload.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      alert('Tier updated!');
      setEditValues({});
      loadTiers();
    } catch(e) { alert(e.message); }
  };

  return (
    <Stack>
      <Title order={3}>Tier Configuration</Title>
      {tiers.map(t => (
          <Paper key={t.id} p="md" withBorder>
            <Title order={4} mb="md">{t.display_name}</Title>
            <Stack>
              <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
                <NumberInput label="Items Processed" value={getEdit(t.id, 'items_processed')} onChange={(v) => setEdit(t.id, 'items_processed', v)} />
                <NumberInput label="Chat Messages" value={getEdit(t.id, 'chat_messages')} onChange={(v) => setEdit(t.id, 'chat_messages', v)} />
                <NumberInput label="Subjects" value={getEdit(t.id, 'max_subjects')} onChange={(v) => setEdit(t.id, 'max_subjects', v)} />
                <NumberInput label="Groups" value={getEdit(t.id, 'max_groups')} onChange={(v) => setEdit(t.id, 'max_groups', v)} />
                <NumberInput label="Storage (GB)" value={getEdit(t.id, 'max_storage_gb')} onChange={(v) => setEdit(t.id, 'max_storage_gb', v)} />
              </SimpleGrid>
              <Divider label="Reset Periods (empty = lifetime)" labelPosition="center" />
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select label="Items Processed Reset" data={['', 'day', 'week', 'month']} value={getEdit(t.id, 'notes_reset_period') || ''} onChange={(v) => setEdit(t.id, 'notes_reset_period', v || null)} clearable />
                <Select label="Chat Messages Reset" data={['', 'day', 'week', 'month']} value={getEdit(t.id, 'chat_reset_period') || ''} onChange={(v) => setEdit(t.id, 'chat_reset_period', v || null)} clearable />
              </SimpleGrid>
              <Button onClick={() => saveTier(t)} fullWidth={isMobile}>Save</Button>
            </Stack>
          </Paper>
      ))}
    </Stack>
  );
}

function AdminSystemSettings() {
  const [s, setS] = useState({});
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadSettings = async () => {
    try {
      const data = await fetchApi('/admin/system-settings');
      setS(data);
    } catch(e) {}
  };
  useEffect(() => { loadSettings(); }, []);

  const [creatingBackup, setCreatingBackup] = useState(false);

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      const res = await fetchApi('/admin/backups/create', { method: 'POST' });
      alert(res.message || 'Backup created successfully!');
    } catch (e) {
      alert(`Backup failed: ${e.message}`);
    } finally {
      setCreatingBackup(false);
    }
  };

  const save = async () => {
    try {
      await fetchApi('/admin/system-settings', {
        method: 'PUT',
        body: JSON.stringify(s)
      });
      alert('Settings saved!');
    } catch(e) { alert(e.message); }
  };

  return (
    <Stack>
      <Title order={3}>System Settings</Title>
      <Paper p="md" withBorder>
        <Stack>
          <Switch label="Lockdown Mode" checked={s.lockdown_mode || false} onChange={(e) => setS({...s, lockdown_mode: e.currentTarget.checked})} />
          <Switch label="Maintenance Mode" checked={s.maintenance_mode || false} onChange={(e) => setS({...s, maintenance_mode: e.currentTarget.checked})} />
          <Select label="Signup Config" value={s.signup_config || 'open'} onChange={(v) => setS({...s, signup_config: v})} data={['open', 'approval', 'invite']} />
          <TextInput label="Domain URL" value={s.domain_url || ''} onChange={(e) => setS({...s, domain_url: e.currentTarget.value})} />
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Stack>
          <Title order={4}>Database Backups</Title>
          <Text size="xs" c="dimmed">
            Configure automated daily backup schedule. You can also view, download, and delete all SQL snapshots in the <strong>Database</strong> tab.
          </Text>
          <Switch label="Enable automatic backups" checked={s.backup_enabled !== false} onChange={(e) => setS({...s, backup_enabled: e.currentTarget.checked})} />
          <NumberInput label="Retention (days)" value={s.backup_retention_days || 7} min={1} max={365} onChange={(v) => setS({...s, backup_retention_days: v})} />
          <Group wrap="wrap">
            <Button onClick={save} fullWidth={isMobile}>Save Settings</Button>
            <Button
              variant="light"
              color="blue"
              onClick={handleCreateBackup}
              loading={creatingBackup}
              leftSection={<IconDatabase size={14} />}
              fullWidth={isMobile}
            >
              Create Backup Now
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  );
}

function AdminRateLimits() {
  const [s, setS] = useState({});
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadSettings = async () => {
    try {
      const data = await fetchApi('/admin/rate-limits');
      setS(data);
    } catch(e) {}
  };
  useEffect(() => { loadSettings(); }, []);

  const save = async () => {
    try {
      await fetchApi('/admin/rate-limits', {
        method: 'PUT',
        body: JSON.stringify(s)
      });
      alert('Rate limits saved!');
    } catch(e) { alert(e.message); }
  };

  return (
    <Stack>
      <Title order={3}>Rate Limits</Title>
      <Paper p="md" withBorder>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput label="Per User API calls/min" value={s.per_user_api || 0} onChange={(v) => setS({...s, per_user_api: v})} />
            <NumberInput label="Global API calls/min" value={s.global_api || 0} onChange={(v) => setS({...s, global_api: v})} />
          </SimpleGrid>
          <Button onClick={save} fullWidth={isMobile}>Save Rate Limits</Button>
        </Stack>
      </Paper>
    </Stack>
  );
}

function AdminEmailConfig() {
  const [s, setS] = useState({});
  const [testEmail, setTestEmail] = useState('');
  const isMobile = useMediaQuery('(max-width: 48em)');

  useEffect(() => {
    fetchApi('/admin/email-config').then(setS).catch(console.error);
  }, []);

  const sendTest = async () => {
    try {
      const res = await fetchApi('/admin/email-config/test', {
        method: 'POST',
        body: JSON.stringify({ test_email: testEmail })
      });
      alert(res.message);
    } catch(e) { alert(e.message); }
  };

  return (
    <Stack>
      <Title order={3}>Email Configuration</Title>
      <Paper p="md" withBorder>
        <Stack>
          <TextInput label="SMTP Provider" value={s.smtp_provider || ''} disabled />
          <TextInput label="Email Address" value={s.email_address || ''} disabled />
          <Divider />
          <TextInput label="Test Email" value={testEmail} onChange={(e) => setTestEmail(e.currentTarget.value)} />
          <Button onClick={sendTest} fullWidth={isMobile}>Send Test Email</Button>
        </Stack>
      </Paper>
    </Stack>
  );
}

function AdminIpFilters() {
  const [filters, setFilters] = useState([]);
  const [filterType, setFilterType] = useState('blacklist');
  const [ruleType, setRuleType] = useState('country');
  const [value, setValue] = useState('');
  const isMobile = useMediaQuery('(max-width: 48em)');

  const load = async () => {
    fetchApi('/admin/ip-filters').then(setFilters).catch(console.error);
  };
  useEffect(() => { load(); }, []);

  const add = async () => {
    try {
      await fetchApi('/admin/ip-filters', {
        method: 'POST',
        body: JSON.stringify({ filter_type: filterType, rule_type: ruleType, value })
      });
      load();
    } catch(e) { alert(e.message); }
  };

  const remove = async (id) => {
    try {
      await fetchApi(`/admin/ip-filters/${id}`, { method: 'DELETE' });
      load();
    } catch(e) { alert(e.message); }
  };

  return (
    <Stack>
      <Title order={3}>IP Filters</Title>
      <Paper p="md" withBorder>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Select label="Type" value={filterType} onChange={setFilterType} data={['blacklist', 'whitelist']} />
            <Select label="Rule" value={ruleType} onChange={setRuleType} data={['country', 'specific_ip']} />
            <TextInput label="Value" value={value} onChange={(e) => setValue(e.currentTarget.value)} />
          </SimpleGrid>
          <Button onClick={add} fullWidth={isMobile}>Add</Button>
        </Stack>
        <ScrollArea mt="md">
          <Table horizontalSpacing={isMobile ? 'xs' : 'sm'}>
            <Table.Thead><Table.Tr><Table.Th>ID</Table.Th><Table.Th>Type</Table.Th><Table.Th>Value</Table.Th><Table.Th>Action</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {filters.map(f => (
                <Table.Tr key={f.id}>
                  <Table.Td>{f.id}</Table.Td>
                  <Table.Td>{f.filter_type}</Table.Td>
                  <Table.Td>{f.value}</Table.Td>
                  <Table.Td><Button size="xs" color="red" variant="subtle" onClick={() => remove(f.id)}>Remove</Button></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>
    </Stack>
  );
}

function AdminAuditLogs() {
  const [logs, setLogs] = useState([]);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const load = async () => {
    fetchApi('/admin/logs?limit=50').then(setLogs).catch(console.error);
  };
  useEffect(() => { load(); }, []);

  return (
    <ScrollArea>
      <Table striped horizontalSpacing={isMobile ? 'xs' : 'sm'}>
        <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>User</Table.Th><Table.Th>Action</Table.Th><Table.Th>Details</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {logs.map((l, i) => (
            <Table.Tr key={i}>
              <Table.Td style={{ whiteSpace: 'nowrap' }}>{new Date(l.timestamp).toLocaleString()}</Table.Td>
              <Table.Td>{l.user_id}</Table.Td>
              <Table.Td>{l.action}</Table.Td>
              <Table.Td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.details}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

function AdminLogFiles() {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [content, setContent] = useState({ lines: [], total_bytes: 0 });
  const [searchQuery, setSearchQuery] = useState('');
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadFiles = async () => {
    try {
      const data = await fetchApi('/admin/log-files');
      setFiles(data);
      if (data.length > 0) setSelectedFile(data[0].name);
    } catch (e) {
      console.error(e);
    }
  };
  useEffect(() => { loadFiles(); }, []);

  useEffect(() => {
    if (!selectedFile) return;
    setSearchQuery('');
    fetchApi(`/admin/log-files/${selectedFile}?limit=500`).then(setContent).catch(console.error);
  }, [selectedFile]);

  const filteredLines = searchQuery
    ? content.lines.filter(l =>
        [l.timestamp, l.level, l.logger, l.message].some(v => v && v.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : content.lines;

  return (
    <Stack>
      <Group>
        <Select
          data={files.map(f => ({ value: f.name, label: `${f.name} (${(f.size_bytes / 1024 / 1024).toFixed(1)} MB)` }))}
          value={selectedFile}
          onChange={setSelectedFile}
          style={{ flex: 1 }}
          searchable
        />
        <Button size="xs" variant="light" onClick={() => setSelectedFile(selectedFile)}>Refresh</Button>
      </Group>
      <TextInput
        placeholder="Search log lines..."
        value={searchQuery}
        onChange={e => setSearchQuery(e.currentTarget.value)}
      />
      {content.lines.length > 0 && (
        <Text size="xs" c="dimmed">{searchQuery ? `${filteredLines.length} of ` : ''}Showing last {content.lines.length} lines of {selectedFile} ({(content.total_bytes / 1024 / 1024).toFixed(1)} MB total)</Text>
      )}
      <ScrollArea style={{ height: isMobile ? 'calc(100vh - 300px)' : 600 }}>
        <Box component="pre" style={{ fontSize: 11, lineHeight: 1.5, margin: 0 }}>
          {filteredLines.map((line, i) => {
            let color;
            if (line.level === 'ERROR') color = 'var(--mantine-color-red-6)';
            else if (line.level === 'WARNING') color = 'var(--mantine-color-yellow-6)';
            else if (line.level === 'INFO') color = 'var(--mantine-color-green-6)';
            return (
              <Box key={i} style={{ color: color || 'inherit' }}>
                {line.timestamp && <Text span size="xs" c="dimmed" component="span">{line.timestamp} </Text>}
                {line.level && <Text span size="xs" fw={600} component="span" c={color}>{line.level} </Text>}
                {line.logger && <Text span size="xs" component="span" c="dimmed">{line.logger}: </Text>}
                <Text span size="xs" component="span">{line.message}</Text>
              </Box>
            );
          })}
        </Box>
      </ScrollArea>
    </Stack>
  );
}

function AdminSystemLogs() {
  const isMobile = useMediaQuery('(max-width: 48em)');

  return (
    <Stack>
      <Title order={3}>System Logs</Title>
      <Tabs defaultValue="audit">
        <Tabs.List>
          <Tabs.Tab value="audit">Audit Logs</Tabs.Tab>
          <Tabs.Tab value="files">Log Files</Tabs.Tab>
        </Tabs.List>
        <Box mt="md">
          <Tabs.Panel value="audit"><AdminAuditLogs /></Tabs.Panel>
          <Tabs.Panel value="files"><AdminLogFiles /></Tabs.Panel>
        </Box>
      </Tabs>
    </Stack>
  );
}

function AdminBackups() {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [settings, setSettings] = useState({ backup_enabled: true, backup_retention_days: 7 });
  const [savingSettings, setSavingSettings] = useState(false);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadBackups = async () => {
    setLoading(true);
    try {
      const data = await fetchApi('/admin/backups');
      setBackups(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to load backups:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadSettings = async () => {
    try {
      const data = await fetchApi('/admin/system-settings');
      if (data) {
        setSettings({
          backup_enabled: data.backup_enabled !== false,
          backup_retention_days: data.backup_retention_days || 7,
        });
      }
    } catch (e) {
      console.error('Failed to load system settings:', e);
    }
  };

  useEffect(() => {
    loadBackups();
    loadSettings();
  }, []);

  const handleCreateBackup = async () => {
    setCreating(true);
    try {
      const res = await fetchApi('/admin/backups/create', { method: 'POST' });
      alert(res.message || 'Backup created successfully!');
      loadBackups();
    } catch (e) {
      alert(`Backup failed: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleDownload = async (filename) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/admin/backups/${encodeURIComponent(filename)}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Download failed with HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Failed to download backup: ${e.message}`);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await fetchApi(`/admin/backups/${encodeURIComponent(deleteTarget)}`, { method: 'DELETE' });
      setDeleteTarget(null);
      loadBackups();
    } catch (e) {
      alert(`Failed to delete backup: ${e.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      const current = await fetchApi('/admin/system-settings');
      await fetchApi('/admin/system-settings', {
        method: 'PUT',
        body: JSON.stringify({
          ...current,
          backup_enabled: settings.backup_enabled,
          backup_retention_days: settings.backup_retention_days,
        }),
      });
      alert('Backup settings saved!');
    } catch (e) {
      alert(`Failed to save settings: ${e.message}`);
    } finally {
      setSavingSettings(false);
    }
  };

  const totalBytes = backups.reduce((acc, b) => acc + (b.size_bytes || 0), 0);
  const formatTotalSize = (bytes) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <Stack gap="lg">
      <Paper p="md" withBorder>
        <Stack gap="sm">
          <Group justify="space-between" wrap="wrap">
            <div>
              <Title order={4}>Automated Backup Schedule</Title>
              <Text size="xs" c="dimmed">
                The background worker runs scheduled backups every 24 hours and cleans up older snapshots based on your retention policy.
              </Text>
            </div>
            <Button
              size="xs"
              variant="outline"
              onClick={handleSaveSettings}
              loading={savingSettings}
            >
              Save Schedule
            </Button>
          </Group>
          <Group grow={!isMobile} align="flex-end" wrap="wrap">
            <Switch
              label="Enable automated daily backups"
              checked={settings.backup_enabled}
              onChange={(e) => setSettings({ ...settings, backup_enabled: e.currentTarget.checked })}
            />
            <NumberInput
              label="Retention period (days)"
              description="Backups older than this are automatically pruned"
              value={settings.backup_retention_days}
              min={1}
              max={365}
              onChange={(v) => setSettings({ ...settings, backup_retention_days: Number(v) || 7 })}
              style={{ maxWidth: 260 }}
            />
          </Group>
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Stack gap="md">
          <Group justify="space-between" wrap="wrap">
            <div>
              <Group gap="xs">
                <Title order={4}>Database Snapshots</Title>
                <Badge variant="light" color="blue">
                  {backups.length} {backups.length === 1 ? 'backup' : 'backups'} ({formatTotalSize(totalBytes)})
                </Badge>
              </Group>
              <Text size="xs" c="dimmed">
                Files stored in <code>./backups/postgres</code>. You can download or delete individual SQL dumps.
              </Text>
            </div>
            <Group gap="xs">
              <Button
                size="xs"
                variant="light"
                leftSection={<IconRefresh size={14} />}
                onClick={loadBackups}
                loading={loading}
              >
                Refresh
              </Button>
              <Button
                size="xs"
                color="blue"
                leftSection={<IconDatabase size={14} />}
                onClick={handleCreateBackup}
                loading={creating}
              >
                Create Backup Now
              </Button>
            </Group>
          </Group>

          {backups.length === 0 ? (
            <Paper p="xl" withBorder style={{ textAlign: 'center' }}>
              <Text c="dimmed" size="sm">No database backups found.</Text>
              <Button
                mt="sm"
                size="xs"
                variant="light"
                onClick={handleCreateBackup}
                loading={creating}
              >
                Generate First Backup
              </Button>
            </Paper>
          ) : (
            <ScrollArea>
              <Table striped horizontalSpacing={isMobile ? 'xs' : 'sm'}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Backup File</Table.Th>
                    <Table.Th>Created At</Table.Th>
                    <Table.Th>File Size</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Actions</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {backups.map((b) => (
                    <Table.Tr key={b.filename}>
                      <Table.Td style={{ fontFamily: 'monospace', fontWeight: 500 }}>
                        <Group gap="xs">
                          <IconFileDatabase size={16} color="var(--mantine-color-blue-6)" />
                          <span>{b.filename}</span>
                        </Group>
                      </Table.Td>
                      <Table.Td style={{ whiteSpace: 'nowrap' }}>
                        {new Date(b.created_at).toLocaleString()}
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="outline" size="sm">{b.size_formatted}</Badge>
                      </Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>
                        <Group gap="xs" justify="flex-end">
                          <Button
                            size="compact-xs"
                            variant="light"
                            leftSection={<IconDownload size={13} />}
                            onClick={() => handleDownload(b.filename)}
                          >
                            Download
                          </Button>
                          <Button
                            size="compact-xs"
                            variant="subtle"
                            color="red"
                            leftSection={<IconTrash size={13} />}
                            onClick={() => setDeleteTarget(b.filename)}
                          >
                            Delete
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          )}
        </Stack>
      </Paper>

      <Modal
        opened={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete Database Backup"
      >
        <Stack>
          <Text size="sm">
            Are you sure you want to permanently delete <strong>{deleteTarget}</strong>?
          </Text>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button color="red" onClick={handleDelete} loading={deleting}>Confirm Delete</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function AdminDatabase() {
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [data, setData] = useState({ columns: [], data: [] });
  const isMobile = useMediaQuery('(max-width: 48em)');

  useEffect(() => {
    fetchApi('/admin/db/tables').then(setTables).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedTable) {
      fetchApi(`/admin/db/table/${selectedTable}`).then(setData).catch(console.error);
    }
  }, [selectedTable]);

  return (
    <Stack>
      <Title order={3}>Database Management</Title>
      <Tabs defaultValue="backups">
        <Tabs.List mb="md">
          <Tabs.Tab value="backups" leftSection={<IconDatabase size={16} />}>Backups & Snapshots</Tabs.Tab>
          <Tabs.Tab value="tables" leftSection={<IconListDetails size={16} />}>Table Browser</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="backups">
          <AdminBackups />
        </Tabs.Panel>

        <Tabs.Panel value="tables">
          <Stack gap="sm">
            <Select label="Table" data={tables} value={selectedTable} onChange={setSelectedTable} searchable />
            {selectedTable && (
              <ScrollArea>
                <Table striped horizontalSpacing={isMobile ? 'xs' : 'sm'}>
                  <Table.Thead>
                    <Table.Tr>
                      {data.columns.map(c => <Table.Th key={c}>{c}</Table.Th>)}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.data.map((row, i) => (
                      <Table.Tr key={i}>
                        {data.columns.map(c => <Table.Td key={c} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(row[c])}</Table.Td>)}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function AdminDiagnostics() {
  const isMobile = useMediaQuery('(max-width: 48em)');
  return (
    <Stack>
      <Title order={3}>Diagnostics</Title>
      <iframe src="/admin/diagnostics" style={{ width: '100%', height: isMobile ? '400px' : '800px', border: 'none' }} title="Diagnostics" />
    </Stack>
  );
}

function AdminGlobalPrompts() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [formData, setFormData] = useState({ name: '', content: '', icon: '' });
  const isMobile = useMediaQuery('(max-width: 48em)');

  const loadPrompts = async () => {
    setLoading(true);
    try {
      const data = await fetchApi('/admin/global-prompts');
      setPrompts(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadPrompts(); }, []);

  const handleSave = async () => {
    if (!formData.name || !formData.content) return;
    try {
      if (editingPrompt) {
        await fetchApi(`/admin/global-prompts/${editingPrompt.id}`, {
          method: 'PUT',
          body: JSON.stringify(formData)
        });
      } else {
        await fetchApi('/admin/global-prompts', {
          method: 'POST',
          body: JSON.stringify(formData)
        });
      }
      setModalOpen(false);
      loadPrompts();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this prompt?')) return;
    try {
      await fetchApi(`/admin/global-prompts/${id}`, { method: 'DELETE' });
      loadPrompts();
    } catch (e) {
      alert(e.message);
    }
  };

  const openModal = (prompt = null) => {
    if (prompt) {
      setEditingPrompt(prompt);
      setFormData({ name: prompt.name, content: prompt.content, icon: prompt.icon || '' });
    } else {
      setEditingPrompt(null);
      setFormData({ name: '', content: '', icon: '' });
    }
    setModalOpen(true);
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={3}>Global Prompts</Title>
        <Button onClick={() => openModal()}>Add Prompt</Button>
      </Group>
      
      <ScrollArea>
        <Table striped highlightOnHover horizontalSpacing={isMobile ? 'xs' : 'sm'}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>ID</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>Content</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {prompts.map(p => (
              <Table.Tr key={p.id}>
                <Table.Td>{p.id}</Table.Td>
                <Table.Td>{p.name}</Table.Td>
                <Table.Td>
                  <Text lineClamp={1} size="sm">{p.content}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs" wrap="wrap">
                    <Button size="xs" variant="light" onClick={() => openModal(p)}>Edit</Button>
                    <Button size="xs" color="red" variant="light" onClick={() => handleDelete(p.id)}>Delete</Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {prompts.length === 0 && !loading && (
              <Table.Tr>
                <Table.Td colSpan={4} align="center">No global prompts found.</Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <Modal opened={modalOpen} onClose={() => setModalOpen(false)} title={editingPrompt ? "Edit Prompt" : "New Prompt"} fullScreen={isMobile}>
        <Stack>
          <TextInput
            label="Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.currentTarget.value })}
            placeholder="E.g. Concise Bullets"
            required
          />
          <TextInput
            label="Icon"
            value={formData.icon}
            onChange={(e) => setFormData({ ...formData, icon: e.currentTarget.value })}
            placeholder="e.g. IconBrain, IconSchool, IconWand"
            description="Find valid Tabler Icon component names at https://tabler.io/icons (Must start with 'Icon' and be camel cased)."
          />
          <Textarea
            label="Content (Instructions)"
            value={formData.content}
            onChange={(e) => setFormData({ ...formData, content: e.currentTarget.value })}
            placeholder="Enter the instructions for the AI..."
            minRows={10}
            autosize
            maxRows={20}
            required
          />
          <Button onClick={handleSave}>{editingPrompt ? "Save Changes" : "Create Prompt"}</Button>
        </Stack>
      </Modal>
    </Stack>
  );
}

function AdminUserContent() {
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [usersLoading, setUsersLoading] = useState(true);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const [groups, setGroups] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [resources, setResources] = useState([]);
  const [exercises, setExercises] = useState([]);
  const [notes, setNotes] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [tasks, setTasks] = useState([]);

  const [detailResource, setDetailResource] = useState(null);
  const [detailExercise, setDetailExercise] = useState(null);
  const [detailNote, setDetailNote] = useState(null);
  const [detailConversation, setDetailConversation] = useState(null);
  const [detailConversationMessages, setDetailConversationMessages] = useState([]);

  const [activeSection, setActiveSection] = useState('groups');
  const [sectionLoading, setSectionLoading] = useState(false);

  useEffect(() => {
    fetchApi('/admin/users').then(data => {
      setUsers(data);
      setUsersLoading(false);
    }).catch(() => setUsersLoading(false));
  }, []);

  const loadSection = async (section) => {
    if (!selectedUserId) return;
    setSectionLoading(true);
    try {
      const data = await fetchApi(`/admin/users/${selectedUserId}/${section}`);
      if (section === 'groups') setGroups(data);
      else if (section === 'subjects') setSubjects(data);
      else if (section === 'resources') setResources(data);
      else if (section === 'exercises') setExercises(data);
      else if (section === 'notes') setNotes(data);
      else if (section === 'conversations') setConversations(data);
      else if (section === 'tasks') setTasks(data);
    } catch (e) {
      console.error(e);
    } finally {
      setSectionLoading(false);
    }
  };

  useEffect(() => {
    if (selectedUserId) loadSection(activeSection);
  }, [selectedUserId, activeSection]);

  const deleteItem = async (section, id) => {
    if (!confirm(`Delete this ${section.slice(0, -1)}?`)) return;
    try {
      await fetchApi(`/admin/users/${selectedUserId}/${section}/${id}`, { method: 'DELETE' });
      loadSection(activeSection);
    } catch (e) { alert(e.message); }
  };

  const reprocessItem = async (section, id) => {
    if (!confirm(`Reprocess this ${section.slice(0, -1)}?`)) return;
    try {
      const res = await fetchApi(`/admin/users/${selectedUserId}/${section}/${id}/reprocess`, { method: 'POST' });
      notifyTaskStarted();
      alert(`Reprocessing submitted. Task ID: ${res.task_id}`);
    } catch (e) { alert(e.message); }
  };

  const cancelTask = async (taskId) => {
    if (!confirm('Cancel this task?')) return;
    try {
      await fetchApi(`/admin/tasks/${taskId}/cancel`, { method: 'POST' });
      loadSection('tasks');
    } catch (e) { alert(e.message); }
  };

  const viewResource = async (id) => {
    try {
      const data = await fetchApi(`/admin/users/${selectedUserId}/resources/${id}`);
      setDetailResource(data);
    } catch (e) { alert(e.message); }
  };

  const viewExercise = async (id) => {
    try {
      const data = await fetchApi(`/admin/users/${selectedUserId}/exercises/${id}`);
      setDetailExercise(data);
    } catch (e) { alert(e.message); }
  };

  const viewNote = async (id) => {
    try {
      const data = await fetchApi(`/admin/users/${selectedUserId}/notes/${id}`);
      setDetailNote(data);
    } catch (e) { alert(e.message); }
  };

  const viewConversation = async (convId) => {
    try {
      const msgs = await fetchApi(`/admin/users/${selectedUserId}/conversations/${convId}`);
      setDetailConversationMessages(msgs);
      setDetailConversation(convId);
    } catch (e) { alert(e.message); }
  };

  const renderTable = (columns, rows, actions) => (
    <ScrollArea>
      <Table striped highlightOnHover horizontalSpacing={isMobile ? 'xs' : 'sm'}>
        <Table.Thead>
          <Table.Tr>{columns.map(c => <Table.Th key={c.key}>{c.label}</Table.Th>)}</Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, i) => (
            <Table.Tr key={row.id || i}>
              {columns.map(c => <Table.Td key={c.key}>{c.render ? c.render(row) : row[c.key] ?? '-'}</Table.Td>)}
              {actions && <Table.Td><Group gap={4} wrap="wrap">{actions(row)}</Group></Table.Td>}
            </Table.Tr>
          ))}
          {rows.length === 0 && !sectionLoading && (
            <Table.Tr><Table.Td colSpan={columns.length + (actions ? 1 : 0)} align="center">No data</Table.Td></Table.Tr>
          )}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );

  const actionBtn = (label, color, onClick) => (
    <Button size="xs" color={color} variant={color === 'red' ? 'light' : 'outline'} onClick={onClick}>{label}</Button>
  );

  return (
    <Stack>
      <Title order={3}>User Content Viewer</Title>

      {usersLoading && <Text c="dimmed" size="sm">Loading users...</Text>}

      <Select
        label="Select User"
        placeholder="Choose a user to inspect"
        data={users.map(u => ({ value: String(u.id), label: `${u.email} (ID: ${u.id}, Tier: ${u.tier})` }))}
        value={selectedUserId ? String(selectedUserId) : null}
        onChange={(v) => { setSelectedUserId(v ? Number(v) : null); setActiveSection('groups'); }}
        searchable
        clearable
      />

      {selectedUserId && (
        <>
          <Tabs value={activeSection} onChange={setActiveSection}>
            <Tabs.List>
              {sectionTabsConfig.map(t => <Tabs.Tab key={t.value} value={t.value}>{t.label}</Tabs.Tab>)}
            </Tabs.List>

            {sectionLoading && <Text c="dimmed" size="sm" mt="md">Loading...</Text>}

            {!sectionLoading && (
              <>
                <Tabs.Panel value="groups" pt="sm">
                  {renderTable(
                    [{ key: 'id', label: 'ID' }, { key: 'name', label: 'Name' }, { key: 'subjects', label: 'Subjects', render: (r) => r.subjects?.map(s => s.name).join(', ') || '-' }, { key: 'created_at', label: 'Created' }],
                    groups,
                    (r) => actionBtn('Delete', 'red', () => deleteItem('groups', r.id))
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="subjects" pt="sm">
                  {renderTable(
                    [{ key: 'id', label: 'ID' }, { key: 'name', label: 'Name' }, { key: 'resource_count', label: 'Resources' }, { key: 'created_at', label: 'Created' }],
                    subjects,
                    (r) => actionBtn('Delete', 'red', () => deleteItem('subjects', r.id))
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="resources" pt="sm">
                  {renderTable(
                    [{ key: 'id', label: 'ID' }, { key: 'title', label: 'Title' }, { key: 'file_type', label: 'Type' }, { key: 'file_size', label: 'Size', render: (r) => r.file_size ? `${(r.file_size / 1024).toFixed(0)}KB` : '-' }, { key: 'page_count', label: 'Pages' }, { key: 'processing_time_ms', label: 'Proc ms' }, { key: 'notes_count', label: 'Notes' }, { key: 'created_at', label: 'Created' }],
                    resources,
                    (r) => (<><Tooltip label="View"><Button size="xs" variant="outline" onClick={() => viewResource(r.id)}><IconEye size={14} /></Button></Tooltip><Tooltip label="Reprocess"><Button size="xs" variant="light" onClick={() => reprocessItem('resources', r.id)}><IconRefresh size={14} /></Button></Tooltip><Tooltip label="Delete"><Button size="xs" color="red" variant="light" onClick={() => deleteItem('resources', r.id)}><IconTrash size={14} /></Button></Tooltip></>)
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="exercises" pt="sm">
                  {renderTable(
                    [{ key: 'id', label: 'ID' }, { key: 'title', label: 'Title' }, { key: 'question_count', label: 'Questions' }, { key: 'model', label: 'Model' }, { key: 'created_at', label: 'Created' }],
                    exercises,
                    (r) => (<><Tooltip label="View"><Button size="xs" variant="outline" onClick={() => viewExercise(r.id)}><IconEye size={14} /></Button></Tooltip><Tooltip label="Reprocess"><Button size="xs" variant="light" onClick={() => reprocessItem('exercises', r.id)}><IconRefresh size={14} /></Button></Tooltip><Tooltip label="Delete"><Button size="xs" color="red" variant="light" onClick={() => deleteItem('exercises', r.id)}><IconTrash size={14} /></Button></Tooltip></>)
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="notes" pt="sm">
                  {renderTable(
                    [{ key: 'id', label: 'ID' }, { key: 'title', label: 'Title' }, { key: 'summary_type', label: 'Type' }, { key: 'model', label: 'Model' }, { key: 'processing_time_ms', label: 'Proc ms' }, { key: 'created_at', label: 'Created' }],
                    notes,
                    (r) => (<><Tooltip label="View"><Button size="xs" variant="outline" onClick={() => viewNote(r.id)}><IconEye size={14} /></Button></Tooltip><Tooltip label="Delete"><Button size="xs" color="red" variant="light" onClick={() => deleteItem('notes', r.id)}><IconTrash size={14} /></Button></Tooltip></>)
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="conversations" pt="sm">
                  {renderTable(
                    [{ key: 'conversation_id', label: 'Conv ID' }, { key: 'title', label: 'Title' }, { key: 'message_count', label: 'Messages' }, { key: 'last_message_at', label: 'Last Message' }],
                    conversations,
                    (r) => <Button size="xs" variant="outline" onClick={() => viewConversation(r.conversation_id)}>View Messages</Button>
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="tasks" pt="sm">
                  {renderTable(
                    [{ key: 'task_id', label: 'Task ID' }, { key: 'task_type', label: 'Type' }, { key: 'status', label: 'Status', render: (r) => <Badge color={r.status === 'completed' ? 'green' : r.status === 'failed' ? 'red' : r.status === 'running' ? 'yellow' : r.status === 'cancelled' ? 'gray' : 'blue'} size={isMobile ? 'xs' : 'sm'}>{r.status}</Badge> }, { key: 'progress', label: 'Progress' }, { key: 'error_message', label: 'Error' }, { key: 'is_hung', label: 'Hung?', render: (r) => r.is_hung ? <Badge color="red" size={isMobile ? 'xs' : 'sm'}>YES</Badge> : <Badge color="green" size={isMobile ? 'xs' : 'sm'}>No</Badge> }, { key: 'updated_at', label: 'Updated' }],
                    tasks,
                    (r) => r.status === 'pending' || r.status === 'running' ? <Button size="xs" color="red" variant="light" onClick={() => cancelTask(r.task_id)}>Cancel</Button> : null
                  )}
                </Tabs.Panel>
              </>
            )}
          </Tabs>

          {/* Resource Detail Modal */}
          <Modal opened={!!detailResource} onClose={() => setDetailResource(null)} title={`Resource: ${detailResource?.title || ''}`} size={isMobile ? '100%' : 'xl'} fullScreen={isMobile}>
            {detailResource && (
              <Stack>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                  <Text size="sm"><Text fw={500} component="span">ID:</Text> {detailResource.id}</Text>
                  <Text size="sm"><Text fw={500} component="span">Title:</Text> {detailResource.title}</Text>
                  <Text size="sm"><Text fw={500} component="span">File:</Text> {detailResource.file_name} ({detailResource.file_type})</Text>
                  <Text size="sm"><Text fw={500} component="span">Size:</Text> {detailResource.file_size ? `${(detailResource.file_size / 1024).toFixed(0)} KB` : '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Pages:</Text> {detailResource.page_count ?? '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Processing Time:</Text> {detailResource.processing_time_ms ? `${detailResource.processing_time_ms}ms` : '-'}</Text>
                </SimpleGrid>
                {detailResource.timings && (
                  <>
                    <Text fw={500} size="sm">Processing Timings:</Text>
                    <Paper p="sm" withBorder><Box component="pre" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(detailResource.timings, null, 2)}</Box></Paper>
                  </>
                )}
                {detailResource.extracted_text && (
                  <>
                    <Text fw={500} size="sm">Extracted Text ({detailResource.content_length} chars):</Text>
                    <ScrollArea style={{ height: isMobile ? 200 : 300 }}>
                      <Paper p="sm" withBorder><Box component="pre" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>{detailResource.extracted_text}</Box></Paper>
                    </ScrollArea>
                  </>
                )}
              </Stack>
            )}
          </Modal>

          {/* Exercise Detail Modal */}
          <Modal opened={!!detailExercise} onClose={() => setDetailExercise(null)} title={`Exercise: ${detailExercise?.title || ''}`} size={isMobile ? '100%' : 'xl'} fullScreen={isMobile}>
            {detailExercise && (
              <Stack>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                  <Text size="sm"><Text fw={500} component="span">ID:</Text> {detailExercise.id}</Text>
                  <Text size="sm"><Text fw={500} component="span">Model:</Text> {detailExercise.model || '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Processing:</Text> {detailExercise.processing_time_ms ? `${detailExercise.processing_time_ms}ms` : '-'}</Text>
                </SimpleGrid>
                {detailExercise.questions && detailExercise.questions.length > 0 && (
                  <>
                    <Text fw={500} size="sm">Questions ({detailExercise.questions.length}):</Text>
                    <ScrollArea style={{ height: isMobile ? 300 : 400 }}>
                      {detailExercise.questions.map((q, i) => (
                        <Paper key={q.id || i} p="sm" withBorder mb="xs">
                          <Text size="sm" fw={500}>Q{i + 1}: {q.question_text}</Text>
                          <Text size="sm" c="dimmed">Answer: {q.answer_text}</Text>
                          {q.explanation && <Text size="sm">Explanation: {q.explanation}</Text>}
                        </Paper>
                      ))}
                    </ScrollArea>
                  </>
                )}
              </Stack>
            )}
          </Modal>

          {/* Note Detail Modal */}
          <Modal opened={!!detailNote} onClose={() => setDetailNote(null)} title={`Note: ${detailNote?.title || ''}`} size={isMobile ? '100%' : 'xl'} fullScreen={isMobile}>
            {detailNote && (
              <Stack>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                  <Text size="sm"><Text fw={500} component="span">ID:</Text> {detailNote.id}</Text>
                  <Text size="sm"><Text fw={500} component="span">Type:</Text> {detailNote.summary_type}</Text>
                  <Text size="sm"><Text fw={500} component="span">Mode:</Text> {detailNote.mode || '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Format:</Text> {detailNote.output_format || '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Model:</Text> {detailNote.model || '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Processing:</Text> {detailNote.processing_time_ms ? `${detailNote.processing_time_ms}ms` : '-'}</Text>
                  <Text size="sm"><Text fw={500} component="span">Version:</Text> {detailNote.version}</Text>
                  <Text size="sm"><Text fw={500} component="span">User Edited:</Text> <Badge color={detailNote.is_user_edited ? 'yellow' : 'green'} size={isMobile ? 'xs' : 'sm'}>{String(detailNote.is_user_edited)}</Badge></Text>
                </SimpleGrid>
                {detailNote.content && (
                  <>
                    <Text fw={500} size="sm">Content ({detailNote.content_length} chars):</Text>
                    <ScrollArea style={{ height: isMobile ? 250 : 400 }}>
                      <Paper p="sm" withBorder><Box component="pre" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>{detailNote.content}</Box></Paper>
                    </ScrollArea>
                  </>
                )}
                {detailNote.quickread && (
                  <>
                    <Text fw={500} size="sm">Quickread:</Text>
                    <ScrollArea style={{ height: isMobile ? 150 : 200 }}>
                      <Paper p="sm" withBorder><Box component="pre" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: 0 }}>{detailNote.quickread}</Box></Paper>
                    </ScrollArea>
                  </>
                )}
              </Stack>
            )}
          </Modal>

          {/* Conversation Messages Modal */}
          <Modal opened={!!detailConversation} onClose={() => { setDetailConversation(null); setDetailConversationMessages([]); }} title={`Conversation: ${detailConversation}`} size={isMobile ? '100%' : 'xl'} fullScreen={isMobile}>
            <ScrollArea style={{ height: isMobile ? 'calc(100vh - 200px)' : 500 }}>
              {detailConversationMessages.map((m, i) => (
                <Paper key={m.id || i} p="sm" withBorder mb="md">
                  <Text size="xs" c="dimmed" mb="xs">{new Date(m.created_at).toLocaleString()} | {m.ai_model || '-'} | Mode: {m.ai_mode || '-'}</Text>
                  <Box mb="xs" p="xs" style={{ backgroundColor: '#f0f4ff', borderRadius: 4 }}>
                    <Text size="sm" fw={500}>Q:</Text>
                    <Text size="sm">{m.message}</Text>
                  </Box>
                  <Box p="xs" style={{ backgroundColor: '#f5f5f5', borderRadius: 4 }}>
                    <Text size="sm" fw={500}>A:</Text>
                    <Text size="sm">{m.response}</Text>
                  </Box>
                  {m.sources && <Text size="xs" c="dimmed" mt="xs">Sources: {m.sources}</Text>}
                  {m.rating != null && <Text size="xs" mt="xs">Rating: {m.rating}/5{m.rating_comment ? ` - ${m.rating_comment}` : ''}</Text>}
                </Paper>
              ))}
              {detailConversationMessages.length === 0 && <Text c="dimmed">No messages in this conversation.</Text>}
            </ScrollArea>
          </Modal>
        </>
      )}
    </Stack>
  );
}

export default function AdminPage() {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const navigate = useNavigate();
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAdmin = async () => {
      try {
        const user = await fetchApi('/auth/me');
        if (user && user.is_admin) {
          setIsAdmin(true);
        } else {
          navigate('/dashboard');
        }
      } catch (e) {
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };
    checkAdmin();
  }, [navigate]);

  if (loading) return <Container mt="xl"><Text>Loading...</Text></Container>;
  if (!isAdmin) return null;

  return (
    <Container fluid p={0}>
      <Box px="md" pt="md" pb="xs">
        <Group mb="md">
          <IconShieldCheck size={28} />
          <Title order={2}>Admin Dashboard</Title>
        </Group>
      </Box>

      <Tabs defaultValue="users" orientation="horizontal">
        <Tabs.List style={{ flexWrap: 'wrap' }}>
          <Tabs.Tab value="users" leftSection={<IconUsers size={16} />}>Users</Tabs.Tab>
          <Tabs.Tab value="pending-approvals" leftSection={<IconUserCheck size={16} />}>Pending Approvals</Tabs.Tab>
          <Tabs.Tab value="invitations" leftSection={<IconMail size={16} />}>Invitations</Tabs.Tab>
          <Tabs.Tab value="tiers" leftSection={<IconStack2 size={16} />}>Tiers</Tabs.Tab>
          <Tabs.Tab value="settings" leftSection={<IconSettings size={16} />}>Settings</Tabs.Tab>
          <Tabs.Tab value="rate-limits" leftSection={<IconClock size={16} />}>Rate Limits</Tabs.Tab>
          <Tabs.Tab value="email" leftSection={<IconMail size={16} />}>Email</Tabs.Tab>
          <Tabs.Tab value="ip" leftSection={<IconServer size={16} />}>IP Filters</Tabs.Tab>
          <Tabs.Tab value="logs" leftSection={<IconListDetails size={16} />}>Logs</Tabs.Tab>
          <Tabs.Tab value="database" leftSection={<IconDatabase size={16} />}>Database</Tabs.Tab>
          <Tabs.Tab value="diagnostics" leftSection={<IconActivity size={16} />}>Diagnostics</Tabs.Tab>
          <Tabs.Tab value="global-prompts" leftSection={<IconMessages size={16} />}>Prompts</Tabs.Tab>
          <Tabs.Tab value="user-content" leftSection={<IconUsers size={16} />}>User Content</Tabs.Tab>
        </Tabs.List>

        <Box px="md" pb="xl">
          <Tabs.Panel value="users"><AdminUsers /></Tabs.Panel>
          <Tabs.Panel value="pending-approvals"><AdminPendingApprovals /></Tabs.Panel>
          <Tabs.Panel value="invitations"><AdminInvitations /></Tabs.Panel>
          <Tabs.Panel value="tiers"><AdminTiers /></Tabs.Panel>
          <Tabs.Panel value="settings"><AdminSystemSettings /></Tabs.Panel>
          <Tabs.Panel value="rate-limits"><AdminRateLimits /></Tabs.Panel>
          <Tabs.Panel value="email"><AdminEmailConfig /></Tabs.Panel>
          <Tabs.Panel value="ip"><AdminIpFilters /></Tabs.Panel>
          <Tabs.Panel value="logs"><AdminSystemLogs /></Tabs.Panel>
          <Tabs.Panel value="database"><AdminDatabase /></Tabs.Panel>
          <Tabs.Panel value="diagnostics"><AdminDiagnostics /></Tabs.Panel>
          <Tabs.Panel value="global-prompts"><AdminGlobalPrompts /></Tabs.Panel>
          <Tabs.Panel value="user-content"><AdminUserContent /></Tabs.Panel>
        </Box>
      </Tabs>
    </Container>
  );
}
