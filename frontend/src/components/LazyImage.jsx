import React, { useEffect, useRef, useState } from 'react';
import { Skeleton } from '@mantine/core';

// Module-level cache: API URL → blob object URL
const imageCache = {};

export const LazyImage = ({ src, alt, title, style, maxWidth, ...props }) => {
  const [actualSrc, setActualSrc] = useState(() => {
    // Synchronously use the cache on first render to avoid flash-of-skeleton for cached images
    if (src && src.startsWith('/api/') && imageCache[src]) {
      return imageCache[src];
    }
    return src && !src.startsWith('/api/') ? src : null;
  });
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const imgRef = useRef(null);

  useEffect(() => {
    if (!src) return;

    // Non-API src: render directly
    if (!src.startsWith('/api/')) {
      setActualSrc(src);
      return;
    }

    // Already cached
    if (imageCache[src]) {
      setActualSrc(imageCache[src]);
      return;
    }

    let isMounted = true;
    const token = localStorage.getItem('token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};

    fetch(src, { headers })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        imageCache[src] = objectUrl;
        if (isMounted) setActualSrc(objectUrl);
      })
      .catch(() => {
        if (isMounted) setError(true);
      });

    return () => { isMounted = false; };
  }, [src]);

  // If the browser already decoded the image before onLoad fired (e.g. from disk cache)
  useEffect(() => {
    if (actualSrc && imgRef.current?.complete && !imgRef.current.naturalWidth === false) {
      setLoaded(true);
    }
  }, [actualSrc]);

  const wrapperStyle = { maxWidth: maxWidth || '100%', margin: '1rem 0' };

  if (error) {
    return (
      <div style={{
        ...wrapperStyle,
        height: 80,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#f8f9fa',
        borderRadius: '8px',
        border: '1px dashed #ced4da',
        color: '#868e96',
        fontSize: '0.85em',
      }}>
        Failed to load image
      </div>
    );
  }

  if (!actualSrc) {
    // Still fetching — show skeleton
    return (
      <div style={wrapperStyle}>
        <Skeleton height={200} width="100%" radius="md" animate />
      </div>
    );
  }

  return (
    <div style={wrapperStyle}>
      {!loaded && <Skeleton height={200} width="100%" radius="md" animate />}
      <img
        ref={imgRef}
        src={actualSrc}
        alt={alt}
        title={title}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        style={{
          display: loaded ? 'block' : 'none',
          width: '100%',
          height: 'auto',
          maxWidth: maxWidth || '100%',
          borderRadius: '8px',
          ...style
        }}
        {...props}
      />
    </div>
  );
};
