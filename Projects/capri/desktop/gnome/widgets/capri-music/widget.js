// Capri Music - a GNOME Shell port of the Plasma capri.music widget.
//
// Now playing, transport controls and a bar visualiser, driven by the shared
// MprisWatcher (./mpris.js, a symlink to ../../shared/mpris.js).
//
// Performance shape, which is the whole reason this looks the way it does:
//   - the visualiser animates `scale-y` with the pivot pinned to the bottom
//     of each bar. That is a GPU transform, so 22 animated bars cost no
//     relayout at all. Animating `height` instead - the obvious translation
//     of the QML original - would queue 22 relayouts per frame.
//   - the bars' transitions are REMOVED when playback stops, not just faded.
//     A paused widget should be genuinely idle, not quietly animating at 5%
//     opacity.
//
// Album art is deliberately limited to local files. MPRIS hands over whatever
// URL the player feels like, and some players (Spotify among them) supply an
// https:// one; loading that would have the shell itself fetch a remote image
// chosen by another process. The art path is also validated before it reaches
// CSS, since it is interpolated into a stylesheet string.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import { MprisWatcher } from './mpris.js';

const RED = '#FF0033';
const GREEN = '#00FF55';
const VIOLET = '#8A3CE8';

const ART_SIZE = 128;
const BAR_COUNT = 22;
const BAR_WIDTH = 5;
const BAR_ROW_HEIGHT = 26;
const BAR_BASE = 4;

const DIM_OPACITY = 76;
const LIT_OPACITY = 242;

/** A local art path, or '' if the URL is remote or in any way unusual.
 *  Anything returned here is interpolated into a stylesheet, so the
 *  characters that could break out of url("...") are rejected outright
 *  rather than escaped. */
function localArtPath(artUrl) {
    if (!artUrl || !artUrl.startsWith('file://')) return '';
    let path;
    try {
        path = GLib.filename_from_uri(artUrl)[0];
    } catch (_e) {
        return '';
    }
    if (!path || /["'()\;\n\r]/.test(path)) return '';
    if (!GLib.file_test(path, GLib.FileTest.EXISTS)) return '';
    return path;
}

const CapriMusicWidget = GObject.registerClass(
    class CapriMusicWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-music',
                vertical: false,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });

            this._config = config || {};
            this._bars = [];
            this._playing = false;

            this.add_child(this._makeArt());
            this.add_child(this._makeBody());

            this._watcher = new MprisWatcher((state) => this._apply(state));
            this._watcher.start();
        }

        _makeArt() {
            const box = new St.Widget({
                style_class: 'capri-music-art',
                width: ART_SIZE,
                height: ART_SIZE,
                layout_manager: new Clutter.BinLayout(),
            });
            this._art = box;

            this._artGlyph = new St.Label({
                text: '♪',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-size: 52px; color: ${RED};`,
            });
            box.add_child(this._artGlyph);

            return box;
        }

        _makeBody() {
            const column = new St.BoxLayout({
                vertical: true,
                y_align: Clutter.ActorAlign.CENTER,
                x_expand: true,
                style: 'spacing: 6px;',
            });

            this._title = new St.Label({
                text: 'nothing playing',
                style_class: 'capri-music-title',
            });
            this._title.clutter_text.set_ellipsize(3 /* Pango ELLIPSIZE_END */);
            column.add_child(this._title);

            this._artist = new St.Label({
                text: '',
                style_class: 'capri-music-artist',
            });
            this._artist.clutter_text.set_ellipsize(3);
            column.add_child(this._artist);

            column.add_child(this._makeBars());
            column.add_child(this._makeControls());

            return column;
        }

        _makeBars() {
            const row = new St.BoxLayout({
                vertical: false,
                height: BAR_ROW_HEIGHT,
                y_align: Clutter.ActorAlign.END,
                style: 'spacing: 3px; padding-top: 2px;',
            });

            for (let i = 0; i < BAR_COUNT; i++) {
                const colour = i % 5 === 0 ? RED : (i % 3 === 0 ? VIOLET : GREEN);
                const bar = new St.Widget({
                    width: BAR_WIDTH,
                    height: BAR_BASE,
                    y_align: Clutter.ActorAlign.END,
                    opacity: DIM_OPACITY,
                    style: `background-color: ${colour}; border-radius: 2px;`,
                });
                // Grow upward from the baseline rather than from the centre.
                bar.set_pivot_point(0.5, 1.0);
                this._bars.push(bar);
                row.add_child(bar);
            }

            return row;
        }

        _makeControls() {
            const row = new St.BoxLayout({
                vertical: false,
                style: 'spacing: 14px; padding-top: 4px;',
            });

            for (const [glyph, method, size] of [
                ['◀◀', 'Previous', 13],
                ['▶', 'PlayPause', 17],
                ['▶▶', 'Next', 13],
            ]) {
                const button = new St.Button({
                    style_class: 'capri-music-btn',
                    label: glyph,
                    style: `font-size: ${size}px;`,
                    can_focus: true,
                });
                button.connect('clicked', () => this._watcher.call(method));
                if (method === 'PlayPause') this._playPause = button;
                row.add_child(button);
            }

            return row;
        }

        _apply(state) {
            this._title.set_text(state.title || 'nothing playing');
            this._artist.set_text(state.artist || '');
            if (this._playPause)
                this._playPause.set_label(state.playing ? '‖' : '▶');

            const art = localArtPath(state.artUrl);
            this._art.set_style(art ? `background-image: url("${art}");` : null);
            this._artGlyph.visible = !art;

            if (state.playing !== this._playing) {
                this._playing = state.playing;
                this._setBarsRunning(state.playing);
            }
        }

        /** Start or stop the visualiser. Transitions are added and removed,
         *  not paused, so a stopped widget costs nothing. */
        _setBarsRunning(running) {
            this._bars.forEach((bar, i) => {
                bar.remove_transition('capri-bar');
                bar.set_opacity(running ? LIT_OPACITY : DIM_OPACITY);

                if (!running) {
                    bar.set_scale(1, 1);
                    return;
                }

                const peak = (6 + ((i * 7) % 22)) / BAR_BASE;
                const transition = new Clutter.PropertyTransition({
                    property_name: 'scale-y',
                });
                transition.set_from(1);
                transition.set_to(peak);
                transition.set_duration(260 + (i % 6) * 70);
                transition.set_repeat_count(-1);
                transition.set_auto_reverse(true);
                transition.set_progress_mode(Clutter.AnimationMode.EASE_IN_OUT_SINE);
                bar.add_transition('capri-bar', transition);
            });
        }

        destroy() {
            if (this._watcher) {
                this._watcher.stop();
                this._watcher = null;
            }
            super.destroy();
        }
    },
);

export default {
    createWidget: (config) => new CapriMusicWidget(config),
};
