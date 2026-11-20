# Host extension patches

Capri's widgets run inside two third-party GNOME Shell extensions. Both had
bugs that affect this desktop, so each is patched locally. The patches live
here so a fresh machine can be brought to the same state, and so it is
obvious what was changed and why.

Re-apply them after either extension updates - an update overwrites the
extension's files and silently takes these fixes with it.

## desktop-widgets-allocation-loop.patch

Apply to `desktop-widgets@NiffirgkcaJ.github.com`.

`_addWidget()` connected `notify::allocation` to a handler that called
`set_position()` unconditionally. Writing a position from inside the
allocation signal re-invalidates the allocation the actor was just given, so
`update_stage_views()` finds it unallocated and logs

    Can't update stage views actor ... needs an allocation

and the relayout it queued re-fires the handler. Measured at ~110 lines per
second per widget - 3291 journal lines in ten seconds with three widgets, all
of it written to disk. The patch compares against the current position and
writes only when it differs (0.5px epsilon, since the anchor maths returns
`targetX - width * 0.5`).

## multi-monitors-bar-dash-api.patch

Apply to `multi-monitors-bar@frederykabryan`.

`Dash._queueRedisplay()` does not exist in GNOME Shell 46, so `_sync()` threw

    this._dash._queueRedisplay is not a function

on every call and the isolated dash kept showing the previous monitor's apps.
The patch routes through a helper that uses the method if the running shell
has it, falls back to the Dash's own deferred-work queue, and finally to a
direct redisplay - rather than hardcoding whichever name one release uses.

## Applying

    cd ~/.local/share/gnome-shell/extensions/desktop-widgets@NiffirgkcaJ.github.com
    patch -p1 --dry-run < <repo>/Projects/capri/desktop/gnome/patches/desktop-widgets-allocation-loop.patch

Drop `--dry-run` once it reports clean. GNOME Shell caches ES modules, so
**log out and back in** afterwards: disabling and re-enabling the extension
keeps running the old code, and Wayland has no `Alt+F2 r`.
