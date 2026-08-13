PREPZA — FINAL FRONTEND COMPLETION, PRODUCT ARCHITECTURE & UX POLISH

IMPORTANT:

Continue working inside the EXISTING PREPZA PROJECT.

DO NOT start a new project.

DO NOT clear the existing context.

DO NOT rebuild the application from scratch.

DO NOT unnecessarily replace working components.

The existing Prepza design, navigation, components, logo and visual identity are the foundation.

This is the FINAL FRONTEND COMPLETION PASS.

The objective is:

WHEN THIS PASS IS COMPLETE, THE PREPZA FRONTEND SHOULD BE PRODUCTION-READY IN STRUCTURE AND UX.

The only major missing layer should be the REAL BACKEND, DATABASE, REAL AUTHENTICATION, REAL FILE STORAGE, REAL AI SERVICES, REAL PAYMENTS and REAL PRODUCTION DATA.

The frontend must already contain the complete user experience for those systems.

============================================================
1. DESIGN PHILOSOPHY
============================================================

Prepza must look like a professional product designed by an experienced product/UI team.

Avoid "AI slop".

Do NOT make the interface excessively colorful, overly rounded, excessively animated, cluttered or full of decorative elements.

Prioritize:

- clean hierarchy
- strong typography
- consistent spacing
- restrained use of color
- clear information architecture
- excellent mobile UX
- professional desktop UX
- predictable interactions
- meaningful whitespace
- subtle visual polish

Use Prepza's existing navy and gold identity.

Gold should be used strategically for emphasis, actions, achievements and premium elements.

Do not turn every element gold.

============================================================
2. ICON SYSTEM
============================================================

IMPORTANT:

AVOID EXCESSIVE EMOJIS.

Do not use emojis as the primary UI language.

Use:

- consistent Prepza signature icons
- familiar professional UI icons
- Lucide-style icons or an equivalent coherent icon system
- custom Prepza icons where appropriate

Examples:

AI Tutor → professional AI icon
Documents → document icon
Quiz → clipboard/check icon
Flashcards → cards icon
Podcast → waveform/audio icon
Library → library/book icon
Groups → people/group icon
Opportunities → briefcase icon
Notifications → bell icon
Settings → gear icon

XP, streaks and achievements should have their own restrained Prepza visual language rather than generic emoji decoration.

Icons must have consistent:

- stroke weight
- size
- spacing
- alignment

============================================================
3. COMPLETE ROUTE AUDIT
============================================================

Audit EVERY route and interactive element.

For every route determine:

Entry point
→ Destination
→ Loading
→ Content
→ Empty state
→ Error state
→ Permission state
→ Success state
→ Confirmation
→ Back navigation
→ Exit destination

No route may terminate in a dead end.

No button may appear clickable without a meaningful action.

No menu item may lead nowhere.

No card that visually appears interactive may be inert.

Every asynchronous action must have:

Idle
→ Loading
→ Success / Failure

states.

============================================================
4. USER ROLES
============================================================

Design experiences for:

Student
Group Owner
Group Admin
Moderator
Content Manager
Finance Manager
Support Admin
Administrator
Super Admin
Organisation / Recruiter

Each role must have appropriate permissions and frontend states.

============================================================
5. STUDENT AUTHENTICATION
============================================================

Complete:

Landing
→ Sign Up
→ Account creation
→ Email verification
→ University
→ Course
→ Year
→ Interests
→ Onboarding
→ Home

Also:

Login
Forgot password
Password reset
Session expired
Account locked/restricted
Logout confirmation

Include warning/error pages where appropriate.

Examples:

Session expired
Access denied
Account suspended
Verification required
Something went wrong
Page not found

============================================================
6. LANDING PAGE
============================================================

Create a complete public Prepza landing page.

Sections:

Hero
Features
AI Tutor
Document Study
Library
Groups
Opportunities
Progress/Achievements
Premium
How Prepza works
FAQ
Footer

Primary CTA:

Get Started

Secondary CTA:

Explore Prepza

Include:

Student-focused messaging
Professional visual hierarchy
Responsive desktop/mobile layouts

Do not make it look like a generic AI SaaS landing page.

