import { useRef, useCallback, useEffect, useState } from 'react';

// Module-level cache so the key is fetched only once per page load.
let _cachedSiteKey = null;
let _fetchPromise = null;

async function fetchSiteKey() {
  if (_cachedSiteKey !== null) return _cachedSiteKey;
  if (_fetchPromise) return _fetchPromise;

  _fetchPromise = fetch('/api/auth/config')
    .then((res) => res.json())
    .then((data) => {
      _cachedSiteKey = data.turnstile_site_key || '';
      return _cachedSiteKey;
    })
    .catch(() => {
      _cachedSiteKey = '';
      return '';
    });

  return _fetchPromise;
}

export function useTurnstile() {
  const widgetIdRef = useRef(null);
  const containerElRef = useRef(null);
  const [siteKey, setSiteKey] = useState(_cachedSiteKey);

  useEffect(() => {
    if (_cachedSiteKey !== null) {
      setSiteKey(_cachedSiteKey);
      return;
    }
    fetchSiteKey().then(setSiteKey);
  }, []);

  const containerRef = useCallback(
    (el) => {
      containerElRef.current = el;
      if (!el || !siteKey || !window.turnstile) return;
      if (el.dataset.turnstileWidget) {
        window.turnstile.reset(el.dataset.turnstileWidget);
        return;
      }
      const id = window.turnstile.render(el, {
        sitekey: siteKey,
        theme: 'light',
      });
      el.dataset.turnstileWidget = id;
      widgetIdRef.current = id;
    },
    [siteKey],
  );

  // Once we have the site key and the container is already mounted, render the widget.
  useEffect(() => {
    const el = containerElRef.current;
    if (!el || !siteKey || !window.turnstile) return;
    if (el.dataset.turnstileWidget) return; // already rendered
    const id = window.turnstile.render(el, {
      sitekey: siteKey,
      theme: 'light',
    });
    el.dataset.turnstileWidget = id;
    widgetIdRef.current = id;
  }, [siteKey]);

  const getToken = useCallback(() => {
    if (widgetIdRef.current && window.turnstile) {
      return window.turnstile.getResponse(widgetIdRef.current);
    }
    return '';
  }, []);

  const reset = useCallback(() => {
    if (widgetIdRef.current && window.turnstile) {
      window.turnstile.reset(widgetIdRef.current);
      widgetIdRef.current = null;
    }
  }, []);

  return { containerRef, getToken, reset };
}
