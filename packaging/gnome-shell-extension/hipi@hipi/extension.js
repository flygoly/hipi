import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Tooltips from 'resource:///org/gnome/shell/ui/tooltips.js';

const STATUS_BASENAME = 'hipi-status.json';
const DEFAULT_LAUNCH = 'hipi ui';

const HiPiIndicator = GObject.registerClass(
class HiPiIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'HiPi');

        this._label = new St.Label({text: 'HiPi --', y_align: Clutter.ActorAlign.CENTER});
        this.add_child(this._label);
        this._styleClass = 'hipi-label-off';
        this._label.add_style_class_name(this._styleClass);

        this._path = `${GLib.get_user_runtime_dir()}/${STATUS_BASENAME}`;
        this._launchCmd = DEFAULT_LAUNCH;
        this._tooltipText = 'HiPi 状态';

        this._tooltip = new Tooltips.Tooltip(this, this._tooltipText);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const refreshItem = new PopupMenu.PopupMenuItem('刷新状态');
        refreshItem.connect('activate', () => this._refresh());
        this.menu.addMenuItem(refreshItem);
        const openItem = new PopupMenu.PopupMenuItem('打开 HiPi');
        openItem.connect('activate', () => this._launchApp());
        this.menu.addMenuItem(openItem);

        this.connect('button-press-event', (_actor, event) => {
            const button = event.get_button();
            if (button === Clutter.BUTTON_PRIMARY) {
                this._launchApp();
                return Clutter.EVENT_STOP;
            }
            if (button === Clutter.BUTTON_MIDDLE) {
                this._refresh();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        this._timeout = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }

    _launchApp() {
        try {
            GLib.spawn_command_line_async(this._launchCmd);
        } catch (e) {
            log(`HiPi launch failed: ${e}`);
        }
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

    _setTooltip(text) {
        this._tooltipText = text;
        this._tooltip.set_text(text);
    }

    _refresh() {
        try {
            const [, bytes] = GLib.file_get_contents(this._path);
            const text = new TextDecoder().decode(bytes);
            const status = JSON.parse(text);
            if (status.launch_command)
                this._launchCmd = status.launch_command;
            if (!status.modem_present) {
                this._setStyleClass('hipi-label-off');
                this._label.text = 'HiPi ✕';
                const hint = status.modem_hint || '未检测到 4G 模组';
                this._setTooltip(`${hint}\n左键打开 HiPi，中键刷新`);
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
            const tech = (m.access_technologies || []).join(', ') || '未知';
            this._setTooltip(
                `${op || '运营商未知'} · ${signal}% · ${tech}` +
                (unread > 0 ? `\n未读短信 ${unread} 条` : '') +
                '\n左键打开 HiPi，中键刷新'
            );
        } catch (_e) {
            this._setStyleClass('hipi-label-off');
            this._label.text = 'HiPi …';
            this._setTooltip('hipi-daemon 未运行或状态文件不可用\n左键打开 HiPi，中键刷新');
        }
    }

    destroy() {
        if (this._timeout)
            GLib.source_remove(this._timeout);
        this._tooltip?.destroy();
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
