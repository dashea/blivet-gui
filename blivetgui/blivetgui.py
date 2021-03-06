# -*- coding: utf-8 -*-
# list_partitions.py
# Main blivet-gui class for GUI
#
# Copyright (C) 2014  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
# Red Hat Author(s): Vojtech Trefny <vtrefny@redhat.com>
#
# ---------------------------------------------------------------------------- #

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gtk, GLib

from blivet.size import Size

from .list_devices import ListDevices
from .list_partitions import ListPartitions
from .list_parents import ListParents
from .list_actions import ListActions
from .main_menu import MainMenu
from .actions_menu import ActionsMenu
from .actions_toolbar import ActionsToolbar, DeviceToolbar
from .visualization.logical_view import LogicalView
from .visualization.physical_view import PhysicalView

from .communication.client import BlivetGUIClient

from .logs import set_logging, set_python_meh, remove_logs
from .i18n import _
from .gui_utils import locate_ui_file
from .dialogs import message_dialogs, other_dialogs, edit_dialog, add_dialog, device_info_dialog
from .processing_window import ProcessingActions
from .loading_window import LoadingWindow

import threading
import os
import sys
import atexit

# ---------------------------------------------------------------------------- #


class BlivetGUI(object):
    """ Class representing the GUI part of the application. It creates all the
        Gtk.Widgets used in blivet-gui.
    """

    def __init__(self, server_socket, secret, version, kickstart_mode=False):

        self.server_socket = server_socket
        self.secret = secret
        self.version = version
        self.kickstart_mode = kickstart_mode

        self.builder = Gtk.Builder()
        self.builder.set_translation_domain("blivet-gui")
        self.builder.add_from_file(locate_ui_file("blivet-gui.ui"))

        # MainWindow
        self.main_window = self.builder.get_object("main_window")
        self.main_window.connect("delete-event", self.quit)

        # BlivetUtils
        self.client = BlivetGUIClient(self, self.server_socket, self.secret)
        dialog = LoadingWindow(self.main_window)
        ret = self.blivet_init(dialog)

        if not ret.success:  # pylint: disable=maybe-no-member
            if ret.reason == "running":
                msg = _("blivet-gui is already running.")

                self.show_error_dialog(msg)
                self.client.quit()
                sys.exit(1)
            else:
                self._reraise_exception(ret.exception, ret.traceback)

        # Logging
        blivetgui_logfile, self.log = set_logging(component="blivet-gui")

        server_logs = self.client.remote_control("logs", blivetgui_logfile)
        log_files = server_logs + [blivetgui_logfile]

        handler = set_python_meh(log_files=log_files)
        handler.install(None)

        atexit.register(remove_logs, log_files=[blivetgui_logfile])
        atexit.register(self.client.quit)

        # Supported types
        self._get_supported_types()

        # Kickstart devices dialog
        if self.kickstart_mode:
            self.use_disks = self.kickstart_disk_selection()

        # MainMenu
        self.main_menu = MainMenu(self)

        # ActionsMenu
        self.popup_menu = ActionsMenu(self)

        # ActionsToolbar
        self.device_toolbar = DeviceToolbar(self)
        self.actions_toolbar = ActionsToolbar(self)

        # ListDevices
        self.list_devices = ListDevices(self)

        # ListPartitions
        self.list_partitions = ListPartitions(self)

        # ListParents
        self.list_parents = ListParents(self)

        # ListActions
        self.label_actions = self.builder.get_object("label_actions")
        self.label_actions.connect("activate-link", self.show_actions)
        self.list_actions = ListActions(self)

        # Vizualisation
        self.logical_view = LogicalView(self)
        self.builder.get_object("image_window").add(self.logical_view.hbox)

        self.physical_view = PhysicalView(self)
        self.builder.get_object("scrolledwindow_physical").add(self.physical_view.vbox)

        # select first device in ListDevice
        self.list_devices.disks_view.set_cursor(1)
        self.main_window.show_all()
        self.list_devices.disks_view.set_cursor(0)

    def _get_supported_types(self):
        """ Get various supported 'types' (filesystems, raid levels...) from
            blivet and store them for future use
        """

        self._supported_raid_levels = {"btrfs volume": self.client.remote_call("get_available_raid_levels", "btrfs volume"),
                                       "mdraid": self.client.remote_call("get_available_raid_levels", "mdraid")}
        self._supported_filesystems = self.client.remote_call("get_available_filesystems")
        self._supported_disklabels = self.client.remote_call("get_available_disklabels", True)

    def _set_physical_view_visible(self, visible):
        notebook = self.builder.get_object("notebook_views")
        physical_page = notebook.get_nth_page(1)

        if visible:
            physical_page.show()
        else:
            physical_page.hide()

    def update_partitions_view(self):
        self.list_partitions.update_partitions_list(self.list_devices.selected_device)
        self.logical_view.visualize_devices(self.list_partitions.partitions_list)

    def update_physical_view(self):
        self.list_parents.update_parents_list(self.list_devices.selected_device)
        self.physical_view.visualize_parents(self.list_parents.parents_list)

        if self.list_devices.selected_device.is_disk:
            self._set_physical_view_visible(False)
        else:
            self._set_physical_view_visible(True)

    def activate_action_buttons(self, activate):
        """ Set the actions toolbar buttons (in)active
        """

        if activate:
            self.actions_toolbar.activate_buttons(["clear", "apply", "undo"])
        else:
            self.actions_toolbar.deactivate_buttons(["clear", "apply", "undo"])

    def activate_device_actions(self, activate_list):
        """ Activate available device actions in device toolbar and popup menu

            :param activate_list: list of items to activate
            :type activate_list: list of str

        """

        for item in activate_list:
            self.device_toolbar.activate_buttons([item])
            self.popup_menu.activate_menu_items([item])

    def deactivate_device_actions(self, deactivate_list):
        """ Deactivate toolbar buttons and menu items

            :param deactivate_list: list of items to deactivate
            :type deactivate_list: list of str

        """

        for item in deactivate_list:
            self.device_toolbar.deactivate_buttons([item])
            self.popup_menu.deactivate_menu_items([item])

    def deactivate_all_actions(self):
        """ Deactivate all partition-based buttons/menu items
        """

        self.device_toolbar.deactivate_all()
        self.popup_menu.deactivate_all()

    def kickstart_disk_selection(self):
        disks = self.client.remote_call("get_disks")

        if len(disks) == 0:
            msg = _("blivet-gui failed to find at least one storage device to work with.\n\n"
                    "Please connect a storage device to your computer and re-run blivet-gui.")

            self.show_error_dialog(msg)
            self.quit()

        dialog = other_dialogs.KickstartSelectDevicesDialog(self.main_window, disks)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            use_disks, install_bootloader, bootloader_device = dialog.get_selection()
            dialog.destroy()

        else:
            dialog.destroy()
            sys.exit(0)

        if install_bootloader and bootloader_device:
            self.client.remote_call("set_bootloader_device", bootloader_device)

        self.client.remote_call("kickstart_hide_disks", use_disks)

        return use_disks

    def _reraise_exception(self, exception, traceback):
        raise type(exception)(str(exception) + "\n" + traceback)

    def show_exception_dialog(self, exception_data, exception_traceback):
        message_dialogs.ExceptionDialog(self.main_window, exception_data, exception_traceback)

    def show_error_dialog(self, error_message):
        message_dialogs.ErrorDialog(self.main_window, error_message)

    def show_warning_dialog(self, warning_message):
        message_dialogs.WarningDialog(self.main_window, warning_message)

    def show_confirmation_dialog(self, title, question):
        dialog = message_dialogs.ConfirmDialog(self.main_window, title, question)
        response = dialog.run()

        return response

    def _raise_exception(self, exception, traceback):
        raise exception.with_traceback(traceback)

    def switch_device_view(self, device):
        if not (device.is_disk or device.type in ("lvmvg", "btrfs volume", "mdarray")):
            raise ValueError

        self.list_devices.select_device_by_name(device.name)

    def device_information(self, _widget=None):
        """ Display information about currently selected device
        """

        blivet_device = self.list_partitions.selected_partition[0]

        dialog = device_info_dialog.DeviceInformationDialog(self.main_window, blivet_device)
        dialog.run()
        dialog.destroy()

    def edit_device(self, _widget=None):
        """ Edit selected device

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        device = self.list_partitions.selected_partition[0]

        if device.type in ("partition", "lvmlv", "luks/dm-crypt"):
            dialog = edit_dialog.PartitionEditDialog(self.main_window, device,
                                                     self.client.remote_call("device_resizable", device),
                                                     self._supported_filesystems,
                                                     self.client.remote_call("get_mountpoints"),
                                                     self.kickstart_mode)

        elif device.type in ("lvmvg",):
            dialog = edit_dialog.LVMEditDialog(self.main_window, device,
                                               self.client.remote_call("get_free_pvs_info"),
                                               self.client.remote_call("get_free_disks_regions"),
                                               self.client.remote_call("get_removable_pvs_info", device))

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            user_input = dialog.get_selection()

            if device.type in ("partition", "lvmlv", "luks/dm-crypt"):
                result = self.client.remote_call("edit_partition_device", user_input)

            elif device.type in ("lvmvg",):
                result = self.client.remote_call("edit_lvmvg_device", user_input)

            if not result.success:
                if not result.exception:
                    self.show_error_dialog(result.message)

                else:
                    self._reraise_exception(result.exception, result.traceback)

            else:
                if result.actions:
                    action_str = _("edit {name} {type}").format(name=device.name, type=device.type)
                    self.list_actions.append("edit", action_str, result.actions)

            self.update_partitions_view()

        dialog.destroy()
        return

    def _allow_add_device(self, parent_device, parent_device_type):
        """ Allow add device?
        """

        msg = None

        if parent_device_type == "lvmvg" and not parent_device.complete:
            msg = _("{name} is not complete. It is not possible to add new LVs to VG with "
                    "missing PVs.").format(name=parent_device.name)

        # not enough free space for at least two 2 MiB physical extents
        if parent_device_type == "lvmpv" and parent_device.size < Size("4 MiB"):
            msg = _("Not enough free space for a new LVM Volume Group.")

        if parent_device.is_disk and parent_device.format and parent_device.format.type == "disklabel":
            disk = parent_device.format.parted_disk
            selected_device = self.list_partitions.selected_partition[0]
            if disk.primaryPartitionCount >= disk.maxPrimaryPartitionCount and selected_device.is_primary:
                msg = _("Disk {name} already reached maximum allowed number of primary partitions "
                        "for {label} disklabel.").format(name=parent_device.name, label=parent_device.format.label_type)

        return (False, msg) if msg else (True, None)

    def add_partition(self, _widget=None, btrfs_pt=False):
        """ Add new partition
            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()
            :param btrfs_pt: create btrfs as partition table
            :type btrfs_pt: bool
        """

        selected_device = self.list_partitions.selected_partition[0]

        parent_device_type = None

        # btrfs volume has no special free space device -- parent device for newly
        # created subvolume is not parent of selected device but device (btrfs volume)
        # itself
        # for snapshots 'parent' is the LV we are making snapshot
        if selected_device.type in ("btrfs volume", "lvmlv", "lvmthinpool"):
            parent_device = selected_device

        # empty lvmpv doesn't have a special free space device
        elif selected_device.type in ("partition", "luks/dm-crypt", "mdarray") and selected_device.format.type == "lvmpv":
            parent_device = selected_device
            parent_device_type = "lvmpv"

        else:
            parent_device = selected_device.parents[0]

            if parent_device.is_disk:
                parent_device_type = "disk"

        if not parent_device_type:
            parent_device_type = parent_device.type

        # allow adding new device?
        allow, msg = self._allow_add_device(parent_device, parent_device_type)

        if not allow:
            message_dialogs.ErrorDialog(self.main_window, msg)
            return

        if parent_device_type == "disk" and self.list_devices.selected_device.format.type != "disklabel" \
           and not btrfs_pt:

            dialog = other_dialogs.AddLabelDialog(self.main_window, self._supported_disklabels)

            selection = dialog.run()

            if selection == "btrfs":
                self.add_partition(btrfs_pt=True)
                return

            if selection:
                result = self.client.remote_call("create_disk_label", self.list_devices.selected_device, selection)
                if not result.success:
                    if not result.exception:
                        self.show_error_dialog(result.message)
                    else:
                        self._reraise_exception(result.exception, result.traceback)

                else:
                    if result.actions:
                        action_str = _("create new disklabel on {name}").format(name=self.list_devices.selected_device.name)
                        self.list_actions.append("add", action_str, result.actions)
                self.update_partitions_view()
            return

        # for snapshots we don't know the free space device because user doesn't choose one
        # we have the lvmlv and lvmvg information only
        if parent_device_type == "lvmlv":
            free_device = self.client.remote_call("get_vg_free", parent_device.parents[0])

        else:
            free_device = self.list_partitions.selected_partition[0]

        dialog = add_dialog.AddDialog(self.main_window,
                                      parent_device_type,
                                      parent_device,
                                      free_device,
                                      self.client.remote_call("get_free_pvs_info"),
                                      self.client.remote_call("get_free_disks_regions", btrfs_pt),
                                      self._supported_raid_levels,
                                      self._supported_filesystems,
                                      self.client.remote_call("get_mountpoints"),
                                      self.kickstart_mode)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:

            user_input = dialog.get_selection()
            result = self.client.remote_call("add_device", user_input)

            if not result.success:
                if not result.exception:
                    self.show_error_dialog(result.message)

                else:
                    self._reraise_exception(result.exception, result.traceback)

            else:
                if result.actions:
                    if not user_input.filesystem:
                        action_str = _("add {size} {type} device").format(size=str(user_input.size),
                                                                          type=user_input.device_type)
                    else:
                        action_str = _("add {size} {fmt} partition").format(size=str(user_input.size),
                                                                            fmt=user_input.filesystem)

                    self.list_actions.append("add", action_str, result.actions)

            self.list_devices.update_devices_view()
            self.update_partitions_view()

        dialog.destroy()
        return

    def delete_selected_partition(self, _widget=None):
        """ Delete selected partition

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        deleted_device = self.list_partitions.selected_partition[0]

        title = _("Confirm delete operation")
        msg = _("Are you sure you want delete device {name}?").format(name=deleted_device.name)

        dialog = message_dialogs.ConfirmDialog(self.main_window, title, msg)
        response = dialog.run()

        if response:
            result = self.client.remote_call("delete_device", deleted_device)

            if not result.success:
                if not result.exception:
                    self.show_error_dialog(result.message)

                else:
                    self._reraise_exception(result.exception, result.traceback)

            else:
                action_str = _("delete partition {name}").format(name=deleted_device.name)
                self.list_actions.append("delete", action_str, result.actions)

            self.update_partitions_view()
            self.list_devices.update_devices_view()

    def perform_actions(self, dialog):
        """ Perform queued actions
        """

        def end(success, error, traceback):
            if success:
                dialog.stop()

            else:
                dialog.destroy()
                self.main_window.set_sensitive(False)
                self._reraise_exception(error, traceback)  # pylint: disable=raising-bad-type

        def show_progress(message):
            dialog.progress_msg(message)

        def do_it():
            """ Run blivet.doIt()
            """

            result = self.client.remote_do_it(show_progress)
            if result.success:
                GLib.idle_add(end, True, None, None)

            else:
                self.client.remote_call("blivet_reset")
                GLib.idle_add(end, False, result.exception, result.traceback)

            return

        thread = threading.Thread(target=do_it)
        thread.start()
        dialog.start()
        thread.join()

        self.list_actions.clear()

        self.list_devices.update_devices_view()
        self.update_partitions_view()

    def apply_event(self, _widget=None):
        """ Apply event for main menu/toolbar

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        .. note::
                This is neccessary because of kickstart mode -- in "standard" mode
                we need only simple confirmation dialog, but in kickstart mode it
                is neccessary to create file choosing dialog for kickstart file save.

        """

        if self.kickstart_mode:

            dialog = other_dialogs.KickstartFileSaveDialog(self.main_window)

            response = dialog.run()

            if response:
                if os.path.isfile(response):
                    title = _("File already exists")
                    msg = _("Selected file already exists, do you want to overwrite it?")
                    dialog_file = message_dialogs.ConfirmDialog(self.main_window, title, msg)
                    response_file = dialog_file.run()

                    if not response_file:
                        return

                self.client.remote_call("create_kickstart_file", response)

                msg = _("File with your Kickstart configuration was successfully saved to:\n\n"
                        "{filename}").format(filename=response)
                message_dialogs.InfoDialog(self.main_window, msg)

        else:
            title = _("Confirm scheduled actions")
            msg = _("Are you sure you want to perform scheduled actions?")
            actions = self.client.remote_call("get_actions")

            dialog = message_dialogs.ConfirmActionsDialog(self.main_window, title, msg, self.list_actions.actions_list)

            response = dialog.run()

            if response:
                processing_dialog = ProcessingActions(self, actions)
                self.perform_actions(processing_dialog)

    def umount_partition(self, _widget=None):
        """ Unmount selected partition

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        result = self.client.remote_call("unmount_device", self.list_partitions.selected_partition[0])

        if not result:
            msg = _("Unmount failed. Are you sure device is not in use?")
            self.show_error_dialog(msg)

        self.update_partitions_view()

    def decrypt_device(self, _widget=None):
        """ Decrypt selected device

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()
        """

        dialog = other_dialogs.LuksPassphraseDialog(self.main_window)

        response = dialog.run()

        if response:
            ret = self.client.remote_call("luks_decrypt", self.list_partitions.selected_partition[0], response)

            if not ret:
                msg = _("Device decryption failed. Are you sure provided password is correct?")
                message_dialogs.ErrorDialog(self.main_window, msg)

                return

        self.list_devices.update_devices_view()
        self.update_partitions_view()

    def actions_undo(self, _widget=None):
        """ Undo last action

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        removed_actions = self.list_actions.pop()
        self.client.remote_call("blivet_cancel_actions", removed_actions)

        self.list_devices.update_devices_view()
        self.update_partitions_view()

    def clear_actions(self, _widget=None):
        """ Clear all scheduled actions

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        self.client.remote_call("blivet_reset")

        self.list_actions.clear()

        self.list_devices.update_devices_view()
        self.update_partitions_view()

    def show_actions(self, _widget=None, _uri=None):
        """ Show scheduled actions
        """

        dialog = message_dialogs.ShowActionsDialog(self.main_window, self.list_actions.actions_list)
        dialog.run()

        return True

    def blivet_init(self, dialog):
        """ Perform queued actions
        """

        ret = []

        def end():
            dialog.stop()

        def do_it(ret):
            ret.append(self.client.remote_control("init", self.kickstart_mode))
            GLib.idle_add(end)

        thread = threading.Thread(target=do_it, args=(ret,))
        thread.start()
        dialog.start()
        thread.join()

        return ret[0]

    def reload(self, _widget=None):
        """ Reload storage information

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        if self.list_actions.actions:
            title = _("Confirm reload storage")
            msg = _("There are pending operations. Are you sure you want to continue?")

            response = self.show_confirmation_dialog(title, msg)

            if not response:
                return

        self.client.remote_call("blivet_reset")

        if self.kickstart_mode:
            self.client.remote_call("kickstart_hide_disks", self.use_disks)

        self.list_actions.clear()

        self.list_devices.update_devices_view()
        self.update_partitions_view()

    def quit(self, _event=None, _widget=None):
        """ Quit blivet-gui

            :param widget: widget calling this function (only for calls via signal.connect)
            :type widget: Gtk.Widget()

        """

        if self.list_actions.actions:
            title = _("Are you sure you want to quit?")
            msg = _("There are pending operations. Are you sure you want to quit blivet-gui now?")

            response = self.show_confirmation_dialog(title, msg)

            if not response:
                return True

        Gtk.main_quit()
