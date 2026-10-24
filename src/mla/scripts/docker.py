import getpass
import grp
import shutil

from ..package_manager import run_privileged


def post_install() -> int:
    """Enable the docker service and let the current user run docker without sudo."""
    user = getpass.getuser()
    if not shutil.which("systemctl"):
        print("systemctl not found; start the docker daemon manually.")
    elif run_privileged(["systemctl", "enable", "--now", "docker.service"]) != 0:
        print("Could not enable docker.service.")
        return 1

    try:
        grp.getgrnam("docker")
    except KeyError:
        if run_privileged(["groupadd", "docker"]) != 0:
            return 1

    if run_privileged(["usermod", "-aG", "docker", user]) != 0:
        return 1
    print(f"Docker is ready. Log out and back in (or run `newgrp docker`) so {user} can use it without sudo.")
    return 0
