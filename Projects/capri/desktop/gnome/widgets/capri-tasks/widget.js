// Capri Tasks - a GNOME Shell port of the Plasma capri.tasks widget.
//
// A plain checklist: type to add, left-click to tick, right-click to remove.
// This is NOT the TickTick list. Capri's reminder delivery reads TickTick
// through her own daemon; this widget is the scratch list that lived in the
// Plasma widget's own config, and it stays deliberately separate.
//
// Storage: ~/.local/share/capri/tasks.json, via GLib's user data dir. The
// Plasma version persisted into the plasmoid's config; the GNOME host has no
// way for a plugin to write back into profiles-json, so the widget owns its
// own file. That path matters for another reason - it is outside the
// repository, so a task the user types can never end up in a commit. This
// repository is public and pushes on commit, and his task titles are his.
//
// Every write is atomic (write to a temporary file, then rename) so a crash
// mid-save cannot leave a truncated list behind.
//
// One caveat worth knowing: these widgets are placed on the shell's
// background layer, below windows. Whether click and keyboard events reach
// an actor down there has to be confirmed on a running shell - if they do
// not, the list still displays correctly and only editing is affected.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import St from 'gi://St';

const RED = '#FF0033';
const GREEN = '#00FF55';
const VIOLET = '#8A3CE8';
const WHITE = '#F2ECFF';
const DIM = '#A294C4';
const INK = '#0A0812';

const WIDTH = 420;
const LIST_HEIGHT = 190;
const MAX_TASKS = 200;

function storePath() {
    return GLib.build_filenamev([GLib.get_user_data_dir(), 'capri', 'tasks.json']);
}

function loadTasks() {
    try {
        const [ok, bytes] = GLib.file_get_contents(storePath());
        if (!ok) return [];
        const parsed = JSON.parse(new TextDecoder().decode(bytes));
        if (!Array.isArray(parsed)) return [];
        return parsed
            .filter((t) => t && typeof t.text === 'string')
            .slice(0, MAX_TASKS)
            .map((t) => ({ text: t.text, done: !!t.done }));
    } catch (_e) {
        return [];     // missing or corrupt: start empty rather than throw
    }
}

function saveTasks(tasks) {
    try {
        const path = storePath();
        const dir = GLib.path_get_dirname(path);
        GLib.mkdir_with_parents(dir, 0o700);
        const file = Gio.File.new_for_path(path);
        // replace_contents with make_backup=false and an atomic rename.
        file.replace_contents(
            new TextEncoder().encode(JSON.stringify(tasks, null, 2)),
            null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
    } catch (e) {
        logError(e, '[capri] tasks: could not save');
    }
}

const CapriTasksWidget = GObject.registerClass(
    class CapriTasksWidget extends St.BoxLayout {
        constructor(config) {
            super({
                style_class: 'capri-tasks',
                vertical: true,
                width: WIDTH,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });

            this._config = config || {};
            this._tasks = loadTasks();

            this._buildUi();
            this._refresh();
        }

        _buildUi() {
            const header = new St.BoxLayout({ vertical: false, x_expand: true });
            header.add_child(new St.Label({
                text: 'TASKS',
                style: 'font-family: "Quicksand"; font-size: 16px;'
                    + ` font-weight: 900; letter-spacing: 3px; color: ${RED};`,
            }));
            header.add_child(new St.Widget({ x_expand: true }));
            this._count = new St.Label({
                text: '0/0',
                y_align: Clutter.ActorAlign.CENTER,
                style: `font-family: "Quicksand"; font-size: 15px; font-weight: bold; color: ${GREEN};`,
            });
            header.add_child(this._count);
            this.add_child(header);

            this._entry = new St.Entry({
                style_class: 'capri-tasks-entry',
                hint_text: 'add a task, press enter',
                can_focus: true,
                x_expand: true,
            });
            this._entry.clutter_text.connect('activate', (text) => {
                const value = text.get_text().trim();
                if (value.length === 0) return;
                if (this._tasks.length >= MAX_TASKS) return;
                this._tasks.push({ text: value, done: false });
                text.set_text('');
                this._commit();
            });
            this.add_child(this._entry);

            this._list = new St.BoxLayout({
                vertical: true,
                style: 'spacing: 3px;',
            });

            const scroll = new St.ScrollView({
                height: LIST_HEIGHT,
                x_expand: true,
                hscrollbar_policy: St.PolicyType.NEVER,
                vscrollbar_policy: St.PolicyType.AUTOMATIC,
                overlay_scrollbars: true,
            });
            // St.ScrollView.add_actor was replaced by set_child; accept either
            // so this widget survives a shell that predates the rename.
            if (typeof scroll.set_child === 'function')
                scroll.set_child(this._list);
            else
                scroll.add_actor(this._list);
            this.add_child(scroll);
        }

        _commit() {
            saveTasks(this._tasks);
            this._refresh();
        }

        _refresh() {
            this._list.destroy_all_children();

            const done = this._tasks.filter((t) => t.done).length;
            this._count.set_text(`${done}/${this._tasks.length}`);

            this._tasks.forEach((task, index) => {
                this._list.add_child(this._makeRow(task, index));
            });
        }

        _makeRow(task, index) {
            const row = new St.BoxLayout({
                style_class: 'capri-tasks-row',
                vertical: false,
                reactive: true,
                x_expand: true,
                style: 'spacing: 9px;',
            });

            const box = new St.Widget({
                width: 17,
                height: 17,
                y_align: Clutter.ActorAlign.CENTER,
                layout_manager: new Clutter.BinLayout(),
                style: `border: 2px solid ${task.done ? GREEN : VIOLET};`
                    + ` border-radius: 5px;`
                    + (task.done ? ` background-color: ${GREEN};` : ''),
            });
            if (task.done) {
                box.add_child(new St.Label({
                    text: '✓',
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                    style: `font-size: 12px; font-weight: bold; color: ${INK};`,
                }));
            }
            row.add_child(box);

            const label = new St.Label({
                text: task.text,
                y_align: Clutter.ActorAlign.CENTER,
                x_expand: true,
                style: 'font-family: "Quicksand"; font-size: 15px;'
                    + ` color: ${task.done ? DIM : WHITE};`,
            });
            label.clutter_text.set_ellipsize(3 /* Pango ELLIPSIZE_END */);
            if (task.done) {
                // St has no text-decoration, so strike through with the
                // attribute Pango itself understands.
                label.clutter_text.set_use_markup(true);
                label.clutter_text.set_markup(
                    `<s>${GLib.markup_escape_text(task.text, -1)}</s>`);
            }
            row.add_child(label);

            row.connect('button-press-event', (_actor, event) => {
                // 3 is the right button: remove. Anything else toggles.
                if (event.get_button() === 3)
                    this._tasks.splice(index, 1);
                else
                    this._tasks[index].done = !this._tasks[index].done;
                this._commit();
                return Clutter.EVENT_STOP;
            });

            return row;
        }
    },
);

export default {
    createWidget: (config) => new CapriTasksWidget(config),
};
