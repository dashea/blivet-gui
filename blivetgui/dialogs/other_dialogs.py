# -*- coding: utf-8 -*-
# other_dialogs.py
# misc Gtk.Dialog classes
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
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gtk, GdkPixbuf

from blivetgui.gui_utils import locate_ui_file
from .helpers import adjust_scrolled_size

from ..i18n import _

# ---------------------------------------------------------------------------- #


class AboutDialog(object):
    """ Standard 'about application' dialog
    """

    def __init__(self, parent_window, version):

        builder = Gtk.Builder()
        builder.set_translation_domain("blivet-gui")
        builder.add_from_file(locate_ui_file('about_dialog.ui'))
        dialog = builder.get_object("about_dialog")

        dialog.set_transient_for(parent_window)
        dialog.set_translator_credits(_("translator-credits"))
        dialog.set_version(version)

        dialog.show_all()
        dialog.run()
        dialog.destroy()


class AddLabelDialog(object):
    """ Dialog window allowing user to add disklabel to disk
    """

    def __init__(self, parent_window, disklabels):
        """

            :param parent_window: parent window
            :type parent_window: Gtk.Window

        """

        builder = Gtk.Builder()
        builder.set_translation_domain("blivet-gui")
        builder.add_from_file(locate_ui_file('add_disklabel_dialog.ui'))
        self.dialog = builder.get_object("dialog")
        self.pttype_combo = builder.get_object("pttype_combo")

        self.dialog.set_transient_for(parent_window)

        for disklabel in disklabels:
            self.pttype_combo.append_text(disklabel)

        self.pttype_combo.set_active(0)

        self.dialog.show_all()

    def run(self):
        response = self.dialog.run()
        label = self.pttype_combo.get_active_text()

        self.dialog.destroy()

        if response == Gtk.ResponseType.OK:
            return label
        else:
            return None


class LuksPassphraseDialog(object):
    """ Dialog window allowing user to enter passphrase to decrypt
    """

    def __init__(self, parent_window):
        """

            :param parent_window: parent window
            :type parent_window: Gtk.Window

        """

        builder = Gtk.Builder()
        builder.set_translation_domain("blivet-gui")
        builder.add_from_file(locate_ui_file('luks_passphrase_dialog.ui'))
        self.dialog = builder.get_object("dialog")

        self.dialog.set_transient_for(parent_window)

        self.entry_passphrase = builder.get_object("entry_passphrase")
        self.dialog.show_all()

    def run(self):

        response = self.dialog.run()
        passphrase = self.entry_passphrase.get_text()
        self.dialog.destroy()

        if response == Gtk.ResponseType.OK:
            return passphrase

        else:
            return None


class KickstartFileSaveDialog(object):
    """ File choose dialog for kickstart file save
    """
    def __init__(self, parent_window):

        builder = Gtk.Builder()
        builder.set_translation_domain("blivet-gui")
        builder.add_from_file(locate_ui_file('kickstart_filesave_dialog.ui'))
        self.dialog = builder.get_object("kickstart_filesave_dialog")

        self.dialog.set_transient_for(parent_window)

    def run(self):

        response = self.dialog.run()

        if response == 1:
            filepath = self.dialog.get_filename()
            self.dialog.destroy()
            return filepath

        else:
            self.dialog.destroy()
            return


