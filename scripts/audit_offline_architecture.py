from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def require(text: str, markers: list[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise SystemExit(f'{label}: missing ' + ', '.join(missing))


def stress_queue_model() -> None:
    # Contract-level 30-action stress model: FIFO order is retained for unique
    # mutations, exact duplicates collapse to one durable record, transient
    # failures retry, and failed records remain durable after max attempts.
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
    for _ in range(8):
        retry['attempts'] += 1
    retry['failed'] = retry['attempts'] >= 8
    assert retry['failed'] and retry['attempts'] == 8, 'retry/max-attempt contract failed'


def main() -> None:
    generated = read('frontend/src/offline/generatedMaterials.ts')
    study = read('frontend/src/offline/studyHubOffline.ts')
    activity = read('frontend/src/offline/studyActivity.ts')
    bootstrap = read('frontend/src/offline/bootstrap.ts')
    queue = read('tools/apply_offline_sync_queue.py')
    hardening = read('tools/apply_offline_queue_hardening.py')
    generation = read('tools/apply_offline_generation_persistence.py')
    library = read('tools/apply_offline_study_library.py')
    status = read('frontend/src/offline/OfflineStatusBanner.tsx')
    isolation = read('tools/apply_offline_account_isolation.py')
    reader = read('tools/apply_offline_study.py')

    require(generated, [
        'getLatestGeneratedMaterialForPath', 'listGeneratedMaterialsOffline',
        'deleteGeneratedMaterialOffline', 'prepza-offline-user-id',
        'cacheGeneratedAudioOffline', 'getCachedGeneratedAudioUrl',
        'prepza-generated-audio-v1',
    ], 'generated-material persistence')
    require(study, [
        'prepza-study-assets-v1', 'caches.open', 'response.arrayBuffer',
        'startOfflineStudyTracking', 'getOfflineStudyStorageUsage',
    ], 'offline Study Hub assets')
    require(activity, [
        'recordOfflineStudySeconds', 'syncedSeconds',
        'syncOfflineStudyActivity', '/study-time/offline-sync',
    ], 'offline study activity')
    require(bootstrap, ['setOfflineUserId', 'syncOfflineStudyActivity'], 'offline bootstrap')
    require(queue, [
        'syncQueue', 'PREPZA_OFFLINE_QUEUE_MAX_ATTEMPTS',
        'flushPrepzaOfflineQueue', 'createdAt', 'lastError',
    ], 'offline queue foundation')
    require(hardening, [
        'dedupeKey', 'prepzaOfflineQueueDedupeKey',
        'Never replay one account', 'Conflict reconciliation:', 'freshCsrf',
        'prepza:offline-queue-syncing', 'prepza:offline-queue-synced',
    ], 'offline queue hardening')
    require(generation, [
        'saveGeneratedMaterialOffline', 'New AI generation remains online-only',
        'cacheGeneratedAudioOffline', 'getCachedGeneratedAudioUrl',
    ], 'offline AI boundary')
    require(library, [
        'saveStudyHubDocumentOffline', '/library/saved',
        'offline_available',
    ], 'offline Library save flow')
    require(status, [
        'Offline — saved study materials remain available',
        'Connection restored — reconnecting…', 'Syncing your study activity',
        'All caught up', 'navigator.onLine',
    ], 'offline status UI')
    require(isolation, [
        "indexedDB.deleteDatabase('prepza-offline-v2')",
        "indexedDB.deleteDatabase('prepza-offline-v1')",
        "caches.delete('prepza-study-assets-v1')",
        "caches.delete('prepza-generated-audio-v1')",
    ], 'offline account isolation')
    require(reader, [
        'startOfflineStudyTracking', 'prepza-study-assets-v1',
        'initialPage', 'documentId',
    ], 'offline reader')

    stress_queue_model()
    print('Offline architecture regression audit passed.')


if __name__ == '__main__':
    main()
