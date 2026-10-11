# BUTTON

**Broadcast automation for community radio stations.** BUTTON keeps a station on air around the clock: music rotation, station imaging, recorded shows, relays and live shows. A web console lets the team run the antenna without knowing the machinery.

[Version française](README.md) · [Documentation (in French)](docs/README.md) · License [AGPL-3.0-or-later](LICENSE)

> **Young project.** BUTTON runs the antenna of the BUTTON radio station. The API, the deployment and the configuration may still change between versions.

## What it does

- **A schedule that runs itself.** Clocks chain music, jingles, sounds and ads, with hard or soft anchors on the minute. A weekly grid picks the clock for each time slot.
- **A varied auto-DJ.** Music comes from a [Beets](https://beets.io/) library, with artist and title separation rules and loudness normalisation (ReplayGain).
- **Live shows without fiddling.** Hosts plug in their encoder (BUTT, Mixxx…) and take the air. A named host may only connect during their own slot, and the schedule resumes by itself afterwards.
- **Relays and hand-overs** with other stations.
- **A web console** for day-to-day on-air work (queue, library, idents, going live), the rundown, programming, sounds and accounts. It works on phones, in light or dark mode.
- **Music uploads from the browser**, resumable, or through a plain shared folder.
- **A monitored antenna**: alerts on silence, unreachable playout or missing live show, metrics and backups.

## How it is built

The engine is a fork of [Radiotomate](https://radiotomate.org/) by Martin Kirchgessner: Python (Quart, SQLAlchemy, Beets) for scheduling, [Liquidsoap](https://www.liquidsoap.info/) for audio. The console is a React application. Around them sit small services: the sound bank catalogue (Meilisearch), now-playing metadata, and Icecast. Everything is deployed with Docker Compose.

See [docs/architecture.md](docs/architecture.md) (in French).

## Getting started

**Install a station**:

```bash
git clone https://github.com/lazbutton/button.git
cd button/deploy
cp .env.example .env      # then replace every "change-me"
docker compose up -d
```

Next steps: [docs/deploiement.md](docs/deploiement.md).

**Develop**: the local bench runs the engine in demo mode next to the console. See [docs/developpement.md](docs/developpement.md).

```bash
./scripts/dev.sh          # engine on :6811, console on :5175
```

## Repository layout

| Folder | Contents |
|---|---|
| [`engine/`](engine/) | The engine (Radiotomate fork) and its Liquidsoap script |
| [`console/`](console/) | The web console (React) |
| [`services/`](services/) | Catalogue, now playing, Icecast |
| [`deploy/`](deploy/) | Station Compose file, init scripts, local audio bench |
| [`docs/`](docs/) | Documentation (in French) |
| [`scripts/`](scripts/) | Development tools |

## Contributing

Contributions are welcome: bug reports, fixes, translations, documentation. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first, and [SECURITY.md](SECURITY.md) to report a vulnerability. The project follows a [code of conduct](CODE_OF_CONDUCT.md). The user interface and documentation are in French; issues and pull requests in English are fine.

## License and credits

BUTTON is released under the [GNU Affero General Public License v3.0 or later](LICENSE). If you run a modified version for other people, for instance by hosting a station, you must give them access to its source code.

The engine derives from [Radiotomate](https://git.sr.ht/~martink/radiotomate), written by Martin Kirchgessner. Authors and bundled assets: [AUTHORS.md](AUTHORS.md).
