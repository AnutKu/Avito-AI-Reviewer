import io
import json
import unittest
import zipfile

from app.services.github import GithubSnapshotError, build_snapshot


def archive_with_notebook():
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 2,
                "source": ["mlflow.start_run()\n", "random_state=42\n", "mlflow.log_metric('f1', 0.9)"],
                "outputs": [{"output_type": "error", "ename": "ValueError", "evalue": "demo"}],
            }
        ]
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("repo-main/solution.ipynb", json.dumps(notebook))
        bundle.writestr("repo-main/image.png", b"ignored")
    return buffer.getvalue()


class GithubSnapshotTest(unittest.TestCase):
    def test_extracts_notebook_content_and_facts(self):
        snapshot = build_snapshot(archive_with_notebook())
        self.assertIn("Ячейка 1", snapshot.content)
        self.assertEqual(snapshot.parsed_facts["runs_in_code"], 1)
        self.assertEqual(snapshot.parsed_facts["metrics"], ["f1"])
        self.assertTrue(snapshot.parsed_facts["seed_fixed"])
        self.assertEqual(snapshot.parsed_facts["failed_cells"], 1)

    def test_rejects_invalid_archive(self):
        with self.assertRaises(GithubSnapshotError):
            build_snapshot(b"not-a-zip")


if __name__ == "__main__":
    unittest.main()
