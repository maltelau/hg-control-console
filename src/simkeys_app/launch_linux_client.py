import argparse
import os
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
    from simkeys_app import simKeys_Client as simkeys
    from simkeys_app import simkeys_runtime as runtime
else:
    from . import simKeys_Client as simkeys
    from . import simkeys_runtime as runtime


def _split_client_args(args):
    if args and args[0] == "--":
        return args[1:]
    return args


def _prepend_env_path(existing, value):
    if not existing:
        return value
    return f"{value}:{existing}"


def _client_library_dirs(client_dir):
    if not client_dir:
        return []
    candidates = [
        os.path.join(client_dir, "lib"),
        os.path.join(client_dir, "miles_linux"),
        os.path.join(client_dir, "miles"),
        client_dir,
    ]
    return [path for path in candidates if os.path.isdir(path)]


def build_launch_environment(hook_path, socket_dir=None, log_dir=None, client_dir=None):
    env = os.environ.copy()
    env["LD_PRELOAD"] = _prepend_env_path(env.get("LD_PRELOAD", ""), hook_path)
    env.setdefault("SDL_MOUSE_RELATIVE", "0")
    env.setdefault("SDL_VIDEO_X11_DGAMOUSE", "0")

    if socket_dir is None:
        socket_dir = simkeys.default_linux_socket_dir()
    os.makedirs(socket_dir, mode=0o700, exist_ok=True)
    env["SIMKEYS_LINUX_SOCKET_DIR"] = socket_dir

    if log_dir:
        os.makedirs(log_dir, mode=0o700, exist_ok=True)
        env["SIMKEYS_LINUX_LOG_DIR"] = log_dir

    for library_dir in reversed(_client_library_dirs(client_dir)):
        env["LD_LIBRARY_PATH"] = _prepend_env_path(env.get("LD_LIBRARY_PATH", ""), library_dir)

    return env


def resolve_nwmain(client_dir, nwmain):
    if os.path.isabs(nwmain):
        return nwmain
    return os.path.abspath(os.path.join(client_dir, nwmain))


def build_parser():
    parser = argparse.ArgumentParser(description="Launch the 32-bit NWN 1.69 Linux client with the HGCC preload hook.")
    parser.add_argument("--client-dir", default=os.getcwd(), help="Directory containing nwmain. Default: current directory.")
    parser.add_argument("--nwmain", default="nwmain", help="nwmain executable path or name. Default: nwmain")
    parser.add_argument("--hook", default=runtime.default_dll_path(), help="Path to libSimKeysHookLinux.so.")
    parser.add_argument("--socket-dir", help="Directory for simkeys_<pid>.sock. Default: XDG_RUNTIME_DIR/hgcc or /tmp/hgcc-uid.")
    parser.add_argument("--log-dir", help="Directory for SimKeysHookLinux_<pid>.log.")
    parser.add_argument("--spawn", action="store_true", help="Spawn nwmain and print its pid instead of replacing this process.")
    parser.add_argument("--dry-run", action="store_true", help="Print the command and environment paths without launching.")
    parser.add_argument("client_args", nargs=argparse.REMAINDER, help="Arguments passed to nwmain. Prefix with -- when needed.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client_dir = os.path.abspath(args.client_dir)
    nwmain = resolve_nwmain(client_dir, args.nwmain)
    hook = os.path.abspath(args.hook)
    client_args = _split_client_args(args.client_args)

    if not os.path.isfile(nwmain):
        raise SystemExit(f"nwmain was not found: {nwmain}")
    if not os.path.isfile(hook):
        raise SystemExit(f"HGCC Linux hook was not found: {hook}")

    env = build_launch_environment(hook, socket_dir=args.socket_dir, log_dir=args.log_dir, client_dir=client_dir)
    command = [nwmain, *client_args]

    if args.dry_run:
        print(f"cwd={client_dir}")
        print(f"LD_PRELOAD={env.get('LD_PRELOAD', '')}")
        print(f"SIMKEYS_LINUX_SOCKET_DIR={env.get('SIMKEYS_LINUX_SOCKET_DIR', '')}")
        if env.get("SIMKEYS_LINUX_LOG_DIR"):
            print(f"SIMKEYS_LINUX_LOG_DIR={env['SIMKEYS_LINUX_LOG_DIR']}")
        print(f"LD_LIBRARY_PATH={env.get('LD_LIBRARY_PATH', '')}")
        print(f"SDL_MOUSE_RELATIVE={env.get('SDL_MOUSE_RELATIVE', '')}")
        print(f"SDL_VIDEO_X11_DGAMOUSE={env.get('SDL_VIDEO_X11_DGAMOUSE', '')}")
        print("command=" + " ".join(command))
        return 0

    if args.spawn:
        child = subprocess.Popen(
            command,
            cwd=client_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(child.pid)
        return 0

    os.chdir(client_dir)
    os.execvpe(command[0], command, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