class KickstartSelectDevicesDialog(Gtk.Dialog):
    """ Dialog window allowing user to select which devices will be used in
        kickstart mode
    """

    def __init__(self, parent_window, blivet_disks):
        """

            :param parent_window: parent_window
            :type parent_window: Gtk.Window
            :param blivet_disks: disks in the system
            :type blivet_disks: blivet.Device

        """

        self.parent_window = parent_window
        self.blivet_disks = blivet_disks

        Gtk.Dialog.__init__(self, _("Select devices"), None, 0,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                             Gtk.STOCK_OK, Gtk.ResponseType.OK))

        self.set_transient_for(self.parent_window)
        self.set_resizable(False)
        self.set_border_width(10)

        self.grid = Gtk.Grid(column_homogeneous=False, row_spacing=10, column_spacing=5)

        box = self.get_content_area()
        box.add(self.grid)

        self.disks_store, scrolledwindow = self.add_device_list()
        self.boot_check, self.boot_device_combo = self.add_bootloader_chooser()

        screen = self.parent_window.get_screen()
        adjust_scrolled_size(scrolledwindow, screen.get_width() * 0.5, screen.get_height() * 0.5)

        self.show_all()

        # yes, it is neccessary to call this twice, don't know why, just some Gtk magic
        adjust_scrolled_size(scrolledwindow, screen.get_width() * 0.5, screen.get_height() * 0.5)

    def add_device_list(self):

        disks_store = Gtk.ListStore(object, bool, GdkPixbuf.Pixbuf, str)
        disks_view = Gtk.TreeView(model=disks_store)

        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_cell_toggled)
        column_toggle = Gtk.TreeViewColumn(None, renderer_toggle, active=1)
        disks_view.append_column(column_toggle)

        renderer_pixbuf = Gtk.CellRendererPixbuf()
        column_pixbuf = Gtk.TreeViewColumn(None, renderer_pixbuf, pixbuf=2)
        disks_view.append_column(column_pixbuf)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn('Pango Markup', renderer_text, markup=3)
        disks_view.append_column(column_text)

        disks_view.set_headers_visible(False)

        icon_theme = Gtk.IconTheme.get_default()
        icon_disk = Gtk.IconTheme.load_icon(icon_theme, "drive-harddisk", 32, 0)
        icon_disk_usb = Gtk.IconTheme.load_icon(icon_theme, "drive-removable-media", 32, 0)

        for disk in self.blivet_disks:
            if disk.removable:
                disks_store.append([disk, False, icon_disk_usb,
                                    str(disk.name) + "\n<i><small>" + str(disk.model) + "</small></i>"])
            else:
                disks_store.append([disk, False, icon_disk,
                                    str(disk.name) + "\n<i><small>" + str(disk.model) + "</small></i>"])

        label_list = Gtk.Label(label=_("Please select at least one of shown devices:"), xalign=1)
        label_list.get_style_context().add_class("dim-label")

        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.add(disks_view)

        self.grid.attach(label_list, 0, 1, 1, 1)
        self.grid.attach(scrolledwindow, 0, 2, 4, 2)

        return disks_store, scrolledwindow

    def on_cell_toggled(self, _event, path):
        self.disks_store[path][1] = not self.disks_store[path][1]

    def add_bootloader_chooser(self):

        label_boot = Gtk.Label(label=_("Install bootloader?:"))
        label_boot.get_style_context().add_class("dim-label")
        self.grid.attach(label_boot, 0, 4, 1, 1)

        boot_check = Gtk.CheckButton()
        self.grid.attach(boot_check, 1, 4, 1, 1)
        boot_check.connect("clicked", self.on_boot_changed)

        label_boot_device = Gtk.Label(label=_("Device to install bootloader:"))
        label_boot_device.get_style_context().add_class("dim-label")
        self.grid.attach(label_boot_device, 0, 5, 1, 1)

        boot_device_combo = Gtk.ComboBoxText()
        boot_device_combo.set_entry_text_column(0)
        boot_device_combo.set_sensitive(False)
        self.grid.attach(boot_device_combo, 1, 5, 2, 1)

        for disk in self.blivet_disks:
            boot_device_combo.append_text(disk.name)

        return boot_check, boot_device_combo

    def on_boot_changed(self, _event):
        self.boot_device_combo.set_sensitive(not self.boot_device_combo.get_sensitive())

    def get_selection(self):
        """ Get user input
        """

        selected_disks_names = []

        for row in self.disks_store:
            if not row[1]:
                selected_disks_names.append(row[0].name)

        return (selected_disks_names, self.boot_device_combo.get_sensitive(),
                self.boot_device_combo.get_active_text())
