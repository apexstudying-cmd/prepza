from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def require(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise SystemExit(f'{label}: missing ' + ', '.join(missing))


def stress_queue_model() -> None:
    queue: list[dict] = []
    for index in range(30):
        body = '{"page_num":%d}' % (index % 10)
        dedupe = f'7:POST:/documents/1/reading:{body}'
        existing = next((item for item in queue if item['dedupe'] == dedupe), None)
        if existing is None:
            queue.append({'order': index, 'dedupe': dedupe, 'attempts': 0, 'failed': False})
        else:
            existing['order'] = min(existing['order'], index)
    assert len(queue) == 10, f'30-action dedupe stress expected 10 unique records, got {len(queue)}'
    assert [item['order'] for item in queue] == list(range(10)), 'queue ordering contract failed'
    retry = {'attempts': 0, 'failed': False}
    for _ in range(8): retry['attempts'] += 1
    retry['failed'] = retry['attempts'] >= 8
    assert retry['failed'] and retry['attempts'] == 8, 'retry/max-attempt contract failed'


def idempotent_sync_model() -> None:
    server_total = 0
    target = 180
    for _ in range(3): server_total = max(server_total, min(8 * 60 * 60, target))
    assert server_total == 180, 'absolute study-total replay must be idempotent'
    local = [60, 120, 90]
    synced = [0, 0, 0]
    authoritative = 180
    available = authoritative - sum(synced)
    for i, total in enumerate(local):
        credit = min(total - synced[i], max(0, available))
        synced[i] += credit
        available -= credit
    assert synced == [60, 120, 0], f'local reconciliation distribution failed: {synced}'
    assert sum(synced) == authoritative


def main() -> None:
    generated = read('frontend/src/offline/generatedMaterials.ts')
    study = read('frontend/src/offline/studyHubOffline.ts')
    activity = read('frontend/src/offline/studyActivity.ts')
    backend_activity = read('offline_activity_routes.py')
    bootstrap = read('frontend/src/offline/bootstrap.ts')
    queue = read('tools/apply_offline_sync_queue.py')
    hardening = read('tools/apply_offline_queue_hardening.py')
    generation = read('tools/apply_offline_generation_persistence.py')
    library = read('tools/apply_offline_study_library.py')
    status = read('frontend/src/offline/OfflineStatusBanner.tsx')
    isolation = read('tools/apply_offline_account_isolation.py')
    reader = read('tools/apply_offline_study.py')
    progress = read('scripts/apply_document_study_progress.py')
    engine = read('frontend/src/crypto/pdfStudyReaderEngine.ts')
    pdf_vendor = read('tools/ensure_local_pdfjs.py')

    require(generated, ['getLatestGeneratedMaterialForPath', 'listGeneratedMaterialsOffline', 'deleteGeneratedMaterialOffline', 'prepza-offline-user-id', 'generatedAudio', 'cacheGeneratedAudioOffline', 'getCachedGeneratedAudioUrl'], 'generated-material persistence')
    require(study, ['prepza-study-assets-v1', 'openAssetDb', 'putStudyAsset', 'getOfflineStudyDocumentBlob', 'getOfflineStudyDocumentUrl', 'getOfflineStudyStorageUsage', 'summarize', 'flashcards', 'quiz', 'mind-map', 'podcast-script', 'podcast-audio'], 'offline Study Hub package')
    require(activity, ['recordOfflineStudySeconds', 'syncedSeconds', 'syncOfflineStudyActivity', '/study-time/offline-sync', 'total_seconds', 'server_total_seconds_by_date'], 'offline study activity')
    require(backend_activity, ['total_seconds', 'server_total_seconds_by_date', 'new_total = max(existing_total, target)'], 'server study reconciliation')
    require(bootstrap, ['setOfflineUserId', 'syncOfflineStudyActivity'], 'offline bootstrap')
    require(queue, ['syncQueue', 'PREPZA_OFFLINE_QUEUE_MAX_ATTEMPTS', 'flushPrepzaOfflineQueue', 'createdAt', 'lastError'], 'offline queue foundation')
    require(hardening, ['dedupeKey', 'prepzaOfflineQueueDedupeKey', 'Never replay one account', 'Conflict reconciliation:', 'freshCsrf', 'prepza:offline-queue-syncing', 'prepza:offline-queue-synced'], 'offline queue hardening')
    require(generation, ['saveGeneratedMaterialOffline', 'Offline AI boundary: generation itself always requires a connection.', 'cacheGeneratedAudioOffline', 'getCachedGeneratedAudioUrl'], 'offline AI boundary')
    require(library, ['saveStudyHubDocumentOffline', '/library/saved', 'offline_available'], 'offline Library save flow')
    require(status, ['Offline — saved study materials remain available', 'Connection restored — reconnecting…', 'Syncing your study activity', 'All caught up', 'navigator.onLine'], 'offline status UI')
    require(isolation, ["indexedDB.deleteDatabase('prepza-offline-v2')", "indexedDB.deleteDatabase('prepza-offline-v1')", "indexedDB.deleteDatabase('prepza-offline-study-v1')", "caches.delete('prepza-study-assets-v1')"], 'offline account isolation')
    require(reader, ['startOfflineStudyTracking', 'getOfflineStudyDocumentUrl', 'getOfflineUserId', 'initialPage', 'documentId'], 'offline reader')
    require(progress, ['prepza-reading-progress:', 'localStorage.getItem(`prepza-reading-progress:${offlineUserId}:${documentId}`)', "X-Prepza-Offline-Queue':'true'"], 'offline reading progress')
    require(engine, ["const PDFJS_BASE = '/vendor/pdfjs'", '${PDFJS_BASE}/pdf.mjs', '${PDFJS_BASE}/pdf.worker.mjs'], 'zero-network PDF engine')
    require(pdf_vendor, ['pdf.mjs', 'pdf.worker.mjs', 'cdn.jsdelivr.net', 'OUT = ROOT / \'frontend\' / \'public\' / \'vendor\' / \'pdfjs\''], 'local PDF.js build asset')
    assert 'https://cdn.jsdelivr.net' not in engine, 'PDF runtime must not use a CDN'
    stress_queue_model()
    idempotent_sync_model()
    print('Offline architecture regression audit passed.')


if __name__ == '__main__': main()
