const MAX_CONTEXT_CHARS = 20_000
const MAX_PROMPT_CHARS = 4_000
const MAX_PAGE_SPAN = 50

export type AdaStudyContext = {
  conversationId: number
  keyEpoch: number
  documentId?: number
  attachmentId?: number
  pageStart: number
  pageEnd: number
  selectedText: string
  userPrompt: string
  contextScope: 'selected_document_pages' | 'selected_chat_document'
  explicit: true
}

function cleanText(value: unknown, max: number, label: string): string {
  if (typeof value !== 'string') throw new Error(`${label} must be text.`)
  const normalized = value.replace(/\u0000/g, '').trim()
  if (!normalized) throw new Error(`${label} cannot be empty.`)
  if (normalized.length > max) throw new Error(`${label} is too large.`)
  return normalized
}

function assertPositiveId(value: unknown, label: string): asserts value is number {
  if (!Number.isInteger(value) || Number(value) < 1) throw new Error(`Invalid ${label}.`)
}

export function createAdaStudyContext(input: {
  conversationId: number
  keyEpoch: number
  documentId?: number
  attachmentId?: number
  pageStart: number
  pageEnd: number
  selectedText: string
  userPrompt: string
  contextScope?: 'selected_document_pages' | 'selected_chat_document'
}): AdaStudyContext {
  assertPositiveId(input.conversationId, 'conversation id')
  if (!Number.isInteger(input.keyEpoch) || input.keyEpoch < 1) throw new Error('A current E2EE key epoch is required.')

  const contextScope = input.contextScope || 'selected_document_pages'
  if (contextScope === 'selected_document_pages') {
    assertPositiveId(input.documentId, 'study document id')
    if (input.attachmentId !== undefined) throw new Error('Document and chat attachment context cannot be combined.')
  } else if (contextScope === 'selected_chat_document') {
    assertPositiveId(input.attachmentId, 'shared chat document')
    if (input.documentId !== undefined) throw new Error('Document and chat attachment context cannot be combined.')
  } else {
    throw new Error('Invalid study context scope.')
  }

  if (!Number.isInteger(input.pageStart) || input.pageStart < 1) throw new Error('Invalid starting page.')
  if (!Number.isInteger(input.pageEnd) || input.pageEnd < input.pageStart) throw new Error('Invalid ending page.')
  if (input.pageEnd - input.pageStart + 1 > MAX_PAGE_SPAN) throw new Error('Selected page range is too large.')

  return {
    conversationId: input.conversationId,
    keyEpoch: input.keyEpoch,
    documentId: input.documentId,
    attachmentId: input.attachmentId,
    pageStart: input.pageStart,
    pageEnd: input.pageEnd,
    selectedText: cleanText(input.selectedText, MAX_CONTEXT_CHARS, 'Selected study context'),
    userPrompt: cleanText(input.userPrompt, MAX_PROMPT_CHARS, 'Ada prompt'),
    contextScope,
    explicit: true,
  }
}

export function toAdaRequestBody(context: AdaStudyContext) {
  return {
    conversation_id: context.conversationId,
    key_epoch: context.keyEpoch,
    ...(context.documentId !== undefined ? { document_id: context.documentId } : {}),
    ...(context.attachmentId !== undefined ? { attachment_id: context.attachmentId } : {}),
    page_start: context.pageStart,
    page_end: context.pageEnd,
    selected_text: context.selectedText,
    prompt: context.userPrompt,
    context_scope: context.contextScope,
    explicit_user_context: true,
  }
}
