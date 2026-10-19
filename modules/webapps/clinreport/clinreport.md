# ClinReport

Clinical report generator for OpenCRAVAT results.

1. In the result viewer, mark variants in the **Note** column:
   `1` pathogenic, `2` likely pathogenic, `3` VUS, `7` not related to the main diagnosis, `8` carrier.
2. On the **Summary** tab, click **Открыть окно заключения** (widget *ClinReport*).
3. Pick the target sample and click **Обработать** (or **Обработать как LPWGS**).
4. Review and edit each sample, pick the template (DZM / FND) and click **Сохранить как…**.

Settings (clinician, template, auto-upload) are stored in `<OpenCRAVAT conf dir>/clinreport.json`. The Postgres
`ReportedVariants` connection comes from the server's environment (`CLINREPORT_DB_HOST/PORT/NAME/USER/PASS`).
