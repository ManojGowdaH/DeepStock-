const API_BASE_URL = 'https://deepstock-thtj.onrender.com';

class ApiError extends Error {
  constructor(message, { status = 0, detail = '' } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function apiRequest(path, options = {}) {
  const url = /^https?:\/\//i.test(path) ? path : `${API_BASE_URL}${path}`;
  const timeoutMs = options.timeoutMs ?? 30000;
  const retries = options.retries ?? 1;
  const { timeoutMs: _ignoredTimeout, retries: _ignoredRetries, ...requestOptions } = options;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...requestOptions,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...requestOptions.headers,
        },
      });

      let payload;
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        try {
          payload = await response.json();
        } catch {
          throw new ApiError('The server returned invalid JSON.', { status: response.status });
        }
      }

      if (!response.ok) {
        const reason = payload?.detail || payload?.message || `Request failed with status ${response.status}.`;
        throw new ApiError(formatApiError(response.status, reason), { status: response.status, detail: reason });
      }

      return payload ?? response;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error.name === 'AbortError') {
        if (attempt < retries) continue;
        throw new ApiError('The DeepStock AI server is taking too long to respond. Please try again.', { status: 504 });
      }
      if (attempt < retries) continue;
      throw new ApiError('Unable to connect to the DeepStock AI server. Please try again in a moment.', { status: 0 });
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  throw new ApiError('Unable to complete the request.', { status: 0 });
}

function formatApiError(status, detail) {
  const friendlyMessages = {
    400: 'The request could not be processed. Please check your inputs.',
    401: 'Authentication is required to use this endpoint.',
    403: 'This operation is not allowed.',
    404: 'The requested stock information was not found.',
    429: 'Too many requests. Please wait a moment and try again.',
    500: 'The server encountered an error. Please try again later.',
    502: 'The data provider is unavailable right now. Please try again later.',
    503: 'The DeepStock AI server is temporarily unavailable. Please try again in a moment.',
  };

  return friendlyMessages[status] || detail || 'The request could not be completed.';
}
