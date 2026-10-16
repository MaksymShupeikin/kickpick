# KickPick design system

The single source of rules for how the KickPick iOS app looks. If a screen disagrees with this file, the screen is fixed. Swift code comments cite sections of this file by number (for example §6.3), so section numbers must not move.

Source: the `ui-ux-pro-max` guide (`.claude/skills/ui-ux-pro-max`). Query: `sports live scores football mobile app minimal monochrome glassmorphism dark gray`, plus searches in the `style`, `color` and `ux` domains and the `swiftui` stack.

## Contents

- [1. What was taken from the guide and what was changed](#1-what-was-taken-from-the-guide-and-what-was-changed)
- [2. Principles](#2-principles)
- [3. Colour](#3-colour)
- [4. Typography](#4-typography)
- [5. Grid and shape](#5-grid-and-shape)
- [6. Materials](#6-materials)
- [7. Images: real only](#7-images-real-only)
- [8. Components](#8-components)
- [9. Motion](#9-motion)
- [10. Forbidden (summary)](#10-forbidden-summary)
- [11. Checklist before a screen is done](#11-checklist-before-a-screen-is-done)

## 1. What was taken from the guide and what was changed

| The guide suggested | Decision | Why |
|---|---|---|
| **Glassmorphism** style: blur 10–20, translucent white 10–30 %, 1 px white 20 % border, highlight, depth | **Adopted** | matches the "frosted glass" request |
| Bright coloured background under the glass | **Replaced** with a grey background with soft white light spots | the glass needs something to blur, but colour is forbidden |
| CTA accent `#2563EB` (blue) | **Rejected**, the accent is white `#FFFFFF` | requirement: white accent, no blue-violet |
| Fonts Barlow Condensed / Barlow ("Sports, athletic, condensed") | **Barlow Condensed for digits only**, all text is SF Pro (headings use `.condensed`) | Barlow has no Cyrillic (checked against the glyph table); SF Pro supports Dynamic Type |
| Button depth (Tactile UI: press with scale-down, spring, haptic feedback; Soft UI: soft shadows 200–300 ms) | **Adopted**, depth from light and shadow | requirement: "3D effect on buttons" |
| Skeuomorphism (textures, gradients of 8–12 points) | **Rejected** | marked "Performance: Poor" in the guide, against "as simple as possible" |
| App Store Landing pattern | **Not applied** | it is for a landing page, ours is an app |
| SVG icons (Heroicons/Lucide) | **SF Symbols** | the native equivalent on iOS, one set |

## 2. Principles

1. As simple as possible: grey background, glass cards, white text and a white accent. Nothing else.
2. White is the only accent colour. There are no other colours except the functional marks in §3.3.
3. Only buttons and selected segments have depth. Cards are flat, they are glass.
4. The interface uses real images only: actual crests, tournament logos and player photos. There are no drawn placeholders.
5. One theme, dark grey (`.preferredColorScheme(.dark)`). A white accent is unreadable on a light background, so there is no light theme.

## 3. Colour

### 3.1 Background
- Base vertical gradient: `#2B2B2F` at the top → `#1A1A1D` at the bottom (shades of grey only).
- Two light spots under the glass: white radial gradients at 7 % opacity (radius ≈ 60 % of the screen width). One at the top left, the other at the centre right. The spots do not move.
- Component: `AppBackground`, placed under every screen (`.background { AppBackground() }`).

### 3.2 Tokens (`Color+Tokens.swift`)

| Token | Value | Used for |
|---|---|---|
| `textPrimary` | `#FFFFFF` | names, score, headings |
| `textSecondary` | white 64 % | time, losing team, captions |
| `textTertiary` | white 52 % | table column headings |
| `accent` | `#FFFFFF` | primary button, selected segment, highlight |
| `onAccent` | `#111113` | text and icons on white |
| `hairline` | white 10 % | row separators (the name `separator` is taken in SwiftUI) |
| `glassStroke` | gradient: white 22 % at the top → white 5 % at the bottom | glass border (highlight at the top) |
| `glassTint` | white 6 % | fill on top of the material |
| `solidSurface` | `#2C2C30` | replaces the glass when "Reduce Transparency" is on |

Contrast check (on the darkest area under the glass ≈ `#2A2A2E`): `textSecondary` ≈ 6.8:1, `textTertiary` ≈ 5.0:1, both above 4.5:1. White text at white 64 % or lower is forbidden.

### 3.3 Functional colours (small marks only, never a background; text only for form letters and ratings)
- Yellow card: an 8×11 pt rectangle in `#FFD60A`.
- Red card: an 8×11 pt rectangle in `#FF453A`.
- Match in progress: a 6 pt dot in `#FF453A` next to the minute. Colour is never the only signal: the minute text is always beside it, for example `67'`.
- A player's goals and assists in a match (`Contributions`): a `soccerball` with the number of goals and a `shoe.fill` boot with the number of assists, in `textPrimary`, shown only if there are any. On the pitch, next to the rating (9 pt); for substitutes, before the minute they came on; in the player's matches, under the minutes. They are counted from the match events and the player's name (ignoring diacritics); an own goal is not the player's goal.
- A player's match rating (in his matches and on the pitch in lineups) is shown as digits in colour: below 6.0 red `loss` `#FF453A`, 6.0–6.9 yellow `cardYellow` `#FFD60A`, 7.0–7.9 green `win` `#30D158`, 8.0 and above blue `standout` `#0A84FF` (`Color.rating`). Season average ratings in tables have no colour.
- Table zone: a 3 pt stripe to the left of the position (`StandingLine`) in the FotMob colour (`qualColor`: Champions League, Europa League, relegation, playoff qualification and so on). Colour is not the only signal: under the tables there is a legend, "stripe + zone name" (`ZoneLegend`, `footnote`, `textSecondary`), and VoiceOver reads the zone in the row.
- Team form is result letters: W green `win` `#30D158`, L red `loss` `#FF453A` (same as the red card), D grey `textSecondary`. Colour is not the only signal: the letter itself is the result.

### 3.4 Forbidden
- Blue-violet gradients, and any coloured gradients and coloured backgrounds.
- Neon glow, coloured shadows.
- Table zones as a row background or text colour; only as a stripe (§3.3).

## 4. Typography

| Role | Font | Size / weight | Dynamic Type |
|---|---|---|---|
| Screen title | SF Pro, `.fontWidth(.condensed)` | 34 / Bold | `.largeTitle` |
| Section title | SF Pro, `.condensed` | 20 / Semibold | `.title3` |
| Body text, team names | SF Pro | 17 / Regular (winner: Semibold) | `.body` |
| Secondary text | SF Pro | 15 / Regular | `.subheadline` |
| Small text (minimum) | SF Pro | 13 / Medium | `.footnote` |
| Score in the match header | Barlow Condensed | 48 / Bold | `relativeTo: .largeTitle` |
| Score in a match row, minute | Barlow Condensed | 22 / Bold | `relativeTo: .title3` |
| Table figures, player numbers | Barlow Condensed | 17 / SemiBold | `relativeTo: .body` |

- Barlow Condensed (OFL) is bundled as two files: `BarlowCondensed-SemiBold.ttf` and `BarlowCondensed-Bold.ttf`. They are registered through `UIAppFonts`.
- All figures that update live use `.monospacedDigit()`, so the row does not jitter.
- Text smaller than 13 pt is not used.

## 5. Grid and shape

- Spacing: scale 4 / 8 / 12 / 16 / 24 / 32. Screen edge 16, card inner padding 16, between cards 12.
- Hierarchy by proximity (the closer the relation, the smaller the gap): section title → its card 12; search → control bar (days, calendar) 16; controls → content 24; between sections (leagues in the match feed) 32.
- Corner radii: rows and small plates 12, cards 20, buttons and segments capsule.
- Touch: minimum 44×44 pt, 8 pt between neighbouring targets.

## 6. Materials

### 6.1 Glass (`.glassCard()`)
```swift
.background(.ultraThinMaterial, in: .rect(cornerRadius: 20))
.overlay(RoundedRectangle(cornerRadius: 20).fill(Color.glassTint))
.overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Color.glassStroke, lineWidth: 1))
.shadow(color: .black.opacity(0.25), radius: 24, y: 8)
```
- With `accessibilityReduceTransparency`: a `solidSurface` fill without the material; the border stays.
- Glass is not placed on glass. Inside a card, rows are separated by a `hairline` line.

### 6.2 Buttons with depth
Depth comes from light at the top and shadow at the bottom. There are no textures; gradients are grey-white only.

**Primary (white)**, `PrimaryButtonStyle`:
- Fill: linear gradient `#FFFFFF` → `#E4E4E7`, top to bottom.
- Inner highlight: a 1 pt stroke on the top half, white 100 % → 0 %.
- Bottom edge: an inner 1 pt stroke `#000000` 12 % along the bottom edge.
- Outer shadow in two layers: `black 30 %, r 1, y 1` and `black 35 %, r 16, y 8`.
- Text `onAccent`, SF Pro 17 Semibold. Height 50, capsule shape.
- Pressed: `scale 0.97`, shadows `r 4, y 2`, gradient 4 % darker; `.spring(response: 0.25, dampingFraction: 0.7)`; `.sensoryFeedback(.impact(weight: .light), trigger:)`.

**Secondary (glass)**, `GlassButtonStyle`: exactly the card glass from §6.1 (same stroke and soft shadow) in a capsule or circle shape, without a separate highlight or the two-layer shadow, because on a small button they give a dark halo at the top. Text `textPrimary`. Pressed: scale and feedback as for the white one.

**Selected segment** (Table / Matches / Bracket, date strip, tab bar): the track is a glass capsule, the selected segment is a white capsule with depth and `onAccent` text. On tap it slides over in 200 ms. The capsule can be dragged with a finger, like the native iOS 26 tab bar: it follows the finger, lifts slightly, gives a haptic click at the border between segments, and on release the segment under the finger is selected. The gesture starts only on horizontal movement, so a vertical swipe from the switcher scrolls the page (iOS 18+; on iOS 17 tap only).

**Scrollable switcher** (`scrolls: true`: club tabs, tournaments in its tables, date strip). More than 5 options means scrolling at once. With `captions`, a small caption above the name (`caption2`, 75 %), height 52. If the names fit, the segments are equal, as usual. If not, each segment is as wide as its name and the track scrolls inside the capsule. A new selection is centred. The pill is dragged only from itself: a swipe anywhere else scrolls the track. While the pill is being dragged, the segment next to it scrolls into view, so the pill can be taken to hidden tabs.

**Haptic feedback**, only where it confirms something:
- a light tap (`.impact(.light)`) when any button with depth is pressed;
- a selection click (`.selection`) for a segment change (tabs, date strip, tab bar, including while dragging the pill), a day from the calendar, a tournament season;
- a medium tap (`.impact(.medium)`) for a goal in an open live match (the score went up; not when a goal is cancelled) and for returning to the first screen by holding "back";
- error (`.error`) when "Couldn't load" appears.
Screen transitions, row taps and scrolling have no feedback, as in the system.

With `accessibilityReduceMotion`, a press changes only the shadow, with no scale. The segment slide has no animation.

### 6.3 Tab bar and navigation
- The system `TabView` with its tab bar hidden; a custom floating one instead: a `SegmentedPicker` with icons, a glass capsule, the selected tab a white capsule with depth, sliding like any segment (§6.2). Content scrolls under it, but the list ends above the bar with a 16 gap: the bottom padding equals the measured bar height (`tabBarHeight` in the environment), so with a large font it grows together with the bar. Under the bar the content fades the same way as under the search field at the top: the list mask (`SearchableScreen`) smoothly makes it transparent above the bar, and under the home indicator the list is not visible at all. Both masks cover only the list padding, so at the very top and very bottom positions nothing is dimmed. The bar exists only on root tab screens and hides while search is open (otherwise it ends up above the dimming and above the keyboard, over the suggestions): when going to any nested screen and when search opens it moves down (0.25 s; with "Reduce Motion" it just fades) and comes back on the root.
- Tabs: "Matches" (`sportscourt`), "Competitions" (`trophy`). Root screens have no large title: at the top is the expanding glass search field (`SearchableScreen`), with the content right under it.
- The interface language is English, dates in `en_GB` ("13 Oct", 24-hour time).
- If the bar has a picker on the right (the season on the tournament screen), the title sits on the left, right after the "back" button: tournament logo 24 + name (`.headline` condensed) in the left slot of the bar (`.topBarLeading`). The width follows the name but is no larger than the space the season button leaves: screen width − season text width − 182 allowance (margins, "back", gaps, button padding). Otherwise the bar collapses the season button into a "…" menu. The middle slot (`.principal`) does not work: on a wide screen the bar centres it. On the button the season is short: "26/27", "26/27 Apertura"; in the picker list the full names are shown, and VoiceOver reads the full one.
- The "back" button is a round glass button with depth (`.glassIcon`, like the calendar button), set once in `withRoutes`. A tap goes back one screen; a hold of 0.5 s goes straight to the first screen of the tab (the match feed or the tournament list) with a medium haptic tap; for VoiceOver the same action is "Back to start". The swipe back from the edge is kept.
- Buttons in the nav bar draw their own glass (`GlassToolbarItem`): on iOS 26 the system glass around them is turned off, to avoid a double one.
- Nested screens (match, player, team): there is no title in the bar, the screen's main block names it. When the block goes fully under the bar, a mini version fades in at its centre (`revealsInBar`): for a match, the crests and the score (the time before kick-off); for a player, the photo and name; for a team, the crest and name. For a finished match, the score card shows the scorers under the teams: hosts on the left (aligned to the centre), guests on the right, with a ball between them (`soccerball`, `textTertiary`). One line per player, in order of first goal: surname and minutes ("Hinshelwood 23', 67'"), penalty "(P)", own goal "(OG)", in the column of the team it counts for. `footnote`, `textSecondary`. Under the score card (gap 12) is a compact "Form / H2H" card, with a mirrored layout like the score. **Form**: each team's last 5 finished matches before this one, from oldest to newest, as W / D / L letters in the digit font, with colours per §3.3: W green, L red, D grey. This is text, not chips. **H2H**: the last 5 head-to-head meetings; on each side that team's result "3W 1D 1L" (the number is `textPrimary`, the letter is in the form colour), in the centre "H2H". A row without data is hidden, and with neither, the whole card is hidden. It is counted from our database, so only over the tournaments we collect. A match has, above the score card, a line with the tournament and matchday ("LaLiga · Matchday 9 ›", logo 20, `textSecondary`, chevron), on the left, like section titles above cards. Tapping opens the tournament in this match's season. The content is split into `SegmentedPicker` tabs: match: Events / Stats / Lineups; player: Matches / Stats / Career; team: Results / Fixtures / Squad / Transfers.
- An event row leads to the player's profile. Events store only names, so the API looks the player up by name in this match's lineup, ignoring diacritics; with two namesakes the event stays non-tappable.
- On the player photo, at the bottom corners, are badges (`TeamBadge`): on the left the national team flag, on the right the club crest, 22 pt in a glass circle of 32, tap area 44. A tap leads to the national team and to the club; VoiceOver: "National team: Spain", "Club: Barcelona". The club is taken from the lineup, otherwise from the FotMob profile. If we have no page for it, the badge is shown but not tappable. The facts card has no country.
- Under the club name is a country line (`TeamLink`: flag + name, leads to the national team). Below it is a facts card (`FactsCard`, like the player's): Stadium, City, Capacity, Opened. Empty rows are not shown. The data comes from the FotMob team page (country, stadium, trophies) and is collected by the collector.
- In the player's facts card, Age is written "19 (13 Jul 2007)": the age, with the date of birth in brackets. After Position and Age come Height ("189 cm"), Foot, Market value ("€2.2M", like transfer amounts) and Contract until ("30 Jun 2027", in GMT).
- A club has the tabs Results · Fixtures · Table · Squad · Transfers · Trophies. Trophies: rows like in the player's statistics (tournament logo, name, "Last won 2023", columns Won and 2nd), more titles higher. Table shows the tables of the current seasons where it plays: the league first, tournaments switched with a second switcher. Only groups containing the club are shown, its row is highlighted with a `rowHighlight` background (white 10 %) and a bold name and is not tappable.
- In a club's Squad, on the right of a player's row is the flag of his country (24, from `flag_url`; VoiceOver reads the country name), not the number. For a national team, instead of the flag there is the crest of the player's club (from his FotMob profile, otherwise from the club squad we have); the national team's own flag is not repeated, and for a player without a club the right side is empty.
- Expanded search is full width; the close control is built into the card: a cross on the right of the field row (`textSecondary`, tap area 44). When there is text, to the left of it is clear (a cross in a circle, `textTertiary`). Tapping the dimming also closes search.
- The **day picker** in the match feed is pinned under the search field (the `SearchableScreen` header): the list scrolls under it, is not visible behind the strip and the field, and fades smoothly in the 16 pt under the strip. Only on the Matches tab. It is a scrollable date strip for 30 days back and forward from today: a caption "Yesterday / Today / Tomorrow" or a weekday ("Thu"), and under it the date ("16 Oct"; for days of another year, with the year: "18 Oct 2025"). The selected day is centred. If the calendar picked a date more than a month away, the strip is built around it.
- **Changing the day without flicker.** Loaded days are kept in memory while the app runs: an opened day shows its matches at once, and fresh ones replace them quietly, with no placeholders. As soon as a day is open, two days in each direction are loaded in the background. Placeholders (`redacted`) appear only for a day that has never been loaded.
- **Swiping the list** of matches turns days like pages: finger left, next day; right, previous day (threshold 60 pt; horizontal movement only, vertical scrolling does not interfere). The new day slides in from the side the date strip moves towards (0.25 s; with "Reduce Motion", a fade instead), and the strip moves to it with a selection click. A day picked in the strip or the calendar slides in the same way.
- The **calendar** (the button to the right of the strip) is a `UICalendarView` in a sheet: picking the month and year in the header does not close the sheet and returns to the day grid. Above the calendar is a row of buttons inset from the sheet's rounded corners: on the right a round "close" (`.glassIcon`, cross), on the left, if the selected day is not today, a glass "Today" (`.glass`) that selects today and closes the sheet. The sheet height fits the content (buttons + month). The sheet closes only on a tap on a day or on "Today" (with the graphical `DatePicker` the date changed already when the month changed).
- **Substitutes** in lineups form one "Substitutes" section: under the title is our switcher with the team names, and below it one card with the selected team's substitutes. If only one team has substitutes, there is no switcher, and the title is "Substitutes · <team>". In a substitute's row, on the right is the flag of his country (24), not the number.
- **Lineups before the match.** For matches in the next 3 days the collector fetches the FotMob lineup every 6 hours, and from 3 hours before kick-off every 20 minutes until a confirmed one comes out. The type (`lineups.type`): `predicted` is the FotMob forecast (starters, formation, coaches, absentees; no substitutes), title "Predicted lineups"; `lastStarting11` is the team's last starting lineup, when there is no forecast, "Last starting lineups"; `standard` is confirmed, no title; `unavailable` means no players, only absentees: "No lineups yet" instead of the pitch. For all unconfirmed ones, ratings and substitution minutes are removed (they come from a past match). The lineup of an upcoming match does not count as a match the player has played.
- In the match feed for a date, tournaments go by rank, not by start time. First European cups (Champions League → Europa League → Conference League) and national team tournaments, then leagues, all in the order of the tournament list (`COMPETITIONS` in `config.py`). Within a tournament, matches by time. The API sets the order.
- Changing a tab (and also the tournament in a club's table, and a tournament's season), when the page is scrolled below the tabs, returns the page to the start of the tabs (`scrollsToTabs`): the new tab opens from its start. Otherwise a shorter tab leaves the lazy list scrolled past its end, and it draws nothing, not even the tabs.
- A tournament's matches scroll to the current matchday each time they are opened: the matchday of the nearest live or upcoming match (`currentRound`; a match postponed without a new date does not count). The matchday name sits under the pinned tabs. If the season is over, the list opens at the top.
- The tabs on these screens and on the tournament screen are pinned under the bar while scrolling (`LazyVStack` with a pinned section header). When pinned, the bar's frosted background continues under them (`joinsBarWhenPinned`), and content goes under a single "bar + tabs" block. The screen's main block is kept outside the lazy stack: otherwise it is unloaded together with its mini version in the bar.

## 7. Images: real only

| What | URL (FotMob CDN, checked) | Size in the UI |
|---|---|---|
| Club or national team crest | `images.fotmob.com/image_resources/logo/teamlogo/{teamId}.png` | 24 in a row, 64 in the match header, 72 on the team screen |
| Tournament logo | `images.fotmob.com/image_resources/logo/leaguelogo/dark/{leagueId}.png`, the monochrome white variant for a dark background | 20 in group headers, 40 in the tournament list |
| Player photo | `images.fotmob.com/image_resources/playerimages/{playerId}.png` | 36 in the squad list, 28 on the pitch, 96 in the card |

- The URL is provided by our API (`logo_url`, `photo_url`). The app does not build URLs.
- While an image loads, a glass circle of the same size stands in its place, so the layout does not jump.
- If loading fails, the same empty circle stays. There are no initials, generated crests or emoji.
- Cache: `URLCache` with 50 MB in memory and 200 MB on disk.
- A logo's `accessibilityLabel` is the team or tournament name.

## 8. Components

### Match row (`MatchRow`)
```
┌───────────────────────────────────────────┐
│ 18:45      [crest] Barcelona           2  │
│            [crest] Real Madrid         1  │
└───────────────────────────────────────────┘
```
- Left column (width 46, 8 to the teams). In the one-day feed, only the time ("21:00"; live, the minute `67'` with a red dot, `textPrimary`; for a cancelled match "Cancelled"): the day is already chosen in the date strip. In other lists (club results, a player's matches, tournament matchdays, search) there are two lines: the time and under it the day ("Today", "Tomorrow", "Yesterday" or "14 Oct"); for a match of a past or future year, the date and year instead of the time ("18 Dec" / "2022"). The first line is `footnote` semibold `textSecondary`, the second regular `textTertiary`, with 3 between them so the lines do not merge. In the header of a finished match, under the score are "FT" and "14 Oct 18:45"; for an upcoming match, instead of a dash, the time in large type "21:00", and under it "Today" / "Tomorrow" / "16 Oct".
- The winner is `textPrimary` Semibold, the loser `textSecondary`. A draw: both `textPrimary` Regular.
- On the right is the score, Barlow Condensed 22. Empty before the match starts.
- **No chips, badges, tags or plates** next to the text: no "LIVE", no "FT", no team form, no stage.
- The whole row is one touch target and one accessibility element: "Barcelona 2, Real Madrid 1, finished".

### Tournament match group
The header sits outside the card: tournament logo 20 + name, SF Pro 15 Semibold `textSecondary`. Below it is one glass card, rows inside separated by a `hairline` line.

### Table
- A glass card, row height 44.
- Columns: `#` (Barlow) · crest 24 + name · `P` · `GD` · `Pts`. Points are Barlow Bold `textPrimary`, the other figures `textSecondary`.
- Column headings are 13 Medium `textTertiary`.
- In group tournaments each group has its own card with a title such as "Group A".
- Zones are a stripe to the left of the position (§3.3); under all the cards is one legend with the zones present in the tables shown, in FotMob order. The cards and the legend are one element of the lazy list: a short legend as a separate element beside a long card makes the list recalculate its height endlessly after scrolling (CPU 100 %).

### Playoff bracket
- Horizontal scroll by round, each round a column with a header "1/8", "1/4", "1/2", "Final".
- A tie is a small glass card with two rows: crest 20, name, aggregate score. The winner is `textPrimary`, the loser `textSecondary`.
- Ties in a column are spread over the height so each stands opposite its ties from the previous round. The skeleton has no connecting lines.
- Leagues have no "Bracket" segment. Cups and national team tournaments always have it; if there is no bracket yet, the empty state is "No bracket yet".
- An opponent not yet known is the text "—" in `textTertiary`.

### Match header
A glass card: two crests of 64 with the names under them, the score between them (Barlow 48) and the status as text under the score. Live, the screen refreshes every 15 s without animating the digits (the collector checks scores as often; an unchanged API response comes back as an empty 304).

### Match prediction

- Under the team form, before the tabs: a `Pre-match forecast` title outside a single glass card. The title says
  the numbers are from before the game, so it stays when the match is live. No calculation time is shown.
- Three columns: `Home`, `Draw`, `Away` — not team names (the score card above already names the teams).
  VoiceOver reads "Home win, Barcelona". The percentages are Barlow Condensed 32, with one
  digit after the decimal point; the highest probability is white Bold, the others `textSecondary`.
- Under the values is a 4 pt proportion bar: hosts white, draw white 64 %, guests white 30 %.
- Only `NS` and `LIVE` when a forecast exists. For `FT`, `CANC` and missing or invalid
  data there is no card. When the status updates, it is hidden together with the screen refresh.
- Before the match starts, the screen refreshes every 10 minutes to pick up a forecast that has appeared;
  near kick-off and live, every 15 seconds. After the match ends the refreshes stop.
- From Dynamic Type XXXL, three rows replace the three columns, so the large percentages fit.

### Match events
- A list in a glass card: minute (Barlow, column 40) · icon · player name, with the assist or who went off in small type under it.
- Home events are aligned left, away events right.
- Icons (SF Symbols, white): goal `soccerball`, substitution `arrow.left.arrow.right`. A card is the rectangle from §3.3.

### Match statistics
A row: home value · name · away value. Under it a thin 4 pt bar: the hosts' share white, the guests' white 30 %.

### Team and player
- **Team**: header (crest 72, name), the squad by position, with rows of photo 36, name and number (Barlow) on the right. Below are the sections "Recent matches" and "Upcoming".
- **Player**: photo 96, name, club crest 24 and club name. Facts are "label / value" pairs in a glass card: number, position, age, country. Season statistics: goals, assists, cards, rating.

### Search
- A custom expanding glass field (`SearchPanel`) at the top of root screens. The query is sent 300 ms after the last keystroke, from 2 characters.
- While nothing is typed, a "Latest" section of three real cards (`/search/suggestions`): the match of the moment (a live one, otherwise from the last two days: European cups and national teams above leagues, by rank, then the latest), the club that leads or won it, and the player with the best rating in that match. Each opens its own screen. The data is fetched afresh each time the field opens.
- Results are the sections Competitions, Teams, Matches, Players: logo or photo + name + a secondary line (club).

### Loading, empty, error
- Loading is a skeleton in the shape of the future data, with no spinners. Bars and circles are white 8 % (`Color.skeleton`) inside the same glass cards, with a soft highlight passing over them from top to bottom (`shimmer()`, 1.4 s; with "Reduce Motion", no highlight). The match has its own skeleton (`MatchSkeleton`: tournament line, score card, form, tabs, rows), as do the player and club (`ProfileSkeleton`), the table (`TableSkeleton`), matchdays and search suggestions (`MatchListSkeleton`, `SkeletonMatchRow`), and the tournament list; the match feed uses its own layout with `.redacted` and the highlight. Everything else is a default card of rows in `Loader`. VoiceOver reads "Loading".
- Empty (`EmptyState`): in a glass card, an empty mini pitch lying sideways: the same `PitchMarkings` layout as in lineups, lines white 35 % fading to the edges with a radial mask. In the centre circle is a ball (`soccerball`, 16 pt, `textSecondary`). Under the pitch is one `textSecondary` line, for example "No events yet". The drawing is vector and hidden from VoiceOver. It does not replace the real images of §7, it is an illustration.
- Error (`ErrorState`): in a glass card, a vector "shot hits the post" scene: a goal with a net (frame white 60 %, 2.5 pt; net 12 %), a dashed ball flight path, sparks at the point of impact, the ball (`soccerball`, 16, `textSecondary`) flies off to the upper right; the edges fade with a radial mask, as in the empty pitch. Under it is "Couldn’t load" (`subheadline` semibold, `textPrimary`), the hint "Check your connection and try again." (`footnote`, `textSecondary`) and a glass button "Try again". The drawing is hidden from VoiceOver.

## 9. Motion

- Durations 150–300 ms. Spring only on buttons.
- No more than 1–2 elements animate on a screen.
- An endless animation is allowed only for the loading skeleton highlight (and it is turned off with "Reduce Motion"). The live dot does not pulse.
- `accessibilityReduceMotion` is checked everywhere there is scaling or movement.

## 10. Forbidden (summary)

- Blue-violet and any coloured gradients, coloured backgrounds and neon.
- Emoji anywhere in the interface.
- Chips, badges, tags and plates next to the text in cards.
- Invented or generated crests, initials instead of a crest, placeholder pictures.
- Textures, noise, "leather", "metal".
- Glass on glass. Text with contrast below 4.5:1.

## 11. Checklist before a screen is done

- [ ] Only grey, white, the functional marks from §3.3 and the logos themselves; no coloured gradients.
- [ ] No emoji and no chips; the status is plain text.
- [ ] All crests, logos and photos come from API URLs; if loading fails, an empty circle remains.
- [ ] Touch targets ≥ 44 pt, gap between them ≥ 8 pt.
- [ ] Dynamic Type up to XXL: nothing is truncated, lines wrap.
- [ ] "Reduce Transparency" on: the glass is solid, the text is readable.
- [ ] "Reduce Motion" on: no scaling and no sliding.
- [ ] Logos and match rows have an `accessibilityLabel`.
- [ ] Live figures are monospaced and do not jitter the row.