============================================================
7. HOME
============================================================

Home should contain:

Continue Studying
Recent Documents
Study Progress
Current Streak
XP/Level
Recommended Groups
Opportunities
AI Tutor
Saved Materials
Premium/Upgrade shortcut

UPGRADE MUST NOT BE HIDDEN.

Create a tasteful Home premium card:

Unlock Prepza Premium

Show meaningful benefits.

CTA:

Upgrade

Also retain:

Profile → Subscription

and

Settings → Subscription

============================================================
8. XP SYSTEM
============================================================

XP represents meaningful learning/community activity.

Possible sources:

- Study a document
- Complete a quiz
- Complete flashcards
- Maintain study streak
- Publish approved educational material
- Helpful community participation
- Complete learning milestones

Do NOT reward spam.

Create:

XP level
XP progress
XP history
How to earn XP

XP should be clickable and lead to:

XP / Progress

============================================================
9. STUDY STREAK
============================================================

Study streak represents consecutive days of meaningful study activity.

Create:

Current streak
Longest streak
Study calendar
Progress

Example:

12 day streak

The streak should be clickable.

It should lead to:

Study Progress / Streak History

Students can share milestones.

============================================================
10. ACHIEVEMENTS
============================================================

Create a professional achievement system.

Examples:

First Document
First Quiz
7-Day Scholar
Quiz Master
Community Helper
Library Contributor

Achievements should include:

Locked
Unlocked
Progress
Description
Requirements
Date achieved

Achievements should be clickable.

Allow students to share achievements.

Create a professional Prepza-branded share card.

Example:

Achievement unlocked:
Quiz Master

25 quizzes completed.

CTA:

Join me on Prepza

Sharing may create:

Profile post
Group post
External share

============================================================
11. FOLLOWING SYSTEM
============================================================

Followers and Following MUST be clickable.

Profile:

Followers → Followers list

Following → Following list

Each person can open:

Student Profile

Student profiles should show appropriate:

Name
Username
University
Course
Year
Bio
Achievements
XP/level
Streak where appropriate
Public materials
Groups
Activity where appropriate

Follow/unfollow must have:

Loading
Success
Error

states.

Following should have a real purpose.

Following can personalize:

Home feed
Recommended groups
Student activity
Notifications
Relevant opportunities

============================================================
12. DOCUMENTS
============================================================

Support the complete frontend flow:

Upload
→ Uploading
→ Processing
→ Ready
→ Study

Document types:

PDF
DOC/DOCX
PPT/PPTX
Images
Other supported educational formats

Document states:

Uploading
Processing
Ready
Failed
Unavailable
Removed
Permission denied

Create:

Document details
Document viewer
Document actions
Save
Share
Rename
Download
Report
Delete

============================================================
13. PERSONAL DOCUMENT UPLOAD
============================================================

"Upload Document" means:

Personal study material.

Student uploads material primarily for their own study.

Flow:

Create
→ Upload Document
→ Select file
→ Add title
→ Select unit
→ Upload
→ Processing
→ Ready
→ Study

============================================================
14. PUBLISH TO PREPZA LIBRARY
============================================================

Use the name:

Publish to Prepza Library

Explain:

"Share educational materials with other students."

"Publishing is free."

"Approved contributions can earn XP."

"Build your contributor reputation."

"Help other students study."

Flow:

Publish to Prepza Library
→ Select document
→ Add title
→ University
→ Course
→ Unit
→ Year
→ Material type
→ Description
→ Confirm rights
→ Submit
→ Under Review
→ Approved / Rejected

Require confirmation:

"I confirm that I have the right or permission to share this material."

Link to:

Terms
Content Policy
Copyright/Takedown Policy

Do not claim Prepza owns student-uploaded content unless explicitly stated in the final legal documents.

After approval:

Show:

Approved
XP earned
Views
Saves
Helpful reactions

Create:

My Published Materials

============================================================
15. COPYRIGHT / CONTENT SAFETY
============================================================

Design:

Report Material
Copyright Concern
Report User
Remove My Material
Admin Review

Students should understand that they are responsible for having appropriate rights/permission to upload and publish materials.

