# ClinReport в уже установленном OpenCRAVAT

Если OpenCRAVAT у вас уже есть (свой компьютер или сервер лаборатории), ClinReport можно добавить в него как расширение.
Если OpenCRAVAT нет — проще поставить [приложение ClinReport](desktop-app.md), в нём всё уже есть.

## Что нужно

- OpenCRAVAT **3.2.3** (проверено) или 2.2.9 и новее. OpenCRAVAT 3.x напрямую на Windows без исправлений приложения
  ClinReport не запускается — на Windows используйте приложение.
- Python, **которым работает OpenCRAVAT** (тот, в котором установлен `oc`).
- Модули OpenCRAVAT `hg38` (нужен просмотрщику) и `wgnote` (столбец Note): `oc module install hg38 wgnote`.

## Установка и обновление

1. Скачайте `clinreport-extension-<версия>.zip` со страницы [Releases](https://github.com/emijks/clinreport/releases) и
   распакуйте.
2. Выполните в распакованной папке:

   ```text
   <python OpenCRAVAT> install_extension.py              # модули + docxtpl
   <python OpenCRAVAT> install_extension.py --with-db    # + клиент Postgres («Выгрузить в базу», «Похожие»)
   ```

3. Перезапустите `oc gui`.

Чтобы **обновить**, сделайте то же с новым архивом: скрипт напишет, с какой версии на какую обновлено. Настройки и свои
шаблоны лежат в папке настроек OpenCRAVAT и при обновлении не трогаются.

Удаление: `<python OpenCRAVAT> install_extension.py --uninstall`.

## Работа

Как в приложении: Note в просмотрщике → вкладка Summary → «Открыть окно заключения» → «Обработать» → «Сохранить как…»
(подробно — [desktop-app.md](desktop-app.md#работа)). Окно заключения можно открыть и без просмотрщика:
`oc gui --webapp clinreport`, затем ввести путь к файлу `.sqlite`.

## База данных (сервер)

«Выгрузить в базу» и «Похожие» работают, если сервер подключён к базе Postgres с таблицей `ReportedVariants`.
Подключение задаёт тот, кто разворачивает сервер, переменными окружения `CLINREPORT_DB_HOST`, `CLINREPORT_DB_PORT`,
`CLINREPORT_DB_NAME`, `CLINREPORT_DB_USER`, `CLINREPORT_DB_PASS`; через окно заключения его не видно и не изменить.
