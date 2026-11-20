// Capri Weather - a GNOME Shell port of the Plasma capri.weather widget.
//
// Current conditions plus a three-day strip, from open-meteo, which needs no
// API key and no account.
//
// LOCATION IS NOT BAKED IN. The Plasma original carried a pair of
// coordinates in its config defaults; this repository is public, so a
// checkout of it should not state where its author lives. The widget takes
// `latitude` / `longitude` / `place` from its own config entry (set in the
// host's profiles-json, which stays on the machine) and shows a plain
// "set a location" message until they are present. That is also what makes
// the widget correct for anyone else who installs this theme.
//
// Two notes on the request itself:
//   - the coordinates go to a third party (open-meteo). That is unavoidable
//     for a weather widget and the Plasma version did the same, but nothing
//     else is sent: the user agent is a generic string, not the machine's.
//   - latitude and longitude are checked as finite numbers in range before
//     they reach the URL, because they come from a config file.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Soup from 'gi://Soup';
import St from 'gi://St';

const RED = '#FF0033';
const GREEN = '#00FF55';
const VIOLET = '#8A3CE8';
const BLUE = '#7FD4F0';
const WHITE = '#F2ECFF';
const DIM = '#A294C4';

const REFRESH_SECONDS = 900;     // 15 minutes; open-meteo updates hourly
const FORECAST_DAYS = 4;         // today plus the three shown in the strip

/** WMO weather code -> short label. */
function describe(code) {
    if (code === 0) return 'CLEAR';
    if (code === 1) return 'MOSTLY CLEAR';
    if (code === 2) return 'PARTLY CLOUDY';
    if (code === 3) return 'OVERCAST';
    if (code === 45 || code === 48) return 'FOG';
    if (code >= 51 && code <= 57) return 'DRIZZLE';
    if (code >= 61 && code <= 67) return 'RAIN';
    if (code >= 71 && code <= 77) return 'SNOW';
    if (code >= 80 && code <= 82) return 'SHOWERS';
    if (code === 85 || code === 86) return 'SNOW SHOWERS';
    if (code >= 95) return 'THUNDERSTORM';
    return '--';
}

function tint(code) {
    if (code < 0) return DIM;
    if (code <= 1) return RED;
    if (code <= 3 || code === 45 || code === 48) return VIOLET;
    if (code >= 71 && code <= 77) return WHITE;
    if (code >= 95) return GREEN;
    return BLUE;
}

function glyph(code) {
    if (code < 0) return '◆';
    if (code <= 1) return '✦';
    if (code <= 3) return '◧';
    if (code === 45 || code === 48) return '≡';
    if ((code >= 71 && code <= 77) || code === 85 || code === 86) return '❄';
    if (code >= 95) return '⚡';
    if (code >= 80) return '⌇';
    if (code >= 51) return '⋮';
    return '◆';
}

/** A finite coordinate in range, or null. Config files are input. */
function coord(value, limit) {
    const n = Number(value);
    if (!Number.isFinite(n) || Math.abs(n) > limit) return null;
    return n;
}

/** 'YYYY-MM-DD' -> 'MON'. */
function weekday(isoDate) {
    const dt = GLib.DateTime.new_from_iso8601(`${isoDate}T12:00:00Z`, null);
    return dt ? dt.format('%a').toUpperCase() : '--';
}

