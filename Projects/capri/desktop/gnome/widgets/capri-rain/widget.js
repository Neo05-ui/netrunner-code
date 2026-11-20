// Capri Code Rain - a GNOME Shell port of the Plasma capri.rain widget.
//
// Columns of glyphs falling at staggered speeds. The point of this widget is
// that it must be beautiful AND free: it sits on the desktop of a 15W laptop
// whose whole job is to run Capri, so an animation that costs a relayout per
// frame is not acceptable.
//
// It animates `translation-y`, not `y`. Translation is a transform applied on
// the GPU, so the shell never relayouts: the columns are positioned exactly
// once, at construction, and nothing in the layout tree changes again for the
// life of the widget. The Plasma original animated `y`, which Qt's scene
// graph handled cheaply; Clutter's equivalent of that trick is the transform.
//
// Nothing here writes a position from inside an allocation signal. Doing that
// re-invalidates the allocation the actor was just given, and the shell then
// logs "needs an allocation" for that actor on every single frame - which is
// exactly the bug this widget's host extension had.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

const WHITE = '#F2ECFF';
const RED = '#FF0033';
const GREEN = '#00FF55';
const VIOLET = '#8A3CE8';

const WIDTH = 420;
const HEIGHT = 330;
const MARGIN = 14;
const COLUMN_WIDTH = 38;
const GLYPH_SIZE = 19;
const LINE_HEIGHT = 23;      // 19px monospace plus leading, measured
const TAIL_GLYPHS = 5;

const GLYPHS = '01アイウエオカキク{}[]<>/\\=+*#$%&@!?'.split('');

/** Deterministic glyph strip. Seeded arithmetic rather than Math.random() so
 *  a column looks the same every time the shell starts - the rain should not
 *  reshuffle itself each login. */
function strip(seed, count) {
    let out = '';
    for (let i = 0; i < count; i++)
        out += `${GLYPHS[(seed * 31 + i * 17) % GLYPHS.length]}\n`;
    return out;
}

function glyphAt(n) {
    return GLYPHS[n % GLYPHS.length];
}

function label(text, colour, { bold = false, opacity = 1 } = {}) {
    const actor = new St.Label({
        text,
        style: `font-family: monospace; font-size: ${GLYPH_SIZE}px;`
            + ` color: ${colour};${bold ? ' font-weight: bold;' : ''}`,
    });
    if (opacity < 1)
        actor.set_opacity(Math.round(opacity * 255));
    return actor;
}

const CapriRainWidget = GObject.registerClass(
    class CapriRainWidget extends St.Widget {
        constructor(config) {
            super({
                style_class: 'capri-rain',
                width: WIDTH,
                height: HEIGHT,
                // Without this the columns draw straight through the border
                // and over whatever sits beside the widget.
                clip_to_allocation: true,
            });

            this._config = config || {};

            const field = new St.Widget({
                x: MARGIN,
                y: MARGIN,
                width: WIDTH - MARGIN * 2,
                height: HEIGHT - MARGIN * 2,
                clip_to_allocation: true,
            });
            this.add_child(field);

            const columns = Math.max(1, Math.floor((WIDTH - 28) / COLUMN_WIDTH));
            for (let i = 0; i < columns; i++)
                field.add_child(this._makeColumn(i));
        }

        _makeColumn(index) {
            const seed = index * 7 + 3;
            const bodyGlyphs = 10 + (index % 5);

            const stream = new St.BoxLayout({
                vertical: true,
                width: COLUMN_WIDTH,
                style: 'spacing: 0;',
            });

            // Head is brightest, then the red second glyph, then the green
            // body, then a violet tail - the same four-stage falloff as the
            // Plasma version.
            stream.add_child(label(glyphAt(seed * 13), WHITE, { bold: true }));
            stream.add_child(label(glyphAt(seed * 5), RED, { bold: true }));
            stream.add_child(label(strip(seed, bodyGlyphs), GREEN, { opacity: 0.75 }));
            stream.add_child(label(strip(seed + 4, TAIL_GLYPHS), VIOLET, { opacity: 0.45 }));

            // Set once, here. Never from an allocation handler.
            stream.set_position(index * COLUMN_WIDTH, 0);

            const streamHeight = (2 + bodyGlyphs + TAIL_GLYPHS) * LINE_HEIGHT;
            const fall = new Clutter.PropertyTransition({
                property_name: 'translation-y',
            });
            fall.set_from(-streamHeight);
            fall.set_to(HEIGHT + 20);
            fall.set_duration(5200 + (index % 7) * 1400);
            fall.set_repeat_count(-1);
            fall.set_progress_mode(Clutter.AnimationMode.LINEAR);
            stream.add_transition('capri-rain-fall', fall);

            return stream;
        }
    },
);

export default {
    createWidget: (config) => new CapriRainWidget(config),
};
