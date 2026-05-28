# NWN Linux Client 1.69 Hook Landmarks

Verified on 2026-05-28 against:

- Linux client: `H:\My Drive\Codex Projects\NWN Linux\English_linuxclient169_xp2.tar\English_linuxclient_xp2\nwmain`
- Diamond reference: `H:\My Drive\Codex Projects\NWN EE Bridge\NWN Diamond\nwmain.exe`

Use `tools/match_linux_client.py` to re-check these anchors before enabling a
Linux hook build:

```powershell
python tools\match_linux_client.py
```

## Binary Shape

The Linux client is a 32-bit, little-endian, non-PIE ELF executable.

| Section | VA | File offset | Size |
| --- | ---: | ---: | ---: |
| `.text` | `0x0804F830` | `0x00007830` | `0x005A4E20` |
| `.rodata` | `0x085F4680` | `0x005AC680` | `0x00036A4F` |
| `.data` | `0x0862C0E0` | `0x005E30E0` | `0x0001D3A0` |
| `.bss` | `0x087AB380` | `0x00762380` | `0x05907520` |

Because the executable is non-PIE, absolute addresses are usable in the same
style as the Diamond hook after validating the exact binary.

## Confirmed Linux Targets

| Purpose | Diamond analog | Linux VA | Evidence |
| --- | ---: | ---: | --- |
| App global slot | `0x0092DC50` | `0x0862C354` | Frequent absolute references in `.text` |
| Quickbar constructor/layout anchor | `0x008AB6D0` vtable area | `0x080D6538` | Writes `0x0862F900` to `panel+0x20`; slots start at `+0x74`; slot stride is `0x184` |
| Quickbar execute | `0x0051FAA0` | `0x080D9C80` | Computes `slot * 0x184 + panel + 0x74`; tail-jumps to slot dispatch |
| Quickbar slot dispatch | `0x005164A0` | `0x080D7DC4` | Checks `panel+0x3708`; reads slot type from `slot+0xA0`; switch table `0x085F8F80` |
| Chat send/parser | `0x0057C9F0` | `0x08265054` | References `"**Console**: "` and the `tellplayer` command path |
| Chat window log | `0x00493BD0` | `0x080B89F0` | References `"[CHAT WINDOW TEXT] [%s] %s"` |
| Current-player resolver | `0x00407850` | `0x08076A9C` | Uses app object `+0x24` as the active player object id |
| Current GUI resolver | n/a helper | `0x08077008` | Returns app object `+0x48` |
| Server object-by-id resolver | `0x005FFAA0` | `0x082AA024` | Wrapper family for server object lookup |

Important quickbar layout difference from Windows:

| Field | Diamond | Linux |
| --- | ---: | ---: |
| Panel vtable check | `panel+0x00 == 0x008AB6D0` | `panel+0x20 == 0x0862F900` |
| Slot array offset | `0x68` | `0x74` |
| Slot stride | `0x134` | `0x184` |
| Primary item id offset | `0x50` | `0x6C` |
| Secondary item id offset | `0x54` | `0x70` |
| Slot type offset | `0x84` | `0xA0` |
| Slot count model | 3 banks x 12 slots | 36 contiguous slots |

The Linux hook uses a separate scanner with these offsets. Equipped-item owner
resolution still needs live validation before exposing a non-zero equipped mask.

## Movement Candidate

The movement path is located, but should stay guarded until tested in-client:

| Purpose | Diamond analog | Linux candidate | Evidence |
| --- | ---: | ---: | --- |
| Walk-to-waypoint path | `0x00407D70` | `0x0807E41C` | References `gui_walkto`, `gui_nowalk`, and `"Client calls walktowaypoint %d"` |
| No-walk block | `0x0042A7AB` | `0x0807E84A` | Logs/calls `gui_nowalk`, returns zero |
| No-walk bypass target | `0x0042A7D2` | `0x0807E878` | Continues into the normal movement path after the no-walk return |

This maps cleanly to the Windows bypass shape, but patching it should be
validated with a live Linux hook and a rollback path.

## Linux Hook Implementation

The Windows hook cannot be reused directly. Linux support now has a separate
32-bit preload hook and runtime backend:

- Native hook: `src/native/SimKeysHookLinux/SimKeysHookLinux.cpp`
- Build wrappers: `src/native/SimKeysHookLinux/build.sh` and
  `src/native/SimKeysHookLinux/build.ps1`
- Client launcher: `simkeys_linux_client.sh` or
  `src/simkeys_app/launch_linux_client.py`
- IPC: Unix domain socket named `simkeys_<pid>.sock`
- Thread dispatch: queued HGCC commands drain from `SDL_GL_SwapBuffers` and
  `SDL_PollEvent`, replacing the Windows `WndProc` dispatch path.
- Overlay: OpenGL/X11 text rendering from the SDL swap hook. The hook resolves
  those symbols dynamically from the loaded client libraries.

The Windows cross-build path uses Zig:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\src\native\SimKeysHookLinux\build.ps1
```

The produced hook is an ELF32 i386 shared object with only `libc.so.6` as a
declared dynamic dependency.

Already-running Linux clients are not injected. Launch `nwmain` with
`LD_PRELOAD=libSimKeysHookLinux.so` through the launcher so HGCC can discover
and control it.

The Linux launcher mirrors the original `nwn` wrapper enough for the legacy
client to start under WSLg: it prepends `lib`, `miles_linux`, `miles`, and the
client directory to `LD_LIBRARY_PATH` when present, and sets
`SDL_MOUSE_RELATIVE=0` plus `SDL_VIDEO_X11_DGAMOUSE=0`. This matters because
`nwmain` depends on the game-supplied Miles library `libmss.so.6` and, in the
classic package layout, the bundled SDL library under `lib`.

The stripped XP2 client archive used for address matching does not include a
complete runnable tree. A Reddit-style layered install was validated in WSL:
Gold Linux client, HOTU Linux client, local 1.69 XP2 archive, then
`./fixinstall`. That produced `miles/libmss.so.6`, `lib/libSDL-1.2.so.0`, and a
working `nwn` wrapper. With the HGCC launcher and preload hook, the client
starts, creates `simkeys_<pid>.sock`, lists as injected, and responds to query,
chat-poll, overlay, quickbar, chat-send, movement, walk-bypass, and action-mode
opcodes. In-game-only commands return controlled not-ready/timeout responses at
the main menu.

Remaining validation work:

- Validation: run `tools/match_linux_client.py` at startup or build time and
  refuse to enable hard-coded addresses if any confirmed anchor fails.
- Movement uses the mapped `0x0807E41C` walk-to-waypoint candidate and the
  `0x0807E84A -> 0x0807E878` no-walk bypass patch. Keep this guarded until it
  is live-tested after logging into a character in the Linux client.
