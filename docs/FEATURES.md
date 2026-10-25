# InGather: features and workflow

**Less scrolling. More together.** InGather is an Instagram-style web app for HackTX 2026, Meta track: *Bringing people closer together with AI*. You privately describe something you want to do. InGather finds compatible people, forms a small group, picks a fair public place everyone votes on, and opens a group chat. AI does the coordination; people make every decision that matters.

> Independent prototype. Not affiliated with Instagram or Meta. Demo people are fictional, and demo verification is simulated: no ID is checked.

This document reflects the `dev` branch as of Oct 25, 2026.

---

## 1. The complete workflow at a glance

```text
 Sign up / sign in ──► Verify (demo or Stripe) ──► Create a private plan
                                                    │  "Describe it" (Muse Spark Intake agent)
                                                    │  or "Fill manually", voice input optional
                                                    ▼
                                    Save with AI consent ──► search starts automatically
                                                    │
                                                    ▼
             ML matcher: eligible people ─► fit scores ─► group with shared free time ─► checks
                                                    │
                                                    ▼
                         "Your people": pass privately, or select and approve invitations
                                                    │
                       ┌────────────────────────────┴───────────────────────────┐
                       ▼                                                        ▼
           Invitee accepts (sees a limited                     Invitee declines (private)
           preview first, then the group)                                  │
                       │                                         automatic replan suggests a
                       │                                         replacement; owner approves
                       ▼                                                        │
      Venue vote: Muse Spark + web search finds 3 real public places ◄──────────┘
      near a privacy-safe midpoint; everyone votes, most votes wins
                       │
                       ▼
      Everyone confirms the exact time, place and group ──► "Confirmed by N of N"
                       │
                       ▼
      Gather Room opens (group chat + Muse Spark icebreaker), Add to calendar (.ics),
      Reserve link, one-to-one chats with group members

 In parallel: Home feed of open groups ─► "Ask to join" (Muse drafts your note) ─► host accepts
```

---

## 2. Accounts and sign-in

### 2.1 Sign up and sign in
- **Email and password:** passwords must be at least 8 characters and are hashed with bcrypt; plain-text passwords are never stored.
- **Show/hide password:** an eye toggle on every password field, accessible to screen readers.
- **Confirm password:** on Join, a second field shows "Passwords don't match yet" live, and **Create account** stays disabled until both match.
- **Sessions:** after sign-in the server issues a signed token (JWT, valid 24 hours). Every request is checked against it. The server works out who you are from the token alone, so nobody can act as another user by editing a request.
- **Supabase Auth (optional):** with `SUPABASE_URL` and `SUPABASE_ANON_KEY` set, sign-up and sign-in go through Supabase. The backend verifies Supabase's token and creates the InGather profile on first sign-in. Local registration closes while Supabase Auth is on. Demo logins keep working.
- **Too many attempts:** repeated login and registration attempts are rate-limited.
- **Switching accounts:** if a different person signs in on the same browser, they land on their own Home, never on the previous person's last page.

### 2.2 Demo accounts (`DEMO_MODE=true` only)
- **The named cast:** one-click "Continue as …" buttons for the fictional cast (Alice, Maya, Sofia, Jordan, Taylor, Eve, Priya, Marcus, Lena, Noah, Diego). Password for any of them: `demo-password`, email `<name>@ingather.example`.
- **Eve is the "attacker"** account, blocked by Alice, for showing that privacy holds.
- **1,000 fictional Austin residents** with realistic bios, illustrated avatars and plans for the coming week, plus 150 open groups formed by the ML matcher, so the Home feed is full.
- **Switching:** the account menu in the bottom-left switches between demo users without signing out.

### 2.3 Verification
New accounts start **unverified** and can't be matched until they verify. After Join, you land on `/verify`.
- **Demo verification:** tick "I confirm I'm 18 or older". The account is labeled **"Demo verification on — simulated, no ID checked"**. The confirmation must be exactly `true`, so values like `1` or `"yes"` are rejected.
- **Stripe Identity (built, needs keys):**
  1. Stripe's hosted page checks a photo ID.
  2. A signature-verified webhook marks the account `verified_live` and sets adulthood from the verified date of birth.
  3. The account is matched only by the Stripe session stored for that user, so it can't be faked. Test mode is labeled "not a real ID check".
