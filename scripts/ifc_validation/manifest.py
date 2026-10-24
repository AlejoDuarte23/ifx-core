import hashlib
import json
import re
from pathlib import Path

HEADER_LIMIT = 1024 * 1024
TOKEN = re.compile(rb"/\*.*?\*/|'(?:[^']|'')*'|[A-Za-z_][A-Za-z_0-9]*|[^\s]", re.S)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def declared_schema(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(HEADER_LIMIT)
    record: list[bytes] = []
    in_header = False
    schemas: list[str] = []
    for match in TOKEN.finditer(header):
        token = match.group()
        if token.startswith(b"/*"):
            continue
        if token != b";":
            record.append(token)
            continue
        upper = [item.upper() for item in record]
        if upper == [b"HEADER"]:
            if in_header:
                raise ValueError(f"duplicate HEADER: {path}")
            in_header = True
        elif in_header and upper == [b"ENDSEC"]:
            if len(schemas) != 1:
                raise ValueError(f"expected one FILE_SCHEMA identifier: {path}")
            return schemas[0]
        elif in_header and upper and upper[0] == b"FILE_SCHEMA":
            if (
                len(record) != 6
                or record[1:3] != [b"(", b"("]
                or record[4:] != [b")", b")"]
                or not record[3].startswith(b"'")
                or not record[3].endswith(b"'")
            ):
                raise ValueError(f"invalid FILE_SCHEMA record: {path}")
            schemas.append(record[3][1:-1].decode("ascii").strip().upper())
        record.clear()
    raise ValueError(f"complete HEADER not found in first {HEADER_LIMIT} bytes: {path}")


def inventory(root: Path, schema: str) -> dict[str, object]:
    if not root.is_dir():
        raise ValueError(f"model directory does not exist: {root}")
    models: list[dict[str, object]] = []
    schema_id = schema.lower().replace("_", "-")
    hashes: set[str] = set()
    duplicates = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".ifc":
            continue
        label = declared_schema(path)
        if label != schema:
            continue
        digest = file_hash(path)
        if digest in hashes:
            duplicates += 1
            continue
        hashes.add(digest)
        models.append(
            {
                "id": f"{schema_id}-{digest[:16]}",
                "path": str(path.resolve()),
                "schema": label,
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
        )
    if not models:
        raise ValueError(f"no {schema} models found in {root}")
    return {"version": 1, "schema": schema, "duplicates": duplicates, "models": models}


def load_manifest(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("manifest version must be 1")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("manifest must contain at least one model")
    ids: set[str] = set()
    hashes: set[str] = set()
    checked: list[dict[str, object]] = []
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("each manifest model must be an object")
        case_id = model.get("id")
        digest = model.get("sha256")
        schema = model.get("schema")
        source = model.get("path")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", case_id):
            raise ValueError("model id must use lower-case letters, digits, and hyphens")
        if case_id in ids:
            raise ValueError(f"duplicate model id: {case_id}")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"invalid SHA-256: {case_id}")
        if digest in hashes:
            raise ValueError(f"duplicate model content: {case_id}")
        if not isinstance(schema, str) or not schema:
            raise ValueError(f"missing declared schema: {case_id}")
        if not isinstance(source, str) or not source:
            raise ValueError(f"missing model path: {case_id}")
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = path.parent / source_path
        if not source_path.is_file():
            raise ValueError(f"required model is missing: {source_path}")
        if file_hash(source_path) != digest:
            raise ValueError(f"model SHA-256 differs: {case_id}")
        if declared_schema(source_path) != schema:
            raise ValueError(f"declared schema differs: {case_id}")
        ids.add(case_id)
        hashes.add(digest)
        checked.append({**model, "path": str(source_path.resolve())})
    return checked
