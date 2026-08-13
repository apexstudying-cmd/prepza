FINAL PREPZA UX POLISH AND INTERACTION PASS

Do NOT rebuild the project.

Do NOT change the existing Prepza visual identity unnecessarily.

Keep the current navy + premium gold design, the existing uploaded official Prepza logo, the current mobile-first structure, and all working screens.

This is a final interaction, navigation and UX completion pass.

The goal is simple:

EVERYTHING THAT LOOKS CLICKABLE MUST HAVE A REAL DESTINATION OR INTERACTION.

==================================================
1. OFFICIAL BRAND
==================================================

Keep using the existing uploaded Prepza logo at:

src/imports/logo.png

Do not redesign, replace, redraw or reinterpret it.

The logo is the official Prepza brand asset.

==================================================
2. FIX AUTHENTICATION
==================================================

Login:

Forgot password?
→ Password Reset screen.

Sign Up:
→ Registration/onboarding screen.

Do not send users directly to Home when they click Sign Up.

Create a simple onboarding flow:

Create Account
→ Name
→ Email
→ Password
→ University
→ Course
→ Year
→ Finish

Use the current Arnold Gichuru / Kenyatta University / Actuarial Science / Year 1 data as the prototype example.

==================================================
3. HOME
==================================================

Notification bell:
→ Notifications screen.

Create a Notifications screen containing:
- Study reminders
- Chat notifications
- Forum activity
- Opportunity alerts
- Prepza announcements

"My Library":
→ Create a dedicated Library screen.

Library should contain:
- Recent Documents
- My Notes
- Past Papers
- AI Summaries
- Flashcards
- Podcasts
- Saved Materials

Every library item must open its appropriate study experience.

Podcast "See all":
→ Podcast Library.

Podcast cards:
→ Podcast Player.

Opportunity cards:
→ Opportunity Details.

Opportunity bookmarks:
→ Toggle saved state.

==================================================
4. CREATE MENU
==================================================

Keep:

Upload Document
Create Forum Post
Ask a Question
Share Opportunity
Upload Educational Content

All actions already implemented should remain.

Fix attachment actions.

In Forum Post Composer:

Image → image picker
Document → document picker
Unit → unit selector

In Question Composer:

Add Image → image picker
Attach Document → document picker

These should open realistic prototype modals/pickers.

==================================================
5. CHAT SYSTEM
==================================================

Chats + button:

→ New Chat / New Group selection screen.

New Chat:
→ student search → select student → chat.

New Group:
→ group name → select members → create group.

Chat header ⋯:
→ Chat Info / Options.

Options:
- Group/Contact info
- Shared media
- Search messages
- Notifications
- Leave group / Delete chat

Attachment button:
→ attachment picker.

Attachment picker options:
- Document
- Image
- Camera
- Audio

==================================================
6. DOCUMENT STUDY
==================================================

This is a CORE PREPZA EXPERIENCE.

Document menu actions must work.

Rename:
→ Rename modal.

Download:
→ Download confirmation/prototype state.

Share:
→ Share sheet.

Save:
→ Toggle saved state and show "Saved to Library".

Delete:
→ Confirmation modal:
"Delete this document?"
Cancel / Delete.

Report:
→ Report modal with reasons.

==================================================
7. DOCUMENT AI ACTIONS
==================================================

Do NOT make all document actions simply switch to the AI tab.

Each action should perform the appropriate experience.

Explain:
→ AI explanation of the selected text.

Simplify:
→ Simplified explanation.

Quiz Me:
→ Quiz screen generated from the selected/current document.

Flashcards:
→ Flashcard screen generated from the selected/current document.

Ask About This Document:
→ AI Chat with the document automatically attached as context.

The AI should visually indicate:

"Using: ACT 101 – Interest Theory"

==================================================
8. DOCUMENT TOOLS
==================================================

Tools:

Flashcards
→ Flashcard Study

Practice Quiz
→ Quiz

Summary
→ Summary

Study Podcast
→ Podcast Player

Mind Map
→ Create a Mind Map screen.

DO NOT leave Mind Map with an empty action.

Save to Library:
→ Toggle saved state + confirmation.

==================================================
9. SUMMARY
==================================================

Save button:
→ Save summary to Library and show confirmation.

Add an optional:
Share
button that opens Share Sheet.

==================================================
10. PODCASTS
==================================================

Create a Podcast Library screen.

Podcast cards:
→ Podcast Player.

More Episodes cards:
→ Podcast Player with that episode selected.

Podcast Player controls should remain functional:
- Play/Pause
- Rewind
- Forward
- Progress

==================================================
11. OPPORTUNITIES
==================================================

