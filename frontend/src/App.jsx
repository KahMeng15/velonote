import SummaryView from "./pages/SummaryView";

import { useState, useEffect } from 'react';
import { useMediaQuery } from '@mantine/hooks';
import { BrowserRouter as Router, Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import { AppShell, Group, Text, Button, NavLink as MantineNavLink, ScrollArea, ActionIcon, Center, Tooltip, Avatar, Menu, UnstyledButton, Portal, Notification, Stack, Alert } from '@mantine/core';
import { 
  IconDashboard, 
  IconLogin, 
  IconHome, 
  IconBooks, 
  IconUpload, 
  IconMessageDots, 
  IconSettings,
  IconChartBar,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconShieldCheck
} from '@tabler/icons-react';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import NotesManager from './pages/NotesManager';
import UploadDocs from './pages/UploadDocs';
import ChatInterface from './pages/ChatInterface';
import ExerciseView from './pages/ExerciseView';
import SubjectView from './pages/SubjectView';
import NoteView from './pages/NoteView';
import Settings from './pages/Settings';
import GroupView from './pages/GroupView';
import AdminPage from './pages/Admin';
import LegalDoc from './pages/LegalDoc';
import { fetchApi } from './lib/api';
import TaskQueueModal from './components/TaskQueueModal';
import { TaskProvider } from './lib/TaskContext';

const CAT_BASE = "https://http.cat";

function GlobalToasts() {
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const handleError = (e) => {
      const detail = e.detail || {};
      const message = typeof detail === 'string' ? detail : (detail.message || 'An error occurred');
      const status = detail.status || null;
      const catUrl = detail.catUrl || (status ? `${CAT_BASE}/${status}` : null);
      setToasts(prev => {
        if (prev.some(t => t.message === message && t.status === status)) return prev;
        const id = Date.now() + Math.random();
        setTimeout(() => {
          setToasts(p => p.filter(t => t.id !== id));
        }, 6000);
        return [...prev, { id, message, status, catUrl }];
      });
    };
    window.addEventListener('apiError', handleError);
    return () => window.removeEventListener('apiError', handleError);
  }, []);

  return (
    <Portal>
      <div style={{ position: 'fixed', bottom: isMobile ? 80 : 20, right: 20, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {toasts.map(t => (
          <Notification
            key={t.id}
            title={t.status ? `Error ${t.status}` : "System Error"}
            color="red"
            onClose={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {t.catUrl && (
                <a href={t.catUrl} target="_blank" rel="noopener noreferrer" style={{ flexShrink: 0, lineHeight: 0 }}>
                  <img
                    src={t.catUrl}
                    alt={`HTTP ${t.status}`}
                    style={{ height: 48, borderRadius: 6, cursor: 'pointer' }}
                    onError={(e) => { e.target.style.display = 'none' }}
                  />
                </a>
              )}
              <Text size="sm">{t.message}</Text>
            </div>
          </Notification>
        ))}
      </div>
    </Portal>
  );
}

function GlobalAlert() {
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const checkMaintenance = async () => {
      try {
        const res = await fetch('/api/auth/public-settings', { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          if (data.maintenance_mode) {
            window.location.href = '/login';
            return;
          }
        }
      } catch (e) {}
      setAlert({ type: 'api', message: 'Cannot connect to the application server.', detail: 'Please check that the server is running and try again.' });
    };

    fetch('/api/health', { signal: controller.signal })
      .then(res => {
        clearTimeout(timeoutId);
        if (!res.ok) {
          checkMaintenance();
          return;
        }
        return res.json().then(data => {
          if (data?.database === 'down') {
            setAlert({ type: 'database', message: 'The database server is not responding.', detail: 'The app cannot access the database. Some features will be unavailable until this is resolved.' });
          }
        });
      })
      .catch(() => {
        clearTimeout(timeoutId);
        checkMaintenance();
      });

    return () => clearTimeout(timeoutId);
  }, []);

  if (!alert) return null;

  return (
    <Alert
      color="orange"
      title={alert.type === 'database' ? 'Database Unreachable' : 'Server Unreachable'}
      withCloseButton
      closeButtonLabel="Dismiss"
      onClose={() => setAlert(null)}
      styles={{ root: { borderRadius: 0 } }}
      style={{ position: 'sticky', top: 0, zIndex: 1000 }}
    >
      <Text size="sm">{alert.message}</Text>
      {alert.detail && <Text size="xs" mt={4} c="dimmed">{alert.detail}</Text>}
    </Alert>
  );
}

function AppLayout({ children }) {
  const [navOpen, setNavOpen] = useState(true);
  const [user, setUser] = useState(null);
  const location = useLocation();

  useEffect(() => {
    // Only fetch if logged in
    if (localStorage.getItem('token')) {
      fetchApi('/auth/me', { quietFail: true }).then(data => {
        if (data) {
          setUser(data);
          if (data.nav_sidebar_open !== undefined) {
            setNavOpen(data.nav_sidebar_open);
          }
        }
      }).catch(err => console.error("Failed to load user preferences", err));
    }
  }, [location.pathname]);

  const toggleNav = async () => {
    const newState = !navOpen;
    setNavOpen(newState);
    try {
      await fetchApi('/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({ nav_sidebar_open: newState })
      });
    } catch (e) {
      console.error("Failed to save nav state", e);
    }
  };

  if (location.pathname === '/login' || location.pathname === '/signup' || location.pathname === '/') {
    return <><GlobalAlert />{children}</>;
  }

  return (
    <>
      <GlobalAlert />
      <AppShell
        navbar={{
          width: navOpen ? 250 : 80,
          breakpoint: 'sm',
          collapsed: { mobile: true },
        }}
        padding={(location.pathname.startsWith('/note/') || location.pathname.startsWith('/resource/') || location.pathname.startsWith('/chat') || location.pathname.startsWith('/exercises/')) ? 0 : 'md'}
        bg="#ffffff"
      >
        <AppShell.Navbar p="md" bg="#ffffff" style={{ borderRight: '1px solid #eaeaea', transition: 'width 0.2s ease' }}>
        <Group justify={navOpen ? "space-between" : "center"} mb="xl" style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <Group gap="sm" wrap="nowrap">
            <img src="/velonote.svg" height={28} alt="velonote" />
            {navOpen && (
              <Text size="xl" fw={900} c="#171738" style={{ fontFamily: 'Instrument Sans, sans-serif' }}>
                velonote
              </Text>
            )}
          </Group>

        </Group>

        <AppShell.Section grow component={ScrollArea}>
          <Tooltip label="Dashboard" disabled={navOpen} position="right">
            <MantineNavLink component={NavLink} to="/dashboard" label={navOpen ? "Dashboard" : ""} leftSection={<IconDashboard size="1.2rem" stroke={1.5} />} />
          </Tooltip>
          <Tooltip label="My Notes" disabled={navOpen} position="right">
            <MantineNavLink component={NavLink} to="/mynotes" label={navOpen ? "My Notes" : ""} leftSection={<IconBooks size="1.2rem" stroke={1.5} />} />
          </Tooltip>
          <Tooltip label="Chat" disabled={navOpen} position="right">
            <MantineNavLink component={NavLink} to="/chat" label={navOpen ? "Chat" : ""} leftSection={<IconMessageDots size="1.2rem" stroke={1.5} />} />
          </Tooltip>
          <Tooltip label="Upload" disabled={navOpen} position="right">
            <MantineNavLink component={NavLink} to="/upload" label={navOpen ? "Upload" : ""} leftSection={<IconUpload size="1.2rem" stroke={1.5} />} />
          </Tooltip>
          {user?.is_admin && (
            <Tooltip label="Admin" disabled={navOpen} position="right">
              <MantineNavLink component={NavLink} to="/admin" label={navOpen ? "Admin" : ""} leftSection={<IconShieldCheck size="1.2rem" stroke={1.5} />} />
            </Tooltip>
          )}
        </AppShell.Section>
        
        <AppShell.Section style={{ borderTop: '1px solid #eaeaea', paddingTop: '10px' }}>
          <Group justify={navOpen ? "space-between" : "center"} wrap="nowrap" gap="xs">
            <Menu position="right-end" withArrow>
              <Menu.Target>
                <UnstyledButton p="xs" style={{ borderRadius: '8px', flex: navOpen ? 1 : 'unset', transition: 'background-color 150ms ease' }}>
                  <Group gap="sm" wrap="nowrap">
                    <Avatar radius="xl" size="sm">{user ? (user.nickname || user.username || 'U').substring(0, 2).toUpperCase() : 'U'}</Avatar>
                    {navOpen && (
                      <div style={{ flex: 1, overflow: 'hidden' }}>
                        <Text size="sm" fw={500} truncate>{user?.nickname || user?.username || 'User'}</Text>
                      </div>
                    )}
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item component={NavLink} to="/settings" leftSection={<IconSettings size={14} />}>Settings</Menu.Item>
                <Menu.Item component={NavLink} to="/login" color="red" leftSection={<IconLogin size={14} />} onClick={() => localStorage.removeItem('token')}>Logout</Menu.Item>
              </Menu.Dropdown>
            </Menu>
            <ActionIcon variant="subtle" color="gray" onClick={toggleNav} visibleFrom="sm" style={{ display: navOpen ? 'flex' : 'none' }}>
              <IconLayoutSidebarLeftCollapse size={20} />
            </ActionIcon>
          </Group>
          {!navOpen && (
            <Center mt="sm">
              <ActionIcon variant="subtle" color="gray" onClick={toggleNav} visibleFrom="sm">
                <IconLayoutSidebarLeftExpand size={20} />
              </ActionIcon>
            </Center>
          )}
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main pb={{ base: 64, sm: 0 }} style={{ display: 'flex', flexDirection: 'column', overflow: location.pathname.startsWith('/chat') ? 'hidden' : undefined }}>
        {children}
      </AppShell.Main>
      <AppShell.Footer hiddenFrom="sm" p={0} style={{ borderTop: '1px solid var(--mantine-color-gray-2)' }}>
        <Group justify="space-evenly" gap={0} p="xs" style={{ height: 56 }}>
          {[
            { to: '/dashboard', icon: IconDashboard, label: 'Dashboard' },
            { to: '/mynotes', icon: IconBooks, label: 'Notes' },
            { to: '/chat', icon: IconMessageDots, label: 'Chat' },
            { to: '/upload', icon: IconUpload, label: 'Upload' },
          ].map(item => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.to) ||
              (item.to === '/mynotes' && (location.pathname.startsWith('/group/') || location.pathname.startsWith('/subject/') || location.pathname.startsWith('/resource/') || location.pathname.startsWith('/note/')));
            return (
              <NavLink key={item.to} to={item.to} style={{ textDecoration: 'none', color: isActive ? '#171738' : '#868e96' }}>
                <Stack gap={2} align="center">
                  <Icon size={22} />
                  <Text size={10} fw={isActive ? 600 : 400}>{item.label}</Text>
                </Stack>
              </NavLink>
            );
          })}
          {user?.is_admin && (
            <NavLink to="/admin" style={{ textDecoration: 'none', color: location.pathname === '/admin' ? '#171738' : '#868e96' }}>
              <Stack gap={2} align="center">
                <IconShieldCheck size={22} />
                <Text size={10} fw={location.pathname === '/admin' ? 600 : 400}>Admin</Text>
              </Stack>
            </NavLink>
          )}
          <Menu position="top" withArrow>
            <Menu.Target>
              <UnstyledButton>
                <Stack gap={2} align="center">
                  <Avatar radius="xl" size="sm">{user ? (user.nickname || user.username || 'U').substring(0, 2).toUpperCase() : 'U'}</Avatar>
                  <Text size={10}>Profile</Text>
                </Stack>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component={NavLink} to="/settings" leftSection={<IconSettings size={14} />}>Settings</Menu.Item>
              <Menu.Item component={NavLink} to="/login" color="red" leftSection={<IconLogin size={14} />} onClick={() => localStorage.removeItem('token')}>Logout</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Footer>
      <GlobalToasts />
      <TaskQueueModal />
    </AppShell>
    </>
  );
}



