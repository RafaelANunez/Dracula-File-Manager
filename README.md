
---

# Dracula File Manager Pro

A robust, dark-themed file management and organization utility built in Python with PySide6. Dracula File Manager Pro is designed to help you quickly search, filter, and organize large batches of files using intelligent, customizable sorting rules.

## 🚀 Key Features

* **Advanced File Search:** Find exactly what you need by filtering through directories recursively based on keywords, file extensions, size constraints, and modification dates.
* **Dual View Modes:** Toggle seamlessly between a detailed List (Tree) view and a Grid view.
* **Media Thumbnails:** Automatically generates grid thumbnails for images and videos (powered by OpenCV).
* **Smart Organizer:** Create and save custom rules to automatically copy or move files into dynamically generated subfolder structures (e.g., sorted by `{Year}/{Month}/{Ext}` or `{Size_Tier}`).
* **Built-in File Operations:** Quickly Copy, Move, Rename, Zip, Unzip, and Delete selected files directly from the dashboard.
* **Customizable Theming:** Comes with a sleek default "Dracula" dark theme, with options to tweak the background, accent, and text colors to your liking.

## 🛠️ Installation (Windows)

The repository includes an automated setup script to make installation seamless.

1. Clone or download this repository to your local machine.
2. Double-click the `install_deps.bat` file. This script will automatically:
* Create a virtual environment named `venv`.


* Activate the newly created virtual environment.


* Install the required Python packages: `PySide6` and `opencv-python`.





*(Note: If you are setting this up manually on macOS or Linux, you can run `pip install PySide6 opencv-python` in your preferred environment.)*

## 💻 Usage

To launch the application on Windows, double-click the `run_app.bat` file.

This startup script will:

* Start Dracula File Manager Pro.


* Set the required `PYTHONPATH` for the session.


* Execute `file_manager.py` using the `pythonw.exe` executable located in the virtual environment, keeping the application window clean without a background console.



### Using the Smart Organizer

1. Navigate to the **Smart Organize** tab via the sidebar.
2. Select a root folder to generate a live preview of the files you want to organize.
3. Use the **Rules & Profiles** section to build custom routing rules. You can parse files by name, extension, size, or date, and define destination paths using dynamic tags (like `{Year}`, `{Week}`, or `{First_Letter}`).
4. Choose whether to move or copy the files, and click **START SORTING**.

## ⚙️ Configuration Files

The application automatically generates two JSON files in the root directory to save your preferences:

* `app_settings.json`: Stores your custom theme colors and search performance settings (like batch size).
* `organizer_presets.json`: Saves your custom Smart Organizer rules and profiles so you don't have to rebuild them.


