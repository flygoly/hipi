import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const STATUS_BASENAME = 'hipi-status.json';

const HiPiIndicator = GObject.registerClass(
class HiPiIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'HiPi');

        this._label = new St.Label({text: 'HiPi --', y_align: Clutter.ActorAlign.CENTER});
        this.add_child(this._label);
        this._styleClass = 'hipi-label-off';
        this._label.add_style_class_name(this._styleClass);

        this._path = `${GLib.get_user_runtime_dir()}/${STATUS_BASENAME}`;

        this._timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }

    _setStyleClass(className) {
        if (this._styleClass)
            this._label.remove_style_class_name(this._styleClass);
        this._styleClass = className;
        this._label.add_style_class_name(className);
    }

    _signalClass(signal) {
        if (signal >= 60)
            return 'hipi-label-good';
        if (signal >= 30)
            return 'hipi-label-ok';
        return 'hipi-label-bad';
    }

    _refresh() {
        try {
            const [, bytes] = GLib.file_get_contents(this._path);
            const text = new TextDecoder().decode(bytes);
            const status = JSON.parse(text);
            if (!status.modem_present) {
                this._setStyleClass('hipi-label-off');
                this._label.text = 'HiPi ✕';
                return;
            }
            const m = status.modem || {};
            const signal = m.signal_quality ?? 0;
            const op = m.operator_name || m.operator_code || '';
            const short = op ? String(op).slice(0, 4) : '4G';
            const unread = status.unread_sms ?? 0;
            const badge = unread > 0 ? ` (${unread})` : '';
            this._setStyleClass(this._signalClass(signal));
            this._label.text = `${short} ${signal}%${badge}`;
        } catch (_e) {
            this._setStyleClass('hipi-label-off');
            this._label.text = 'HiPi …';
        }
    }

    destroy() {
        if (this._timeout)
            GLib.source_remove(this._timeout);
        super.destroy();
    }
});

export default class HiPiExtension extends Extension {
    enable() {
        this._indicator = new HiPiIndicator();
        Main.panel.addToStatusArea('hipi-indicator', this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