- **Wording rule:** verification is never described as "safe". The app says it confirms identity, not behavior.

---

## 3. Creating a plan

A plan is **private by default**. Only you see it.

### 3.1 Two ways to fill it
1. **Describe it (default):**
   - Type, or speak with the mic, a sentence such as *"I'm in Philadelphia Jan 17–19 for a tech conference, free 5–9 PM, want 2–3 people for coffee and museums."*
   - **Fill with AI** sends it to the **Muse Spark Intake agent**. It is told today's date and your timezone, and fills: activity, title, goal, city, IANA timezone (worked out from the city), dates (always upcoming), free-time windows on each day, interests, intent and group size.
   - Every AI-filled field shows a violet **"Filled by Intake agent"** mark that disappears when you edit it.
   - A note explains any assumption, for example "assumed free until 9 PM", and **"Still needed from you"** lists anything the AI couldn't work out.
   - The server re-checks every field: past dates, impossible group sizes and times outside the plan's dates are thrown out and listed as missing. If no times are found, you get an empty row to fill in instead of a leftover placeholder.
   - **Nothing is saved until you click Save.**
2. **Fill manually:** the same form, filled by you.

### 3.2 Form fields
- **The plan itself:** activity (Conference, Travel, Hackathon, Study, Coffee & food, Local event, Other), title, goal, city, timezone, from and to dates.
- **Free times:** day plus from and until, in the plan's local time. These stay private; the system only learns whether a group overlaps.
- **Public event location (optional):** a public venue such as a convention center, used to find nearby places. Never a home or hotel.
- **Who you want:** interests, what you're looking for (friends, networking, activity partner), group size (2–4 including you), and group meetups only (recommended).
- **Public-safe preview (optional):** the only text a match can see before accepting.
- **Discovery:** **Private** (default; your agent can search, but nobody can find you) or **Mutual discovery** (your preview may be suggested to eligible, opted-in people).
- **AI consent:** "Let Gather Agent process this plan with AI". Without it, no search runs.

### 3.3 Voice input
The mic records your voice in the browser, and **Muse Voice Transcribe** turns it into text in the goal box.

### 3.4 Cover photos
- **Your own cover:** after you save, a **Muse Image** cover is generated in the background from the activity, city and interests only, never your name or goal text. It is styled as a candid, realistic phone photo with real city details, using Muse Image's built-in image search.
- **Until it's ready:** a realistic library photo for that activity in that city, for example `study-philadelphia`, or for the activity alone.
- **Regenerate:** "Generate cover with Muse Image" makes a new one.

### 3.5 Saving
Saving with AI consent **starts the search immediately** and opens the plan page on the results.

---

## 4. Finding people (ML matcher)

### 4.1 What happens during a search
The plan page shows a plain status, "Finding people who share your plans…", then "Checking when everyone's free…", then "Picking a good public spot…". Behind it:
1. **Eligibility (server rules, never AI):** other users whose active plan is in **mutual discovery**, in the same city, with overlapping dates and free time. They must be verified adults, not paused, not blocked in either direction, and not already passed on or declined.
2. **Scoring:** the **InGather matcher** is a gradient-boosted model over 11 pair features, with interest embeddings learned from 1.76M Meetup.com members. It is trained on 300k real join decisions from the public Meetup.com dataset. Each candidate gets a fit score.
3. **Group building:** it tries combinations of candidates. It fills the **group size you asked for** where a bigger group still shares at least an hour of free time, and also scores how well the members fit each other.
4. **Time and place:** it picks a time inside everyone's shared window and suggests a generic public place, or a mapped one near your public event location.
5. **Checks:** public place, everyone free then, group size within bounds, nobody excluded or blocked. Then it saves a proposal. **Nobody is invited yet.**

A search finishes in about a second and costs no AI tokens. If nobody fits, you see a plain message and a **Try again** button. **Search again** reruns it at any time.

### 4.2 Reviewing suggestions ("Your people")
- **Each suggestion shows:** the person's first name, avatar, interests and a grounded reason, for example "Shares tech and food; also here for a conference; free together 6h".
- **Pass:** removes someone privately. They are never told. You can add optional feedback ("Prefer same event", "Prefer group", "Different activity", "Schedule doesn't fit"), and a new search starts that excludes them.
- **Select, then Review invitations:** a dialog lists exactly who will be invited and states that nothing has been sent yet. **Send N invitations** sends only to them.

