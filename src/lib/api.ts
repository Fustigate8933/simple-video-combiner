const API_BASE_URL = 'http://127.0.0.1:8765'

export interface ScanResponse {
  mp4_count: number
  image_count: number
  music_count: number
}

export interface MergeOptions {
  source_dir: string
  output_file: string
  music_dir: string
  photo_duration: number
  original_volume: number
  music_volume: number
}

export interface DryRunResponse {
  command: string[]
  command_text: string
  messages: string[]
  summary: ScanResponse
}

export interface JobCreateResponse {
  job_id: string
}

export interface JobStatusResponse {
  job_id: string
  status: string
  logs: string[]
  error: string | null
}

interface ErrorPayload {
  detail?: string
  message?: string
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  return text ? (JSON.parse(text) as T) : ({} as T)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    })
  } catch (error) {
    throw new ApiError(0, error instanceof Error ? error.message : 'Failed to reach Kiwi backend')
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`

    try {
      const payload = await readJson<ErrorPayload>(response)
      detail = payload.detail ?? payload.message ?? detail
    } catch {
      // Ignore non-JSON error payloads and keep the default message.
    }

    throw new ApiError(response.status, detail)
  }

  return readJson<T>(response)
}

export function scan(sourceDir: string, musicDir: string): Promise<ScanResponse> {
  return request<ScanResponse>('/scan', {
    method: 'POST',
    body: JSON.stringify({
      source_dir: sourceDir,
      music_dir: musicDir,
    }),
  })
}

export function dryRun(options: MergeOptions): Promise<DryRunResponse> {
  return request<DryRunResponse>('/dry-run', {
    method: 'POST',
    body: JSON.stringify(options),
  })
}

export async function startJob(options: MergeOptions): Promise<JobStatusResponse> {
  const created = await request<JobCreateResponse>('/jobs', {
    method: 'POST',
    body: JSON.stringify(options),
  })

  return getJob(created.job_id)
}

export function getJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/jobs/${jobId}`)
}

export function cancelJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
}

export interface JobSubscription {
  close: () => void
  done: Promise<void>
}

export function subscribeJob(
  jobId: string,
  onStatus: (status: string) => void,
  onLog: (line: string) => void,
): JobSubscription {
  const controller = new AbortController()

  const done = (async () => {
    const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/events`, {
      signal: controller.signal,
      headers: {
        Accept: 'text/event-stream',
      },
    })

    if (!response.ok) {
      let detail = `Unable to subscribe to job ${jobId}`

      try {
        const payload = await readJson<ErrorPayload>(response)
        detail = payload.detail ?? payload.message ?? detail
      } catch {
        // Ignore parse errors for SSE failures.
      }

      throw new ApiError(response.status, detail)
    }

    if (!response.body) {
      throw new ApiError(response.status, 'The backend did not provide an event stream')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = 'message'

    const flushEvent = (chunk: string) => {
      const trimmed = chunk.trim()
      if (!trimmed) {
        currentEvent = 'message'
        return
      }

      const lines = trimmed.split('\n')
      let data = ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
          continue
        }

        if (line.startsWith('data:')) {
          data += `${line.slice(5).trim()}\n`
        }
      }

      const payload = data.trim()
      if (!payload) {
        currentEvent = 'message'
        return
      }

      if (currentEvent === 'status') {
        onStatus(payload)
      } else if (currentEvent === 'log') {
        onLog(payload)
      }

      currentEvent = 'message'
    }

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        flushEvent(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
      }
    }

    flushEvent(buffer)
  })()

  return {
    close: () => controller.abort(),
    done,
  }
}
