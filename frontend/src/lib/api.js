// API Client Wrapper

const API_BASE = '/api';

export const getAuthToken = () => {
  return localStorage.getItem('token');
};

export const setAuthToken = (token) => {
  localStorage.setItem('token', token);
};

export const clearAuthToken = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
};

export const apiEventEmitter = new EventTarget();

/** Notify the global task queue to refresh immediately (e.g. after starting a background job). */
export function notifyTaskStarted() {
  window.dispatchEvent(new CustomEvent('task_started'));
}

/**
 * Core fetch wrapper that automatically attaches the JWT token
 * and prefixes the URL with /api (which Vite proxies to FastAPI).
 */
export async function fetchApi(endpoint, options = {}) {
  const token = getAuthToken();
  const headers = { ...options.headers };

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Handle CSRF Token from cookie
  const method = (options.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
    if (csrfMatch && csrfMatch[1]) {
      headers['X-CSRF-Token'] = decodeURIComponent(csrfMatch[1]);
    }
  }

  const fetchOptions = {
    ...options,
    headers,
  };

  if (!options.method || options.method.toUpperCase() === 'GET') {
    fetchOptions.cache = options.cache || 'no-store';
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, fetchOptions);
  } catch (err) {
    if (!options.quietFail) {
      window.dispatchEvent(new CustomEvent('apiError', {
        detail: { message: 'Could not connect to the server. The application or database may be down.', status: 0 }
      }));
    }
    throw new Error('Service unreachable');
  }

  if (response.status === 401) {
    // Handle unauthorized globally (e.g. log out)
    clearAuthToken();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (response.status === 503) {
    let errorMsg = 'Service unavailable';
    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const errorData = await response.json();
        errorMsg = errorData.detail || errorMsg;
      }
    } catch (e) {}
    // Maintenance mode: redirect to /login without clearing token
    if (errorMsg.toLowerCase().includes('maintenance')) {
      window.location.href = '/login';
      throw new Error(errorMsg);
    }
  }

  if (!response.ok) {
    let errorMsg = 'An error occurred';
    let catUrl = null;
    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const errorData = await response.json();
        errorMsg = errorData.detail || errorMsg;
        catUrl = errorData.cat_url || null;
      } else {
        const textData = await response.text();
        if (textData && textData.length < 200) {
          errorMsg = textData;
        }
      }
    } catch (e) {}
    
    if (response.status === 500) {
      errorMsg = "Internal Server Error: " + errorMsg;
    }
    
    window.dispatchEvent(new CustomEvent('apiError', {
      detail: { message: errorMsg, status: response.status, catUrl }
    }));
    throw new Error(errorMsg);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  // Try to parse JSON response, but tolerate non-JSON bodies (race conditions, HTML errors)
  try {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return await response.json();
    }
    // If no JSON content-type, attempt to parse but fall back to text/null on failure
    try {
      return await response.json();
    } catch (e) {
      const text = await response.text();
      return text ? text : null;
    }
  } catch (e) {
    return null;
  }
}
