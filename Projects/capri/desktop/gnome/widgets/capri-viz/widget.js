// Capri Visualiser - a GNOME Shell port of the Plasma capri.viz widget.
//
// A wide panel of bars that comes alive when any MPRIS player is playing and
// settles flat when nothing is. It is decoration, not analysis: no audio is
// captured, and the bar heights are a deterministic pattern per index. The
// Plasma original did the same - pulling real FFT data would mean tapping the
// PulseAudio monitor source, which is a far bigger ask than a desktop
// ornament deserves.
//
// Like capri-music this animates `scale-y` about a bottom pivot, so the whole
// panel is GPU transforms and the shell performs no relayout while it runs.
// The transitions are removed outright when playback stops.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import { MprisWatcher } from './mpris.js';

const WIDTH = 420;
const HEIGHT = 190;
const PADDING = 20;
const BAR_COUNT = 22;
const BAR_GAP = 4;

const RESTING_SCALE = 0.05;
const DIM_OPACITY = 76;
const LIT_OPACITY = 242;

function hex(r, g, b) {
    const pair = (v) => Math.max(0, Math.min(255, Math.round(v)))
        .toString(16).padStart(2, '0');
    return `#${pair(r)}${pair(g)}${pair(b)}`;
}

/** Red to violet across the first half, violet to green across the second -
 *  the same two-stop ramp the QML version computed inline. */
function barColour(index) {
    const t = index / (BAR_COUNT - 1);
    if (t < 0.5) {
        const u = t / 0.5;
        return hex(255 - u * 117, u * 60, 51 + u * 181);
    }
    const v = (t - 0.5) / 0.5;
    return hex(138 - v * 138, 60 + v * 195, 232 - v * 147);
}

const CapriVizWidget = GObject.registerClass(
    class CapriVizWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-viz',
                vertical: false,
                width: WIDTH,
                height: HEIGHT,
                y_align: Clutter.ActorAlign.END,
                style: `spacing: ${BAR_GAP}px;`,
            });

            this._config = config || {};
            this._bars = [];
            this._playing = false;

            const inner = WIDTH - PADDING * 2;
            const barWidth = Math.floor((inner - BAR_GAP * (BAR_COUNT - 1)) / BAR_COUNT);
            const barHeight = HEIGHT - PADDING * 2;

            for (let i = 0; i < BAR_COUNT; i++) {
                const bar = new St.Widget({
                    width: barWidth,
                    height: barHeight,
                    y_align: Clutter.ActorAlign.END,
                    opacity: DIM_OPACITY,
                    style: `background-color: ${barColour(i)};`
                        + ` border-radius: ${Math.round(barWidth / 2)}px;`,
                });
                // Full-height bar scaled down from the baseline: the actor
                // never changes size, only its transform.
                bar.set_pivot_point(0.5, 1.0);
                bar.set_scale(1, RESTING_SCALE);
                this._bars.push(bar);
                this.add_child(bar);
            }

            this._watcher = new MprisWatcher((state) => {
                if (state.playing === this._playing) return;
                this._playing = state.playing;
                this._setRunning(state.playing);
            });
            this._watcher.start();
        }

        _setRunning(running) {
            this._bars.forEach((bar, i) => {
                bar.remove_transition('capri-viz');
                bar.set_opacity(running ? LIT_OPACITY : DIM_OPACITY);

                if (!running) {
                    bar.set_scale(1, RESTING_SCALE);
                    return;
                }

                const transition = new Clutter.PropertyTransition({
                    property_name: 'scale-y',
                });
                transition.set_from(RESTING_SCALE + (i % 4) * 0.03);
                transition.set_to(0.12 + ((i * 37) % 9) * 0.085);
                transition.set_duration(300 + (i % 7) * 60);
                transition.set_repeat_count(-1);
                transition.set_auto_reverse(true);
                transition.set_progress_mode(Clutter.AnimationMode.EASE_IN_OUT_SINE);
                bar.add_transition('capri-viz', transition);
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
    createWidget: (config) => new CapriVizWidget(config),
};
