# -*- coding: utf-8 -*-
# ClipMaster - Enhanced Clipboard Management for NVDA
# Copyright (C) 2026 Selvakumar G <jgfselva@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

import os
import json
import time
import shutil
import subprocess
import ctypes
import webbrowser
import re
from datetime import datetime
from ctypes import wintypes
import wx
import ui
import api
import gui
from logHandler import log

CATEGORIES = [
    "All",
    "Audio",
    "Video",
    "Images",
    "PDF",
    "PPT",
    "Documents",
    "Excel",
    "Text",
    "Files",
    "Folders"
]

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT

CF_HDROP = 15
FO_DELETE = 3
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010

class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR)
    ]

def send_to_recycle_bin(path):
    if not os.path.exists(path):
        return False
    try:
        buffer = ctypes.create_unicode_buffer(path + "\0\0")
        fileop = SHFILEOPSTRUCTW()
        fileop.hwnd = None
        fileop.wFunc = FO_DELETE
        fileop.pFrom = ctypes.cast(buffer, wintypes.LPCWSTR)
        fileop.pTo = None
        fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION
        return shell32.SHFileOperationW(ctypes.byref(fileop)) == 0
    except Exception as e:
        log.error(f"Error moving to Recycle Bin: {e}")
        return False

class ShareAppDialog(wx.Dialog):
    def __init__(self, parent, target_item):
        super(ShareAppDialog, self).__init__(
            parent, title="Select Application to Share", style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP
        )
        self.target_item = target_item
        self.apps = sorted([
            "ChatGPT",
            "Copy Path / Content to Clipboard",
            "Desktop Icons / Desktop Folder",
            "Facebook",
            "Gmail",
            "Google Gemini",
            "Instagram",
            "Messenger",
            "Telegram",
            "Unigram",
            "WhatsApp"
        ])

        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(self, label="Choose an application or service to share with:")
        sizer.Add(lbl, 0, wx.ALL, 8)

        self.app_list = wx.ListBox(self, choices=self.apps)
        self.app_list.SetSelection(0)
        sizer.Add(self.app_list, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ok = wx.Button(self, wx.ID_OK, label="&Share")
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        btn_sizer.Add(self.btn_ok, 0, wx.ALL, 5)
        btn_sizer.Add(self.btn_cancel, 0, wx.ALL, 5)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(sizer)
        self.Layout()
        self.app_list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.EndModal(wx.ID_OK))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

    def on_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def get_selected_app(self):
        sel = self.app_list.GetSelection()
        return self.apps[sel] if sel != wx.NOT_FOUND else self.apps[0]