### 4.3 Automatic replanning
If an invitee **declines**, a new search starts automatically. It suggests a replacement, keeps everyone who accepted, and **waits for your approval** before inviting anyone new.

---

## 5. Invitations and joining a group

### 5.1 As an invitee
- **What you see:** the Invitations tab shows the activity, city, day, group size and organizer. The venue and other members stay hidden until you accept.
- **Your choices:** **Accept**, **Decline** (private, no reason needed), **Block** the organizer, or **Report**.
- **After accepting:** you see the group roster (first names and interests) and take part in the venue vote.

### 5.2 Home feed of open groups
- **What's in it:** Home shows **open groups** you could ask to join, ranked by the matcher for you. Only the day, part of day, kind of place, first names, spots left and match % are shown. No exact time, venue or full names until you're accepted.
- **Filters:** category tabs (Explore, Travel, Conference, Study, Coffee, Hackathon, Events), a sort (**Best match** or **Soonest**) and day chips (Any day, Today, Tomorrow, This weekend).
- **Ask to join:** add an optional note. **"Write it with Muse"** drafts it from your own bio and interests.
- **Hosts:** they see a requests panel with your note and match, then accept or decline privately. Accepting adds you, resets earlier confirmations and posts a **Muse-written welcome note**. Hosts can turn **"Let people ask to join"** on or off. In demo mode, fictional hosts answer on their own after a few seconds.
- **Who can see a group:** only open groups that haven't started, have spots left and have no blocks with any member.

---

## 6. Agreeing on a place: the venue vote

1. **Home areas:** each person can set an approximate **home area** (city, neighborhood or ZIP) in Profile. The server rounds it to about 1 km and never shows it to anyone, including the owner.
2. **Midpoint:** the server averages the group's rounded points into a **midpoint**.
3. **Pick the place together:** **Muse Spark with web search** gets only the city, the rounded midpoint, the meetup time, the activity and the shared interests. It returns **3 real public places** that fit the group and are open then, each with a "why this spot". Coordinates are never shown in the text.
4. **Verification badge:** each option is marked **"Verified via search"**, with a source link, only if its source came from the actual search results. Otherwise it says "Suggestion — not verified". Without the AI, it offers generic place types and never invents names.
5. **Voting:** every participant taps one option and can change their vote until everyone has voted. A live tally shows who's still voting.
6. **Winner:** most votes wins, with a burst animation. A tie goes to the AI's top-ranked option.
7. **None of these work:** a fresh set of 3, once per group.
8. **Final confirmation:** the winner becomes the meetup's place, and everyone must confirm the new version.

---

## 7. Confirming the meetup (SafeMeet)

