// Shared MPRIS watcher for the Capri GNOME widgets.
//
// Canonical copy. Each widget that needs it carries a relative symlink to
// this file (capri-music/mpris.js, capri-viz/mpris.js) so that every widget
// directory stays a self-contained drop-in: the host imports widget.js by
// URI, and a sibling './mpris.js' resolves correctly even when the widget
// directory is itself a symlink into the repo. A '../../shared/' import would
// not - it would resolve inside the extension's plugins directory.
//
// Design note: this does NOT poll for playback state. It subscribes to
// PropertiesChanged on the MPRIS object path for every sender at once, plus
// NameOwnerChanged narrowed to the org.mpris.MediaPlayer2 namespace, and
// keeps a slow rescan only as a safety net for players that change state
// without announcing it. Idle cost is therefore zero - which matters,
// because the whole point of this desktop is to leave the CPU free for
// Capri herself.

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const BUS_PREFIX = 'org.mpris.MediaPlayer2';
const PLAYER_PATH = '/org/mpris/MediaPlayer2';
const PLAYER_IFACE = 'org.mpris.MediaPlayer2.Player';

// Browsers publish an MPRIS player for any tab that makes a sound, so a
// YouTube tab would otherwise hijack the widget away from a real player.
const IGNORE = ['chrom', 'brave', 'firefox', 'opera', 'vivaldi', 'edge', 'electron'];

const RESCAN_SECONDS = 15;
const DEBOUNCE_MS = 250;

export const EMPTY = {
    bus: '',
    status: 'Stopped',
    playing: false,
    title: '',
    artist: '',
    artUrl: '',
};

/** MPRIS reports artist as an array of strings; a few players send a bare
 *  string instead. Accept both. */
function artistOf(metadata) {
    const a = metadata['xesam:artist'];
    if (!a) return '';
    return Array.isArray(a) ? a.join(', ') : String(a);
}

export class MprisWatcher {
    /** @param {Function} onChange - called with a state object on every change */
    constructor(onChange) {
        this._onChange = onChange;
        this._subscriptions = [];
        this._rescanId = null;
        this._debounceId = null;
        this.state = { ...EMPTY };
    }

    start() {
        const bus = Gio.DBus.session;

        // Every player's property changes arrive on the same object path, so
        // one subscription with a null sender covers all of them.
        this._subscriptions.push(bus.signal_subscribe(
            null, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
            PLAYER_PATH, null, Gio.DBusSignalFlags.NONE, () => this._scanSoon()));

        // Players appearing and disappearing. MATCH_ARG0_NAMESPACE keeps this
        // to MPRIS names instead of waking us for every name on the bus.
        this._subscriptions.push(bus.signal_subscribe(
            'org.freedesktop.DBus', 'org.freedesktop.DBus', 'NameOwnerChanged',
            '/org/freedesktop/DBus', BUS_PREFIX,
            Gio.DBusSignalFlags.MATCH_ARG0_NAMESPACE, () => this._scanSoon()));

        this._rescanId = GLib.timeout_add_seconds(
            GLib.PRIORITY_LOW, RESCAN_SECONDS, () => {
                this._scan();
                return GLib.SOURCE_CONTINUE;
            });

        this._scan();
    }

    stop() {
        for (const id of this._subscriptions)
            Gio.DBus.session.signal_unsubscribe(id);
        this._subscriptions = [];
        for (const field of ['_rescanId', '_debounceId']) {
            if (this[field]) {
                GLib.source_remove(this[field]);
                this[field] = null;
            }
        }
    }

    /** Fire-and-forget a transport control on the currently chosen player. */
    call(method) {
        if (!this.state.bus) return;
        Gio.DBus.session.call(
            this.state.bus, PLAYER_PATH, PLAYER_IFACE, method, null, null,
            Gio.DBusCallFlags.NONE, -1, null, (conn, res) => {
                try {
                    conn.call_finish(res);
                } catch (e) {
                    logError(e, `[capri] MPRIS ${method} failed`);
                }
            });
    }

    /** Coalesce a burst of signals into one scan. A track change can emit
     *  several PropertiesChanged in a few milliseconds. */
    _scanSoon() {
        if (this._debounceId) return;
        this._debounceId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, DEBOUNCE_MS, () => {
                this._debounceId = null;
                this._scan();
                return GLib.SOURCE_REMOVE;
            });
    }

    _scan() {
        Gio.DBus.session.call(
            'org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'ListNames', null,
            new GLib.VariantType('(as)'), Gio.DBusCallFlags.NONE, -1, null,
            (conn, res) => {
                let names;
                try {
                    names = conn.call_finish(res).deepUnpack()[0];
                } catch (e) {
                    return;     // bus unavailable; keep the last known state
                }
                const players = names.filter((n) =>
                    n.startsWith(`${BUS_PREFIX}.`) &&
                    !IGNORE.some((bad) => n.toLowerCase().includes(bad)));
                this._probe(players);
            });
    }

    _probe(players) {
        if (players.length === 0) {
            this._publish({ ...EMPTY });
            return;
        }

        const found = [];
        let pending = players.length;

        for (const bus of players) {
            Gio.DBus.session.call(
                bus, PLAYER_PATH, 'org.freedesktop.DBus.Properties', 'GetAll',
                new GLib.Variant('(s)', [PLAYER_IFACE]),
                new GLib.VariantType('(a{sv})'), Gio.DBusCallFlags.NONE,
                -1, null, (conn, res) => {
                    try {
                        // recursiveUnpack, not deepUnpack: Metadata is a{sv},
                        // and deepUnpack would leave each value a Variant.
                        const props = conn.call_finish(res).recursiveUnpack()[0];
                        found.push({ bus, props });
                    } catch (e) {
                        // A player that vanished mid-probe is normal.
                    }
                    pending -= 1;
                    if (pending === 0) this._choose(found);
                });
        }
    }

    /** Prefer whatever is actually playing; otherwise show the first player
     *  so a paused track still has its title on screen. */
    _choose(found) {
        if (found.length === 0) {
            this._publish({ ...EMPTY });
            return;
        }
        const chosen = found.find((f) => f.props.PlaybackStatus === 'Playing')
            || found[0];
        const metadata = chosen.props.Metadata || {};
        const status = chosen.props.PlaybackStatus || 'Stopped';

        this._publish({
            bus: chosen.bus,
            status,
            playing: status === 'Playing',
            title: metadata['xesam:title'] || '',
            artist: artistOf(metadata),
            artUrl: metadata['mpris:artUrl'] || '',
        });
    }

    _publish(state) {
        const same = Object.keys(EMPTY).every((k) => state[k] === this.state[k]);
        if (same) return;       // do not redraw for an unchanged player
        this.state = state;
        this._onChange(state);
    }
}
