# ClinReport

Generate clinical report from GenLab OpenCRAVAT SQLite


## Usage

0. Mark variants to reflect in the report

- Open SQLite in OpenCRAVAT viewer
- mark variants of interest in `Note` field with the corresponding number:
    `1`: патогенный
    `2`: вероятно патогенный
    `3`: вариант с неизвестной клинической значимостью
    `7`: вариант, не связанный с основным диагнозом
    `8`: носительство


SQLite with changes (with marked variants) is saved in the `jobs` folder of OpenCRAVAT


1. Run ClinReport

Run application and follow app-instructions:

    - chose SQLite with marked variants
    - select main sample for duo/trio
    - click `generate`
    - chose where to save document


Or you can run `clinreport.py` with CLI interface:

    ```
    usage: clinreport.py [-h] [-t TARGET_SAMPLE] sqlite

    sqlite                Path to OpenCRAVAT SQLite

    options:
    -h, --help            show this help message and exit
    -t, --target-sample TARGET_SAMPLE
                            Main sample in duo/trio
    ```


## Setup

### Requirements

python3

`pip install -r requirements.txt`

### How to crate Windows/MacOS application

`pyinstaller --windowed --add-data "config.json:." --add-data "templates:templates" --collect-all docx --name clinreport --noconfirm app.py`


### Tips

In order to handle MacOS errors such as “the application is damaged” or “cannot be opened,” use the following command:

`xattr -cr /PATH/TO/clinreport.app`
