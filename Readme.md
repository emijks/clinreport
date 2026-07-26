# ClinReport

Generate clinical report from OpenCRAVAT SQLite

## Usage

### Prepare SQLite

Mark variants to reflect in the report:
1. open SQLite in OpenCRAVAT GUI;
2. mark variants of interest in `Note` field with the corresponding number:
    - `1`: "Патогенный";
    - `2`: "Вероятно патогенный";
    - `3`: "Вариант с неизвестной клинической значимостью";
    - `7`: "Вариант, не связанный с основным диагнозом";
    - `8`: "Носительство";

3. SQLite with changes (with marked variants) is saved in the `jobs` folder of OpenCRAVAT.

### Run ClinReport

#### Using the graphical application (GUI)

1. Launch the application. (_If you are running from source:_ `python app.py`)
2. In the main window, click **`Выбрать файл`**.
3. In the file selection dialog, choose an OpenCRAVAT SQLite.
4. In the **Processing** window:
   - select the target sample from the drop-down list (for Duo/Trio);
   - click **`Обработать`** for a standard report, or **`Обработать как LPWGS`** for a 10x report.
5. A window will open for each sample found in the database. You can review and edit the available fields.
6. Click **`Сохранить как...`**, choose the destination folder and filename, and save the generated report.

#### Using the command-line interface (CLI)

```text
usage: cli.py [-h] [-t TARGET_SAMPLE] [-r {default,10x}]
              [--template {DZM,FND}] [-o OUTPUT_DIR]
              [--no-ru-annotations]
              sqlite

positional arguments:
  sqlite                Path to OpenCRAVAT SQLite

options:
  -h, --help            Show this help message and exit
  -t, --target-sample TARGET_SAMPLE
                        Main sample in Duo/Trio
  -r, --report {default,10x}
                        Report type to generate
  --template {DZM,FND}  Template for default reports
  -o, --output-dir OUTPUT_DIR
                        Directory where .docx files will be saved
  --no-ru-annotations   Skip fetching Russian OMIM/secondary annotation overrides
```


## Setup

### Requirements

- python3
- Install dependencies: `pip install -r requirements.txt`

### Build the Windows/MacOS application

```
pyinstaller \
  --windowed \
  --add-data "config.json:." \
  --add-data "templates:templates" \
  --collect-all docx \
  --name clinreport \
  --noconfirm \
  app.py
```

### Tips

On macOS, if you encounter errors such as "The application is damaged" or "cannot be opened", run:

`xattr -cr /PATH/TO/clinreport.app`
