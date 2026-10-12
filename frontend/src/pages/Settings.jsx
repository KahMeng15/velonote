import { useState, useEffect } from 'react';
import { Box, Title, Paper, TextInput, PasswordInput, Textarea, Button, Group, Stack, Text, Divider, RingProgress, Center, Loader, ActionIcon, Table, Modal, ScrollArea, Notification } from '@mantine/core';
import { IconEdit, IconTrash, IconPlus, IconSparkles, IconAlertCircle } from '@tabler/icons-react';
import { fetchApi } from '../lib/api';

export default function Settings() {
  
  const [profile, setProfile] = useState({ nickname: '', full_name: '', email: '' });
  const [hasPassword, setHasPassword] = useState(true);
  const [quotas, setQuotas] = useState(null);
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [changingEmail, setChangingEmail] = useState(false);
  const [deleteConfirmOpened, setDeleteConfirmOpened] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [userPrompts, setUserPrompts] = useState([]);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [promptName, setPromptName] = useState('');
  const [promptContent, setPromptContent] = useState('');
  const [createPromptModalOpened, setCreatePromptModalOpened] = useState(false);
  const [newPromptInput, setNewPromptInput] = useState('');
  const [generatingNewPrompt, setGeneratingNewPrompt] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [profileData, quotasData, promptsData] = await Promise.all([
          fetchApi('/auth/me'),
          fetchApi('/auth/quotas').catch(() => null),
          fetchApi('/prompts').catch(() => [])
        ]);
        
        setProfile({
          nickname: profileData.nickname || '',
          full_name: profileData.full_name || '',
          email: profileData.email || ''
        });
        setHasPassword(profileData.has_password !== false);
        setQuotas(quotasData);
        setUserPrompts(promptsData || []);
      } catch (err) {
        console.error("Failed to load settings data", err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  useEffect(() => {
    if (message) {
      const t = setTimeout(() => setMessage(null), 4000);
      return () => clearTimeout(t);
    }
  }, [message]);

  const handleProfileUpdate = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await fetchApi('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({
          nickname: profile.nickname,
          full_name: profile.full_name
        })
      });
      setMessage({ type: 'success', text: 'Profile updated successfully!' });
      
      // Update local storage so sidebar/dashboard update
      const user = JSON.parse(localStorage.getItem('user') || '{}');
      localStorage.setItem('user', JSON.stringify({ ...user, ...profile }));
      
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to update profile' });
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordRequest = async () => {
    if (!newPassword || (!hasPassword && !currentPassword)) return;
    if (hasPassword && !currentPassword) return;
    setChangingPassword(true);
    setMessage(null);
    try {
      const body = hasPassword
        ? { current_password: currentPassword, new_password: newPassword }
        : { current_password: '', new_password: newPassword };
      await fetchApi('/auth/request-password-change', {
        method: 'POST',
        body: JSON.stringify(body)
      });
      setMessage({ type: 'success', text: 'Password changed successfully!' });
      setCurrentPassword('');
      setNewPassword('');
      setHasPassword(true);
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to change password' });
    } finally {
      setChangingPassword(false);
    }
  };

  const handleChangeEmail = async () => {
    if (!newEmail || !emailPassword) return;
    setChangingEmail(true);
    setMessage(null);
    try {
      const res = await fetchApi('/auth/change-email', {
        method: 'POST',
        body: JSON.stringify({ new_email: newEmail, password: emailPassword })
      });
      setMessage({ type: 'success', text: 'Email changed! Verification sent to new address.' });
      setProfile(prev => ({ ...prev, email: res.email }));
      setNewEmail('');
      setEmailPassword('');
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to change email' });
    } finally {
      setChangingEmail(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    try {
      await fetchApi('/auth/profile', { method: 'DELETE' });
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to delete account' });
      setDeleteConfirmOpened(false);
    } finally {
      setDeleting(false);
    }
  };

  const handleSavePrompt = async () => {
    if (!promptName.trim() || !promptContent.trim()) return;
    setSavingPrompt(true);
    try {
      if (editingPrompt) {
        const res = await fetchApi(`/prompts/${editingPrompt.id}`, {
          method: 'PUT',
          body: JSON.stringify({ name: promptName, content: promptContent })
        });
        setUserPrompts(userPrompts.map(p => p.id === res.id ? res : p));
      } else {
        const res = await fetchApi('/prompts', {
          method: 'POST',
          body: JSON.stringify({ name: promptName, content: promptContent })
        });
        setUserPrompts([...userPrompts, res]);
      }
      setEditingPrompt(null);
      setPromptName('');
      setPromptContent('');
      setCreatePromptModalOpened(false);
    } catch (err) {
      console.error(err);
    } finally {
      setSavingPrompt(false);
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
        if (res.prompt) setPromptContent(res.prompt);
        if (res.name) setPromptName(res.name);
      }
    } catch (err) {
      console.error("Failed to generate prompt", err);
    } finally {
      setGeneratingNewPrompt(false);
    }
  };

  const handleDeletePrompt = async (id) => {
    try {
      await fetchApi(`/prompts/${id}`, { method: 'DELETE' });
      setUserPrompts(userPrompts.filter(p => p.id !== id));
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditPrompt = (prompt) => {
    setEditingPrompt(prompt);
    setPromptName(prompt.name);
    setPromptContent(prompt.content);
    setNewPromptInput('');
    setCreatePromptModalOpened(true);
  };

  const handleCancelEditPrompt = () => {
    setEditingPrompt(null);
    setPromptName('');
    setPromptContent('');
    setCreatePromptModalOpened(false);
  };

  if (loading) {
    return <Center h="50vh"><Loader size="lg" /></Center>;
  }

  return (
    <Box maw={1400}>
      <Title order={2} mb="xl">Account Settings</Title>

      {message && (
        <Box style={{ position: 'fixed', top: 20, right: 20, zIndex: 1000 }}>
          <Notification
            withBorder
            withCloseButton
            onClose={() => setMessage(null)}
            color={message.type === 'error' ? 'red' : 'teal'}
            title={message.type === 'error' ? 'Error' : 'Success'}
          >
            {message.text}
          </Notification>
        </Box>
      )}

      <Box
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
          gap: 'var(--mantine-spacing-md)',
          alignItems: 'start',
        }}
      >
        <Paper withBorder p="xl" radius="md">
          <Title order={4} mb="md">Public Profile</Title>
          <Stack>
            <TextInput 
              label="Nickname" 
              value={profile.nickname} 
              onChange={(e) => setProfile({...profile, nickname: e.currentTarget.value})} 
            />
            <TextInput 
              label="Full Name" 
              value={profile.full_name} 
              onChange={(e) => setProfile({...profile, full_name: e.currentTarget.value})} 
            />
            <Group justify="flex-end" mt="md">
              <Button onClick={handleProfileUpdate} loading={saving}>Save Changes</Button>
            </Group>
          </Stack>
        </Paper>

        <Paper withBorder p="xl" radius="md">
          <Title order={4} mb="md">{hasPassword ? 'Change Password' : 'Set Password'}</Title>
          <Stack>
            {hasPassword && (
              <PasswordInput
                label="Current Password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.currentTarget.value)}
              />
            )}
            <PasswordInput
              label="New Password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.currentTarget.value)}
            />
            <Group justify="flex-end" mt="md">
              <Button
                variant="light"
                onClick={handlePasswordRequest}
                loading={changingPassword}
                disabled={hasPassword ? (!currentPassword || !newPassword) : !newPassword}
              >
                {hasPassword ? 'Change Password' : 'Set Password'}
              </Button>
            </Group>
          </Stack>
        </Paper>

        <Paper withBorder p="xl" radius="md">
          <Title order={4} mb="md">Email Address</Title>
          <Text size="sm" c="dimmed" mb="md">
            Current email: <b>{profile.email}</b>
          </Text>
          <Stack>
            <TextInput
              label="New Email"
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.currentTarget.value)}
              placeholder="your@newemail.com"
            />
            <PasswordInput
              label="Confirm with Password"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.currentTarget.value)}
            />
            <Group justify="flex-end" mt="md">
              <Button
                variant="light"
                onClick={handleChangeEmail}
                loading={changingEmail}
                disabled={!newEmail || !emailPassword}
              >
                Change Email
              </Button>
            </Group>
          </Stack>
        </Paper>

        <Paper withBorder p="xl" radius="md">
          <Title order={4} mb="md" c="red">Danger Zone</Title>
          <Group gap="xs" mb="md">
            <IconAlertCircle size={20} color="var(--mantine-color-red-6)" />
            <Text size="sm" c="dimmed">
              Once you delete your account, there is no going back. Please be certain.
            </Text>
          </Group>
          <Button color="red" variant="outline" onClick={() => setDeleteConfirmOpened(true)}>
            Delete Account
          </Button>
        </Paper>

        <Paper withBorder p="xl" radius="md">
          <Group justify="space-between" align="center" mb="xl">
            <div>
              <Title order={4} mb="xs">Custom Prompt Templates</Title>
              <Text size="sm" c="dimmed">
                Manage your custom prompt templates used for generating summaries.
              </Text>
            </div>
            <Button leftSection={<IconPlus size={16} />} onClick={() => {
              setEditingPrompt(null);
              setPromptName('');
              setPromptContent('');
              setNewPromptInput('');
              setCreatePromptModalOpened(true);
            }}>
              Create Template
            </Button>
          </Group>

          <Title order={5} mb="sm">Your Templates</Title>
          {userPrompts.length === 0 ? (
            <Text c="dimmed" size="sm">You haven't created any custom templates yet.</Text>
          ) : (
            <ScrollArea>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th style={{ width: '100px' }}>Actions</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {userPrompts.map(prompt => (
                  <Table.Tr key={prompt.id}>
                    <Table.Td>{prompt.name}</Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <ActionIcon variant="subtle" onClick={() => handleEditPrompt(prompt)}>
                          <IconEdit size={16} />
                        </ActionIcon>
                        <ActionIcon variant="subtle" color="red" onClick={() => handleDeletePrompt(prompt.id)}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table></ScrollArea>
          )}
        </Paper>

        <Paper withBorder p="xl" radius="md">
          <Title order={4} mb="xs">Usage & Quotas</Title>
          {quotas && (
            <Text size="sm" c="dimmed" mb="xl">
              Plan: <b>{quotas.tier_name}</b>
            </Text>
          )}

          {quotas && (() => {
            const q = quotas.quotas || {};
            const sumUsed = (...keys) => keys.reduce((s, k) => s + (q[k]?.used || 0), 0);
            const sumLimit = (...keys) => {
              const vals = keys.map(k => q[k]?.limit).filter(v => v !== undefined);
              if (vals.some(v => v === -1)) return -1;
              return vals.reduce((s, v) => s + v, 0);
            };
            const isUnlimited = (...keys) => keys.some(k => q[k]?.unlimited || q[k]?.limit === -1);
            const cards = [
              {
                key: 'items_processed',
                label: 'Items Processed',
                color: 'blue',
                used: sumUsed('resources', 'notes', 'exercises'),
                limit: sumLimit('resources', 'notes', 'exercises'),
                unlimited: isUnlimited('resources', 'notes', 'exercises'),
                reset_period: q.notes?.reset_period,
              },
              {
                key: 'chat_messages',
                label: 'Chat Messages',
                color: 'indigo',
                used: sumUsed('conversations', 'messages'),
                limit: sumLimit('conversations', 'messages'),
                unlimited: isUnlimited('conversations', 'messages'),
                reset_period: q.messages?.reset_period,
              },
              { key: 'subjects', label: 'Subjects', color: 'violet', ...q.subjects },
              { key: 'groups', label: 'Groups', color: 'grape', ...q.groups },
              {
                key: 'storage_gb',
                label: 'Storage (GB)',
                color: 'teal',
                ...q.storage_gb,
                used: q.storage_gb?.used !== undefined ? Number(q.storage_gb.used).toFixed(1) : 0,
              },
            ];
            return (
              <Box
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                  gap: 'var(--mantine-spacing-md)',
                  alignItems: 'stretch',
                }}
              >
                {cards.map(q => {
                  if (!q) return null;
                  const pct = q.limit > 0 ? Math.round((Math.min(q.used, q.limit) / q.limit) * 100) : 0;
                  const color = pct >= 90 ? 'red' : pct >= 75 ? 'yellow' : q.color;
                  const period = q.reset_period ? `per ${q.reset_period}` : 'lifetime';
                  return (
                    <Paper key={q.key} withBorder p="sm" radius="md">
                      <Group gap="sm" wrap="nowrap">
                        <RingProgress
                          size={54}
                          thickness={5}
                          roundCaps
                          sections={[{ value: pct, color }]}
                        />
                        <Box style={{ flex: 1, minWidth: 0 }}>
                          <Group gap="xs" wrap="nowrap" justify="space-between">
                            <Text size="sm" fw={500}>{q.label}</Text>
                            <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                              {q.unlimited
                                ? `${q.used} (unlimited, ${period})`
                                : `${q.used} / ${q.limit} (${period})`
                              }
                            </Text>
                          </Group>
                        </Box>
                      </Group>
                    </Paper>
                  );
                })}
              </Box>
            );
          })()}

          {!quotas && <Text c="dimmed">No quota data available.</Text>}
        </Paper>
      </Box>
      <Modal opened={createPromptModalOpened} onClose={() => setCreatePromptModalOpened(false)} title={editingPrompt ? "Edit Custom Template" : "Create Custom Template"} centered size="lg">
        <form onSubmit={(e) => { e.preventDefault(); handleSavePrompt(); }}>
          <Stack gap="md">
            <TextInput
              label="Template Name"
              placeholder="e.g. Executive Summary"
              value={promptName}
              onChange={(e) => setPromptName(e.currentTarget.value)}
              required
              data-autofocus
            />
            <Textarea
              label="Prompt Content"
              placeholder="Enter the instructions for the AI..."
              value={promptContent}
              onChange={(e) => setPromptContent(e.currentTarget.value)}
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
              <Button type="submit" loading={savingPrompt} disabled={!promptName.trim() || !promptContent.trim()}>
                {editingPrompt ? 'Update Template' : 'Create Template'}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
      <Modal opened={deleteConfirmOpened} onClose={() => !deleting && setDeleteConfirmOpened(false)} title="Delete Account" centered size="sm">
        <Stack>
          <Group gap="xs">
            <IconAlertCircle size={24} color="var(--mantine-color-red-6)" />
            <Text fw={500}>Are you absolutely sure?</Text>
          </Group>
          <Text size="sm" c="dimmed">
            This will permanently delete your account and all associated data. This action cannot be undone.
          </Text>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => setDeleteConfirmOpened(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button color="red" onClick={handleDeleteAccount} loading={deleting}>
              {deleting ? 'Deleting...' : 'Delete My Account'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Box>
  );
}