function RootRedirect() {
  const isAuthenticated = !!localStorage.getItem('token');
  return isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />;
}

function NotFound() {
  return (
    <Center style={{ height: '80vh', flexDirection: 'column', gap: 24 }}>
      <img src="https://http.cat/404" alt="404" style={{ height: 300, borderRadius: 12 }} />
      <Text size="xl" fw={600} c="dimmed">Page not found</Text>
      <Button component={NavLink} to="/dashboard" variant="light">Go home</Button>
    </Center>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/docs/:doc" element={<LegalDoc />} />
        <Route path="/*" element={
          <TaskProvider>
            <AppLayout>
              <Routes>
                <Route path="/" element={<RootRedirect />} />
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Login />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/mynotes" element={<NotesManager />} />
                <Route path="/upload" element={<UploadDocs />} />
                <Route path="/chat" element={<ChatInterface />} />
                <Route path="/chat/:cvid" element={<ChatInterface />} />
                <Route path="/exercises/:id" element={<ExerciseView />} />
                <Route path="/exercises/:id/:mode" element={<ExerciseView />} />
                <Route path="/group/:id" element={<GroupView />} />
                <Route path="/subject/:id" element={<SubjectView />} />
                <Route path="/subject/:id/:tab" element={<SubjectView />} />
                <Route path="/resource/:id" element={<NoteView />} />
                <Route path="/note/:summaryId" element={<SummaryView />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </AppLayout>
          </TaskProvider>
        } />
      </Routes>
    </Router>
  );
}

export default App;
