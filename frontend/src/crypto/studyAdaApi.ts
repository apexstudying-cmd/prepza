import { toAdaRequestBody } from './studyAdaContext'
import type { AdaStudyContext } from './studyAdaContext'

export type AdaStudyResponse = {
  answer: string
  model_used?: string
  key_epoch: number
  context_scope: 'selected_document_pages' | 'selected_chat_document'
}

function assertResponse(body: unknown, context: AdaStudyContext): AdaStudyResponse {
  if (!body || typeof body !== 'object') throw new Error('Ada returned an invalid response.')
  const value = body as Record<string, unknown>
  if (typeof value.answer !== 'string' || !value.answer.trim()) throw new Error('Ada returned an invalid response.')
  if (Number(value.key_epoch) !== context.keyEpoch) throw new Error('Ada context is stale. Reopen the study context and retry.')
  if (value.context_scope !== context.contextScope) throw new Error('Ada returned an invalid study scope.')
  return {
    answer: value.answer,
    model_used: typeof value.model_used === 'string' ? value.model_used : undefined,
    key_epoch: Number(value.key_epoch),
    context_scope: value.context_scope as AdaStudyResponse['context_scope'],
  }
}

export async function askAdaAboutSelectedStudyContext(
  context: AdaStudyContext,
): Promise<AdaStudyResponse> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    throw new Error('Ada needs an internet connection. Your decrypted study document remains available on this device.')
  }

  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
  const timeout = controller ? window.setTimeout(() => controller.abort(), 30_000) : null
  try {
    const response = await window.fetch(`/chats/${context.conversationId}/ada/study`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(toAdaRequestBody(context)),
      ...(controller ? { signal: controller.signal } : {}),
    })

    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.error || 'Ada could not answer right now.')
    return assertResponse(body, context)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Ada took too long to respond. Check your connection and try again.')
    }
    throw error
  } finally {
    if (timeout !== null) window.clearTimeout(timeout)
  }
}
