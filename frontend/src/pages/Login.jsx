import { useState, useEffect } from 'react';
import { useMediaQuery } from '@mantine/hooks';
import {
  TextInput,
  PasswordInput,
  Checkbox,
  Anchor,
  Text,
  Group,
  Button,
  Stack,
  Flex,
  Box,
  Title,
  Alert,
  Divider,
} from '@mantine/core';
import { IconCheck, IconAlertCircle, IconInfoCircle } from '@tabler/icons-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchApi, setAuthToken } from '../lib/api';
import { useTurnstile } from '../hooks/useTurnstile';

// Firebase imports
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithPopup, GoogleAuthProvider } from 'firebase/auth';

const quotes = [
  { text: "The beautiful thing about learning is that no one can take it away from you.", author: "B.B. King" },
  { text: "Education is the passport to the future, for tomorrow belongs to those who prepare for it today.", author: "Malcolm X" },
  { text: "The future belongs to those who believe in the beauty of their dreams.", author: "Eleanor Roosevelt" },
  { text: "Don't let what you cannot do interfere with what you can do.", author: "John Wooden" }
];

// Cache Firebase app instance
let _firebaseAuth = null;

async function getFirebaseAuth() {
  if (_firebaseAuth) return _firebaseAuth;
  const config = await fetch('/api/auth/firebase-config').then(r => r.json());
  const app = initializeApp(config);
  _firebaseAuth = getAuth(app);
  return _firebaseAuth;
}

