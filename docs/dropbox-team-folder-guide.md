# Dropbox Team Folder Guide

This guide configures a project-local `repokit-backup` environment and pins a
Dropbox Business Team Folder. It uses browser-based OAuth: do not create or
pass a `--token-file`.

The example maps the Dropbox folder
`/Team Folder - (LIB)/taqtrade_dummy` to the alias `taqtrade`.

## Important Dropbox Path Rule

Preserve the leading slash for Dropbox Business Team Folders:

```text
taqtrade:folder     # Personal/member namespace
taqtrade:/folder    # Dropbox team-root namespace
```

Use `/Team Folder - (LIB)/...` unchanged. A saved remote path is an opaque
rclone path; do not strip its leading slash.

## UCloud SSH Prerequisite

Before configuring Dropbox from a UCloud container, verify from the local
machine that SSH reaches the **same active UCloud job**:

```powershell
ssh ucloud@ssh.cloud.sdu.dk -p <job-ssh-port>
```

For example, if the UCloud job is reached on port `2020`:

```powershell
ssh ucloud@ssh.cloud.sdu.dk -p 2020
```

This checks the job-specific host, port, and authentication that the browser
OAuth tunnel will need. The SSH port can change for each UCloud job. Exit the
interactive session after confirming it works; the OAuth tunnel uses a separate
local PowerShell window.

## UCloud Ubuntu Container Setup

Create the project under `/work`, which must be a persistent UCloud location:

```bash
mkdir -p /work/taqtrade-project
cd /work/taqtrade-project
python3 -m venv .venv
source .venv/bin/activate
which python
python -m pip install --upgrade pip
```

`which python` should print:

```text
/work/taqtrade-project/.venv/bin/python
```

Install the packages:

```bash
python -m pip install https://github.com/CBS-HPC/repokit-common/releases/download/v1.0.0/repokit_common-1.0.0-py3-none-any.whl
python -m pip install https://github.com/CBS-HPC/repokit-backup/releases/download/v1.0.0/repokit_backup-1.0.0-py3-none-any.whl
```

Initialize the project:

```bash
repokit-backup init
```

The `.venv`, `bin/rclone.conf`, and `bin/rclone_remote.json` remain available
only while the project directory under `/work` persists. Do not commit the
`bin/` directory: `rclone.conf` contains OAuth credentials.

## Add And Authenticate The Dropbox Remote

Browser OAuth is interactive. Configure the remote first without a mapping,
then pin the Dropbox Team Folder after authentication. This avoids using a
token file and does not save a local source path.

```bash
repokit-backup add --remote taqtrade --backend dropbox --ssh
```

Answer the prompts as follows:

```text
Create a local/remote path mapping now? [Y/n]: n
App port [53682]: <press Enter>
SSH host/user (user@host): ucloud@ssh.cloud.sdu.dk
SSH port [22]: <the SSH port used for this UCloud job, for example 2672>
```

`App port` is the rclone OAuth callback port, not the UCloud SSH port. Leave
it at `53682`: rclone opens its callback server on this port. The SSH port is
entered separately at the final prompt.

The `--ssh` option does not create the tunnel. Keep the UCloud terminal
running while rclone prints its browser URL and waits for authorization. Then,
from a **separate local Windows PowerShell window**, run the printed tunnel
command. For a job reached with `ssh ucloud@ssh.cloud.sdu.dk -p 2672`, this is:

```powershell
ssh -N -L 53682:127.0.0.1:53682 ucloud@ssh.cloud.sdu.dk -p 2672
```

Keep both the UCloud command and this second local PowerShell window running.
The tunnel window normally displays no output. In the local browser, open the
complete `http://127.0.0.1:53682/auth?...` URL printed by rclone. Do not open
only `http://127.0.0.1:53682/`, and do not reuse an OAuth URL after restarting
the `add` command because its `state` value changes.

The `Failed to open browser automatically` message in the UCloud terminal is
expected because the container has no graphical browser. It is not an OAuth
failure.

The browser login automatically saves the Dropbox OAuth token in the
project-local `bin/rclone.conf`; no `--token-file` is needed.

After the OAuth flow completes, pin the Team Folder non-interactively:

```bash
repokit-backup pin \
  --remote taqtrade \
  --remote-path "/Team Folder - (LIB)/taqtrade_dummy"
```

## Transfer Selected Files

Pull matching files into a local restore folder:

```bash
repokit-backup pull \
  --remote taqtrade \
  --path ./restore \
  --mode copy \
  --search "taqtrade_202001*"
```

Push matching local files back to the pinned Team Folder:

```bash
repokit-backup push \
  --remote taqtrade \
  --path ./taqtrade_dummy \
  --mode copy \
  --search "taqtrade_202001*"
```

`--mode copy` is appropriate for selected-file transfers because it does not
delete files at the destination. The default `sync` mode mirrors directories
and can delete destination files that do not exist at the source.

## Start A New UCloud Container

When submitting the new UCloud job, attach the persistent `taqtrade-project`
folder before starting the job:

1. In the UCloud job-submission page, select **Add folder** or **Select folders
   to use**.
2. Choose the existing persistent `taqtrade-project` folder from UCloud Files
   or the relevant project space. Create the folder there first if it does not
   yet exist.
3. Start the job. UCloud mounts selected folders below `/work`, so this folder
   must appear at `/work/taqtrade-project` in the new container.

See the [UCloud job-submission documentation](https://docs.cloud.sdu.dk/guide/submitting.html)
for the folder-selection interface.

Check that the selected folder is mounted, then reactivate the existing project
environment:

```bash
ls /work
cd /work/taqtrade-project
source .venv/bin/activate
which python
```

The expected interpreter is:

```text
/work/taqtrade-project/.venv/bin/python
```

When the persistent folder was attached, you do not need to reinstall the
packages, run `repokit-backup init`, or complete Dropbox OAuth again. The
saved Dropbox OAuth credential and pinned Team Folder remain in
`/work/taqtrade-project/bin/`.

Verify the mapping and Dropbox team-root access:

```bash
repokit-backup list
repokit-backup ls --remote taqtrade
```
