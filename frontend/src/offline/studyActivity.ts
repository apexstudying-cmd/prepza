// Compatibility facade for the retired per-document Study Activity implementation.
// The authoritative tracker now lives in studyHubActivityTracker.ts and owns one
// Study Hub clock across documents and features.
export {
  setOfflineStudyUserId,
  recordOfflineStudySeconds,
  startOfflineStudyTracking,
  getOfflineStudyScreenSnapshot,
  getOfflineStudySnapshot,
  syncOfflineStudyActivity,
} from './studyHubActivityTracker'
