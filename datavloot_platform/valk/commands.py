"""
`datavloot valk ...`: fetch the pinned SRDP checkout and drive docker compose.

Every subprocess here is printed before it runs, so the operator can repeat it
by hand. That matters more than usual because the stack is SRDP's: when something
in it misbehaves, the fix is usually in their runbook, not ours.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

from datavloot_platform.valk import render as render_mod
from datavloot_platform.vessel import VesselConfig, VesselConfigError, load_vessel


def _run(cmd: list[str], *, cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check)


def _require(tool: str, hint: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"Error: `{tool}` was not found on PATH. {hint}")
    return path


def load_valk(project: str | None) -> VesselConfig:
    try:
        config = load_vessel(pathlib.Path(project).resolve() if project else None)
    except VesselConfigError as exc:
        sys.exit(f"Error: {exc}")
    if not config.is_valk:
        sys.exit(
            "Error: this project sails as the Optimist. Set `vessel: valk` in datavloot.yml "
            "(and fill in the `valk:` block) first. See docs/valk.md."
        )
    return config


# ---------------------------------------------------------------------------

def cmd_render(config: VesselConfig, *, datavloot_source: str | None) -> None:
    result = render_mod.render(config, datavloot_source=datavloot_source)
    rel = lambda p: p.relative_to(config.project_dir).as_posix()  # noqa: E731
    print(f"Rendered the Valk for '{config.name}' at {rel(result.valk_dir)}/")
    for path in result.written:
        print(f"  wrote    {rel(path)}")
    for path in result.skipped:
        print(f"  kept     {rel(path)}  (has secrets; delete it to regenerate)")
    for warning in result.warnings:
        print(f"  WARNING  {warning}")
    print()
    print("Next: datavloot valk fetch && datavloot valk certs && datavloot valk up")
    print(f"Then read {rel(result.valk_dir)}/README.md for the one-time Zitadel step.")


def cmd_fetch(config: VesselConfig) -> None:
    """Check SRDP out at the pinned commit into <project>/.srdp (shallow, exact SHA)."""
    _require("git", "Install git to fetch the SRDP stack.")
    valk = config.valk
    assert valk is not None
    dest = render_mod.srdp_dir(config)

    if (dest / ".git").is_dir():
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True, check=False
        ).stdout.strip()
        if head == valk.srdp_ref:
            print(f"SRDP already at {valk.srdp_ref[:12]} in {dest}")
            return
        print(f"SRDP checkout is at {head[:12]}, pin is {valk.srdp_ref[:12]}; updating.")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        _run(["git", "init", "-q"], cwd=dest)
        _run(["git", "remote", "add", "origin", valk.srdp_repo], cwd=dest)

    # A shallow fetch of one commit: the pin is a SHA, and `clone --depth 1` can
    # only take a branch or tag.
    _run(["git", "fetch", "-q", "--depth", "1", "origin", valk.srdp_ref], cwd=dest)
    _run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=dest)
    print(f"SRDP {valk.srdp_ref[:12]} checked out in {dest}")


def cmd_certs(config: VesselConfig) -> None:
    """
    mkcert certificates for every hostname, where SRDP's compose expects them.

    SRDP's Zitadel runs TLS itself and reads these files even behind Let's Encrypt,
    so this step is needed in both local and prod modes.
    """
    mkcert = _require("mkcert", "See https://github.com/FiloSottile/mkcert; run `mkcert -install` once.")
    valk = config.valk
    assert valk is not None
    certs = render_mod.srdp_dir(config) / "deploy" / "docker" / "certs"
    if not certs.parent.is_dir():
        sys.exit("Error: SRDP is not checked out yet. Run `datavloot valk fetch` first.")
    certs.mkdir(parents=True, exist_ok=True)
    hosts = [valk.host(h) for h in render_mod.HOSTS]
    _run([mkcert, "-cert-file", str(certs / "selfsigned.crt"), "-key-file", str(certs / "selfsigned.key"), *hosts])


def compose_command(config: VesselConfig, *args: str, prod: bool = False) -> list[str]:
    """The full `docker compose` invocation, both stacks layered, our .env in charge."""
    files = render_mod.compose_files(config, prod=prod)
    project_dir = render_mod.srdp_dir(config) / "deploy" / "docker"
    env_file = config.project_dir / render_mod.VALK_DIRNAME / ".env"
    cmd = ["docker", "compose", "--project-directory", str(project_dir), "--env-file", str(env_file)]
    for f in files:
        cmd += ["-f", str(f)]
    cmd += list(args)
    return cmd


def _preflight(config: VesselConfig, *, prod: bool) -> None:
    _require("docker", "Install Docker Engine or Docker Desktop.")
    missing = [f for f in render_mod.compose_files(config, prod=prod) if not f.is_file()]
    if missing:
        sys.exit(
            "Error: missing compose files:\n  "
            + "\n  ".join(str(m) for m in missing)
            + "\nRun `datavloot valk render` and `datavloot valk fetch` first."
        )
    env_file = config.project_dir / render_mod.VALK_DIRNAME / ".env"
    if not env_file.is_file():
        sys.exit(f"Error: {env_file} is missing. Run `datavloot valk render`.")


def cmd_up(config: VesselConfig, *, prod: bool, build: bool) -> None:
    _preflight(config, prod=prod)
    args = ["up", "-d"] + (["--build"] if build else [])
    _run(compose_command(config, *args, prod=prod))
    valk = config.valk
    assert valk is not None
    print()
    print("Stack is starting. Services:")
    for host in render_mod.HOSTS:
        print(f"  https://{valk.host(host)}")
    print()
    print("First boot: create the Zitadel OIDC application and paste its client id/secret")
    print(f"into deploy/valk/.env, then run `datavloot valk up` again. Runbook: deploy/valk/README.md")


def cmd_down(config: VesselConfig, *, prod: bool) -> None:
    _preflight(config, prod=prod)
    _run(compose_command(config, "down", prod=prod))


def cmd_compose(config: VesselConfig, extra: list[str], *, prod: bool) -> None:
    """Pass-through: `datavloot valk compose logs -f crowsnest`."""
    _preflight(config, prod=prod)
    _run(compose_command(config, *extra, prod=prod), check=False)