Opportunity bookmark:
→ Toggle saved state.

Apply Now:
→ Application confirmation/external application placeholder.

Show:

"You're leaving Prepza to apply on the organization's website."

Buttons:

Continue
Cancel

Share:
→ Share Sheet.

==================================================
12. PROFILE
==================================================

Edit Profile:
→ Edit Profile screen.

Include:
- Profile photo/avatar
- Name
- Bio
- University
- Course
- Year

Save Changes:
→ Return to Profile with updated information.

Avatar edit button:
→ Avatar selection/upload modal.

Share Profile:
→ Share Sheet.

Saved:
→ Library/Saved Materials.

Materials:
→ Relevant document/flashcard screens.

Activity:
→ Relevant activity destinations.

==================================================
13. SETTINGS
==================================================

Keep the Settings screen.

Every row that looks interactive must work.

Account:
Edit Profile → Edit Profile
Email → Email change modal
Phone → Phone change modal
University → University selector
Course → Course selector

Preferences:
Study Preferences → Study Preferences
AI Preferences → AI Preferences
Language → Language selector
Appearance → Appearance options

Notifications:
Keep working toggles.

Privacy:
Keep working toggles.

Security:
Change Password → Password screen
Login Sessions → Sessions screen
Two-Factor Authentication → 2FA setup screen

Subscription:
Current Plan → Subscription screen
Upgrade → Subscription/Premium screen
Billing → Billing screen

Support:
Help Centre → Help screen
Contact Support → Contact support
Report a Problem → Report form

About:
About Prepza → About screen
Terms → Terms screen
Privacy Policy → Privacy screen

Log Out:
→ Confirmation modal before logging out.

==================================================
14. NAVIGATION CLEANUP
==================================================

Ensure every screen has a sensible Back destination.

Do not send every action back to Home.

Examples:

Document → Library/previous document context
Podcast → Podcast Library
Summary → Document Study
Quiz → Document Study
Flashcards → Document Study
Comments → originating post
Opportunity Detail → Opportunities
Settings → Profile
Chat Detail → Chats

==================================================
15. REMOVE DEAD INTERACTIONS
==================================================

Search the entire application for:

buttons
icons
cards
tabs
links
menus
avatars
filters
CTAs
overflow menus

that appear clickable but have no action.

Fix every one.

Do not leave empty onClick handlers.

Do not leave buttons whose only action is closing a menu unless that is actually their purpose.

==================================================
16. FIX TECHNICAL ROUTING
==================================================

Clean up the Screen type and routing system.

Remove references to nonexistent screens.

If Podcast Library exists in navigation logic, implement the Podcast Library screen properly.

Every screen referenced by navigation must actually exist.

Every implemented screen must be reachable.

==================================================
17. DESIGN CONSISTENCY
==================================================

Do not redesign the entire application.

Preserve the current visual language:

Deep navy
Premium gold
White/light surfaces
Rounded cards
Modern typography
Social-media-inspired layouts
Mobile-first interaction

The official Prepza Sigma logo remains the primary brand identity.

==================================================
18. CORE PREPZA EXPERIENCE
==================================================

The most important user journey must be:

Student has lecture notes
↓
Presses +
↓
Upload Document
↓
Selects PDF / Word / PowerPoint / Image
↓
Prepza processes document
↓
Document Ready
↓
Study with AI
↓
Ask questions
↓
Highlight text
↓
Explain / Simplify
↓
Generate Quiz
↓
Generate Flashcards
↓
Create Podcast
↓
Save to Library

This workflow should feel extremely smooth.

The student should never wonder:

"What do I press next?"

==================================================
19. FINAL QUALITY CHECK
==================================================

Before finishing:

1. Test every bottom navigation item.
2. Test every major CTA.
3. Test every card that appears clickable.
4. Test every overflow menu.
5. Test every save/bookmark button.
6. Test every share button.
7. Test every upload action.
8. Test every AI action.
9. Test Settings.
10. Test Back navigation.
11. Remove all dead buttons.
12. Remove all nonexistent routes.
13. Ensure the app feels like one coherent product.

FINAL PRODUCT FEEL:

Prepza should feel like:

WhatsApp + Instagram + AI Tutor + Student Library + Opportunities

inside one premium university app.

Most importantly:

"I have notes."

→ Upload them.

"Prepza understands them."

→ Study them.

"I don't understand this."

→ Ask AI.

"I need practice."

→ Generate a quiz.

"I want to listen."

→ Create a podcast.

"I want to discuss it."

→ Forum or chat.

"I need an opportunity."

→ Opportunities.

This should feel like a product students WANT to open every day.