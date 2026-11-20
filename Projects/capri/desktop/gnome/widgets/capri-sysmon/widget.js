// Capri System Monitor — a GNOME Shell port of the Plasma capri.sysmon widget.
//
// Reads the same four files the Plasma original did, so the numbers are
// identical: /proc/stat, /proc/meminfo, /proc/uptime, /proc/net/dev. No shell
// commands, no polling of external tools — the whole widget is four file
// reads every REFRESH_SECONDS, which is why it costs nothing on a 15W chip.
//
// CPU percentage is a DELTA between samples, not an instantaneous figure.
// /proc/stat holds monotonically increasing jiffy counters; reading it once
// tells you the average since boot, which is useless. The first tick after
// construction therefore shows 0 until a second sample exists.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

const RED = '#FF0033';
const GREEN = '#00FF55';
const VIOLET = '#8A3CE8';
const BLUE = '#7FD4F0';
const WHITE = '#F2ECFF';
const DIM = '#A294C4';

const REFRESH_SECONDS = 4;
const BAR_WIDTH = 240;
const BAR_HEIGHT = 8;
const KIB_PER_GIB = 1048576;

/** Read a file, returning '' rather than throwing — a widget must never
 *  take the shell down because /proc moved. */
function readFile(path) {
    try {
        const [ok, bytes] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(bytes) : '';
    } catch (_e) {
        return '';
    }
}

function gib(kb) {
    return (kb / KIB_PER_GIB).toFixed(1);
}

function humanRate(bytesPerSecond) {
    if (bytesPerSecond > 1048576) return `${(bytesPerSecond / 1048576).toFixed(1)} MB/s`;
    if (bytesPerSecond > 1024) return `${(bytesPerSecond / 1024).toFixed(0)} KB/s`;
    return `${Math.max(0, Math.round(bytesPerSecond))} B/s`;
}

