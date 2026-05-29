# SimKeysHookLinux

HGCC preload hook for the 32-bit NWN 1.69 Linux client.

## Build

On a Linux system with a 32-bit C++ toolchain installed:

```bash
sudo apt install g++-multilib
./src/native/SimKeysHookLinux/build.sh
```

The build output is `src/native/SimKeysHookLinux/libSimKeysHookLinux.so`, and the runtime copy is `bin/libSimKeysHookLinux.so`.
OpenGL/X11 symbols are resolved from the running client with `dlsym`, so the
hook does not link against development GL/X11 libraries.

## Launch

Start the client through the repo launcher so `nwmain` receives `LD_PRELOAD`:

```bash
./simkeys_linux_client.sh --client-dir /path/to/English_linuxclient_xp2
```

Use an existing working Linux NWN client. The launcher adds the client's `lib`,
`miles_linux`, `miles`, and root directories to `LD_LIBRARY_PATH` when they
exist, and sets the same SDL mouse compatibility flags used by the original
`nwn` wrapper. Pass `--system-sdl` to skip the bundled `lib` directory when a
client should use the distro SDL library.

Useful options:

```bash
./simkeys_linux_client.sh --client-dir /path/to/client --spawn
./simkeys_linux_client.sh --client-dir /path/to/client --system-sdl
./simkeys_linux_client.sh --client-dir /path/to/client --socket-dir /tmp/hgcc-test --dry-run
./simkeys_linux_client.sh --client-dir /path/to/client -- --user-arg passed-to-nwmain
```

Set `SIMKEYS_LINUX_LOG_LEVEL=2` before launching for debug socket/protocol logs.
Linux overlay requests are accepted for GUI compatibility, but in-client OpenGL
overlay drawing is disabled by default because some X11/GL stacks terminate the
client on overlay setup. Set `SIMKEYS_LINUX_ENABLE_OVERLAY=1` before launching
to opt in to Linux overlay rendering.

Quickbar and chat inline trace detours are disabled by default. The socket
command path can discover the quickbar panel on demand and falls back to SDL
key events when direct internal quickbar calls are unsafe. Set
`SIMKEYS_LINUX_ENABLE_QUICKBAR_TRACE=1` or `SIMKEYS_LINUX_ENABLE_CHAT_TRACE=1`
only when passive quickbar/chat capture is needed on a client stack known to
tolerate those detours.

The hook exposes the same HGCC opcode protocol as the Windows DLL, but over
`simkeys_<pid>.sock` in `SIMKEYS_LINUX_SOCKET_DIR`, `$XDG_RUNTIME_DIR/hgcc`, or
`/tmp/hgcc-<uid>`.