const CapriWeatherWidget = GObject.registerClass(
    class CapriWeatherWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-weather',
                vertical: true,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
                reactive: true,
            });

            this._config = config || {};
            this._latitude = coord(this._config.latitude, 90);
            this._longitude = coord(this._config.longitude, 180);
            this._timeoutId = null;
            this._session = null;

            this._buildUi();

            // Click anywhere to refresh, as the Plasma version did.
            this.connect('button-press-event', () => {
                this._fetch();
                return Clutter.EVENT_STOP;
            });

            if (this._latitude === null || this._longitude === null) {
                this._showMessage('SET A LOCATION',
                    'add latitude and longitude to this widget’s config');
                return;
            }

            this._fetch();
            this._timeoutId = GLib.timeout_add_seconds(
                GLib.PRIORITY_LOW, REFRESH_SECONDS, () => {
                    this._fetch();
                    return GLib.SOURCE_CONTINUE;
                });
        }

        _buildUi() {
            const header = new St.BoxLayout({ vertical: false, x_expand: true });
            header.add_child(new St.Label({
                text: 'WEATHER',
                style: 'font-family: "Quicksand"; font-size: 16px;'
                    + ` font-weight: 900; letter-spacing: 3px; color: ${RED};`,
            }));
            const spacer = new St.Widget({ x_expand: true });
            header.add_child(spacer);
            this._place = new St.Label({
                text: (this._config.place || '').toUpperCase(),
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-family: "Quicksand"; font-size: 14px; font-weight: bold; color: ${DIM};`,
            });
            header.add_child(this._place);
            this.add_child(header);

            const current = new St.BoxLayout({
                vertical: false,
                style: 'spacing: 16px; padding-top: 4px;',
            });

            this._glyph = new St.Label({
                text: glyph(-1),
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-size: 44px; color: ${DIM};`,
            });
            current.add_child(this._glyph);

            const tempColumn = new St.BoxLayout({
                vertical: true,
                y_align: Clutter.ActorAlign.CENTER,
            });
            this._temp = new St.Label({
                text: '--°',
                style: 'font-family: "Quicksand"; font-size: 38px;'
                    + ` font-weight: 900; color: ${WHITE};`,
            });
            this._condition = new St.Label({
                text: 'LOADING',
                style: 'font-family: "Quicksand"; font-size: 13px;'
                    + ` font-weight: bold; letter-spacing: 1.5px; color: ${DIM};`,
            });
            tempColumn.add_child(this._temp);
            tempColumn.add_child(this._condition);
            current.add_child(tempColumn);

            const stats = new St.BoxLayout({
                vertical: true,
                y_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 3px; padding-left: 10px;',
            });
            this._stats = {};
            for (const key of ['feels', 'humid', 'wind']) {
                const row = new St.BoxLayout({ vertical: false, style: 'spacing: 8px;' });
                row.add_child(new St.Label({ text: key, style_class: 'capri-weather-key' }));
                const value = new St.Label({ text: '--', style_class: 'capri-weather-val' });
                row.add_child(value);
                this._stats[key] = value;
                stats.add_child(row);
            }
            current.add_child(stats);
            this.add_child(current);

            this._strip = new St.BoxLayout({
                vertical: false,
                x_expand: true,
                style: 'spacing: 10px; padding-top: 6px;',
            });
            this.add_child(this._strip);
        }

        _showMessage(title, detail) {
            this._temp.set_text('');
            this._condition.set_text(title);
            this._condition.set_style('font-family: "Quicksand"; font-size: 13px;'
                + ` font-weight: bold; letter-spacing: 1.5px; color: ${RED};`);
            this._place.set_text(detail.toUpperCase());
        }

        _fetch() {
            if (this._latitude === null || this._longitude === null) return;

            const url = 'https://api.open-meteo.com/v1/forecast'
                + `?latitude=${this._latitude}&longitude=${this._longitude}`
                + '&current=temperature_2m,relative_humidity_2m,'
                + 'apparent_temperature,weather_code,wind_speed_10m'
                + '&daily=weather_code,temperature_2m_max,temperature_2m_min'
                + `&timezone=auto&forecast_days=${FORECAST_DAYS}`;

            if (!this._session) {
                // A generic agent string: the shell should not announce this
                // machine to a weather API.
                this._session = new Soup.Session({
                    user_agent: 'capri-weather/1',
                    timeout: 20,
                });
            }

            const message = Soup.Message.new('GET', url);
            this._session.send_and_read_async(
                message, GLib.PRIORITY_LOW, null, (session, result) => {
                    let text;
                    try {
                        const bytes = session.send_and_read_finish(result);
                        if (message.get_status() !== Soup.Status.OK) return;
                        text = new TextDecoder().decode(bytes.get_data());
                    } catch (e) {
                        return;     // offline: keep the last good reading
                    }
                    try {
                        this._apply(JSON.parse(text));
                    } catch (e) {
                        logError(e, '[capri] weather: unreadable response');
                    }
                });
        }

        _apply(data) {
            const now = data.current;
            if (!now) return;

            const code = now.weather_code;
            this._glyph.set_text(glyph(code));
            this._glyph.set_style(`font-size: 44px; color: ${tint(code)};`);
            this._temp.set_text(`${Math.round(now.temperature_2m)}°`);
            this._condition.set_text(describe(code));
            this._condition.set_style('font-family: "Quicksand"; font-size: 13px;'
                + ` font-weight: bold; letter-spacing: 1.5px; color: ${tint(code)};`);
            this._place.set_text((this._config.place || '').toUpperCase());

            this._stats.feels.set_text(`${Math.round(now.apparent_temperature)}°`);
            this._stats.humid.set_text(`${now.relative_humidity_2m}%`);
            this._stats.wind.set_text(`${Math.round(now.wind_speed_10m)} km/h`);

            this._strip.destroy_all_children();
            const daily = data.daily;
            if (!daily || !daily.time) return;
            // From index 1: index 0 is today, already shown above.
            for (let i = 1; i < Math.min(FORECAST_DAYS, daily.time.length); i++) {
                this._strip.add_child(this._makeDay(
                    weekday(daily.time[i]),
                    daily.weather_code[i],
                    Math.round(daily.temperature_2m_max[i]),
                    Math.round(daily.temperature_2m_min[i])));
            }
        }

        _makeDay(day, code, high, low) {
            const card = new St.BoxLayout({
                style_class: 'capri-weather-day',
                vertical: false,
                height: 44,
                x_expand: true,
                x_align: Clutter.ActorAlign.FILL,
                style: 'spacing: 8px;',
            });
            const centred = new St.BoxLayout({
                vertical: false,
                x_expand: true,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
                style: 'spacing: 8px;',
            });
            for (const [text, style] of [
                [day, `font-weight: 900; color: ${DIM};`],
                [glyph(code), `font-size: 14px; color: ${tint(code)};`],
                [`${high}°`, `font-weight: 900; color: ${WHITE};`],
                [`${low}°`, `font-weight: bold; color: ${VIOLET};`],
            ]) {
                centred.add_child(new St.Label({
                    text,
                    y_align: Clutter.ActorAlign.CENTER,
                    style: `font-family: "Quicksand"; font-size: 12px; ${style}`,
                }));
            }
            card.add_child(centred);
            return card;
        }

        destroy() {
            if (this._timeoutId) {
                GLib.source_remove(this._timeoutId);
                this._timeoutId = null;
            }
            if (this._session) {
                this._session.abort();
                this._session = null;
            }
            super.destroy();
        }
    },
);

export default {
    createWidget: (config) => new CapriWeatherWidget(config),
};
