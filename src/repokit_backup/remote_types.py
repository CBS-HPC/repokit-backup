"""Remote type detection and normalization."""


def _detect_remote_type(remote_name: str) -> str:
    remote_lower = remote_name.lower()
    known_types = [
        "dropbox",
        "onedrive",
        "googledrive",
        "gdrive",
        "erda",
        "ucloud",
        "lumi",
        "local",
        "s3",
        "sftp",
    ]
    for remote_type in known_types:
        if remote_lower.startswith(remote_type):
            if remote_type in ["googledrive", "gdrive"]:
                return "drive"
            return remote_type
    return "sftp"


def _get_base_remote_type(remote_name: str) -> str:
    remote_type = _detect_remote_type(remote_name)
    type_mapping = {
        "erda": "sftp",
        "ucloud": "sftp",
        "googledrive": "drive",
        "gdrive": "drive",
    }
    return type_mapping.get(remote_type, remote_type)

