# -*- coding: utf-8 -*-
import os
import re
import shutil
import datetime
import ctypes
from ctypes import wintypes
import wx
import api
import ui
from logHandler import log

try:
    import comtypes.client
except Exception:
    pass


# Ctypes structure for Windows Recycle Bin API Query
class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


class ClipAnnounceHandler:
    def __init__(self, clip_manager_instance=None):
        self.clip_manager = clip_manager_instance

    def _get_formatted_size(self, size_bytes):
        """Formats bytes into readable KB, MB, or GB strings."""
        if size_bytes < 1024:
            return f"{size_bytes} Bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _get_folder_size_and_count(self, folder_path):
        """Calculates total size (bytes), file count, and folder count inside a folder recursively."""
        total_size = 0
        file_count = 0
        dir_count = 0
        try:
            for root, dirs, files in os.walk(folder_path):
                dir_count += len(dirs)
                file_count += len(files)
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if os.path.exists(fp) and not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                    except Exception:
                        continue
        except Exception as e:
            log.error(f"Error calculating folder size for {folder_path}: {e}")
        return total_size, file_count, dir_count

    def _get_recycle_bin_info(self):
        """Fetches total items and total size in Windows Recycle Bin using Shell API."""
        try:
            rbinfo = SHQUERYRBINFO()
            rbinfo.cbSize = ctypes.sizeof(SHQUERYRBINFO)
            result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(rbinfo))
            if result == 0:
                return rbinfo.i64NumItems, rbinfo.i64Size
        except Exception as e:
            log.error(f"Error querying Recycle Bin: {e}")
        return None, None

    def _get_my_computer_info(self):
        """Aggregates drive capacities for 'My Computer' / 'This PC'."""
        info_lines = ["Name: My Computer / This PC", "Type: System Directory / Drives Overview"]
        total_capacity = 0
        total_free = 0
        drive_details = []

        try:
            for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive_path = f"{drive_letter}:\\"
                if os.path.exists(drive_path):
                    try:
                        total, used, free = shutil.disk_usage(drive_path)
                        total_capacity += total
                        total_free += free
                        drive_details.append(
                            f"Drive {drive_letter}: Total {self._get_formatted_size(total)} | Free {self._get_formatted_size(free)}"
                        )
                    except Exception:
                        pass
        except Exception as e:
            log.error(f"Error fetching drives info for My Computer: {e}")

        info_lines.append(f"Total Combined Capacity: {self._get_formatted_size(total_capacity)}")
        info_lines.append(f"Total Combined Free Space: {self._get_formatted_size(total_free)}")
        if drive_details:
            info_lines.append("\r\nDrives List:")
            info_lines.extend(drive_details)

        return info_lines

    def _get_media_duration_win(self, file_path):
        """Retrieves media duration (Audio/Video) via Windows Shell API."""
        try:
            folder, filename = os.path.split(file_path)
            shell = comtypes.client.CreateObject("Shell.Application")
            ns = shell.NameSpace(folder)
            item = ns.ParseName(filename)
            duration_str = ns.GetDetailsOf(item, 27)
            if duration_str:
                return duration_str
        except Exception as e:
            log.error(f"Error fetching media duration: {e}")
        return None

    def _resolve_real_extension(self, parent_folder, item_name):
        """Finds true extension even when 'Hide extensions for known file types' is ON in Windows."""
        direct_path = os.path.join(parent_folder, item_name)
        if os.path.exists(direct_path):
            return direct_path

        all_extensions = [
            '.mp3', '.wav', '.flac', '.aiff', '.aif', '.opus', '.m4a', '.aac', '.ogg', '.wma',
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.3gp', '.flv',
            '.txt', '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.csv',
            '.py', '.json', '.html', '.xml', '.zip', '.rar', '.7z', '.exe', '.lnk'
        ]

        for ext in all_extensions:
            test_path = direct_path + ext
            if os.path.exists(test_path):
                return test_path

        try:
            for f in os.listdir(parent_folder):
                if os.path.splitext(f)[0].lower() == item_name.lower():
                    return os.path.join(parent_folder, f)
        except Exception:
            pass

        return None

    def _get_focused_path_or_special(self):
        """Resolves full path for Drives, Folders, Files, or returns special Desktop Shell item identifier."""
        obj = api.getFocusObject()
        if not obj:
            return None, None

        raw_name = str(getattr(obj, "name", "") or "")
        display_text = str(getattr(obj, "displayText", "") or "")
        
        acc_name = ""
        try:
            if hasattr(obj, 'IAccessibleObject') and obj.IAccessibleObject:
                acc_name = str(obj.IAccessibleObject.accName(obj.IAccessibleChildID) or "")
        except Exception:
            pass

        combined_text = f"{raw_name} {display_text} {acc_name}".lower()
        clean_text = re.sub(r'[^a-zA-Z0-9]', '', combined_text)
        item_name = raw_name.strip()

        # 1. DRIVE LETTER CHECK FIRST (C:\, D:\, E:\)
        drive_match = re.search(r'([A-Za-z]):\\?', item_name)
        if drive_match:
            drive_letter = f"{drive_match.group(1).upper()}:\\"
            if os.path.exists(drive_letter):
                return drive_letter, item_name

        # 2. EXPLORER ACTIVE WINDOW SELECTION VIA SHELL API (REAL FILES FIRST)
        try:
            shell = comtypes.client.CreateObject("Shell.Application")
            for window in shell.Windows():
                try:
                    selected_items = window.Document.SelectedItems()
                    if selected_items and selected_items.Count > 0:
                        for idx in range(selected_items.Count):
                            s_item = selected_items.Item(idx)
                            if item_name and (s_item.Name.lower() == item_name.lower() or 
                                              os.path.basename(s_item.Path).lower() == item_name.lower()):
                                if os.path.exists(s_item.Path):
                                    return s_item.Path, item_name
                        first_path = selected_items.Item(0).Path
                        if os.path.exists(first_path):
                            return first_path, item_name
                except Exception:
                    continue
        except Exception as e:
            log.error(f"Error resolving path via Shell COM: {e}")

        # 3. CHECK DESKTOP PATHS DIRECTLY FOR REAL FILES/FOLDERS
        desktop_paths = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop")
        ]
        for d_path in desktop_paths:
            test_folder = os.path.join(d_path, item_name)
            if os.path.exists(test_folder):
                return test_folder, item_name

            resolved_path = self._resolve_real_extension(d_path, item_name)
            if resolved_path:
                return resolved_path, item_name

        # 4. NVDA PARENT TREE WALKER FOR DIRECTORIES
        parent = getattr(obj, 'parent', None)
        while parent:
            parent_name = getattr(parent, 'name', '')
            if parent_name and os.path.exists(parent_name) and os.path.isdir(parent_name):
                test_sub = os.path.join(parent_name, item_name)
                if os.path.exists(test_sub):
                    return test_sub, item_name
                resolved_path = self._resolve_real_extension(parent_name, item_name)
                if resolved_path:
                    return resolved_path, item_name
            parent = getattr(parent, 'parent', None)

        # 5. DIRECT FALLBACK ATTRIBUTES (IF PATH IS A VALID DISK FILE/FOLDER)
        if hasattr(obj, 'path') and obj.path and os.path.exists(obj.path):
            return obj.path, item_name
        if hasattr(obj, 'value') and obj.value and os.path.exists(obj.value):
            return obj.value, item_name

        # 6. SPECIAL CASE MATCHING (IF NO REAL DISK FILE MATCHES, THEN CHECK SYSTEM ICONS)
        if "recyclebin" in clean_text or "recycle" in clean_text:
            return "SPECIAL_RECYCLE_BIN", raw_name

        target_names = ["this pc", "my computer", "computer", "thispc", "mycomputer"]
        if raw_name.lower().strip() in target_names or any(tn in clean_text for tn in ["thispc", "mycomputer"]):
            return "SPECIAL_MY_COMPUTER", raw_name

        return None, item_name

    def announce_file_info(self):
        file_path, item_name = self._get_focused_path_or_special()

        info_lines = []

        # 1. SPECIAL CASE: RECYCLE BIN
        if file_path == "SPECIAL_RECYCLE_BIN":
            num_items, total_bytes = self._get_recycle_bin_info()
            info_lines.append("Name: Recycle Bin")
            info_lines.append("Type: System Directory")
            if num_items is not None:
                info_lines.append(f"Contains: {num_items} items")
                info_lines.append(f"Total Size: {self._get_formatted_size(total_bytes)}")
            else:
                info_lines.append("Unable to retrieve Recycle Bin details.")

        # 2. SPECIAL CASE: MY COMPUTER / THIS PC
        elif file_path == "SPECIAL_MY_COMPUTER":
            info_lines = self._get_my_computer_info()

        # 3. DRIVE PROPERTIES
        elif file_path and len(file_path) <= 3 and (file_path.endswith(":\\") or file_path.endswith(":")):
            drive_path = file_path if file_path.endswith(":\\") else file_path + "\\"
            try:
                total, used, free = shutil.disk_usage(drive_path)
                info_lines.append(f"Drive Name: {drive_path}")
                info_lines.append("Type: Disk Drive / Removable Storage")
                info_lines.append(f"Total Capacity: {self._get_formatted_size(total)}")
                info_lines.append(f"Free Space: {self._get_formatted_size(free)}")
                info_lines.append(f"Used Space: {self._get_formatted_size(used)}")
            except Exception as e:
                info_lines.append(f"Unable to fetch drive details: {e}")

        # 4. FOLDER PROPERTIES
        elif file_path and os.path.isdir(file_path):
            folder_name = os.path.basename(file_path)
            info_lines.append(f"Folder Name: {folder_name}")
            info_lines.append("Type: Folder")
            
            size_bytes, file_count, dir_count = self._get_folder_size_and_count(file_path)
            info_lines.append(f"Size: {self._get_formatted_size(size_bytes)}")
            info_lines.append(f"Contains: {file_count} Files, {dir_count} Folders")

            try:
                mod_time = os.path.getmtime(file_path)
                mod_date = datetime.datetime.fromtimestamp(mod_time).strftime("%B %d, %Y %I:%M:%S %p")
                info_lines.append(f"Modified Date: {mod_date}")
            except Exception:
                pass

        # 5. FILE PROPERTIES
        elif file_path and os.path.isfile(file_path):
            file_name = os.path.basename(file_path)
            ext = os.path.splitext(file_name)[1].lower()
            file_size = os.path.getsize(file_path)
            mod_time = os.path.getmtime(file_path)

            mod_date = datetime.datetime.fromtimestamp(mod_time).strftime("%B %d, %Y %I:%M:%S %p")

            info_lines.append(f"File Name: {file_name}")
            info_lines.append(f"Extension: {ext if ext else 'Unknown'}")
            info_lines.append(f"Size: {self._get_formatted_size(file_size)}")

            media_extensions = {
                '.mp3', '.wav', '.flac', '.aiff', '.aif', '.opus', '.m4a', '.aac', '.ogg', '.wma',
                '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm', '.3gp', '.flv'
            }
            if ext in media_extensions:
                duration = self._get_media_duration_win(file_path)
                if duration:
                    info_lines.append(f"Duration: {duration}")

            info_lines.append(f"Modified Date: {mod_date}")

        else:
            ui.message("No valid file, folder, or drive selected.")
            return

        final_text = "\r\n".join(info_lines)
        wx.CallAfter(self._show_properties_dialog, final_text)

    def _show_properties_dialog(self, text_content):
        """Displays text content inside a Multi-line ReadOnly TextCtrl Dialog for NVDA Navigation."""
        parent = wx.GetApp().GetTopWindow()
        dialog = wx.Dialog(parent, title="Item Properties", size=(450, 350))

        sizer = wx.BoxSizer(wx.VERTICAL)
        text_ctrl = wx.TextCtrl(
            dialog,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            value=text_content
        )
        sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        ok_button = wx.Button(dialog, wx.ID_OK, label="Close")
        sizer.Add(ok_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        dialog.SetSizer(sizer)
        text_ctrl.SetFocus()
        dialog.ShowModal()
        dialog.Destroy()
        ui.message("Properties window closed.")