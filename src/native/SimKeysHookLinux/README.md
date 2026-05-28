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
`nwn` wrapper.

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