Create appropriate warning and confirmation pages.

If material is reported:

Submitted
→ Under Review
→ Resolved / Removed / Dismissed

============================================================
16. DOCUMENT STUDY EXPERIENCE
============================================================

Core experience:

Document
→ Study

Tools:

Explain
Simplify
Ask AI
Quiz Me
Flashcards
Summary
Podcast
Mind Map
Save
Share

Each tool must have a real frontend destination.

Example:

Quiz Me
→ Quiz generation state
→ Quiz ready
→ Quiz

Flashcards
→ Generation state
→ Flashcard set

Podcast
→ Generation state
→ Podcast player

Mind Map
→ Mind map generation
→ Mind map view

============================================================
17. AI TUTOR
============================================================

AI Tutor actions:

Explain
Quiz Me
Summarize
Flashcards
Podcast

These actions must use the current study context where applicable.

Design:

AI response loading
AI response
AI failure
Retry
Conversation history
Suggested follow-up questions

Do not make every AI button simply navigate to the same generic screen.

============================================================
18. LIBRARY
============================================================

Create a complete Library.

Sections:

My Documents
Saved Materials
Published Materials
Summaries
Flashcards
Quizzes
Podcasts

Every item is clickable.

Empty states must contain useful CTAs.

Example:

No documents yet.

Upload your first document.

============================================================
19. DOWNLOADS
============================================================

Opportunity expiry is separate from file downloads.

Do NOT claim Prepza can remove files from a student's device after download.

For educational documents, design support for:

View Online
Download
Offline Available
Download Expired where applicable

If temporary offline access is eventually implemented:

"Available offline for 48 hours."

============================================================
20. GROUPS = FORUMS
============================================================

IMPORTANT PRODUCT DECISION:

Groups are Prepza's forum/community system.

Do NOT create a completely separate forum product.

A Group is a study community/forum.

Examples:

MAT 101 — Year 1
STA 101 — Year 1
Actuarial Science Year 1
KU Actuarial Students

Group tabs:

Posts
Questions
Files
Members

============================================================
21. GROUP CREATION
============================================================

Create:

Group name
Group profile picture
Description
University
Course
Unit
Year
Privacy

Then:

Add Members

Allow search and multi-select.

Show selected members.

Create Group.

============================================================
22. GROUP ADMINISTRATION
============================================================

Owner:

Rename
Change picture
Edit description
Add members
Remove members
Promote admins
Demote admins
Manage permissions
Delete group

Admins:

Add/remove members
Moderate posts
Edit group information

Members:

Post
Ask questions
Comment
Share permitted materials
Leave

Create:

Group Settings
Permissions

============================================================
23. CHAT
============================================================

Complete actual chat UI.

Every conversation must contain:

Message history
Text input
Send
Attachment
Image
Document
Audio/voice interface where appropriate

States:

Sending
Sent
Delivered
Read
Failed
Retry

============================================================
24. NEW GROUP
============================================================

New Group must include:

Group name
Group profile picture
Description
Member search
Member selection
Selected members
Create group

No fake member selection.

============================================================
25. CHAT / GROUP MANAGEMENT
============================================================

Create Group Info.

Include:

Members
Admins
Add member
Remove member
Promote admin
Demote admin
Rename
Change picture
Permissions
Leave group

Include confirmation dialogs for destructive actions.

============================================================
26. CREATE MENU
============================================================

Create should contain:

Upload Document
Create Post
Ask Question
Publish to Prepza Library
Share Opportunity

Create Post:

Select Group
→ Compose
→ Attach
→ Publish

Ask Question:

Select Group
→ Question
→ Attach
→ Publish

There should NOT be a mysterious standalone "Forum" destination disconnected from Groups.

============================================================
27. EXPLORE
============================================================

Explore should contain:

Documents
Notes
Past Papers
Students
Groups
Opportunities

Do NOT make "AI Content" a major Explore category.

AI-generated content belongs primarily within the learning/document ecosystem.

============================================================
28. OPPORTUNITIES
============================================================

Opportunity categories:

Internships
Scholarships
Competitions
Jobs
Events

Student actions:

View
Save
Share
Report
Apply

Statuses:

Draft
Pending Review
Active
Featured
Expiring Soon
Expired
Archived

Every opportunity has:

Published date
Application deadline
Expiry date

Automatic expiration must be represented in the frontend.

============================================================
29. ORGANISATION / RECRUITER PORTAL
============================================================

Create a professional organisation-facing frontend.

Public route:

Organisations / Recruiters

Purpose:

Allow verified organisations to submit opportunities and eventually pay for promotional placement.

Organisation flow:

Organisation landing
→ Create account
→ Verification
→ Organisation dashboard
→ Create opportunity
→ Submit
→ Review
→ Publish

Organisation dashboard:

Opportunities
Applications/traffic where applicable
Create Opportunity
Drafts
Analytics
Billing
Organisation Profile

============================================================
30. FEATURED / SPONSORED OPPORTUNITIES
============================================================

Normal opportunity publishing can remain free.

Organisations may eventually purchase:

Featured placement
Sponsored placement
Targeted promotional campaigns
Recruitment partnerships

Create frontend structures for:

Standard
Featured
Sponsored

Do NOT hard-code final pricing.

Use placeholder pricing only for prototype purposes.

Clearly distinguish:

Organic opportunity
Featured
Sponsored

Sponsored content must be visibly labelled.

============================================================
31. OPPORTUNITY ADMINISTRATION
============================================================

Admin can:

Create
Edit
Approve
Reject
Feature
Unfeature
Extend
Expire
Archive
Delete

Admin can control:

Expiry date
Featured duration
Sponsored status
Visibility
Target university
Target course
Target year

============================================================
32. ADMIN PLATFORM
============================================================

Complete the existing Admin Platform.

It must have its own professional desktop-first experience.

Do not make it look like the student mobile app with a sidebar.

Navigation:

Dashboard
Users
Content
Groups
Opportunities
AI & Usage
Payments
Communications
Analytics
Moderation
Platform Controls
Admin Users
Audit Logs
System

============================================================
33. ADMIN DASHBOARD
============================================================

Show real-data-ready cards for:

Students
Active Students
Documents
AI Usage
Storage
Revenue
Subscriptions

Charts:

Student growth
Revenue
AI usage
Uploads

Activity:

New users
Uploads
Reports
Payments
AI processing

Never rely on permanent fake production numbers.

============================================================
34. ADMIN USERS
============================================================

Search
Filter
View
Suspend
Restore
Change role
Review activity

============================================================
35. ADMIN CONTENT
============================================================

Manage:

Documents
Library materials
Notes
Past papers
AI-generated content
Podcasts
Flashcards
Quizzes

Actions:

Review
Approve
Reject
Edit
Feature
Remove
Report

============================================================
36. ADMIN GROUPS / COMMUNITY
============================================================

Manage:

Groups
Posts
Questions
Comments
Reports
Members

Moderation tools:

Review
Remove
Dismiss report
Warn
Suspend

============================================================
37. ADMIN OPPORTUNITIES
============================================================

Manage:

Opportunities
Featured
Sponsored
Expired
Pending approval
Organisation submissions

Controls for:

Expiry
Visibility
Featured duration
Targeting

============================================================
38. ADMIN AI & USAGE
============================================================

Show:

AI requests
Successful requests
Failed requests
Usage
Estimated cost
Document processing
Podcast generation
Quiz generation
Flashcard generation

Filters:

Date
Feature
User
Status

============================================================
39. ADMIN PAYMENTS
============================================================

Show:

Revenue
Transactions
Subscriptions
Failed payments
Payment references
Organisation promotional payments

============================================================
40. ADMIN COMMUNICATIONS
============================================================

Create:

Announcements
Push notifications
In-app announcements
Email campaigns

States:

Draft
Scheduled
Sending
Sent
Failed

============================================================
41. ADMIN ANALYTICS
============================================================

Show:

DAU
MAU
Retention
Registrations
Uploads
AI usage
Popular units
Popular groups
Forum engagement
Opportunity engagement
Revenue

============================================================
42. PLATFORM CONTROLS
============================================================

Create:

Platform Controls

