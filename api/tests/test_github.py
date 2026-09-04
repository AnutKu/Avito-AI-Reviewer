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


def archive_notebook_json(execution_counts, markdown=0):
    cells = [
        {"cell_type": "code", "execution_count": count, "source": ["x = 1\n"], "outputs": []}
        for count in execution_counts
    ]
    cells += [{"cell_type": "markdown", "source": ["## Раздел\n"]} for _ in range(markdown)]
    return json.dumps({"cells": cells})


class GithubSnapshotTest(unittest.TestCase):
    def test_extracts_notebook_content_and_facts(self):
        snapshot = build_snapshot(archive_with_notebook())
        self.assertIn("Ячейка 1", snapshot.content)
        self.assertEqual(snapshot.parsed_facts["runs_in_code"], 1)
        self.assertEqual(snapshot.parsed_facts["metrics"], ["f1"])
        self.assertTrue(snapshot.parsed_facts["seed_fixed"])
        self.assertEqual(snapshot.parsed_facts["failed_cells"], 1)

    def test_notebook_facts_are_grouped_per_file(self):
        # Плоский список счётчиков со всего репозитория давал бы ложный
        # «непорядок выполнения» на каждом стыке между ноутбуками.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("repo-main/a.ipynb", archive_notebook_json([1, 2, 3]))
            bundle.writestr("repo-main/b.ipynb", archive_notebook_json([1, 2]))

        notebooks = build_snapshot(buffer.getvalue()).parsed_facts["notebooks"]

        self.assertEqual([item["path"] for item in notebooks], ["a.ipynb", "b.ipynb"])
        self.assertEqual(notebooks[0]["execution_counts"], [1, 2, 3])
        self.assertEqual(notebooks[1]["execution_counts"], [1, 2])

    def test_unrun_cells_and_cell_kinds_are_counted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("repo-main/a.ipynb", archive_notebook_json([1, None, 3], markdown=2))

        facts = build_snapshot(buffer.getvalue()).parsed_facts["notebooks"][0]

        self.assertEqual(facts["code_cells"], 3)
        self.assertEqual(facts["unrun_cells"], 1)
        self.assertEqual(facts["markdown_cells"], 2)
        self.assertGreater(facts["markdown_chars"], 0)

    def test_rejects_invalid_archive(self):
        with self.assertRaises(GithubSnapshotError):
            build_snapshot(b"not-a-zip")

    def test_untruncated_snapshot_reports_no_losses(self):
        snapshot = build_snapshot(archive_with_notebook())
        self.assertFalse(snapshot.parsed_facts["truncated"])
        self.assertEqual(snapshot.parsed_facts["omitted_files"], [])
        self.assertEqual(snapshot.parsed_facts["snapshot_chars"], len(snapshot.content))

    def test_limit_is_respected_and_losses_are_recorded(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("repo-main/a.py", "a" * 2000)
            bundle.writestr("repo-main/b.py", "b" * 2000)
            bundle.writestr("repo-main/c.py", "c" * 2000)

        snapshot = build_snapshot(buffer.getvalue(), max_chars=2500)

        self.assertTrue(snapshot.parsed_facts["truncated"])
        self.assertLessEqual(len(snapshot.content), 2500)
        self.assertEqual(snapshot.parsed_facts["snapshot_chars"], len(snapshot.content))
        self.assertEqual(snapshot.parsed_facts["snapshot_limit"], 2500)
        # Ничего не теряется молча: каждый файл либо во files, либо в omitted_files.
        self.assertEqual(
            sorted(snapshot.parsed_facts["files"] + snapshot.parsed_facts["omitted_files"]),
            ["a.py", "b.py", "c.py"],
        )

    def test_partially_included_file_is_listed_as_included(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("repo-main/a.py", "a" * 1000)
            bundle.writestr("repo-main/b.py", "b" * 5000)

        snapshot = build_snapshot(buffer.getvalue(), max_chars=3000)

        self.assertIn("b.py", snapshot.parsed_facts["files"])
        self.assertIn("[Файл обрезан по лимиту снапшота]", snapshot.content)
        self.assertLessEqual(len(snapshot.content), 3000)


if __name__ == "__main__":
    unittest.main()
