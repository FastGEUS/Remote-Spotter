# Remote Spotter

**Language / Язык:** [Русский](README.md) | **English**

**Public beta · source code for self-hosting**

**Remote pit wall for iRacing and Le Mans Ultimate · by Svet**

Remote Spotter helps a driver and a spotter work together from different
networks. The driver runs a small application, while the spotter views a racing
dashboard in a separate window: standings, car condition, fuel, flags, and
available session data. You can watch the driver's screen share in Discord
at the same time.

## How it works

1. The driver application reads telemetry from the running game through shared memory / the SDK and sends raw data to your VPS.
2. The VPS receives the data, performs calculations, and provides the results to the spotter dashboard.
3. The spotter application displays the web interface inside its own window.
4. Both applications automatically establish SSH tunnels to the server. This setup does not require a domain name.

The driver's computer handles reading, packing, and transmitting data;
calculations run on the server. The interface is rendered on the spotter's
computer. The application does not transmit video or replace Discord.

## Current features

- Minimal driver window: connection, game status, and spotter presence.
- Spotter dashboard with a track map, standings, flags, fuel, and car condition.
- Sector data and comparisons where supported by the data source.
- Reconnection, diagnostics, and automatic preparation of SSH private key permissions on Windows.
- Driver and spotter applications can run simultaneously on the same PC.

This project is still under development. Data availability depends on the game.
The dashboard catalog contains 76 cards, but this does not mean that every
TinyPedal feature has been ported or works identically in both games. In iRacing,
some tire data is available as pit snapshots, the track map is reconstructed
approximately, and a proximity indicator is used instead of an exact opponent
radar. iRacing sector times are estimates; local yellow flags are not mapped
to individual sectors.

Current versions: Windows clients **0.6.7**, server **0.4.7**. The server supports
one driver–spotter pair / one room. A service for multiple independent teams,
user accounts, and a complete catalog of track maps have not been implemented.

## What you need to set up yourself

1. Prepare both participants' computers and install the required Windows components.
2. Rent or use your own Linux VPS and configure access to it.
3. Create separate SSH keys and configure permissions for the applications to connect.
4. Build the server component, deploy it to the VPS, and start the service.
5. Obtain separate application access tokens for the driver and the spotter.
6. Build the Windows applications from source and give each participant their application folder.
7. Configure your server address, the appropriate SSH key, and the access token for each role.
8. Test the connection and telemetry in a practice session before a race.

General requirements: Windows x64 for clients, Python 3.11–3.13 x64 to build
them, OpenSSH Client for connections, Linux/Python for the VPS, and Go 1.24
or newer to build the server. Python does not need to be installed to run
the built EXE applications. A detailed beginner's guide with commands and
troubleshooting is being prepared for Boosty. A link will be added after
publication.

The source code is openly available. The paid material is an optional guide
to setting up the application yourself; purchasing it is not required to use
the code. VPS rental and access to the game are separate costs. The public
version does not include access to the developer's server.

## Source code and credits

`remote/` contains telemetry capture, game adapters, server calculations, and
the client GUIs; `relay/` contains the Go server and web dashboard; `deploy/`
contains build and deployment scripts. TinyPedal sources and the shared memory
libraries used by the project are included in the repository. Public source
code does not include personal access tokens, SSH keys, or configured access
profiles. Public clients display a setup form on their first launch.

The project is based on [TinyPedal](https://github.com/TinyPedal/TinyPedal),
version v2.50.0, commit `b6ef05a695686cd18e0b807cd8933fd91e813ad5`.
[pyirsdk](https://github.com/kutu/pyirsdk) is used for iRacing.
Source versions are recorded in `remote/upstream-lock.json`.
The original TinyPedal description is preserved in `UPSTREAM_README.md`.

Remote Spotter's remote connection, GUI, and dashboard development — **Svet**.
TinyPedal authors and third-party library authors retain credit for their
components. The main project is distributed under [GNU GPLv3](LICENSE.txt);
dependency licenses are preserved in the source and build materials.

The Windows EXE applications do not yet have a trusted digital signature:
SmartScreen may warn about an unknown publisher. Do not publish private keys,
access tokens, personal builds, or logs containing credentials in a public
repository.

## Feedback

Report bugs and suggest improvements through [GitHub Issues](https://github.com/FastGEUS/Remote-Spotter/issues).
Include the game, client and server versions, Windows version, and steps to
reproduce the problem. Remove access tokens, keys, and personal information
before attaching logs. Individual installation assistance and ongoing support
are not included with free access to the source code.