const CapriSysmonWidget = GObject.registerClass(
    class CapriSysmonWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-sysmon',
                vertical: true,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });

            this._config = config || {};
            this._prevCpu = null;
            this._prevNet = null;
            this._prevTime = 0;
            this._timeoutId = null;

            this._buildUi();
            this._tick();
            this._timeoutId = GLib.timeout_add_seconds(
                GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
                    this._tick();
                    return GLib.SOURCE_CONTINUE;
                });
        }

        _buildUi() {
            const header = new St.Label({
                text: 'SYSTEM',
                style: `font-family: "Quicksand"; font-size: 16px; font-weight: 900;`
                    + ` letter-spacing: 3px; color: ${RED}; padding-bottom: 8px;`,
            });
            this.add_child(header);

            this._rows = {};
            for (const [key, label, colour] of [
                ['cpu', 'CPU', GREEN],
                ['mem', 'MEM', BLUE],
                ['swap', 'SWP', VIOLET],
            ]) {
                this.add_child(this._makeRow(key, label, colour));
            }

            this._foot = new St.Label({
                text: '--',
                style: `font-family: "Quicksand"; font-size: 13px; color: ${DIM};`
                    + ' padding-top: 10px; letter-spacing: 1px;',
            });
            this.add_child(this._foot);
        }

        /** label | track+fill | value — the fill's width is what animates. */
        _makeRow(key, labelText, colour) {
            const row = new St.BoxLayout({ vertical: false, style: 'spacing: 10px; padding: 3px 0;' });

            row.add_child(new St.Label({
                text: labelText,
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-family: "Quicksand"; font-size: 13px; font-weight: bold;`
                    + ` letter-spacing: 2px; color: ${WHITE}; width: 44px;`,
            }));

            // St.BoxLayout, NOT St.Widget: the fill has to stretch to the
            // track's full height, and a BoxLayout honours y_expand whereas
            // the FixedLayout that St.Widget inherits would give the child
            // only its own preferred height.
            //
            // (An earlier version of this comment blamed a bare St.Widget for
            // the shell's "needs an allocation" flood. That was wrong twice
            // over: St.Widget already inherits a layout manager, and the real
            // cause was the host extension writing set_position() from inside
            // a notify::allocation handler.)
            const track = new St.BoxLayout({
                vertical: false,
                y_align: Clutter.ActorAlign.CENTER,
                width: BAR_WIDTH,
                height: BAR_HEIGHT,
                style: 'background-color: rgba(255,255,255,0.10); border-radius: 4px;',
            });
            const fill = new St.Widget({
                x_align: Clutter.ActorAlign.START,
                y_expand: true,
                width: 0,
                style: `background-color: ${colour}; border-radius: 4px;`,
            });
            track.add_child(fill);
            row.add_child(track);

            const value = new St.Label({
                text: '--',
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-family: "Quicksand"; font-size: 13px; color: ${DIM};`,
            });
            row.add_child(value);

            this._rows[key] = { fill, value, colour };
            return row;
        }

        _setRow(key, percent, text) {
            const row = this._rows[key];
            if (!row) return;
            const clamped = Math.max(0, Math.min(100, percent || 0));
            // set the actor's width property, not a CSS width: CSS width on a
            // child inside a BoxLayout is advisory and the box wins.
            row.fill.set_width(Math.round((clamped / 100) * BAR_WIDTH));
            row.value.set_text(text);
        }

        _tick() {
            this._readCpu();
            this._readMemory();
            this._foot.set_text(`${this._readUptime()}    ${this._readNetwork()}`);
        }

        _readCpu() {
            const first = readFile('/proc/stat').split('\n')[0];
            if (!first || !first.startsWith('cpu')) return;
            const fields = first.trim().split(/\s+/).slice(1).map(Number);
            const idle = fields[3] + (fields[4] || 0);
            const total = fields.reduce((a, b) => a + b, 0);
            if (this._prevCpu) {
                const dTotal = total - this._prevCpu.total;
                const dIdle = idle - this._prevCpu.idle;
                if (dTotal > 0) {
                    const pct = (1 - dIdle / dTotal) * 100;
                    this._setRow('cpu', pct, `${Math.round(Math.max(0, pct))}%`);
                }
            }
            this._prevCpu = { total, idle };
        }

        _readMemory() {
            const info = readFile('/proc/meminfo');
            const val = (key) => {
                const m = info.match(new RegExp(`^${key}:\\s+(\\d+)`, 'm'));
                return m ? parseInt(m[1], 10) : 0;
            };
            const memTotal = val('MemTotal');
            const memAvailable = val('MemAvailable');
            if (memTotal > 0) {
                const used = memTotal - memAvailable;
                this._setRow('mem', (used / memTotal) * 100,
                    `${gib(used)} / ${gib(memTotal)} GiB`);
            }
            const swapTotal = val('SwapTotal');
            const swapFree = val('SwapFree');
            if (swapTotal > 0) {
                const used = swapTotal - swapFree;
                this._setRow('swap', (used / swapTotal) * 100,
                    `${gib(used)} / ${gib(swapTotal)} GiB`);
            } else {
                this._setRow('swap', 0, 'off');
            }
        }

        _readUptime() {
            const raw = readFile('/proc/uptime').trim().split(/\s+/)[0];
            if (!raw) return '--';
            const s = Math.floor(parseFloat(raw));
            const d = Math.floor(s / 86400);
            const h = Math.floor((s % 86400) / 3600);
            const m = Math.floor((s % 3600) / 60);
            return `up ${d > 0 ? `${d}d ` : ''}${h}h ${m}m`;
        }

        /** Sum every interface except loopback, then rate it against the clock. */
        _readNetwork() {
            const lines = readFile('/proc/net/dev').split('\n');
            let rx = 0;
            let tx = 0;
            for (let i = 2; i < lines.length; i++) {
                const parts = lines[i].trim().split(/\s+/);
                if (parts.length < 10) continue;
                if (parts[0].replace(':', '') === 'lo') continue;
                rx += parseInt(parts[1], 10) || 0;
                tx += parseInt(parts[9], 10) || 0;
            }
            const now = GLib.get_monotonic_time() / 1000;
            let text = '↓ --   ↑ --';
            if (this._prevNet && this._prevTime) {
                const secs = (now - this._prevTime) / 1000;
                if (secs > 0) {
                    text = `↓ ${humanRate((rx - this._prevNet.rx) / secs)}`
                        + `   ↑ ${humanRate((tx - this._prevNet.tx) / secs)}`;
                }
            }
            this._prevNet = { rx, tx };
            this._prevTime = now;
            return text;
        }

        destroy() {
            if (this._timeoutId) {
                GLib.source_remove(this._timeoutId);
                this._timeoutId = null;
            }
            super.destroy();
        }
    },
);

export default {
    createWidget: (config) => new CapriSysmonWidget(config),
};