- **Finalizing:** the organizer sets or edits the final public place and time. Every member, including the organizer, then confirms that **exact version**. Any change resets the confirmations.
- **Confirmed:** when all have confirmed, the status becomes **"Confirmed by N of N people"**.
- **Safety reminders:** meet in public, arrange your own transport, don't share your home, hotel or phone number, tell someone you trust, leave anytime. **Share with trusted contact** uses the phone's share sheet, or copies the details.
- **Add to calendar:** a standard `.ics` file with the right time and venue, for Google, Apple or Outlook.
- **Reserve:** shown only when the venue has a real online booking link (OpenTable, Resy, Tock, SevenRooms or the venue's own site).
- **Where confirmed events open:** on Home, the plan card says **Open your group** and goes straight to the group.

---

## 8. Chatting

- **Gather Room:** a group chat for confirmed members only, with the venue and a map. When the group confirms, **Muse Spark writes an icebreaker** from the interests most of the group shares, for example "What's one spot in the city you'd love to explore next — museum, café, or food market?". Messages are plain text, so typed HTML is shown as text and never run.
- **Messages inbox:** the Messenger button (top right) lists your **group chats** and **one-to-one chats** with people from confirmed meetups. You can search and filter it by Groups or People.

---

## 9. Managing your things

Each item has a 🗑 button with a confirmation step:

| Item | Effect |
|---|---|
| Plan card | Deletes the plan, its suggestions and any group made from it, for everyone. |
| Unanswered invitation | Declines it privately and removes it. |
| Accepted invitation or group | Leaves the group; you lose access to its details and chat. |
| Group chat | Leaves the group. |
| One-to-one chat | Deletes the conversation and messages for both people. |

**Profile** lets you upload a photo (JPEG/PNG/WebP, up to 3 MB) or keep a random illustrated avatar you can shuffle, edit your name, bio and interests, optionally add "About you" details (gender, age range, education, work; each group with its own "Show to accepted group members" switch, off by default), set a home area, pause all discovery, choose group-only meetups, see your verification status and manage blocks.

---

## 10. Privacy and security model

- **Enforced by the backend, never by prompts.** One `Policy` service decides all access. Anyone outside a plan, group, chat, vote or calendar file gets a uniform **404**, so they can't even tell it exists.
- **What other people see:** your exact free times, goal text, email, home area and verification details are never shown to anyone else.
- **Optional "about you" fields:** gender, age range (ranges only), education and work are self-reported and never inferred. They're never used to match or rank anyone and never sent to an AI model. Each group is hidden until you switch it on, and even then only accepted members of your groups and people from confirmed meetups see it; never strangers, the feed or people who were only invited.
- **Avatars:** without a photo you get a random illustrated avatar. Its style follows the gender you chose (if any); its look is random, never guessed from your name. Uploads are checked by their actual bytes.
- **What the AI sees:** only minimized data. Intake gets your own text, the venue agent gets the city and rounded midpoint, the icebreaker gets the activity, venue type and shared interests, and covers get the activity, city and interests. Matching uses the trained model, so no chat model sees other people.
- **Human approval at every step:** you approve every invitation, for an exact roster and version. Each person accepts on their own. Every confirmation is for an exact version.
- **Blocks:** work in both directions, everywhere.
- **Abuse protection:** rate limits on searches, invitations, messages, drafts and logins.
- **Tested attacks:** 138 backend tests cover cases such as Eve reading Alice's plan, someone else accepting your invitation, self-verifying and forged Stripe webhooks.

---

## 11. Meta AI in the product

| Model | Used for |
|---|---|
| `muse-spark-1.3` | Intake agent (text to plan), venue agent with web search, icebreaker, join-note drafting, host welcome notes, demo venue and bio enrichment |
| `muse-image-1.0` | Realistic plan covers and the photo library |
| `muse-voice-transcribe-1.0` | Speaking your plan |
| InGather matcher (trained ML model) | Picking compatible people and groups: fast, consistent, and no chat model judging people |
| Muse connector (MCP at `/mcp`) | Your own Muse agent can list your plans, run a search and read invitations with a revocable token. It cannot approve or confirm anything. |

---

## 12. Design

- **Look:** an Instagram-inspired palette (yellow → orange → pink → purple → blue gradient) for buttons, story rings, the logo and the active nav item. Each activity has its own color.
- **Navigation:** a sidebar on desktop and a bottom bar on phones: Home, Invitations, Create, Profile.
- **Motion:** card entrances, a press scale on buttons, a vote "pop" and a confirmation burst, all turned off for users who prefer reduced motion.
- **Accessibility:** touch targets at least 44 px, visible focus rings, labels on every control, and contrast-checked text on gradients.

---

## 13. Running and deploying

```bash
cp .env.example .env            # add MODEL_API_KEY (Meta Model API)
docker compose up -d --build    # http://localhost:8000
docker compose down -v && docker compose up -d   # wipe all data and reseed the demo
```

- **Startup:** the container runs database migrations (Alembic) and, in demo mode, seeds the demo people.
- **Supabase:** set `SUPABASE_DATABASE_URL` to use Supabase Postgres instead of the bundled Postgres. Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` for Supabase sign-in.
- **Deploying:** one image serves the API and the React app, so it can be deployed to any container host with a managed Postgres.
- **Tests:** `cd backend && uv run pytest -q` and `cd frontend && npm test && npm run build`.
- **Photo library:** `cd backend && uv run python ../scripts/generate_images.py` regenerates it.

---

## 14. Known limits

- **Stripe:** verification needs your Stripe test keys, and test mode doesn't check a real ID.
- **Venues:** a venue's opening hours come from web search, not a booking system. The "Verified via search" badge can mark a real place as unverified when its source link doesn't match exactly.
- **Speed:** a venue search takes about 25–35 seconds.
- **Not live yet:** the Muse connector hasn't been tried with a real Muse agent, because that needs a public URL.
- **Before a real launch:** no email confirmation or password reset, and no human moderation team behind reports.
