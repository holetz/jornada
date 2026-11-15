# Security policy

## Supported versions

Only the latest commit on the default branch (`master`) receives fixes.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Report it privately through
GitHub's private vulnerability reporting:
<https://github.com/holetz/jornada/security/advisories/new>.

Include what you found, how to reproduce it and the impact you expect. The maintainer listed in
`GOVERNANCE.md` acknowledges a report on a best-effort basis, keeps you informed while it is being
fixed and credits you in the advisory unless you prefer otherwise.

## Scope

jornada runs locally on a single Linux desktop. Its web page listens on `127.0.0.1` only and
requires a per-session token for writes and for screenshots. Reports about that local surface, the
data it stores under `~/.local/share/jornada/` and the systemd user service are in scope.
