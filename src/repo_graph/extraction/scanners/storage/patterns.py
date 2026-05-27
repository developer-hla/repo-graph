"""Storage scanner regexes and method sets."""

from __future__ import annotations

import re

STORAGE_NAME_RE = r"[A-Za-z_][\w.]*"
STORAGE_METHOD_RE = re.compile(
    rf"(?:(?P<receiver>{STORAGE_NAME_RE})\s*\.\s*)?"
    r"(?P<method>readFileSync|writeFileSync|createReadStream|createWriteStream|ReadAllText|"
    r"ReadAllBytes|WriteAllText|WriteAllBytes|OpenRead|OpenWrite|DownloadAsync|UploadAsync|"
    r"downloadToFile|uploadFromFile|getObject|putObject|get_object|put_object|readFile|writeFile|"
    r"appendFile|download|upload)\s*\(",
    re.IGNORECASE,
)
STORAGE_KEY_VALUE_RE = re.compile(
    r"(?P<key>Bucket|bucket|bucketName|Container|container|containerName|Share|share|Key|key|BlobName|"
    r"blobName|Path|path|FilePath|filePath)"
    r"\s*[:=]\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)
STORAGE_FIRST_ARG_RE = re.compile(
    r"\(\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)

READ_METHODS = frozenset(
    {
        "createreadstream",
        "download",
        "downloadasync",
        "downloadtofile",
        "get_object",
        "getobject",
        "openread",
        "readallbytes",
        "readalltext",
        "readfile",
        "readfilesync",
    }
)
WRITE_METHODS = frozenset(
    {
        "appendfile",
        "createwritestream",
        "openwrite",
        "put_object",
        "putobject",
        "upload",
        "uploadasync",
        "uploadfromfile",
        "writeallbytes",
        "writealltext",
        "writefile",
        "writefilesync",
    }
)
BROAD_STORAGE_METHODS = frozenset({"appendfile", "download", "readfile", "upload", "writefile"})
RECEIVER_HINTS = (
    "blob",
    "bucket",
    "container",
    "directory",
    "file",
    "fs",
    "ftp",
    "path",
    "s3",
    "share",
    "storage",
)