Allow admins to enable/disable/configure:

Registrations
Uploads
Library publishing
XP
Achievements
Downloads
AI Tutor
AI generation
Podcasts
Flashcards
Quizzes
Groups
Messaging
Opportunity submissions
Opportunity publishing
Featured opportunities
Sponsored opportunities
Subscriptions
Payments
Notifications
Maintenance mode

Show:

Feature
Status
Last changed
Changed by

Require confirmation for high-impact changes.

============================================================
43. ADMIN ROLES
============================================================

Create:

Super Admin
Admin
Moderator
Content Manager
Finance Manager
Support

Include:

Admin Users
Roles
Permissions
Audit Logs

============================================================
44. AUDIT LOGS
============================================================

Create an admin audit system frontend.

Show:

Admin
Action
Object
Timestamp
Result

Examples:

Approved document
Removed post
Suspended user
Changed platform setting
Featured opportunity

============================================================
45. NOTIFICATIONS
============================================================

Design notifications for:

Messages
Group activity
Comments
Achievements
XP
Study reminders
Document processing
AI completion
Opportunity alerts
Admin announcements

States:

Unread
Read
Empty
Error

============================================================
46. SEARCH
============================================================

Search should support:

Students
Documents
Groups
Opportunities
Units
Posts where appropriate

States:

Searching
Results
No results
Error

============================================================
47. SUBSCRIPTIONS
============================================================

Create complete frontend:

Current plan
Plans
Premium benefits
Upgrade
Payment processing
Success
Failure
Cancelled
History
Expiry
Renew

Use KES.

Do not hide Upgrade inside Settings.

============================================================
48. SETTINGS
============================================================

Complete:

Profile
Email
Phone
University
Course
Study preferences
AI preferences
Language
Appearance
Notifications
Privacy
Security
Password
Sessions
2FA
Subscription
Billing
Help
Support
Terms
Privacy
Logout

Every clickable row must lead somewhere.

============================================================
49. LEGAL / WARNING SCREENS
============================================================

Design frontend entry points and warning/confirmation states for:

Terms
Privacy Policy
Content Policy
Copyright/Takedown
Community Guidelines

Warnings:

Unauthorized upload
Copyright concern
Report content
Account suspension
Group removal
Payment failure
Subscription expiry
Access denied
Session expired
Unsafe/unsupported file
File too large
AI unavailable
Network unavailable
Page not found

Do not write final legal language yet.

Create the UX structure so the legal documents can be inserted later.

============================================================
50. LOADING / SKELETON SYSTEM
============================================================

Create reusable skeleton loaders for every network-backed area.

Include:

Home
Explore
Library
Documents
AI
Groups
Posts
Opportunities
Chats
Profiles
Notifications
Admin
Analytics
Tables

Skeletons must match actual content shapes.

Use subtle animation.

Never leave blank screens during normal loading.

============================================================
51. MICRO-INTERACTIONS & ANIMATIONS
============================================================

Use animation selectively.

Animations should communicate:

Navigation
Loading
Success
Progress
Expansion
Modal transitions
Page transitions
Achievement unlocks
XP progression
Upload processing
Message sending
Save/bookmark changes

Do NOT animate everything.

Avoid excessive bouncing, floating, glowing or flashy effects.

Animations should feel:

Fast
Subtle
Professional
Purposeful

============================================================
52. TOASTS / CONFIRMATIONS
============================================================

Create consistent feedback for:

Saved
Uploaded
Published
Deleted
Copied
Reported
Followed
Unfollowed
Group created
Message sent
Payment successful
Payment failed
AI generation complete

Use consistent Prepza toast components.

============================================================
53. EMPTY STATES
============================================================

Every list must have a designed empty state.

Examples:

No documents
No saved materials
No groups
No chats
No notifications
No opportunities
No followers
No following
No published materials
No achievements
No reports
No payments
No AI history

Every empty state should explain what to do next.

============================================================
54. REAL DATA ARCHITECTURE
============================================================

Do not design the product around permanent fake data.

The frontend must work correctly with:

0 records
1 record
10 records
100+ records

Create realistic prototype data only for design demonstration.

