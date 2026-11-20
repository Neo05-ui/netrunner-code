#!/usr/bin/env bash
# Install Capri's GNOME desktop widgets into the Desktop Widgets extension.
#
# Symlinks rather than copies, so editing the repo updates the live widget.
# The host extension discovers plugins by enumerating its own plugins/ dir and
# follows symlinks (it queries with FileQueryInfoFlags.NONE), so a link to a
# directory is seen as a directory.
#
# Caveat worth knowing: an update to the host extension replaces its plugins/
# directory and takes these links with it. Re-run this script afterwards.
set -euo pipefail

EXT="$HOME/.local/share/gnome-shell/extensions/desktop-widgets@NiffirgkcaJ.github.com"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/widgets" && pwd)"

[ -d "$EXT" ] || { echo "Desktop Widgets extension not installed at $EXT"; exit 1; }
mkdir -p "$EXT/plugins"

fail=0
for d in "$SRC"/*/; do
  name="$(basename "$d")"
  ln -sfn "$d" "$EXT/plugins/$name"

  # Verify through the link, not in the source tree: capri-music and
  # capri-viz reach the shared MPRIS watcher by a relative symlink, and a
  # relative link that resolves in the repo can still dangle once the
  # directory is reached through plugins/.
  for required in plugin.json widget.js; do
    if [ ! -r "$EXT/plugins/$name/$required" ]; then
      echo "  FAILED $name: $required unreadable through the link"
      fail=1
      continue 2
    fi
  done
  for extra in "$EXT/plugins/$name"/*.js; do
    [ -e "$extra" ] || continue
    if [ ! -r "$extra" ]; then
      echo "  FAILED $name: $(basename "$extra") unreadable through the link"
      fail=1
    fi
  done
  echo "  linked $name"
done

[ "$fail" -eq 0 ] || { echo; echo "One or more widgets would not load. Fix the above before restarting the shell."; exit 1; }

echo
echo "Enable the host if it is not already running:"
echo "  gnome-extensions enable desktop-widgets@NiffirgkcaJ.github.com"
