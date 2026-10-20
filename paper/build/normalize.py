import zipfile, sys

B = "http://purl.oclc.org/ooxml/"
S = "http://schemas.openxmlformats.org/"
REL = S + "officeDocument/2006/relationships"

M = {
    B + "officeDocument/relationships/extendedProperties": REL + "/extended-properties",
    B + "officeDocument/relationships": REL,
    B + "officeDocument/customXml": S + "officeDocument/2006/customXml",
    B + "officeDocument/docPropsVTypes": S + "officeDocument/2006/docPropsVTypes",
    B + "officeDocument/extendedProperties": S + "officeDocument/2006/extended-properties",
    B + "officeDocument/math": S + "officeDocument/2006/math",
    B + "drawingml/wordprocessingDrawing": S + "drawingml/2006/wordprocessingDrawing",
    B + "drawingml/main": S + "drawingml/2006/main",
    B + "wordprocessingml/main": S + "wordprocessingml/2006/main",
}
ORDER = sorted(M, key=len, reverse=True)

def convert(src, dst):
    zi, zo = zipfile.ZipFile(src), zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    for it in zi.infolist():
        data = zi.read(it.filename)
        if it.filename.endswith((".xml", ".rels")):
            text = data.decode("utf8")
            for k in ORDER:
                text = text.replace(k, M[k])
            data = text.encode("utf8")
        zo.writestr(it, data)
    zo.close()

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
