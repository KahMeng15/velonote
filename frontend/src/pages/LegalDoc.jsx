import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Text, Button, Center, Loader } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';

const DOC_TITLES = {
  termsofservice: 'Terms of Service',
  privacypolicy: 'Privacy Policy',
  fairuse: 'Fair Use Policy',
};

export default function LegalDoc() {
  const { doc } = useParams();
  const navigate = useNavigate();
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!DOC_TITLES[doc]) {
      setError('Document not found');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/support/${doc}`)
      .then(r => {
        if (!r.ok) throw new Error('Failed to load document');
        return r.json();
      })
      .then(data => {
        let html = data.content || '';
        html = html.replace(/<link[^>]*>/g, '');
        html = html.replace(/<button class="close-button".*?<\/button>/, '');
        html = html.replace(/<\/?html[^>]*>/g, '');
        html = html.replace(/<\/?head[^>]*>/g, '');
        html = html.replace(/<\/?body[^>]*>/g, '');
        html = html.replace(/<!DOCTYPE[^>]*>/i, '');
        setContent(html);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [doc]);

  return (
    <Box style={{ maxWidth: 800, margin: '0 auto', padding: '40px 24px' }}>
      <Button
        variant="subtle"
        leftSection={<IconArrowLeft size={18} />}
        onClick={() => { if (window.history.length > 1) { navigate(-1); } else { window.close(); } }}
        mb="xl"
        c="dimmed"
      >
        Back to Login
      </Button>

      {loading && (
        <Center py={80}>
          <Loader />
        </Center>
      )}

      {error && (
        <Text c="red">{error}</Text>
      )}

      {!loading && !error && (
        <Box dangerouslySetInnerHTML={{ __html: content }} />
      )}
    </Box>
  );
}
