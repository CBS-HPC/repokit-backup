# Security Policy

## Supported Versions

Security fixes are applied to the current 1.x release line. The historical
0.x line is unsupported.

| Version | Supported |
| --- | --- |
| 1.x | Yes |
| 0.x | No |

## Reporting A Vulnerability

Do not report suspected vulnerabilities in public GitHub issues. Report them
privately to the CBS-HPC maintainers using the security contact documented by
the organization, including:

- affected repokit-backup version and operating system
- minimal reproduction steps
- potential impact and any proof of concept
- whether credentials, remote files, or arbitrary local paths are involved

Maintainers will acknowledge the report, assess impact, and coordinate a fix
before public disclosure.

## Credential Handling

repokit-backup can persist rclone configuration, OAuth tokens, S3 credentials,
and SSH-related settings below a project root. Treat these as secrets.

- Run `repokit-backup init`; it adds `.env` and `bin/` to `.gitignore`.
- Never commit `bin/rclone.conf`, `bin/rclone_ucloud.conf`,
  `bin/rclone_remote.json`, or a project `.env` file.
- Use `--token-file`, `--lumio-secret-file`, and `--erda-password-file` for
  automation rather than placing secrets directly in shell history.
- Restrict filesystem access to the project runtime directory and rotate a
  credential if it is copied to logs, Git history, or a shared archive.
- Review a remote path before using `--on-existing overwrite`; this option can
  delete remote content.

## Supply-Chain Controls

When rclone is not already installed, repokit-backup downloads a pinned rclone
1.73.2 release archive over HTTPS and verifies its SHA-256 checksum before
extracting it. System-provided rclone installations are intentionally trusted
as part of the local environment; organizations that need stricter control
should install and manage rclone themselves.
