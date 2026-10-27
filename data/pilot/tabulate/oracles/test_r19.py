from tabulate import tabulate


def test_html_escapes_the_cell_text():
    assert tabulate([["<b>"]], tablefmt="html") == (
        '<table>\n<tbody>\n<tr><td style="text-align: left;">&lt;b&gt;</td></tr>\n</tbody>\n</table>'
    )


def test_unsafehtml_leaves_the_cell_text_alone():
    assert tabulate([["<b>"]], tablefmt="unsafehtml") == (
        '<table>\n<tbody>\n<tr><td style="text-align: left;"><b></td></tr>\n</tbody>\n</table>'
    )
