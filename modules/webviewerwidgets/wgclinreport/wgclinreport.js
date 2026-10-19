// Summary-tab entry point: opens the ClinReport webapp for the result shown in
// the viewer. dbPath / jobId / username are the viewer's own globals.
widgetGenerators['clinreport'] = {
    'info': {
        'name': 'Клиническое заключение (ClinReport)',
        'width': 380,
        'height': 170,
        'function': function (div) {
            var params = new URLSearchParams();
            if (typeof dbPath !== 'undefined' && dbPath) {
                params.set('dbpath', dbPath);
            }
            if (typeof jobId !== 'undefined' && jobId) {
                params.set('job_id', jobId);
            }
            if (typeof username !== 'undefined' && username) {
                params.set('username', username);
            }
            var url = '/webapps/clinreport/index.html?' + params.toString();

            // The viewer's own @font-face names (webresult/nocache/css/widget.css);
            // set on each element, since the card's default styles override inheritance.
            var font = "'roboto-light', 'Segoe UI', Arial, sans-serif";
            var text = getEl('p');
            text.style.margin = '4px 0 12px';
            text.style.fontFamily = font;
            text.style.fontSize = '13px';
            text.textContent = 'Отметьте варианты в колонке Note (1 — P, 2 — LP, 3 — VUS, '
                + '7 — не связан с диагнозом, 8 — носительство) и откройте окно заключения.';
            addEl(div, text);

            var button = getEl('button');
            button.className = 'butn';
            button.textContent = 'Открыть окно заключения';
            button.style.padding = '6px 14px';
            button.style.fontFamily = "'roboto-medium', 'Segoe UI', Arial, sans-serif";
            button.style.fontSize = '13px';
            button.addEventListener('click', function () {
                window.open(url, '_blank');
            });
            addEl(div, button);
        }
    }
};
