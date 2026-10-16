# KickPick iOS app

The SwiftUI client: scores, tables, matches, teams and players from the KickPick API, in a dark frosted-glass
design. For whoever builds, runs or changes the app.

## Requirements

- Xcode 26 and [XcodeGen](https://github.com/yonaskolb/XcodeGen)
- iOS 17 or later, iPhone only, portrait, dark appearance
- A running backend (see [backend/README.md](../backend/README.md))

## Running

```bash
cd ios && xcodegen && open KickPick.xcodeproj
```

The `.xcodeproj` is generated from `project.yml` and is not in git: change settings in `project.yml`, then run
`xcodegen` again.

### API

The app talks to the deployed API at `https://kickpick.vokh.dev` (`API_BASE_URL` in `project.yml`), on the simulator
and on a real iPhone. Set `DEVELOPMENT_TEAM` in `project.yml` to your signing team to run on a device.

To use a local backend in the simulator, set `API_BASE_URL` to `http://localhost:8000` and run `xcodegen` again.

## Project structure

| Folder | Contents |
|---|---|
| `KickPick/App` | App entry, tab bar, splash screen |
| `KickPick/API` | `APIClient` and the `Codable` models |
| `KickPick/Design` | Design system in code: tokens, glass, buttons, segmented picker, states and skeletons |
| `KickPick/Features` | Screens: Matches, Competitions, Teams (club, national team, player), Search, shared loaders and rows |
| `KickPick/Resources` | Fonts (Barlow Condensed for numbers) |
| `KickPickTests` | Unit tests |

The rules every screen follows are in [design.md](../design.md); code comments cite its sections (for example
"design.md §6.3").

## Behaviour worth knowing

- Screens load through `Loader`: cached data shows at once, a skeleton shimmer shows otherwise, and live screens poll
  every 15 seconds.
- The API answers `429` with `Retry-After` when rate-limited; the client waits and retries once.
- The matches feed keeps neighbouring days cached and prefetched, so swiping between days is seamless.

## Testing

```bash
xcodebuild test -project KickPick.xcodeproj -scheme KickPick \
  -destination 'platform=iOS Simulator,name=iPhone 17'
```
