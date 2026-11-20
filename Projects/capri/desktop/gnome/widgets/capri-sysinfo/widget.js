// Capri System Info - a GNOME Shell port of the Plasma capri.sysinfo widget.
//
// A fastfetch-style card: distro, kernel, CPU, RAM, desktop and theme, with
// the seven-pointed Capri shard drawn beside it. Every value it shows is read
// once, at construction - none of it changes while the session is up - so
// unlike capri-sysmon this widget owns no timer and costs nothing after the
// first paint.
//
// Two deliberate departures from the Plasma original:
//   - the username comes from GLib.get_user_name() rather than a hardcoded
//     username, so the card is correct on someone else's laptop. This whole
//     tree is meant to be installable by anyone, and a hardcoded username is
//     the kind of detail that makes a theme feel like it was stolen from
//     somebody's dotfiles.
//   - the desktop row reports the running shell and its version instead of
//     the literal string "KDE Plasma".

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

const RED = '#FF0033';
const VIOLET = '#8A3CE8';

const SHARD_WIDTH = 104;
const KIB_PER_GIB = 1048576;

// [unit x, unit y, radius fraction] - seven spikes, each returning to 32% of
// its own radius, which is what gives the shard its shattered silhouette.
const SPIKES = [
    [0, -1, 0.95], [0.75, -0.55, 0.7], [0.95, 0.2, 0.85], [0.45, 0.85, 0.65],
    [-0.3, 0.95, 0.75], [-0.9, 0.35, 0.8], [-0.7, -0.6, 0.6],
];

const SWATCHES = [
    '#FF0033', '#FF4466', '#8A3CE8', '#B06BFF',
    '#00FF55', '#66FFA0', '#7FD4F0', '#F2ECFF',
];

/** Read a file, returning '' rather than throwing: a widget must never take
 *  the shell down because something under /proc or /etc moved. */
function readFile(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(bytes) : '';
    } catch (_e) {
        return '';
    }
}

function firstMatch(text, pattern, fallback = '--') {
    const m = text.match(pattern);
    return m ? m[1].trim() : fallback;
}

/** Shell version without importing resource:///, which would make the whole
 *  module fail to load if that path ever moves. GNOME exports it on the
 *  session bus, but reading it synchronously is not worth a D-Bus round trip
 *  for a cosmetic line, so fall back to the desktop name alone. */
function desktopName() {
    const desktop = (GLib.getenv('XDG_CURRENT_DESKTOP') || 'GNOME')
        .split(':').pop();
    const session = GLib.getenv('GNOME_SHELL_SESSION_MODE');
    return session ? `${desktop} (${session})` : desktop;
}

function collect() {
    const cpu = firstMatch(readFile('/proc/cpuinfo'), /^model name\s*:\s*(.+)$/m)
        .replace(/\(R\)|\(TM\)|CPU|Processor/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    const memKib = parseInt(
        firstMatch(readFile('/proc/meminfo'), /^MemTotal:\s+(\d+)/m, '0'), 10);

    return {
        host: readFile('/etc/hostname').trim() || GLib.get_host_name() || 'localhost',
        user: GLib.get_user_name() || 'user',
        rows: [
            ['os', firstMatch(readFile('/etc/os-release'), /^PRETTY_NAME="?([^"\n]+)"?/m)],
            ['kernel', firstMatch(readFile('/proc/version'), /version (\S+)/)],
            ['cpu', cpu || '--'],
            ['ram', memKib > 0 ? `${(memKib / KIB_PER_GIB).toFixed(1)} GiB` : '--'],
            ['de', desktopName()],
            ['theme', 'Capri'],
        ],
    };
}

const CapriSysinfoWidget = GObject.registerClass(
    class CapriSysinfoWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-sysinfo',
                vertical: false,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });

            this._config = config || {};
            const info = collect();

            this.add_child(this._makeShard());
            this.add_child(this._makeColumn(info));
        }

        /** The shard, drawn with cairo instead of QML's Canvas. */
        _makeShard() {
            const area = new St.DrawingArea({
                width: SHARD_WIDTH,
                y_expand: true,
                y_align: Clutter.ActorAlign.FILL,
            });

            area.connect('repaint', (self) => {
                const cr = self.get_context();
                const [w, h] = self.get_surface_size();
                const cx = w / 2;
                const cy = h / 2;
                const base = Math.min(cx, cy);

                cr.newPath();
                SPIKES.forEach(([ux, uy, frac], i) => {
                    const r = base * frac;
                    const px = cx + ux * r;
                    const py = cy + uy * r;
                    if (i === 0)
                        cr.moveTo(px, py);
                    else
                        cr.lineTo(px, py);
                    cr.lineTo(cx + ux * r * 0.32, cy + uy * r * 0.32);
                });
                cr.closePath();

                // fillPreserve, not fill: cairo consumes the path when it
                // fills, whereas QML's Canvas kept it, so the original could
                // fill() and then stroke() the same outline. Plain fill()
                // here would stroke nothing and lose the violet edge.
                cr.setSourceRGBA(1, 0, 0.2, 0.80);
                cr.fillPreserve();
                cr.setSourceRGBA(0.541, 0.235, 0.910, 0.95);
                cr.setLineWidth(2);
                cr.stroke();

                cr.arc(cx, cy, base * 0.17, 0, 2 * Math.PI);
                cr.setSourceRGBA(0, 1, 0.333, 0.95);
                cr.fill();

                // Required: GJS will not collect the cairo context itself and
                // logs a warning for every leaked one.
                cr.$dispose();
            });

            return area;
        }

        _makeColumn(info) {
            const column = new St.BoxLayout({
                vertical: true,
                y_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 2px;',
            });

            column.add_child(new St.Label({
                text: `${info.user}@${info.host}`,
                style: 'font-family: "Quicksand"; font-size: 17px;'
                    + ` font-weight: 900; color: ${RED};`,
            }));

            column.add_child(new St.Widget({
                height: 1,
                x_expand: true,
                style: `background-color: ${VIOLET}; margin: 5px 0;`,
            }));

            for (const [key, value] of info.rows) {
                const row = new St.BoxLayout({ vertical: false, style: 'spacing: 7px;' });
                row.add_child(new St.Label({
                    text: key,
                    style_class: 'capri-sysinfo-key',
                }));
                const val = new St.Label({
                    text: value,
                    style_class: 'capri-sysinfo-val',
                });
                // A long CPU model would otherwise stretch the whole card.
                val.clutter_text.set_ellipsize(3 /* Pango.EllipsizeMode.END */);
                val.set_x_expand(true);
                row.add_child(val);
                column.add_child(row);
            }

            const swatches = new St.BoxLayout({
                vertical: false,
                style: 'spacing: 5px; padding-top: 8px;',
            });
            for (const colour of SWATCHES) {
                swatches.add_child(new St.Widget({
                    width: 17,
                    height: 9,
                    style: `background-color: ${colour}; border-radius: 3px;`,
                }));
            }
            column.add_child(swatches);

            return column;
        }
    },
);

export default {
    createWidget: (config) => new CapriSysinfoWidget(config),
};
