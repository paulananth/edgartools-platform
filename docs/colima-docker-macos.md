# Colima Docker Setup On macOS

This repo uses Docker for local image builds and runtime smoke checks. On macOS,
prefer Colima over Docker Desktop.

## Intel Mac Setup

On Intel Macs running macOS 14.x, use QEMU. Colima/Lima may default to `vz`, but
current Lima images can fail on Intel macOS before 15.5 with a warning similar to:

```text
vmType vz: On Intel Mac, macOS 15.5 or later is required to run Linux 6.12 or later
```

Install the required tools:

```bash
brew install colima docker qemu
```

Start Colima with Docker:

```bash
colima start \
  --vm-type qemu \
  --mount-type 9p \
  --cpus 2 \
  --memory 4 \
  --disk 40 \
  --runtime docker \
  --arch x86_64 \
  --save-config
```

For larger local image builds, increase CPU, memory, or disk at creation time.
Disk can only be increased after a VM has been created.

## Validation

Check the VM, Docker context, and Docker daemon:

```bash
colima status
docker context ls
docker version
docker info
```

Expected signs of a healthy setup:

- `colima status` reports `runtime: docker`.
- `colima status` reports `vmType: qemu` or `colima is running using QEMU`.
- `docker context ls` has `colima` as the active context.
- `docker version` shows a macOS client and a Linux server.

Optional smoke test:

```bash
docker run --rm hello-world
docker image rm hello-world:latest
```

## Repair Notes

If `colima start` fails with:

```text
instance "colima" already exists
```

and `limactl` reports a missing `lima.yaml`, the Colima/Lima instance directory is
stale or incomplete. First confirm there is no useful Docker data to preserve:

```bash
colima status || true
LIMA_HOME="$HOME/.colima/_lima" limactl list || true
du -sh "$HOME/.colima/_lima/colima" "$HOME/.colima/_lima/_disks/colima" 2>/dev/null || true
```

If the broken instance and disk are empty, move them out of the way and recreate
Colima:

```bash
ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/.colima/_lima/_repair-backups-$ts"

mv "$HOME/.colima/_lima/colima" \
  "$HOME/.colima/_lima/_repair-backups-$ts/colima.broken" 2>/dev/null || true

mv "$HOME/.colima/_lima/_disks/colima" \
  "$HOME/.colima/_lima/_repair-backups-$ts/colima-disk.broken" 2>/dev/null || true

colima start \
  --vm-type qemu \
  --mount-type 9p \
  --cpus 2 \
  --memory 4 \
  --disk 40 \
  --runtime docker \
  --arch x86_64 \
  --save-config
```

Remove only inactive cleanup artifacts:

```bash
find "$HOME/.colima" -name .DS_Store -type f -delete
rm -rf "$HOME/.colima/_lima"/_repair-backups-*
rm -rf "$HOME/Library/Caches/colima/caches"
```

Do not remove `~/.colima/_lima/colima`, `~/.colima/_lima/_disks/colima`, or
`~/.colima/default/docker.sock` while the active Colima VM is in use.