Production data should eventually come entirely from the backend.

Never require fake statistics for the UI to look complete.

============================================================
55. FRONTEND / BACKEND GAP DISCOVERY
============================================================

While completing this project, identify every backend capability implied by the frontend.

Also inspect the existing Prepza backend conceptually.

If a backend capability already exists but has no frontend:

Design the required frontend.

If a frontend feature requires backend functionality that does not exist:

Document that requirement for the later Claude implementation.

Do NOT throw away existing backend capabilities.

The eventual Claude instruction must explicitly say:

INSPECT THE CURRENT PREPZA BACKEND FIRST.

UPGRADE AND EXTEND IT.

DO NOT BLINDLY REBUILD IT.

PRESERVE WORKING SYSTEMS.

MAP THE FINAL FRONTEND AGAINST THE EXISTING BACKEND.

ADD MISSING FRONTEND FOR EXISTING BACKEND CAPABILITIES.

ADD MISSING BACKEND ONLY WHERE REQUIRED.

============================================================
56. FINAL ROUTE-BY-ROUTE TEST
============================================================

Before considering this project complete, simulate:

New student
Signup
Onboarding
Home

Upload document
Processing
Study
AI
Quiz
Flashcards
Podcast
Save

Publish material
Rights confirmation
Review
Approval
XP
Achievement
Share

Discover group
Join
Post
Ask question
Reply
Follow student

Create chat
Send message
Attachment
Create group
Select members
Manage group

Discover opportunity
Save
Apply
Share
Submit opportunity
Admin approval
Featured
Sponsored
Expiry

Upgrade
Select plan
Payment
Success
Premium

Admin login
Dashboard
Users
Content
Groups
Opportunities
AI
Payments
Analytics
Moderation
Platform Controls
Audit logs

Organisation login
Verification
Create opportunity
Submit
Billing
Featured/Sponsored

At every step ask:

Where does this go?

What happens while loading?

What happens if it succeeds?

What happens if it fails?

What if there is no data?

What if the user lacks permission?

What happens next?

Where does Back take the user?

How does the user recover?

Fix every issue discovered.

============================================================
57. FINAL QUALITY STANDARD
============================================================

The finished product should NOT feel like:

- a template
- an AI-generated dashboard
- a collection of disconnected screens
- a collection of pretty mockups

It should feel like:

A real product whose backend has simply not been connected yet.

The user should be able to understand every interaction without explanation.

The interface should be clean, confident, restrained and professional.

Use animation only where it improves comprehension or feedback.

Use icons consistently.

Use whitespace intelligently.

Avoid unnecessary emojis.

Avoid unnecessary cards.

Avoid unnecessary buttons.

Avoid unnecessary features.

Every element must earn its place.

============================================================
58. FINAL HANDOFF REQUIREMENT
============================================================

When this frontend completion pass is finished, ensure the project contains:

- Complete student frontend
- Complete admin frontend
- Organisation/recruiter frontend
- Complete routing
- Complete loading states
- Skeleton loaders
- Empty states
- Error states
- Warning states
- Permission states
- Confirmation dialogs
- Success states
- Animations/micro-interactions
- Responsive layouts
- Consistent design system
- Complete navigation
- No dead buttons
- No dead routes
- No unexplained features

The frontend is considered complete only when the only major missing pieces are:

Real backend
Real database
Real authentication
Real storage
Real AI API connections
Real realtime infrastructure
Real payment processing
Real production data
Production security

After this is complete, STOP frontend expansion.

The next phase will be:

1. Final frontend inspection
2. Terms of Service
3. Privacy Policy
4. Content/Copyright Policy
5. Frontend/backend gap analysis
6. Claude backend upgrade plan
7. Claude implementation in LARGE LOGICAL FEATURE CHUNKS

Claude must NOT work button-by-button.

Claude should work in cohesive feature chunks.

For each chunk:

- inspect related existing code
- modify/create all necessary files
- connect related frontend/backend functionality
- run relevant tests
- provide the exact terminal commands required
- explain what changed
- identify any remaining dependency

Do not waste time repeatedly making isolated one-button changes.

The final objective is a complete, coherent Prepza product.