export default function Login() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [panel, setPanel] = useState('login'); // 'login' | 'register' | 'forgot' | 'google-complete' | 'verify' | 'reset'
  const turnstile = useTurnstile();

  const [quote, setQuote] = useState(quotes[0]);

  // Shared state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Login state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [resending, setResending] = useState(false);

  // Register state
  const [regNickname, setRegNickname] = useState('');
  const [regFullName, setRegFullName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [agreeTos, setAgreeTos] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreeFairUse, setAgreeFairUse] = useState(false);
  const [googleApprovalSignup, setGoogleApprovalSignup] = useState(false);

  // Password reset state
  const [resetToken, setResetToken] = useState('');
  const [resetNewPassword, setResetNewPassword] = useState('');
  const [resetConfirmPassword, setResetConfirmPassword] = useState('');

  // Forgot password state
  const [forgotEmail, setForgotEmail] = useState('');

  // Google "complete profile" state
  const [googleIdToken, setGoogleIdToken] = useState(null);
  const [googleNickname, setGoogleNickname] = useState('');
  const [googleFullName, setGoogleFullName] = useState('');
  const [googleAgreeTos, setGoogleAgreeTos] = useState(false);
  const [googleAgreePrivacy, setGoogleAgreePrivacy] = useState(false);
  const [googleAgreeFairUse, setGoogleAgreeFairUse] = useState(false);

  // Public settings
  const [signupConfig, setSignupConfig] = useState('open');
  const [maintenanceMode, setMaintenanceMode] = useState(false);

  // Invitation token from URL
  const [invitationToken, setInvitationToken] = useState(null);
  const [invitedEmail, setInvitedEmail] = useState('');

  useEffect(() => {
    const inviteToken = searchParams.get('token');
    if (inviteToken) {
      setInvitationToken(inviteToken);
      fetch(`/api/auth/invitation/${encodeURIComponent(inviteToken)}`)
        .then(r => { if (r.ok) return r.json(); throw new Error(); })
        .then(data => {
          if (data.email) setInvitedEmail(data.email);
          setPanel('register');
        })
        .catch(() => setError('Invalid or expired invitation link.'));
    }
  }, []);

  useEffect(() => {
    setQuote(quotes[Math.floor(Math.random() * quotes.length)]);
    fetch('/api/auth/public-settings').then(r => r.json()).then(data => {
      if (data) {
        setSignupConfig(data.signup_config || 'open');
        setMaintenanceMode(data.maintenance_mode || false);
      }
    }).catch(() => {});

    // Auto-handle password reset token in URL
    const resetTokenParam = searchParams.get('reset_token');
    if (resetTokenParam) {
      setResetToken(resetTokenParam);
      setPanel('reset');
      fetch(`/api/auth/password-reset-token-valid?token=${encodeURIComponent(resetTokenParam)}`)
        .then(r => r.json())
        .then(data => {
          if (!data.valid) {
            setError(data.message || 'Invalid or expired reset link.');
            setPanel('login');
          }
        })
        .catch(() => {
          setError('Failed to validate reset link.');
          setPanel('login');
        });
      return;
    }

    // Auto-handle email verification token in URL
    const verifyToken = searchParams.get('verify_token');
    if (verifyToken) {
      setPanel('verify');
      const controller = new AbortController();
      fetch('/api/auth/verify-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: verifyToken }),
        signal: controller.signal,
      })
        .then(r => r.json())
        .then(data => {
          setPanel('login');
          setSearchParams({}, { replace: true });
          if (data.detail && !data.access_token) {
            setError(data.detail);
          } else {
            setSuccess(data.message || 'Email verified!');
          }
        })
        .catch(err => {
          if (err.name === 'AbortError') return;
          setPanel('login');
          setSearchParams({}, { replace: true });
          setError('Verification request failed.');
        });
      return () => controller.abort();
    }
  }, []);

  const switchPanel = (p) => {
    setError(null);
    setSuccess(null);
    setPanel(p);
  };

  const handleAuthSuccess = async (data) => {
    setAuthToken(data.access_token);
    if (data.user) localStorage.setItem('user', JSON.stringify(data.user));
    try {
      const userProfile = await fetchApi('/auth/me');
      localStorage.setItem('user', JSON.stringify(userProfile));
    } catch {}
    navigate('/dashboard');
  };

  // ── LOGIN ──────────────────────────────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, cf_turnstile_response: cfToken }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to login');
      await handleAuthSuccess(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  const isVerificationError = error && error.toLowerCase().includes('not verified');

  const handleResendVerification = async (emailAddr) => {
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    setResending(true);
    try {
      const res = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailAddr, cf_turnstile_response: cfToken }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to resend');
      setError(null);
      setSuccess('Verification email sent! Check your inbox (and spam folder).');
    } catch (err) {
      setError(err.message);
    } finally {
      setResending(false);
      turnstile.reset();
    }
  };

  // ── GOOGLE SIGN-IN ─────────────────────────────────────────────────────────
  const handleGoogleSignIn = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const auth = await getFirebaseAuth();
      const provider = new GoogleAuthProvider();
      provider.setCustomParameters({ prompt: 'select_account' });
      const result = await signInWithPopup(auth, provider);
      const idToken = await result.user.getIdToken();

      const cfToken = turnstile.getToken();
      if (!cfToken) {
        turnstile.reset();
        setError('Please complete the human verification before signing in with Google.');
        return;
      }

      const res = await fetch('/api/auth/google-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken, invitation_token: invitationToken, cf_turnstile_response: cfToken }),
      });
      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || 'Google sign-in failed');

      if (data.is_new_user) {
        setGoogleIdToken(idToken);
        setGoogleFullName(data.full_name || '');
        setGoogleNickname(data.suggested_nickname || '');
        switchPanel('google-complete');
      } else {
        await handleAuthSuccess(data);
      }
    } catch (err) {
      if (err.code !== 'auth/popup-closed-by-user') {
        setError(err.message || 'Google sign-in failed');
      }
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  // ── GOOGLE COMPLETE PROFILE ────────────────────────────────────────────────
  const handleGoogleComplete = async (e) => {
    e.preventDefault();
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    if (!googleAgreeTos || !googleAgreePrivacy || !googleAgreeFairUse) {
      setError('You must agree to all policies to register.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/auth/google-complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idToken: googleIdToken,
          nickname: googleNickname,
          full_name: googleFullName,
          invitation_token: invitationToken,
          agree_tos: googleAgreeTos,
          agree_privacy: googleAgreePrivacy,
          agree_fair_use: googleAgreeFairUse,
          cf_turnstile_response: cfToken,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Profile completion failed');
      if (data.pending_approval) {
        setSearchParams({}, { replace: true });
        setGoogleApprovalSignup(true);
        setPanel('registration-done');
      } else {
        await handleAuthSuccess(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  // ── REGISTER ───────────────────────────────────────────────────────────────
  const handleRegister = async (e) => {
    e.preventDefault();
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    if (!agreeTos || !agreePrivacy || !agreeFairUse) {
      setError('You must agree to all policies to register.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const url = invitationToken ? `/api/auth/register?token=${encodeURIComponent(invitationToken)}` : '/api/auth/register';
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: invitedEmail || regEmail,
          password: regPassword,
          nickname: regNickname,
          full_name: regFullName,
          agree_tos: agreeTos,
          agree_privacy: agreePrivacy,
          agree_fair_use: agreeFairUse,
          cf_turnstile_response: cfToken,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = Array.isArray(data.detail)
          ? data.detail.map(d => d.msg).join(', ')
          : data.detail || 'Registration failed';
        throw new Error(msg);
      }
      setError(null);
      setSearchParams({}, { replace: true });
      setPanel('registration-done');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  // ── FORGOT PASSWORD ────────────────────────────────────────────────────────
  const handleForgotPassword = async (e) => {
    e.preventDefault();
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/auth/password-reset-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: forgotEmail, cf_turnstile_response: cfToken }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Request failed');
      setSuccess('If that email is registered, a reset link has been sent. Check your spam folder if you don\'t see it.');
      setError(null);
      setPanel('login');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  // ── RESET PASSWORD ──
  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (resetNewPassword !== resetConfirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (resetNewPassword.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    const cfToken = turnstile.getToken();
    if (!cfToken) {
      setError('Please complete the human verification.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/auth/password-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: resetToken, new_password: resetNewPassword, cf_turnstile_response: cfToken }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Password reset failed');
      setSuccess(data.message || 'Password has been reset! You can now log in.');
      setSearchParams({}, { replace: true });
      setTimeout(() => switchPanel('login'), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      turnstile.reset();
    }
  };

  const PolicyCheckboxes = ({ agreeTos, setAgreeTos, agreePrivacy, setAgreePrivacy, agreeFairUse, setAgreeFairUse, prefix = '' }) => (
    <Box mt="md" p="md" bg="gray.0" style={{ border: '1px solid #ddd', borderRadius: '4px' }}>
      <Text fw={600} size="sm" mb="sm">I agree to:</Text>
      <Stack gap="xs">
        <Checkbox
          id={`${prefix}agree-tos`}
          checked={agreeTos}
          onChange={(e) => setAgreeTos(e.currentTarget.checked)}
          label={<Anchor href="/docs/termsofservice" target="_blank" size="sm">Terms of Service</Anchor>}
        />
        <Checkbox
          id={`${prefix}agree-privacy`}
          checked={agreePrivacy}
          onChange={(e) => setAgreePrivacy(e.currentTarget.checked)}
          label={<Anchor href="/docs/privacypolicy" target="_blank" size="sm">Privacy Policy</Anchor>}
        />
        <Checkbox
          id={`${prefix}agree-fair-use`}
          checked={agreeFairUse}
          onChange={(e) => setAgreeFairUse(e.currentTarget.checked)}
          label={<Anchor href="/docs/fairuse" target="_blank" size="sm">Fair Use Policy</Anchor>}
        />
      </Stack>
    </Box>
  );

  const GoogleIcon = () => (
    <svg viewBox="0 0 24 24" width={20} height={20} xmlns="http://www.w3.org/2000/svg">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  );

  const wide = useMediaQuery('(min-width: 1500px)');
  const qFont = wide ? '4.5rem' : '3rem';
  const mFont = wide ? '5rem' : '3.5rem';
  const aFont = wide ? '2rem' : '1.5rem';

  return (
    <Flex h="100vh" bg="#fff" p={0}>

      {/* Left Side: Quotes & Gradient */}
      <Box
        visibleFrom="md"
        style={{
          width: '50%',
          background: 'linear-gradient(160deg, #171738 0%, #593C8F 55%, #8EF9F3 100%)',
          margin: '1.5rem',
          borderRadius: '1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px',
          position: 'relative',
          flexShrink: 0,
        }}
      >
        <Box style={{ maxWidth: '90%', display: 'flex', flexDirection: 'column' }}>
          <Group align="flex-start" wrap="nowrap" gap="sm" mb="lg">
            <Text ff="Instrument Serif, serif" c="rgba(255, 255, 255, 0.4)" style={{ fontSize: mFont, lineHeight: 0.8, marginTop: '3px' }}>
              "
            </Text>
            <Text ff="Instrument Serif, serif" fs="italic" c="#fff" style={{ fontSize: qFont, lineHeight: 0.9, flex: 1 }}>
              {quote.text}
            </Text>
            <Text ff="Instrument Serif, serif" c="rgba(255, 255, 255, 0.4)" style={{ fontSize: mFont, lineHeight: 0.8, alignSelf: 'flex-end', marginBottom: '-10px' }}>
              "
            </Text>
          </Group>
          <Text ff="Instrument Sans, sans-serif" c="#fff" fw={500} style={{ fontSize: aFont, alignSelf: 'flex-end', opacity: 0.9 }}>
            {quote.author}
          </Text>
        </Box>
      </Box>

      {/* Right Side: Auth Forms */}
        <Box
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            padding: '32px 5%',
            backgroundColor: '#fff',
            overflowY: 'auto',
          }}
        >
          <Box style={{ width: '100%', maxWidth: '420px', margin: '0 auto' }}>
            <Box mb={40}>
              <Box ta="center">
                <img src="/velonote.svg" height={48} alt="velonote" style={{ display: 'block', margin: '0 auto' }} />
                <Text fw={900} c="#171738" style={{ fontFamily: 'Instrument Sans, sans-serif', fontSize: 'clamp(1.5rem, 6vw, 2.5rem)', lineHeight: 1 }}>
                  velo<span style={{ color: '#593C8F' }}>note</span>
                </Text>
              </Box>
            </Box>

          {success && (
            <Alert icon={<IconCheck size={16} />} color="teal" mb="md" withCloseButton onClose={() => setSuccess(null)}>
              {success}
            </Alert>
          )}
          {error && !isVerificationError && (
            <Alert icon={<IconAlertCircle size={16} />} color="red" mb="md" withCloseButton onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* ── LOGIN ── */}
          {panel === 'login' && (
            <form onSubmit={handleLogin}>
              {maintenanceMode && (
                <Alert icon={<IconAlertCircle size={16} />} color="yellow" mb="md">
                  🔧 Maintenance in progress, brb
                </Alert>
              )}
              {isVerificationError && (
                <Alert icon={<IconAlertCircle size={16} />} color="red" mb="md" withCloseButton onClose={() => setError(null)}>
                  {resending ? (
                    <>Sending verification email…</>
                  ) : (
                    <>Your email has not been verified yet. Please check your inbox (and spam folder) or{' '}
                      <Anchor component="button" type="button" c="red" onClick={() => handleResendVerification(email)}>
                        resend the verification email
                      </Anchor>.</>
                  )}
                </Alert>
              )}
              <Stack gap="md">
                <TextInput
                  id="login-email"
                  label="Email"
                  placeholder="you@email.com"
                  required
                  size="md"
                  value={email}
                  onChange={(e) => setEmail(e.currentTarget.value)}
                />
                <PasswordInput
                  id="login-password"
                  label="Password"
                  placeholder="••••••••"
                  required
                  size="md"
                  value={password}
                  onChange={(e) => setPassword(e.currentTarget.value)}
                />
              </Stack>

              <Button id="btn-login" fullWidth size="md" type="submit" loading={loading} mt="xl" style={{ backgroundColor: '#171738' }}>
                Log In
              </Button>

              {!maintenanceMode && (
                <>
                  <Divider label="or" labelPosition="center" my="md" />

                  <Button
                    id="btn-google-login"
                    fullWidth
                    size="md"
                    variant="outline"
                    color="gray"
                    leftSection={<GoogleIcon />}
                    style={{ color: '#171738', borderColor: '#ccc' }}
                    loading={loading}
                    type="button"
                    onClick={handleGoogleSignIn}
                  >
                    Continue with Google
                  </Button>
                </>
              )}

              {signupConfig === 'approval' && !maintenanceMode && (
                <Alert icon={<IconInfoCircle size={16} />} py="xs" mt="md">
                  <Text size="sm">Account registration requires approval from an administrator.</Text>
                </Alert>
              )}

              <Box mt="md" ref={turnstile.containerRef} ta="center" />

              <Group mt="lg" gap="xs" justify="center">
                {signupConfig === 'invite' ? (
                  <Text size="sm" c="dimmed" ta="center">Invite only system, contact the system administrator to sign up and use this app.</Text>
                ) : maintenanceMode ? null : (
                  <>
                  <Text size="sm" c="dimmed">Don't have an account? </Text>
                  <Anchor component="button" type="button" size="sm" onClick={() => switchPanel('register')}>
                    Sign Up
                  </Anchor>
                  </>
                )}
              </Group>
              <Group mt={5} justify="center">
                <Anchor component="button" type="button" size="sm" onClick={() => switchPanel('forgot')}>
                  Forgot password?
                </Anchor>
              </Group>
            </form>
          )}

          {/* ── REGISTER ── */}
          {panel === 'register' && (
            signupConfig === 'invite' && !invitationToken ? (
              <Box py={40}>
                <Title order={2} mb="md" c="#171738">Registration is invite-only</Title>
                <Text size="md" c="dimmed" mb="xl">
                  New account registration is currently restricted to invited users only. Contact an administrator to request an invitation.
                </Text>
                <Button fullWidth size="md" style={{ backgroundColor: '#171738' }} onClick={() => switchPanel('login')}>
                  Back to Login
                </Button>
              </Box>
            ) : (
            <form onSubmit={handleRegister}>
              <Button
                id="btn-google-signup"
                fullWidth
                size="md"
                variant="outline"
                color="gray"
                leftSection={<GoogleIcon />}
                mb="md"
                style={{ color: '#171738', borderColor: '#ccc' }}
                loading={loading}
                type="button"
                onClick={handleGoogleSignIn}
              >
                Sign up with Google
              </Button>

              <Divider label="or sign up manually" labelPosition="center" mb="md" />

              <Stack gap="md">
                <TextInput
                  id="reg-nickname"
                  required
                  label="Nickname"
                  placeholder="What should we call you?"
                  size="md"
                  value={regNickname}
                  onChange={(e) => setRegNickname(e.currentTarget.value)}
                />
                <TextInput
                  id="reg-fullname"
                  label="Full Name"
                  placeholder="Your full name"
                  size="md"
                  value={regFullName}
                  onChange={(e) => setRegFullName(e.currentTarget.value)}
                />
                <TextInput
                  id="reg-email"
                  required
                  label="Email"
                  placeholder="you@email.com"
                  size="md"
                  value={invitedEmail || regEmail}
                  disabled={!!invitedEmail}
                  onChange={(e) => setRegEmail(e.currentTarget.value)}
                />
                <PasswordInput
                  id="reg-password"
                  required
                  label="Password"
                  placeholder="••••••••"
                  size="md"
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.currentTarget.value)}
                />
              </Stack>

              <PolicyCheckboxes
                agreeTos={agreeTos} setAgreeTos={setAgreeTos}
                agreePrivacy={agreePrivacy} setAgreePrivacy={setAgreePrivacy}
                agreeFairUse={agreeFairUse} setAgreeFairUse={setAgreeFairUse}
                prefix="reg-"
              />

              <Button id="btn-register" fullWidth size="md" mt="xl" type="submit" loading={loading} style={{ backgroundColor: '#171738' }}>
                Create Account
              </Button>

              {signupConfig === 'approval' && (
                <Alert icon={<IconInfoCircle size={16} />} py="xs" mt="md">
                  <Text size="sm">After verifying your email, your account will need to be approved by an administrator before you can log in.</Text>
                </Alert>
              )}

              <Box mt="md" ref={turnstile.containerRef} />

              <Group mt="lg" gap="xs" justify="center">
                <Text size="sm" c="dimmed">Already have an account?</Text>
                <Anchor component="button" type="button" size="sm" onClick={() => switchPanel('login')}>
                  Log in
                </Anchor>
              </Group>
            </form>
            )
          )}

          {/* ── REGISTRATION DONE ── */}
          {panel === 'registration-done' && (
            <Box py={40}>
              <Title order={2} mb="md" c="#171738">Account created!</Title>
              {signupConfig === 'approval' ? (
                googleApprovalSignup ? (
                  <>
                    <Text size="md" c="dimmed" mb="xl">
                      Your account has been created and is pending administrator approval. We'll notify you once it is ready.
                    </Text>
                  </>
                ) : (
                  <>
                    <Text size="md" c="dimmed" mb="xs">
                      We've sent a verification email to <strong>{invitedEmail || regEmail}</strong>.
                    </Text>
                    <Text size="md" c="dimmed" mb="xs">
                      Please verify your email using the link sent to your inbox.
                    </Text>
                    <Text size="md" c="dimmed" mb="xl">
                      After verification, your account will be reviewed by an administrator. You'll receive an email once your account is approved.
                    </Text>
                  </>
                )
              ) : (
                <>
                  <Text size="md" c="dimmed" mb="xs">
                    We've sent a verification email to <strong>{invitedEmail || regEmail}</strong>.
                  </Text>
                  <Text size="md" c="dimmed" mb="xl">
                    Please check your inbox (and spam folder) and click the link to verify your account before logging in.
                  </Text>
                </>
              )}
              <Button fullWidth size="md" style={{ backgroundColor: '#171738' }} onClick={() => switchPanel('login')}>
                Continue to Login
              </Button>
              {!googleApprovalSignup && (
              <Text size="sm" c="dimmed" mt="md">
                Didn't receive the email?{' '}
                {resending ? (
                  'Sending…'
                ) : (
                  <Anchor component="button" type="button" size="sm" onClick={() => handleResendVerification(invitedEmail || regEmail)}>
                    Resend verification email
                  </Anchor>
                )}
              </Text>
              )}
            </Box>
          )}

          {/* ── GOOGLE COMPLETE PROFILE ── */}
          {panel === 'google-complete' && (
            <form onSubmit={handleGoogleComplete}>
              <Text size="md" fw={600} mb="sm" c="#171738">Complete your profile</Text>
              <Text size="sm" c="dimmed" mb="lg">
                Just a few more details to get you started with Google sign-in.
              </Text>
              <Stack gap="md">
                <TextInput
                  id="gc-nickname"
                  required
                  label="Nickname"
                  placeholder="What should we call you?"
                  size="md"
                  value={googleNickname}
                  onChange={(e) => setGoogleNickname(e.currentTarget.value)}
                />
                <TextInput
                  id="gc-fullname"
                  label="Full Name"
                  placeholder="Your full name"
                  size="md"
                  value={googleFullName}
                  onChange={(e) => setGoogleFullName(e.currentTarget.value)}
                />
              </Stack>

              <PolicyCheckboxes
                agreeTos={googleAgreeTos} setAgreeTos={setGoogleAgreeTos}
                agreePrivacy={googleAgreePrivacy} setAgreePrivacy={setGoogleAgreePrivacy}
                agreeFairUse={googleAgreeFairUse} setAgreeFairUse={setGoogleAgreeFairUse}
                prefix="gc-"
              />

              <Box mt="md" ref={turnstile.containerRef} />
              <Button id="btn-gc-submit" fullWidth size="md" mt="xl" type="submit" loading={loading} style={{ backgroundColor: '#171738' }}>
                Finish Sign Up
              </Button>
            </form>
          )}

          {/* ── VERIFY ── */}
          {panel === 'verify' && (
            <Box py={0}>
              <Text size="lg" c="dimmed">Verifying your email, please hang on…</Text>
            </Box>
          )}

          {/* ── FORGOT PASSWORD ── */}
          {panel === 'forgot' && (
            <form onSubmit={handleForgotPassword}>
              <Text size="md" c="dimmed" mb="lg">
                Enter your email address and we will send you a link to reset your password.
              </Text>
              <TextInput
                id="forgot-email"
                required
                label="Email"
                placeholder="you@email.com"
                size="md"
                mb="xl"
                value={forgotEmail}
                onChange={(e) => setForgotEmail(e.currentTarget.value)}
              />
              <Button id="btn-reset" fullWidth size="md" type="submit" loading={loading} style={{ backgroundColor: '#171738' }}>
                Send Reset Link
              </Button>
              <Box mt="md" ref={turnstile.containerRef} />
              <Group mt="lg" gap="xs" justify="center">
                <Anchor component="button" type="button" size="sm" onClick={() => switchPanel('login')}>
                  Back to Login
                </Anchor>
              </Group>
            </form>
          )}

          {/* ── RESET PASSWORD ── */}
          {panel === 'reset' && (
            <form onSubmit={handleResetPassword}>
              <Text size="md" c="dimmed" mb="lg">
                Enter your new password.
              </Text>
              <Stack gap="md">
                <PasswordInput
                  id="reset-password"
                  required
                  label="New Password"
                  placeholder="••••••••"
                  size="md"
                  value={resetNewPassword}
                  onChange={(e) => setResetNewPassword(e.currentTarget.value)}
                />
                <PasswordInput
                  id="reset-confirm"
                  required
                  label="Confirm Password"
                  placeholder="••••••••"
                  size="md"
                  value={resetConfirmPassword}
                  onChange={(e) => setResetConfirmPassword(e.currentTarget.value)}
                />
              </Stack>
              <Button id="btn-reset-password" fullWidth size="md" type="submit" loading={loading} mt="xl" style={{ backgroundColor: '#171738' }}>
                Reset Password
              </Button>
              <Box mt="md" ref={turnstile.containerRef} />
              <Group mt="lg" gap="xs" justify="center">
                <Anchor component="button" type="button" size="sm" onClick={() => { setSearchParams({}, { replace: true }); switchPanel('login'); }}>
                  Back to Login
                </Anchor>
              </Group>
            </form>
          )}
        </Box>
      </Box>
    </Flex>
  );
}
