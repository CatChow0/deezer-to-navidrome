"""Finds the audio file behind a track. The routes only ever take a track ID;
every path, wherever it came from, must resolve inside a music folder."""
from pathlib import Path, PurePosixPath

from core import config
from core.stats_import import library_paths


def _roots() -> list:
    scan_dirs, _, _, _ = config.get_paths_from_config()
    return [root.resolve() for root in scan_dirs]


def inside_music_folders(path):
    """The real path if it is a file inside a music folder, else None."""
    try:
        real = Path(path).resolve()
        if real.is_file() and any(real.is_relative_to(root) for root in _roots()):
            return real
    except (OSError, ValueError, RuntimeError):
        pass
    return None


def local_file(track):
    """`track` needs `key` and `file_path`. Files move, so the library index is
    asked when the stored path no longer leads anywhere."""
    for candidate in (track["file_path"], library_paths().get(track["key"])):
        if candidate:
            found = inside_music_folders(candidate)
            if found:
                return found
    return None


def container_path(library_root, relative, mappings=None):
    """Navidrome's library folder and file path, as a path in this container."""
    if not relative or not library_root or ".." in PurePosixPath(relative).parts:
        return None
    wanted = PurePosixPath(library_root, relative)
    if mappings is None:
        _, _, _, mappings = config.get_paths_from_config()
    for host, navidrome in mappings.items():
        base = PurePosixPath(navidrome.as_posix())
        if wanted.is_relative_to(base):
            return str(host.joinpath(*wanted.relative_to(base).parts))
    return None
