const MAX_CONTEXT_CHARS = 20_000
const MAX_PROMPT_CHARS = 4_000

export type AdaStudyContext = {
  conversationId: number
  keyEpoch: number
  documentId: number
  pageStart: number
  pageEnd: number
  selectedText: string
  userPrompt: string
  explicit: true
}

function cleanText(value: unknown, max: number, label: string): string {
  if (typeof value !== 'string') throw new Error(`${label} must be text.`)
  const normalized = value.replace(/\u0000/g, '').trim()
  if (!normalized) throw new Error(`${label} cannot be empty.`)
  if (normalized.length > max) throw new Error(`${label} is too large.`)
  return normalized
}

/**
 * Creates the only context shape that the chat UI should hand to Ada.
 *
 * This is deliberately an explicit opt-in object: the caller must supply a
 * selected document/page range and selected text. There is no API here that
 * accepts an entire conversation history, entire document, or local key.
 */
export function createAdaStudyContext(input: {
  conversationId: number
  keyEpoch: number
  documentId: number
  pageStart: number
  pageEnd: number
  selectedText: string
  userPrompt: string
}): AdaStudyContext {
  if (!Number.isInteger(input.conversationId) || input.conversationId < 1) {
    throw new Error('Invalid conversation id.')
  }
  if (!Number.isInteger(input.keyEpoch) || input.keyEpoch < 0) {
    throw new Error('Invalid conversation key epoch.')
  }
  if (!Number.isInteger(input.documentId) || input.documentId < 1) {
    throw new Error('Invalid study document id.')
  }
  if (!Number.isInteger(input.pageStart) || input.pageStart < 1) {
    throw new Error('Invalid starting page.')
  }
  if (!Number.isInteger(input.pageEnd) || input.pageEnd < input.pageStart) {
    throw new Error('Invalid ending page.')
  }

  return {
    conversationId: input.conversationId,
    keyEpoch: input.keyEpoch,
    documentId: input.documentId,
    pageStart: input.pageStart,
    pageEnd: input.pageEnd,
    selectedText: cleanText(input.selectedText, MAX_CONTEXT_CHARS, 'Selected study context'),
    userPrompt: cleanText(input.userPrompt, MAX_PROMPT_CHARS, 'Ada prompt'),
    explicit: true,
  }
}

export function toAdaRequestBody(context: AdaStudyContext) {
  return {
    conversation_id: context.conversationId,
    key_epoch: context.keyEpoch,
    document_id: context.documentId,
    page_start: context.pageStart,
    page_end: context.pageEnd,
    selected_text: context.selectedText,
    prompt: context.userPrompt,
    context_scope: 'selected_document_pages',
    explicit_user_context: true,
  }
}