class ClipSpeakHistoryDialog(wx.Dialog):
    def __init__(self, parent, handler, previous_hwnd=None):
        super(ClipSpeakHistoryDialog, self).__init__(
            parent, 
            title=f"{handler.user_name} Clipboard History", 
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.STAY_ON_TOP
        )
        self.handler = handler
        self.previous_hwnd = previous_hwnd
        self.current_level = "CATEGORIES"
        self.selected_category = "All"
        self.selected_date_folder = ""
        self.folder_path_stack = [] 
        self.display_mapping = [] 
        self.selected_items = []

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.label = wx.StaticText(self, label="Select Category:")
        main_sizer.Add(self.label, 0, wx.ALL, 5)
        
        self.list_box = wx.ListBox(self, choices=CATEGORIES)
        self.list_box.SetSelection(0)
        main_sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 5)

        self.action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_item_play = wx.Button(self, label="&Play")
        self.btn_item_open = wx.Button(self, label="&Open")
        self.btn_item_read = wx.Button(self, label="Read in &Notepad")
        self.btn_item_rename = wx.Button(self, label="&Rename")
        self.btn_item_move = wx.Button(self, label="&Move")
        self.btn_item_share = wx.Button(self, label="&Share")
        self.btn_item_delete = wx.Button(self, label="&Delete")

        for btn in [self.btn_item_play, self.btn_item_open, self.btn_item_read, 
                    self.btn_item_rename, self.btn_item_move, self.btn_item_share, self.btn_item_delete]:
            self.action_sizer.Add(btn, 0, wx.ALL, 3)

        main_sizer.Add(self.action_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.base_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_user_name = wx.Button(self, label="Change User Name")
        self.btn_edit_shortcut = wx.Button(self, label="Edit Shortcut Key")
        
        pwd_label = "Change / Remove Password" if self.handler.get_password() else "Set Password"
        self.btn_password = wx.Button(self, label=pwd_label)
        
        self.btn_target_path = wx.Button(self, label="Change Target Directory")
        self.btn_dictation = wx.Button(self, label="Soft Dictation")
        self.btn_close = wx.Button(self, label="&Close")

        for b in [self.btn_user_name, self.btn_edit_shortcut, self.btn_password, 
                  self.btn_target_path, self.btn_dictation, self.btn_close]:
            self.base_btn_sizer.Add(b, 0, wx.ALL, 5)

        main_sizer.Add(self.base_btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        self.SetSizer(main_sizer)
        self.Layout()

        self._update_button_visibility()

        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.Bind(wx.EVT_CLOSE, self.on_close_dialog)
        self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self.process_enter())
        self.list_box.Bind(wx.EVT_LISTBOX, self.on_list_selection_changed)

        self.btn_item_play.Bind(wx.EVT_BUTTON, self.on_action_open)
        self.btn_item_open.Bind(wx.EVT_BUTTON, self.on_action_open)
        self.btn_item_read.Bind(wx.EVT_BUTTON, self.on_action_read)
        self.btn_item_rename.Bind(wx.EVT_BUTTON, self.on_action_rename)
        self.btn_item_move.Bind(wx.EVT_BUTTON, self.on_action_move)
        self.btn_item_share.Bind(wx.EVT_BUTTON, self.on_action_share)
        self.btn_item_delete.Bind(wx.EVT_BUTTON, self.on_action_delete)

        self.btn_user_name.Bind(wx.EVT_BUTTON, lambda e: self.handler._prompt_change_user_name())
        self.btn_edit_shortcut.Bind(wx.EVT_BUTTON, lambda e: self.handler._prompt_edit_shortcut(self))
        self.btn_password.Bind(wx.EVT_BUTTON, lambda e: self.handler._prompt_set_password(self))
        self.btn_target_path.Bind(wx.EVT_BUTTON, lambda e: self.handler._change_global_save_path(self))
        self.btn_dictation.Bind(wx.EVT_BUTTON, lambda e: self.handler.start_dictation())
        self.btn_close.Bind(wx.EVT_BUTTON, lambda e: self.close_and_restore_focus())

    def close_and_restore_focus(self):
        self.EndModal(wx.ID_CANCEL)
        if self.previous_hwnd:
            try:
                user32.SetForegroundWindow(self.previous_hwnd)
            except Exception:
                pass

    def on_close_dialog(self, event):
        self.close_and_restore_focus()

    def _update_button_visibility(self):
        if self.current_level == "CATEGORIES":
            self.action_sizer.ShowItems(False)
            if self.selected_category == "All":
                self.base_btn_sizer.ShowItems(True)
            else:
                self.base_btn_sizer.ShowItems(False)
        elif self.current_level == "DATE_LEVEL":
            self.action_sizer.ShowItems(False)
            self.base_btn_sizer.ShowItems(False)
        elif self.current_level == "FILES_LEVEL":
            self.base_btn_sizer.ShowItems(False)
            self.action_sizer.ShowItems(True)
            cat = self.selected_category
            if cat in ["Audio", "Video"]:
                self.btn_item_play.Show()
                self.btn_item_open.Hide()
                self.btn_item_read.Hide()
            elif cat in ["Text", "Files"]:
                self.btn_item_play.Hide()
                self.btn_item_open.Show()
                self.btn_item_read.Show()
            else:
                self.btn_item_play.Hide()
                self.btn_item_open.Show()
                self.btn_item_read.Hide()

        self.action_sizer.Layout()
        self.base_btn_sizer.Layout()
        self.Layout()

    def load_date_folders(self, category):
        self.selected_category = category
        self.folder_path_stack = []
        cat_dir = os.path.join(self.handler.default_save_dir, category)
        
        if not os.path.exists(cat_dir) or not os.listdir(cat_dir):
            self.handler._announce_empty_category(category)
            self.navigate_back()
            return

        date_folders = [f for f in os.listdir(cat_dir) if os.path.isdir(os.path.join(cat_dir, f))]
        
        def parse_date(d_str):
            try:
                return datetime.strptime(d_str, "%B %d, %Y")
            except Exception:
                return datetime.min

        sorted_dates = sorted(date_folders, key=parse_date)

        if not sorted_dates:
            self.handler._announce_empty_category(category)
            self.navigate_back()
            return

        self.current_level = "DATE_LEVEL"
        self.label.SetLabel(f"Date Folders in {category}:")
        self.display_mapping = sorted_dates
        self.list_box.Set(sorted_dates)

        focus_index = 0
        if self.selected_date_folder in sorted_dates:
            focus_index = sorted_dates.index(self.selected_date_folder)

        self.list_box.SetSelection(focus_index)
        if sorted_dates:
            self.selected_items = [sorted_dates[focus_index]]
        else:
            self.selected_items = []
            
        self._update_button_visibility()
        self.list_box.SetFocus()

    def load_files_in_folder_path(self, target_folder_path):
        if not os.path.exists(target_folder_path):
            ui.message("Folder not found")
            return

        files = os.listdir(target_folder_path)
        if not files:
            ui.message("Folder is empty")
            if self.folder_path_stack:
                self.folder_path_stack.pop()
                if self.folder_path_stack:
                    self.load_files_in_folder_path(self.folder_path_stack[-1])
                    return
            self.load_date_folders(self.selected_category)
            return

        files_sorted = sorted(files, key=lambda x: x.lower())
        self.display_mapping = []
        display_names = []

        json_list = self.handler.history_data.get(self.selected_category, [])
        time_lookup = {item.get("content", ""): item.get("time", "") for item in json_list if isinstance(item, dict)}

        for f in files_sorted:
            full_p = os.path.join(target_folder_path, f)
            t_str = time_lookup.get(full_p, "")
            if not t_str and os.path.exists(full_p):
                mtime = os.path.getmtime(full_p)
                t_str = datetime.fromtimestamp(mtime).strftime("%I:%M %p")

            disp_text = f"{f} - {t_str}" if t_str else f
            display_names.append(disp_text)
            self.display_mapping.append({
                "title": f,
                "content": full_p,
                "category": self.selected_category,
                "date": self.selected_date_folder,
                "time": t_str
            })

        self.current_level = "FILES_LEVEL"
        folder_name = os.path.basename(target_folder_path)
        self.label.SetLabel(f"Contents of {folder_name}:")
        self.list_box.Set(display_names)

        if display_names:
            self.list_box.SetSelection(0)
            self.selected_items = [self.display_mapping[0]]

        self._update_button_visibility()
        self.list_box.SetFocus()

    def toggle_space_selection(self):
        idx = self.list_box.GetSelection()
        if idx == wx.NOT_FOUND or not self.display_mapping:
            return

        curr_item = self.display_mapping[idx]
        item_name = curr_item["title"] if isinstance(curr_item, dict) else curr_item

        if curr_item in self.selected_items:
            self.selected_items.remove(curr_item)
            ui.message(f"Not selected {item_name}")
        else:
            self.selected_items.append(curr_item)
            ui.message(f"Selected {item_name}")

    def on_char_hook(self, event):
        key_code = event.GetKeyCode()
        focused = self.FindFocus()

        if self.current_level == "CATEGORIES" and focused == self.list_box:
            if key_code in [wx.WXK_LEFT, wx.WXK_RIGHT]:
                return

        if key_code == wx.WXK_SPACE and focused == self.list_box and (self.current_level in ["FILES_LEVEL", "DATE_LEVEL"]):
            self.toggle_space_selection()
            return

        if event.ControlDown() and key_code == ord('A'):
            if self.current_level == "FILES_LEVEL":
                count = self.list_box.GetCount()
                self.selected_items = list(self.display_mapping)
                ui.message(f"Selected {count} files")
                self._update_button_visibility()
                return
            elif self.current_level == "DATE_LEVEL":
                count = self.list_box.GetCount()
                self.selected_items = list(self.display_mapping)
                ui.message(f"Selected {count} folders")
                self._update_button_visibility()
                return

        if event.ShiftDown() and key_code == wx.WXK_DELETE and (self.current_level in ["FILES_LEVEL", "DATE_LEVEL"]):
            self.confirm_and_permanent_delete()
            return

        if key_code == wx.WXK_DELETE and (self.current_level in ["FILES_LEVEL", "DATE_LEVEL"]):
            self.confirm_and_recycle_bin()
            return

        if key_code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and focused == self.list_box:
            self.process_enter()
            return

        elif key_code in [wx.WXK_ESCAPE, wx.WXK_BACK]:
            if key_code == wx.WXK_ESCAPE:
                if (self.current_level in ["FILES_LEVEL", "DATE_LEVEL"]) and self.selected_items:
                    self.selected_items = []
                    ui.message("Cleared all selections")
                    self._update_button_visibility()
                    return
                elif self.current_level == "CATEGORIES":
                    self.close_and_restore_focus()
                    return

            if self.current_level == "FILES_LEVEL":
                if self.folder_path_stack and len(self.folder_path_stack) > 1:
                    self.folder_path_stack.pop()
                    self.load_files_in_folder_path(self.folder_path_stack[-1])
                else:
                    self.folder_path_stack = []
                    self.load_date_folders(self.selected_category)
                return
            elif self.current_level == "DATE_LEVEL":
                self.navigate_back()
                return
            elif self.current_level == "CATEGORIES":
                self.close_and_restore_focus()
                return

        event.Skip()

    def on_list_selection_changed(self, event):
        if self.current_level == "CATEGORIES":
            self.selected_category = self.list_box.GetStringSelection()
            self._update_button_visibility()
        elif self.current_level == "DATE_LEVEL":
            idx = self.list_box.GetSelection()
            if idx != wx.NOT_FOUND and self.display_mapping:
                self.selected_date_folder = self.display_mapping[idx]
                if len(self.selected_items) <= 1:
                    self.selected_items = [self.selected_date_folder]
        elif self.current_level == "FILES_LEVEL":
            idx = self.list_box.GetSelection()
            if idx != wx.NOT_FOUND and self.display_mapping:
                item = self.display_mapping[idx]
                if len(self.selected_items) <= 1:
                    self.selected_items = [item]
                self._update_button_visibility()

    def process_enter(self):
        selection = self.list_box.GetStringSelection()
        if self.current_level == "CATEGORIES":
            self.selected_category = selection
            self.load_date_folders(selection)

        elif self.current_level == "DATE_LEVEL":
            if selection:
                self.selected_date_folder = selection
                date_path = os.path.join(self.handler.default_save_dir, self.selected_category, selection)
                self.folder_path_stack = [date_path]
                self.load_files_in_folder_path(date_path)

        elif self.current_level == "FILES_LEVEL":
            if self.selected_items:
                item = self.selected_items[0]
                target_p = item.get("content", "") if isinstance(item, dict) else ""
                if target_p and os.path.isdir(target_p):
                    self.folder_path_stack.append(target_p)
                    self.load_files_in_folder_path(target_p)
                elif isinstance(item, dict):
                    self.handler._open_file(item, self.selected_category, self)

    def navigate_back(self):
        self.current_level = "CATEGORIES"
        self.label.SetLabel("Select Category:")
        self.list_box.Set(CATEGORIES)
        self.list_box.SetSelection(CATEGORIES.index(self.selected_category) if self.selected_category in CATEGORIES else 0)
        self._update_button_visibility()
        self.list_box.SetFocus()

    def confirm_and_recycle_bin(self):
        if self.current_level == "DATE_LEVEL":
            if not self.selected_items:
                ui.message("No folders selected")
                return

            count = len(self.selected_items)
            msg = f"Are you sure you want to move {count} folder(s) to Recycle Bin?" if count > 1 else f"Are you sure you want to move folder '{self.selected_items[0]}' to Recycle Bin?"
            
            res = wx.MessageBox(msg, "Recycle Bin Confirmation", wx.YES_NO | wx.NO_DEFAULT, self)
            if res == wx.YES:
                for folder in self.selected_items:
                    full_path = os.path.join(self.handler.default_save_dir, self.selected_category, folder)
                    if os.path.exists(full_path):
                        send_to_recycle_bin(full_path)
                ui.message(f"Moved {count} folder(s) to Recycle Bin")
                self.load_date_folders(self.selected_category)
            return

        if not self.selected_items:
            ui.message("No items selected")
            return

        count = len(self.selected_items)
        first_title = self.selected_items[0]['title'] if isinstance(self.selected_items[0], dict) else self.selected_items[0]
        msg = f"Are you sure you want to move {count} item(s) to Recycle Bin?" if count > 1 else f"Are you sure you want to move '{first_title}' to Recycle Bin?"
        
        res = wx.MessageBox(msg, "Move to Recycle Bin Confirmation", wx.YES_NO | wx.NO_DEFAULT, self)
        if res == wx.YES:
            for item in self.selected_items:
                if isinstance(item, dict):
                    src_path = item.get("content", "")
                    if os.path.exists(src_path):
                        send_to_recycle_bin(src_path)
                    self.handler._delete_item_from_json(item)
            
            ui.message(f"Moved {count} item(s) to Recycle Bin")
            if self.folder_path_stack:
                self.load_files_in_folder_path(self.folder_path_stack[-1])

    def confirm_and_permanent_delete(self):
        if self.current_level == "DATE_LEVEL":
            if not self.selected_items:
                ui.message("No folders selected")
                return

            count = len(self.selected_items)
            msg = f"Are you sure you want to permanently delete {count} folder(s)?" if count > 1 else f"Are you sure you want to permanently delete folder '{self.selected_items[0]}'?"
            
            res = wx.MessageBox(msg, "Permanent Delete Confirmation", wx.YES_NO | wx.NO_DEFAULT, self)
            if res == wx.YES:
                for folder in self.selected_items:
                    full_path = os.path.join(self.handler.default_save_dir, self.selected_category, folder)
                    if os.path.exists(full_path):
                        try:
                            shutil.rmtree(full_path)
                        except Exception as e:
                            log.error(f"Permanent delete error: {e}")
                ui.message(f"Permanently deleted {count} folder(s)")
                self.load_date_folders(self.selected_category)
            return

        if not self.selected_items:
            ui.message("No items selected")
            return

        count = len(self.selected_items)
        first_title = self.selected_items[0]['title'] if isinstance(self.selected_items[0], dict) else self.selected_items[0]
        msg = f"Are you sure you want to permanently delete {count} item(s)?" if count > 1 else f"Are you sure you want to permanently delete '{first_title}'?"
        
        res = wx.MessageBox(msg, "Permanent Delete Confirmation", wx.YES_NO | wx.NO_DEFAULT, self)
        if res == wx.YES:
            for item in self.selected_items:
                if isinstance(item, dict):
                    src_path = item.get("content", "")
                    if os.path.exists(src_path):
                        try:
                            if os.path.isdir(src_path):
                                shutil.rmtree(src_path)
                            else:
                                os.remove(src_path)
                        except Exception as e:
                            log.error(f"Error permanently deleting file: {e}")
                    self.handler._delete_item_from_json(item)
            
            ui.message(f"Permanently deleted {count} item(s)")
            if self.folder_path_stack:
                self.load_files_in_folder_path(self.folder_path_stack[-1])

    def on_action_open(self, event):
        if self.selected_items and isinstance(self.selected_items[0], dict):
            self.handler._open_file(self.selected_items[0], self.selected_category, self)

    def on_action_read(self, event):
        if self.selected_items and isinstance(self.selected_items[0], dict):
            self.handler._read_in_notepad(self.selected_items[0])

    def on_action_rename(self, event):
        if self.selected_items and isinstance(self.selected_items[0], dict):
            if self.handler._rename_item(self.selected_items[0], self):
                if self.folder_path_stack:
                    self.load_files_in_folder_path(self.folder_path_stack[-1])

    def on_action_move(self, event):
        if self.selected_items:
            valid_items = [i for i in self.selected_items if isinstance(i, dict)]
            if valid_items:
                self.handler._move_selected_items(valid_items, self)
                if self.folder_path_stack:
                    self.load_files_in_folder_path(self.folder_path_stack[-1])

    def on_action_share(self, event):
        if self.selected_items and isinstance(self.selected_items[0], dict):
            self.handler._share_item(self.selected_items[0], self)

    def on_action_delete(self, event):
        self.confirm_and_recycle_bin()


class ClipManager(object):
    def __init__(self, plugin_instance=None):
        self.plugin_instance = plugin_instance
        self.default_root_drive = "D:"
        self.default_folder_name = "ClipSpeak History"
        self.config_dir = os.path.join(os.path.dirname(__file__), "clipSpeak_data")
        
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        self.json_path = os.path.join(self.config_dir, "clipboard_history.json")
        self.name_file_path = os.path.join(self.config_dir, "user_name.txt")
        self.pwd_file_path = os.path.join(self.config_dir, "app_pwd.txt")
        self.shortcut_file_path = os.path.join(self.config_dir, "toggle_shortcut.txt")
        self.target_path_config = os.path.join(self.config_dir, "target_path.txt")

        self._load_target_path_config()
        self.default_save_dir = self._resolve_target_path(self.default_root_drive, self.default_folder_name)
        self._ensure_category_folders_exist(self.default_save_dir)

        self.user_name = self.load_user_name()
        self.toggle_shortcut = self.load_toggle_shortcut()
        self.history_data = self.load_history()
        self.history_enabled = True

    def _ensure_category_folders_exist(self, base_path):
        if not os.path.exists(base_path):
            try:
                os.makedirs(base_path)
            except Exception:
                pass
        for cat in CATEGORIES:
            if cat != "All":
                cat_dir = os.path.join(base_path, cat)
                if not os.path.exists(cat_dir):
                    try:
                        os.makedirs(cat_dir)
                    except Exception as e:
                        log.error(f"Failed to create category folder {cat_dir}: {e}")

    def is_history_active(self):
        return self.history_enabled

    def _load_target_path_config(self):
        if os.path.exists(self.target_path_config):
            try:
                with open(self.target_path_config, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                    if len(lines) >= 2:
                        self.default_root_drive = lines[0].strip()
                        self.default_folder_name = lines[1].strip()
            except Exception as e:
                log.error(f"Error loading target path: {e}")

    def _save_target_path_config(self):
        try:
            with open(self.target_path_config, "w", encoding="utf-8") as f:
                f.write(f"{self.default_root_drive}\n{self.default_folder_name}")
        except Exception as e:
            log.error(f"Error saving target path: {e}")

    def validate_password_format(self, pwd):
        if not pwd:
            return True
        digits = re.findall(r'\d', pwd)
        if len(digits) > 2:
            return False
        return True

    def _verify_password_prompt(self):
        saved_pwd = self.get_password()
        if not saved_pwd:
            return True

        ui.message("Enter your password")
        
        while True:
            dlg = wx.TextEntryDialog(
                gui.mainFrame, 
                "Enter your password:", 
                "Enter Your Password", 
                style=wx.TE_PASSWORD | wx.OK | wx.CANCEL
            )
            res = dlg.ShowModal()
            val = dlg.GetValue().strip()
            dlg.Destroy()

            if res == wx.ID_OK:
                if val == saved_pwd:
                    return True
                else:
                    ui.message("Incorrect password. Please enter correct password.")
            else:
                return False

    def toggle_history_mode(self, gesture=None):
        if not self.history_enabled:
            if not self._verify_password_prompt():
                return
        self.history_enabled = not self.history_enabled
        ui.message("Clipboard History On" if self.history_enabled else "Clipboard History Off")

    script_toggle_history_mode = toggle_history_mode

    def load_toggle_shortcut(self):
        """Loads shortcut key from file. Returns empty string if shortcut is removed."""
        if os.path.exists(self.shortcut_file_path):
            with open(self.shortcut_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def save_toggle_shortcut(self, shortcut):
        """Saves shortcut to file and triggers re-binding/unbinding in GlobalPlugin."""
        with open(self.shortcut_file_path, "w", encoding="utf-8") as f:
            f.write(shortcut)
        self.toggle_shortcut = shortcut

        if shortcut:
            ui.message(f"Shortcut key updated to {shortcut}")
        else:
            ui.message("Shortcut key disabled")

        if self.plugin_instance and hasattr(self.plugin_instance, 'bind_custom_shortcut'):
            self.plugin_instance.bind_custom_shortcut()

    def _prompt_edit_shortcut(self, parent_dialog=None):
        """Prompts user to enter new shortcut key or clear it completely to disable."""
        parent = parent_dialog if parent_dialog else gui.mainFrame
        dlg = wx.TextEntryDialog(
            parent, 
            "Enter new shortcut key (e.g. nvda+shift+h). Clear text and press OK to disable shortcut:", 
            "Edit Shortcut Key", 
            self.toggle_shortcut
        )
        if dlg.ShowModal() == wx.ID_OK:
            new_key = dlg.GetValue().strip()
            self.save_toggle_shortcut(new_key)
        dlg.Destroy()

    def load_user_name(self):
        if os.path.exists(self.name_file_path):
            with open(self.name_file_path, "r", encoding="utf-8") as f:
                return f.read().strip() or "Blessia Pearl"
        return "Blessia Pearl"

    def save_user_name(self, name):
        with open(self.name_file_path, "w", encoding="utf-8") as f:
            f.write(name)
        self.user_name = name
        ui.message(f"User name updated to {name}")

    def get_password(self):
        if os.path.exists(self.pwd_file_path):
            with open(self.pwd_file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return ""

    def save_password(self, pwd):
        with open(self.pwd_file_path, "w", encoding="utf-8") as f:
            f.write(pwd)
        ui.message("Password set successfully.")

    def delete_password(self):
        if os.path.exists(self.pwd_file_path):
            try:
                os.remove(self.pwd_file_path)
            except Exception as e:
                log.error(f"Error deleting password file: {e}")
        ui.message("Password removed. Continuing normal operation.")

    def _prompt_set_password(self, parent_dialog=None):
        parent = parent_dialog if parent_dialog else gui.mainFrame
        current_pwd = self.get_password()

        dlg = wx.TextEntryDialog(
            parent, 
            "Set or Clear Password (Max 2 numbers allowed). Delete text and press OK to remove password:", 
            "Password Settings", 
            value=current_pwd,
            style=wx.TE_PASSWORD | wx.OK | wx.CANCEL
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            pwd = dlg.GetValue().strip()
            if not pwd:
                self.delete_password()
                if parent_dialog and hasattr(parent_dialog, 'btn_password'):
                    parent_dialog.btn_password.SetLabel("Set Password")
            else:
                if self.validate_password_format(pwd):
                    self.save_password(pwd)
                    if parent_dialog and hasattr(parent_dialog, 'btn_password'):
                        parent_dialog.btn_password.SetLabel("Change / Remove Password")
                else:
                    ui.message("Invalid Password! Maximum 2 digits allowed.")
        dlg.Destroy()

    def load_history(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for cat in CATEGORIES:
                        if cat not in data and cat != "All":
                            data[cat] = []
                    return data
            except Exception as e:
                log.error(f"Error loading history JSON: {e}")
        return {cat: [] for cat in CATEGORIES if cat != "All"}

    def save_history(self):
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"Error saving history JSON: {e}")

    def _categorize_text(self, text):
        if not text:
            return "Text"
        
        clean_text = os.path.normpath(text.strip().strip('"').strip("'"))
        ext = os.path.splitext(clean_text)[1].lower()

        audio_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.m4b', '.caf', '.aiff', '.aif', '.amr', '.mid'}
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.3gp', '.m4v', '.mpg', '.mpeg', '.ts'}
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.ico', '.svg', '.tif', '.tiff'}

        if ext in audio_exts:
            return "Audio"
        elif ext in video_exts:
            return "Video"
        elif ext in image_exts:
            return "Images"
        elif ext == ".pdf":
            return "PDF"
        elif ext in [".ppt", ".pptx", ".pps", ".ppsx"]:
            return "PPT"
        elif ext in [".docx", ".doc", ".rtf", ".odt"]:
            return "Documents"
        elif ext in [".xlsx", ".xls", ".csv", ".ods"]:
            return "Excel"
        elif ext in [".py", ".cpp", ".c", ".java", ".html", ".css", ".js", ".json", ".log", ".txt"]:
            return "Files" if os.path.exists(clean_text) else "Text"

        if os.path.exists(clean_text):
            return "Folders" if os.path.isdir(clean_text) else "Files"
        return "Text"

    def _get_native_clipboard_files(self):
        files = []
        if user32.OpenClipboard(None):
            try:
                h_drop = user32.GetClipboardData(CF_HDROP)
                if h_drop:
                    count = shell32.DragQueryFileW(h_drop, 0xFFFFFFFF, None, 0)
                    for i in range(count):
                        buf = ctypes.create_unicode_buffer(260)
                        shell32.DragQueryFileW(h_drop, i, buf, 260)
                        files.append(buf.value)
            finally:
                user32.CloseClipboard()
        return files

    def record_current_clipboard(self):
        if not self.history_enabled:
            return

        files = self._get_native_clipboard_files()
        if files:
            for f_path in files:
                cat = self._categorize_text(f_path)
                self.add_to_history(f_path, category=cat)
            return

        try:
            text_val = api.getClipData()
            if text_val and isinstance(text_val, str) and text_val.strip():
                cat = self._categorize_text(text_val)
                self.add_to_history(text_val, category=cat)
        except Exception as e:
            log.error(f"Record clipboard error: {e}")

    def append_clipboard(self):
        if not self.history_enabled:
            return

        try:
            new_text = api.getClipData()
            if new_text and isinstance(new_text, str) and new_text.strip():
                txt_list = self.history_data.get("Text", [])
                if txt_list:
                    last_item = txt_list[-1]
                    last_path = last_item.get("content", "")
                    if os.path.exists(last_path):
                        with open(last_path, "a", encoding="utf-8") as f:
                            f.write("\n" + new_text)
                        last_item["time"] = time.strftime("%I:%M %p")
                        self.save_history()
                        return
                self.add_to_history(new_text, category="Text")
        except Exception as e:
            log.error(f"Append clipboard error: {e}")

    def _copy_to_internal_storage(self, src_path, category="Files", target_dir=None, file_name=None):
        save_dir = target_dir if target_dir else self.default_save_dir
        date_folder_str = time.strftime("%B %d, %Y")
        
        cat_date_dir = os.path.join(save_dir, category, date_folder_str)
        if not os.path.exists(cat_date_dir):
            try:
                os.makedirs(cat_date_dir)
            except Exception as e:
                log.error(f"Failed to create category date folder: {e}")
                cat_date_dir = save_dir

        if category == "Text" and not os.path.exists(src_path):
            lines = [line.strip() for line in src_path.splitlines() if line.strip()]
            first_line = lines[0] if lines else "Text_Copy"
            
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                first_line = first_line.replace(char, '')
            
            clean_title_name = first_line[:30].strip() or "Text_Copy"
            dest_name = f"{clean_title_name}.txt"
            dest_path = os.path.join(cat_date_dir, dest_name)
            
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(cat_date_dir, f"{clean_title_name}_{counter}.txt")
                counter += 1

            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(src_path)
            return dest_path

        base_name = os.path.basename(src_path) if os.path.exists(src_path) else f"File_{int(time.time())}.txt"
        name_part, ext_part = os.path.splitext(base_name)
        dest_name = file_name if file_name else base_name
        dest_path = os.path.join(cat_date_dir, dest_name)

        counter = 1
        while os.path.exists(dest_path):
            dest_name = f"{name_part}_{counter}{ext_part}"
            dest_path = os.path.join(cat_date_dir, dest_name)
            counter += 1

        try:
            if os.path.exists(src_path):
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
            return dest_path
        except Exception as e:
            log.error(f"Copy to category storage error: {e}")
            return src_path

    def add_to_history(self, text, category="Text", target_dir=None, file_name=None):
        if not self.history_enabled or not text:
            return None, None
            
        clean_path = os.path.normpath(text.strip().strip('"').strip("'"))
        cat = category if category != "Text" else self._categorize_text(clean_path)
        
        saved_content_path = self._copy_to_internal_storage(text, category=cat, target_dir=target_dir, file_name=file_name)
        clean_title = os.path.basename(saved_content_path)

        if cat not in self.history_data:
            self.history_data[cat] = []

        new_entry = {
            "title": clean_title,
            "content": saved_content_path,
            "date": time.strftime("%B %d, %Y"),
            "time": time.strftime("%I:%M %p"),
            "timestamp": time.time(),
            "category": cat
        }
        
        self.history_data[cat].append(new_entry)
        self.save_history()
        return cat, clean_title

    def script_show_history_dialog(self, gesture=None):
        if not self._verify_password_prompt():
            return
        wx.CallAfter(self._open_main_dialog)

    show_history_dialog = script_show_history_dialog

    def start_dictation(self, gesture=None):
        try:
            ui.message("Dictation started")
            import keyboard
            keyboard.send("windows+h")
        except Exception:
            subprocess.Popen(["cmd.exe", "/c", "start ms-inputapp:dictation"])

    def _open_main_dialog(self):
        try:
            previous_hwnd = user32.GetForegroundWindow()
            parent_window = gui.mainFrame
            dlg = ClipSpeakHistoryDialog(parent_window, self, previous_hwnd=previous_hwnd)
            dlg.CenterOnScreen()
            dlg.Raise()
            dlg.SetFocus()
            dlg.ShowModal()
            dlg.Destroy()
        except Exception as e:
            log.error(f"Open main dialog error: {e}")

    def _prompt_change_user_name(self):
        dlg = wx.TextEntryDialog(gui.mainFrame, "Enter User Name:", "Change User Name", self.user_name)
        if dlg.ShowModal() == wx.ID_OK:
            self.save_user_name(dlg.GetValue().strip())
        dlg.Destroy()

    def _resolve_target_path(self, drive_str, folder_str):
        d_clean = drive_str.strip()
        d_lower = d_clean.lower()
        
        if d_lower in ["desktop", ""]:
            base_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        elif d_lower in ["documents", "document"]:
            base_dir = os.path.join(os.path.expanduser("~"), "Documents")
        elif len(d_clean) == 1:
            base_dir = f"{d_clean.upper()}:\\"
        elif ":" in d_clean:
            base_dir = d_clean if d_clean.endswith("\\") else f"{d_clean}\\"
        else:
            base_dir = f"{d_clean.upper()}:\\"

        return os.path.join(base_dir, folder_str.strip())

    def _change_global_save_path(self, parent_dialog):
        dlg1 = wx.TextEntryDialog(parent_dialog, "Step 1: Enter Drive or Location (e.g. D:, E:, Desktop):", "Target Directory - Step 1", self.default_root_drive)
        if dlg1.ShowModal() == wx.ID_OK:
            root_drive = dlg1.GetValue().strip()
            dlg1.Destroy()
            
            dlg2 = wx.TextEntryDialog(parent_dialog, "Step 2: Enter Folder Name:", "Target Directory - Step 2", self.default_folder_name)
            if dlg2.ShowModal() == wx.ID_OK:
                folder_name = dlg2.GetValue().strip()
                dlg2.Destroy()
                
                target_path = self._resolve_target_path(root_drive, folder_name)
                try:
                    self._ensure_category_folders_exist(target_path)
                    self.default_root_drive = root_drive
                    self.default_folder_name = folder_name
                    self.default_save_dir = target_path
                    self._save_target_path_config()
                    self.save_history()

                    ui.message(f"Target Directory updated to {target_path}")
                except Exception as e:
                    log.error(f"Directory creation error: {e}")
                    ui.message("Failed to create folder path")

    def _move_selected_items(self, items, parent_dialog):
        dlg1 = wx.TextEntryDialog(parent_dialog, "Step 1: Enter Drive or Location (e.g. D:, E:, Desktop):", "Move Items - Step 1", "D:")
        if dlg1.ShowModal() == wx.ID_OK:
            root_drive = dlg1.GetValue().strip()
            dlg1.Destroy()

            dlg2 = wx.TextEntryDialog(parent_dialog, "Step 2: Enter Destination Folder Name:", "Move Items - Step 2", "My Folder")
            if dlg2.ShowModal() == wx.ID_OK:
                folder_name = dlg2.GetValue().strip()
                dlg2.Destroy()

                target_dir = self._resolve_target_path(root_drive, folder_name)
                if not os.path.exists(target_dir):
                    try:
                        os.makedirs(target_dir)
                    except Exception as e:
                        log.error(f"Failed to create move target directory: {e}")

                success_count = 0
                for item in items:
                    if isinstance(item, dict):
                        src_path = item.get("content", "")
                        if os.path.exists(src_path):
                            dest_path = os.path.join(target_dir, os.path.basename(src_path))
                            try:
                                shutil.move(src_path, dest_path)
                                self._delete_item_from_json(item)
                                success_count += 1
                            except Exception as e:
                                log.error(f"Move error: {e}")

                ui.message(f"Moved {success_count} item(s) to {target_dir}")

    def _announce_empty_category(self, category):
        cat_lower = category.lower()
        if cat_lower in ["audio", "video"]:
            ui.message(f"the {cat_lower} file is empty")
        elif cat_lower == "folders":
            ui.message("the folder is empty")
        elif cat_lower in ["files", "pdf", "ppt", "documents", "excel"]:
            ui.message(f"the {cat_lower} file is empty")
        else:
            ui.message(f"the {cat_lower} is empty")

    def _open_file(self, item, category="Files", parent_dialog=None):
        file_path = item.get("content", "") if isinstance(item, dict) else ""
        try:
            if file_path and os.path.exists(file_path):
                os.startfile(file_path)
                ui.message(f"Opening {os.path.basename(file_path)}")
            else:
                ui.message("File path not found")
        except Exception as e:
            log.error(f"Open file error: {e}")

    def _read_in_notepad(self, item):
        content_path = item.get("content", "") if isinstance(item, dict) else ""
        if content_path and os.path.exists(content_path):
            subprocess.Popen(["notepad.exe", content_path])
            ui.message("Editing Notepad")
        else:
            ui.message("Text file not found")

    def _share_item(self, item, parent_dialog):
        share_dlg = ShareAppDialog(parent_dialog, item)
        if share_dlg.ShowModal() == wx.ID_OK:
            app_choice = share_dlg.get_selected_app()
            share_dlg.Destroy()
            
            content_path = item.get("content", "") if isinstance(item, dict) else ""
            if content_path and os.path.exists(content_path):
                try:
                    with open(content_path, "r", encoding="utf-8") as f:
                        api.copyToClip(f.read())
                except Exception:
                    api.copyToClip(content_path)
            else:
                api.copyToClip(content_path)

            if app_choice == "Desktop Icons / Desktop Folder":
                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                try:
                    os.startfile(desktop_path)
                    ui.message("Opening Desktop Folder. Content copied to clipboard.")
                except Exception as e:
                    log.error(f"Error opening Desktop: {e}")
            elif app_choice == "Google Gemini":
                webbrowser.open("https://gemini.google.com")
            elif app_choice == "ChatGPT":
                webbrowser.open("https://chatgpt.com")
            elif app_choice == "WhatsApp":
                try:
                    subprocess.Popen(["cmd.exe", "/c", "start whatsapp:"])
                except Exception:
                    webbrowser.open("https://web.whatsapp.com")
            elif app_choice in ["Telegram", "Unigram"]:
                try:
                    subprocess.Popen(["cmd.exe", "/c", "start tg:"])
                except Exception:
                    webbrowser.open("https://web.telegram.org")
            elif app_choice == "Gmail":
                webbrowser.open("https://mail.google.com")
            elif app_choice in ["Facebook", "Messenger"]:
                webbrowser.open("https://www.facebook.com")
            elif app_choice == "Instagram":
                webbrowser.open("https://www.instagram.com")
            else:
                ui.message("Content copied to clipboard for sharing.")

    def _rename_item(self, item, parent_dialog):
        if not isinstance(item, dict):
            return False
        current_title = item.get("title", "")
        dlg = wx.TextEntryDialog(parent_dialog, "Enter new title:", "Rename Item", current_title)
        if dlg.ShowModal() == wx.ID_OK:
            new_name = dlg.GetValue().strip()
            if new_name:
                old_path = item.get("content", "")
                dir_name = os.path.dirname(old_path)
                old_ext = os.path.splitext(old_path)[1]
                
                new_ext = os.path.splitext(new_name)[1]
                if not new_ext and old_ext:
                    new_filename = f"{new_name}{old_ext}"
                else:
                    new_filename = new_name

                new_path = os.path.join(dir_name, new_filename)

                if os.path.exists(old_path):
                    try:
                        os.rename(old_path, new_path)
                        item["content"] = new_path
                        item["title"] = new_filename
                        self.save_history()
                        ui.message("Renamed successfully")
                        dlg.Destroy()
                        return True
                    except Exception as e:
                        log.error(f"Failed to rename physical file: {e}")
        dlg.Destroy()
        return False

    def _delete_item_from_json(self, item):
        for cat in self.history_data:
            if item in self.history_data[cat]:
                self.history_data[cat].remove(item)
        self.save_history()