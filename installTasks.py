# ClipMaster - Enhanced Clipboard Management for NVDA
# Copyright (C) 2026 Selvakumar G <jgfselva@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

# ClipMaster Installation Tasks
# Provides necessary routines during add-on installation and update.

import os
import shutil


def onInstall():
    """Migrates user history data from previous installation if available."""
    # Path to user data in the previous installation directory
    old_data = os.path.join(os.path.dirname(__file__), "..", "ClipMaster", "clipHistoryData")
    
    # Path to user data in the new installation directory
    new_data = os.path.join(os.path.dirname(__file__), "clipHistoryData")

    # Migrate history database or data folder if it exists in the old version
    if os.path.exists(old_data) and not os.path.exists(new_data):
        try:
            if os.path.isdir(old_data):
                shutil.copytree(old_data, new_data)
            else:
                shutil.copy2(old_data, new_data)
        except (IOError, OSError):
            pass