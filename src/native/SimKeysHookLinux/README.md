# SimKeysHookLinux

HGCC preload hook for the 32-bit NWN 1.69 Linux client.

## Build

From Windows, install Zig and cross-compile the 32-bit Linux shared object:

```powershell
winget install -e --id zig.zig --scope user
powershell -NoProfile -ExecutionPolicy Bypass -File .\src\native\SimKeysHookLinux\build.ps1
```

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

The launcher adds the client's `lib`, `miles_linux`, `miles`, and root
directories to `LD_LIBRARY_PATH` when they exist, and sets the same SDL mouse
compatibility flags used by the original `nwn` wrapper. A complete Diamond
Linux install needs the game-supplied Miles library `libmss.so.6`; depending on
the install package, it may be under `miles` or `miles_linux`. That library is
not installed by Ubuntu packages.

The classic client layering is Gold Linux client, HOTU Linux client, then the
1.69 XP2 Linux client, followed by `./fixinstall`. A tree containing only the
XP2 client patch is not enough to run because it lacks `miles/libmss.so.6` and
the bundled SDL library under `lib`.

Useful options:

```bash
./simkeys_linux_client.sh --client-dir /path/to/client --spawn
./simkeys_linux_client.sh --client-dir /path/to/client --socket-dir /tmp/hgcc-test --dry-run
./simkeys_linux_client.sh --client-dir /path/to/client -- --user-arg passed-to-nwmain
```

Set `SIMKEYS_LINUX_LOG_LEVEL=2` before launching for debug socket/protocol logs.

The hook exposes the same HGCC opcode protocol as the Windows DLL, but over
`simkeys_<pid>.sock` in `SIMKEYS_LINUX_SOCKET_DIR`, `$XDG_RUNTIME_DIR/hgcc`, or
`/tmp/hgcc-<uid>`.
