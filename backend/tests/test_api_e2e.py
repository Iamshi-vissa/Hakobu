"""End to end over HTTP: upload → convert → progress → download (jobs run inline)."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.config import get_settings
from tests.conftest import detected


def upload(client, data: bytes, name: str) -> dict:
    response = client.post("/api/upload", content=data, headers={"X-File-Name": name})
    assert response.status_code == 200, response.text
    return response.json()


def start(client, file_id: str, target: str, **options) -> dict:
    response = client.post("/api/convert", json={"file_id": file_id, "target_format": target, "options": options})
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["redis"] is True


def test_formats_matrix_and_etag(client) -> None:
    response = client.get("/api/formats")
    body = response.json()
    assert {"png", "docx", "mp4"} <= set(body["conversions"]) and body["max_upload_mb"] == 200
    assert response.headers["cache-control"].startswith("public")
    assert client.get("/api/formats", headers={"If-None-Match": response.headers["etag"]}).status_code == 304


def test_upload_convert_download(client, samples, tmp_path) -> None:
    uploaded = upload(client, samples.get("png").read_bytes(), "Holiday photo.png")
    assert uploaded["format"]["id"] == "png" and uploaded["targets"][0]["format"] == "jpg"

    job = start(client, uploaded["file_id"], "webp", width=100)
    assert job["status"] == "done" and job["output_name"] == "Holiday photo.webp"

    status = client.get(f"/api/jobs/{job['job_id']}").json()
    assert status["progress"] == 100

    response = client.get(f"/api/download/{job['job_id']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "filename*=UTF-8''Holiday%20photo.webp" in response.headers["content-disposition"]
    out = tmp_path / "x.webp"
    out.write_bytes(response.content)
    assert detected(out) == "webp"


def test_sse_stream_reports_final_state(client, samples) -> None:
    job = start(client, upload(client, samples.get("md").read_bytes(), "a.md")["file_id"], "html")
    with client.stream("GET", f"/api/jobs/{job['job_id']}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    assert events[-1]["status"] == "done"


def test_chunked_resumable_upload(client, samples) -> None:
    data = samples.get("pdf").read_bytes()
    total, half = len(data), len(data) // 2
    first = client.post(
        "/api/upload",
        content=data[:half],
        headers={"X-File-Name": "doc.pdf", "Content-Range": f"bytes 0-{half - 1}/{total}"},
    )
    assert first.status_code == 202
    upload_id = first.json()["upload_id"]
    headers = {"X-File-Name": "doc.pdf", "X-Upload-Id": upload_id}
    wrong = client.post(
        "/api/upload",
        content=data[half:],
        headers={**headers, "Content-Range": f"bytes {half + 10}-{total - 1}/{total}"},
    )
    assert wrong.status_code == 409 and wrong.json()["error"]["received"] == half
    done = client.post(
        "/api/upload", content=data[half:], headers={**headers, "Content-Range": f"bytes {half}-{total - 1}/{total}"}
    )
    assert done.status_code == 200 and done.json()["format"]["id"] == "pdf" and done.json()["size"] == total


def test_multi_output_job_is_zipped(client, samples) -> None:
    job = start(client, upload(client, samples.get("pdf").read_bytes(), "pages.pdf")["file_id"], "png", dpi=50)
    assert job["output_count"] == 2 and job["output_name"] == "pages.zip"
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/download/{job['job_id']}").content))
    assert archive.namelist() == ["pages-1.png", "pages-2.png"]


def test_batch_download_zip(client, samples) -> None:
    png = upload(client, samples.get("png").read_bytes(), "a.png")["file_id"]
    jobs = [start(client, png, fmt)["job_id"] for fmt in ("jpg", "gif")]
    response = client.get("/api/download/batch", params=[("job_ids", j) for j in jobs])
    assert sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist()) == ["a.gif", "a.jpg"]


def test_result_cache_reuses_output(client, samples) -> None:
    data = samples.get("png").read_bytes()
    first = start(client, upload(client, data, "one.png")["file_id"], "jpg", quality=70)
    second = start(client, upload(client, data, "two.png")["file_id"], "jpg", quality=70)
    assert second["job_id"] != first["job_id"] and second["output_name"] == "two.jpg"
    assert (
        client.get(f"/api/download/{second['job_id']}").content
        == client.get(f"/api/download/{first['job_id']}").content
    )


def test_same_format_returns_original(client, samples) -> None:
    data = samples.get("png").read_bytes()
    job = start(client, upload(client, data, "same.png")["file_id"], "png")
    assert client.get(f"/api/download/{job['job_id']}").content == data


def test_merge_pdf_and_images(client, samples) -> None:
    ids = [upload(client, samples.get(f).read_bytes(), f"x.{f}")["file_id"] for f in ("pdf", "png")]
    response = client.post("/api/merge", json={"file_ids": ids})
    assert response.json()["status"] == "done" and response.json()["output_name"] == "merged.pdf"


@pytest.mark.parametrize(
    ("data", "code", "status"),
    [
        (b"\x7fELF" + b"\x00" * 100, "unsupported_format", 415),
        (b"", "invalid_request", 400),
    ],
)
def test_upload_errors(client, data: bytes, code: str, status: int) -> None:
    response = client.post("/api/upload", content=data, headers={"X-File-Name": "x.png"})
    assert response.status_code == status and response.json()["error"]["code"] == code


def test_too_large(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    response = client.post("/api/upload", content=b"x" * (2 * 1024 * 1024), headers={"X-File-Name": "big.txt"})
    assert response.status_code == 413 and response.json()["error"]["code"] == "too_large"


def test_unsupported_conversion_and_bad_options(client, samples) -> None:
    file_id = upload(client, samples.get("png").read_bytes(), "a.png")["file_id"]
    response = client.post("/api/convert", json={"file_id": file_id, "target_format": "mp3"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "unsupported_conversion"
    bad_options = {"file_id": file_id, "target_format": "jpg", "options": {"quality": 900}}
    response = client.post("/api/convert", json=bad_options)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


def test_corrupted_file_fails_job(client) -> None:
    file_id = upload(client, b"%PDF-1.7\n this is not really a pdf", "broken.pdf")["file_id"]
    job = start(client, file_id, "png")
    assert job["status"] == "failed" and job["error_code"] == "corrupted"


def test_unknown_ids(client) -> None:
    assert client.get("/api/jobs/doesnotexist_doesnotexist").status_code == 404
    assert client.get("/api/download/../../etc/passwd").status_code == 404


def test_rate_limit(client, samples, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 2)
    data = samples.get("txt").read_bytes()
    codes = [client.post("/api/upload", content=data, headers={"X-File-Name": "a.txt"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
