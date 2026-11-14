# Upload flow extraction map

**Snapshot:** 14 November 2026, consolidated candidate PR [#79](https://github.com/apexstudying-cmd/prepza/pull/79); exact verified code head `c494d147393035ac40bc8875f62d1ff6339c477a`.

**Status:** the three active screens are extracted together into `frontend/src/screens/upload/UploadFlowScreens.tsx`; exact-head Frontend Build, Release Browser and PostgreSQL backup/restore all PASS on `c494d147393035ac40bc8875f62d1ff6339c477a`. The app remains the route/state owner and injects its existing TopBar. This does not claim launch certification.

## Active runtime ownership

| Concern | Current owner | Contract to preserve |
|---|---|---|
| Current screen and active document selection | App.tsx through the existing app-navigation hook | setScreen, activeDocumentId and setActiveDocumentId remain parent-owned; do not move this state into the feature module |
| Route union | frontend/src/types/navigation.ts | Existing upload, upload-share-choice and processing keys remain unchanged |
| Route dispatch | App.tsx | Upload receives setScreen and setActiveDocumentId; the other two screens receive setScreen and activeDocumentId |
| Global shell | frontend/src/navigation/AppShell.tsx | Upload keeps the existing bottom navigation; upload-share-choice and processing remain in noNav |
| API and errors | frontend/src/lib/appApi.ts | Existing cookie/session behavior, CSRF token header and ApiError handling remain authoritative |
| Theme and shared header | frontend/src/theme/theme.ts and app-local TopBar in App.tsx | Preserve existing theme tokens; do not import the app shell into a feature module |
| Document response type | frontend/src/types/documents.ts | Keep the existing DocumentDetail contract |
| Offline file persistence | frontend/src/offline/studyHubOffline.ts | Save the original selected File to the account-scoped Study Hub store before navigating away |
| File helpers and policy | App.tsx | getFileExtension and ALLOWED_UPLOAD_EXTENSIONS are also passed to ChatDetail; sha256Hex computes the existing SHA-256 content identity; MAX_UPLOAD_SIZE_BYTES remains 50 MiB |

## Existing flow — do not redesign during extraction

### 1. UploadScreen

1. Accept only PDF, DOC, DOCX, PPT, PPTX, JPG, JPEG and PNG.
2. Reject files larger than 50 MiB before making an API request.
3. Hash the selected bytes with Web Crypto SHA-256.
4. Fetch /me to obtain the signed-in user ID and CSRF token.
5. POST /documents with title, original filename, byte size and content hash.
6. For a new upload with a signed URL, PUT the original File to storage, then POST /documents/{id}/uploaded.
7. Retry that confirmation exactly once after a 409 response, waiting 1.5 seconds; rethrow other errors.
8. Persist the original File locally with its user ID, title, file type and content hash.
9. Set the active document ID and route to the explicit post-upload choice screen.

A duplicate registration skips the signed PUT/confirmation path but still follows the existing local-first persistence and navigation path. Preserve that branch.

### 2. UploadShareChoiceScreen

- Fetch the current document detail for the active document ID.
- Keep the uploaded document private in Study Hub by default.
- Publishing to Prepza Library is an explicit action that routes to the existing publish-library screen.
- “Study my document”, “Maybe later”, and the existing back action route to processing; do not auto-publish or add a new route.

### 3. ProcessingScreen

- Poll /documents/{id} immediately and then every 2.5 seconds while status is non-terminal.
- Stop polling for ready and failed; cancel the pending timeout when the screen unmounts or the active document changes.
- A ready document routes to doc-ready; a failed document offers the existing retry route to upload.
- Preserve the current transient polling-error copy and retry behavior.

## Source-transform inventory

The active frontend/package.json prebuild chain does not currently rewrite these three screen bodies by component name. The characterization test records this boundary.

| Script | Current relationship | Extraction consequence |
|---|---|---|
| tools/apply_library_publish_context_ux.py | Active prebuild transform; targets PublishLibraryScreen in App.tsx, not the three screens above | Leave it alone while extracting the upload/choice/processing trio. Retarget it before extracting PublishLibraryScreen in the next slice |
| scripts/apply_upload_share_choice_ux.py | Historical/manual patch; not in the active prebuild chain; still assumes App.tsx | Retarget or retire after the module-aware contract supersedes its App.tsx-only anchors |
| scripts/verify_upload_share_choice_ux.py | Standalone legacy verifier that reads App.tsx; not in the Frontend Build test command | Retarget or retire once the new contract is authoritative |
| scripts/apply_upload_publish_binding.py and scripts/apply_upload_publish_binding_repair.py | Historical/manual PublishLibraryScreen patches; not in prebuild | Do not run as part of the upload-flow extraction; reconcile during the PublishLibrary slice |
| archive/patches/chunk3_patch.py | Archived historical patch | Never treat it as an active build step |

The current UploadScreen also receives file helpers/constants that are shared with the ChatDetail route. Keep those shared contracts available to ChatDetail; do not duplicate or silently narrow the accepted types.

## Applied extraction boundary

Target module applied: `frontend/src/screens/upload/UploadFlowScreens.tsx`, with named exports for the three existing screens. Shared file helpers now live in `frontend/src/lib/fileUtils.ts`; upload/chat attachment limits and image types live in `frontend/src/screens/upload/uploadConfig.ts`.

1. Moved the existing component bodies without rewriting their state, effects, API calls, retry logic, JSX or route transitions.
2. Kept screen and activeDocumentId state in the app-navigation owner and passed only explicit props.
3. Injected the existing TopBar; moved shared file helpers/constants into shared modules used by ChatDetail and ChatOptions; imported the existing API, theme, document type and offline persistence modules directly.
4. Kept App.tsx out of the feature module.
5. Kept AppShell.noNav, the Screen union, route IDs, Home Quick Actions and bottom navigation unchanged.
6. Left the active Library publishing transformer on PublishLibraryScreen for the separate upcoming extraction.
7. Added module-owner, helper-owner and route-prop assertions; the existing screen logic was moved without behavioral edits.

## Verification contract

tests/test_upload_flow_module_contract.py is a characterization suite that accepts either the current inline owner or the planned single feature-module owner. It protects:

- allowed file types and 50 MiB limit;
- hash, CSRF registration, signed PUT, upload confirmation, conflict-only retry and local-first persistence order;
- explicit private-by-default sharing choice;
- processing polling, terminal states and timer cleanup;
- route props, Screen IDs and bottom-navigation visibility;
- the active versus historical source-transform inventory.

The test is included in the Frontend Build workflow. Because the pull-request workflow paths include tests/** and the backup/restore workflow paths include **/*.py, this test-only candidate update also exercises the full responsive/cross-system release workflow and the PostgreSQL upgrade/backup/restore rehearsal on the exact new SHA.

No API, authorization, upload limit, navigation, business rule, production data or provider behavior was changed by this extraction.


## Candidate verification state

The extraction preserves the moved component bodies' state/effects, API calls, upload confirmation retry, local-first File persistence, private-by-default choice, processing poll cadence/cleanup, route IDs and AppShell navigation policy. The existing app-local TopBar is injected as a typed component prop rather than imported from App.tsx.

**PASS on exact code head c494d147393035ac40bc8875f62d1ff6339c477a.** Frontend Build [43570716681](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716681) passed 179 source/transform tests, 5 offline Library tests, functional/schema audits, TypeScript, service-worker validation and production build. Release Browser [43570716679](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716679) passed responsive, Shop buyer/seller/admin, B2B, 99 PostgreSQL QA, online/offline and generated-artifact journeys. PostgreSQL Backup Restore [43570716644](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716644) passed both existing-database upgrade and PostgreSQL 17 restore jobs.
