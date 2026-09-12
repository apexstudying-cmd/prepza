import { toAdaRequestBody } from './studyAdaContext'
import type { AdaStudyContext } from './studyAdaContext'

export type AdaStudyResponse = {
  answer: string
  model_used?: string
  key_epoch: number
  context_scope: 'selected_document_pages' | 'selected_chat_document'
}

export async function askAdaAboutSelectedStudyContext(
  context: AdaStudyContext,
): Promise<AdaStudyResponse> {
  const response = await window.fetch(`/chats/${context.conversationId}/ada/study`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toAdaRequestBody(context)),
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) throw new Error(body?.error || 'Ada could not answer right now.')
  if (!body || typeof body.answer !== 'string') throw new Error('Ada returned an invalid response.')
  return body as AdaStudyResponse
}
