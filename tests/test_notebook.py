"""Notebook generator (docs/ai/05 §7). Verifies the generated .ipynb is valid
and runs the proven mount → install → transcribe → resume flow."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from yazit.cli import main
from yazit.notebook.generator import (
    NotebookSpec,
    build_notebook,
    generate_colab_notebook,
    pip_target,
)


def _cell_texts(nb: dict) -> list[str]:
    return ["".join(c["source"]) for c in nb["cells"]]


def test_pip_target() -> None:
    assert pip_target(()) == "yazit"
    assert pip_target(("url",)) == "yazit[url]"
    assert pip_target(("url", "drive")) == "yazit[url,drive]"


def test_no_unrendered_placeholders() -> None:
    # Check the cell SOURCE text (json.dumps would contain `}}` from JSON braces).
    cells_text = "\n".join(_cell_texts(build_notebook(NotebookSpec(source="./x.mp4"))))
    assert "{{" not in cells_text
    assert "}}" not in cells_text


def test_notebook_has_proven_flow_in_order() -> None:
    nb = build_notebook(NotebookSpec(source="https://youtu.be/abc", extras=("url",)))
    srcs = _cell_texts(nb)
    joined = "\n".join(srcs)

    mount_i = next(i for i, s in enumerate(srcs) if "drive.mount" in s)
    install_i = next(i for i, s in enumerate(srcs) if "!pip install" in s)
    run_i = next(i for i, s in enumerate(srcs) if "subprocess.run" in s)
    assert mount_i < install_i < run_i  # mount → install → transcribe

    assert "yazit[url]" in joined  # url extra baked into the pip target
    assert "https://youtu.be/abc" in joined  # source baked in
    # the Errno-107 split is visible in the config cell
    assert "/content/yazit-workspace" in joined  # local scratch
    assert "/content/drive/MyDrive" in joined  # durable Drive output
    assert "'colab'" in joined  # --runtime colab


def test_generated_file_is_valid_json(tmp_path: Path) -> None:
    out = generate_colab_notebook(NotebookSpec(source="./x.mp4"), tmp_path / "nb.ipynb")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["nbformat"] == 4
    assert len(data["cells"]) >= 4


@pytest.mark.skipif(
    importlib.util.find_spec("nbformat") is None, reason="nbformat ([dev]) not installed"
)
def test_generated_notebook_passes_nbformat_validate(tmp_path: Path) -> None:
    import nbformat

    out = generate_colab_notebook(NotebookSpec(source="./x.mp4"), tmp_path / "nb.ipynb")
    nb = nbformat.read(str(out), as_version=4)
    nbformat.validate(nb)  # raises nbformat.ValidationError on an invalid notebook


def test_cli_gen_notebook_url(tmp_path: Path) -> None:
    out = tmp_path / "out.ipynb"
    assert main(["gen-notebook", "https://youtu.be/abc", "-o", str(out)]) == 0
    assert "yazit[url]" in out.read_text(encoding="utf-8")  # url source → url extra


def test_cli_gen_notebook_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "n.ipynb"
    assert main(["gen-notebook", "./video.mp4", "-o", str(out), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["notebook"].endswith("n.ipynb")
    assert payload["extras"] == []
