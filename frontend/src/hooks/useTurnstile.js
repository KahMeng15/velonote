import { useRef, useCallback, useEffect, useState } from 'react';

// Module-level cache so the key is fetched only once per page load.
let _cachedSiteKey = null;
let _cachedEnabled = false;
let _fetchPromise = null;

async function fetchAuthConfig() {
  if (_cachedSiteKey !== null) {
    return { siteKey: _cachedSiteKey, enabled: _cachedEnabled };
  }
  if (_fetchPromise) return _fetchPromise;

  _fetchPromise = fetch('/api/auth/config')
    .then((res) => res.json())
    .then((data) => {
      _cachedSiteKey = data.turnstile_site_key || '';
      _cachedEnabled = Boolean(data.turnstile_enabled && _cachedSiteKey);
      return { siteKey: _cachedSiteKey, enabled: _cachedEnabled };
    })
    .catch(() => {
      _cachedSiteKey = '';
      _cachedEnabled = false;
      return { siteKey: '', enabled: false };
    });

  return _fetchPromise;
}

export function useTurnstile() {
  const widgetIdRef = useRef(null);
  const containerElRef = useRef(null);
  const [siteKey, setSiteKey] = useState(_cachedSiteKey || '');
  const [enabled, setEnabled] = useState(_cachedEnabled);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (_cachedSiteKey !== null) {
      setSiteKey(_cachedSiteKey);
      setEnabled(_cachedEnabled);
      return;
    }
    fetchAuthConfig().then(({ siteKey: key, enabled: isEnabled }) => {
      setSiteKey(key);
      setEnabled(isEnabled);
    });
  }, []);

  // If enabled but window.turnstile script never loads (e.g. adblocker/offline), fail open
  useEffect(() => {
    if (!enabled || !siteKey) return;
    if (window.turnstile) return;

    const timer = setTimeout(() => {
      if (!window.turnstile) {
        console.warn('[Turnstile] Script did not load in time; bypassing Turnstile requirement.');
        setHasError(true);
      }
    }, 4000);

    return () => clearTimeout(timer);
  }, [enabled, siteKey]);

  const renderWidget = useCallback(
    (el) => {
      if (!el || !enabled || !siteKey || !window.turnstile || hasError) return;
      if (el.dataset.turnstileWidget) {
        window.turnstile.reset(el.dataset.turnstileWidget);
        return;
      }
      try {
        const id = window.turnstile.render(el, {
          sitekey: siteKey,
          theme: 'light',
          'error-callback': (code) => {
            console.warn(`[Turnstile] Widget error (code: ${code}); bypassing verification.`);
            setHasError(true);
          },
        });
        el.dataset.turnstileWidget = id;
        widgetIdRef.current = id;
      } catch (err) {
        console.warn('[Turnstile] Failed to render widget:', err);
        setHasError(true);
      }
    },
    [enabled, siteKey, hasError],
  );

  const containerRef = useCallback(
    (el) => {
      containerElRef.current = el;
      renderWidget(el);
    },
    [renderWidget],
  );

  // Once we have the site key and the container is already mounted, render the widget.
  useEffect(() => {
    const el = containerElRef.current;
    renderWidget(el);
  }, [renderWidget]);

  const isRequired = Boolean(enabled && !hasError);

  const getToken = useCallback(() => {
    if (!isRequired) return '';
    if (widgetIdRef.current && window.turnstile) {
      return window.turnstile.getResponse(widgetIdRef.current);
    }
    return '';
  }, [isRequired]);

  const reset = useCallback(() => {
    if (widgetIdRef.current && window.turnstile) {
      try {
        window.turnstile.reset(widgetIdRef.current);
      } catch (e) {}
      widgetIdRef.current = null;
    }
  }, []);

  return { containerRef, getToken, reset, enabled, hasError, isRequired };
}
