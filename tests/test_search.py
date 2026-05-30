"""Tests for scripts/search.py"""

from unittest.mock import patch
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.search import score_name, fetch_ios, fetch_v2fly, display_stdout, display_pager


class TestScoreName:
    """score_name(query, name) → float [0, 100]"""

    def test_exact_match(self):
        assert score_name("openai", "OpenAI") == 100
        assert score_name("openai", "openai") == 100
        assert score_name("OPENAI", "openai") == 100

    def test_substring_match(self):
        # 查询词是名称的子串
        assert score_name("open", "OpenAI") == 80
        assert score_name("hub", "GitHub") == 80
        assert score_name("micro", "Microsoft") == 80

    def test_no_match(self):
        assert score_name("opencode", "OpenAI") == 0
        assert score_name("banana", "GitHub") == 0
        assert score_name("zzzzz", "OpenAI") == 0


class TestFetchIOS:
    """fetch_ios(cache, cat, platforms) → (deduped_lines, local_files, source_paths)"""

    def test_reads_from_cache_and_dedups(self, tmp_path):
        ios_dir = tmp_path / "files" / "ios" / "TestCat"
        ios_dir.mkdir(parents=True)
        (ios_dir / "Clash.list").write_text("DOMAIN-SUFFIX,example.com\nDOMAIN,test.com\n")
        (ios_dir / "Surge.list").write_text(
            "DOMAIN-SUFFIX,example.com\nHOST-SUFFIX,example.com,TestCat\n"
        )
        platforms = {"Clash": ["rule/Clash/TestCat/TestCat.list"], "Surge": ["rule/Surge/TestCat/TestCat.list"]}
        lines, files, source_paths = fetch_ios(tmp_path, "TestCat", platforms)
        assert lines == [
            "DOMAIN-SUFFIX,example.com",
            "DOMAIN,test.com",
            "HOST-SUFFIX,example.com,TestCat",
        ]
        assert len(files) == 2
        assert source_paths == ["rule/Clash/TestCat/TestCat.list", "rule/Surge/TestCat/TestCat.list"]

    def test_filters_comments(self, tmp_path):
        ios_dir = tmp_path / "files" / "ios" / "TestEmpty"
        ios_dir.mkdir(parents=True)
        (ios_dir / "Clash.list").write_text("# comment\nDOMAIN-SUFFIX,real.com\n# another\n")
        platforms = {"Clash": ["rule/Clash/TestEmpty/TestEmpty.list"]}
        lines, files, source_paths = fetch_ios(tmp_path, "TestEmpty", platforms)
        assert lines == ["DOMAIN-SUFFIX,real.com"]
        assert source_paths == ["rule/Clash/TestEmpty/TestEmpty.list"]

    def test_all_comments_returns_empty(self, tmp_path):
        ios_dir = tmp_path / "files" / "ios" / "TestComments"
        ios_dir.mkdir(parents=True)
        (ios_dir / "Clash.list").write_text("# just a comment\n# another comment\n")
        platforms = {"Clash": ["rule/Clash/TestComments/TestComments.list"]}
        lines, files, source_paths = fetch_ios(tmp_path, "TestComments", platforms)
        assert lines == []

    def test_empty_platforms_no_files(self, tmp_path):
        lines, files, source_paths = fetch_ios(tmp_path, "NoSuch", {})
        assert lines == []
        assert files == []
        assert source_paths == []


class TestFetchV2Fly:
    """fetch_v2fly(cache, name, path) → (lines, [Path], [source_path])"""

    def test_reads_from_cache(self, tmp_path):
        v2_dir = tmp_path / "files" / "v2fly"
        v2_dir.mkdir(parents=True)
        (v2_dir / "testname").write_text("example.com\ntest.org\n")
        lines, files, source_paths = fetch_v2fly(tmp_path, "testname", "data/testname")
        assert lines == ["example.com", "test.org"]
        assert len(files) == 1
        assert source_paths == ["data/testname"]

    def test_filters_comments(self, tmp_path):
        v2_dir = tmp_path / "files" / "v2fly"
        v2_dir.mkdir(parents=True)
        (v2_dir / "comments").write_text("# comment\nreal.domain\n")
        lines, files, source_paths = fetch_v2fly(tmp_path, "comments", "data/comments")
        assert lines == ["real.domain"]

    def test_empty_file(self, tmp_path):
        v2_dir = tmp_path / "files" / "v2fly"
        v2_dir.mkdir(parents=True)
        (v2_dir / "empty").write_text("")
        lines, files, source_paths = fetch_v2fly(tmp_path, "empty", "data/empty")
        assert lines == []

    def test_no_local_file_download_fails_gracefully(self, tmp_path):
        with patch("scripts.search.dl", side_effect=Exception("network error")):
            lines, files, source_paths = fetch_v2fly(tmp_path, "nonexistent", "data/nonexistent")
        assert lines == []
        assert files == []
        assert source_paths == []


class TestDisplayStdout:
    """display_stdout(results) → prints to stdout"""

    def test_normal_output(self, capsys):
        results = [
            ("ios_rule_script", "GitHub", ["DOMAIN,github.com", "DOMAIN-SUFFIX,github.io"],
             [Path("/f1.list")], ["rule/Clash/GitHub/GitHub.list"]),
        ]
        display_stdout(results)
        out = capsys.readouterr().out
        assert "📦 blackmatrix7/ios_rule_script" in out
        assert "GitHub" in out
        assert "DOMAIN,github.com" in out
        assert "rule/Clash/GitHub/GitHub.list" in out
        assert "截断" not in out

    def test_two_repos(self, capsys):
        results = [
            ("ios_rule_script", "GitHub", ["rule1"], [Path("/f1")], ["rule/Clash/GitHub/GitHub.list"]),
            ("v2fly_dlc", "github", ["rule2"], [Path("/f2")], ["data/github"]),
        ]
        display_stdout(results)
        out = capsys.readouterr().out
        assert "📦 blackmatrix7/ios_rule_script" in out
        assert "📦 v2fly/domain-list-community" in out
        assert "rule/Clash/GitHub/GitHub.list" in out
        assert "data/github" in out

    def test_truncation_with_file_links(self, capsys):
        lines_github = [f"DOMAIN-SUFFIX,{i}.com" for i in range(150)]
        lines_microsoft = [f"DOMAIN-SUFFIX,{i}.org" for i in range(100)]
        f1 = Path("/cache/files/ios/GitHub/Clash.list")
        f2 = Path("/cache/files/ios/Microsoft/Clash.list")
        results = [
            ("ios_rule_script", "GitHub", lines_github, [f1], ["rule/Clash/GitHub/GitHub.list"]),
            ("ios_rule_script", "Microsoft", lines_microsoft, [f2], ["rule/Clash/Microsoft/Microsoft.list"]),
        ]
        display_stdout(results)
        out = capsys.readouterr().out

        assert "截断" in out
        assert f1.resolve().as_uri() in out
        assert f2.resolve().as_uri() in out
        assert "rule/Clash/GitHub/GitHub.list" in out
        assert "rule/Clash/Microsoft/Microsoft.list" in out
        assert "未显示" in out

    def test_all_empty(self, capsys):
        results = [
            ("ios_rule_script", "GitHub", [], [Path("/f1")], ["rule/Clash/GitHub/GitHub.list"]),
        ]
        display_stdout(results)
        out = capsys.readouterr().out
        assert "(空)" in out

    def test_below_threshold_no_truncation(self, capsys):
        lines = [f"DOMAIN-SUFFIX,{i}.com" for i in range(50)]
        results = [("ios_rule_script", "Small", lines, [Path("/f1")], ["rule/Clash/Small/Small.list"])]
        display_stdout(results)
        out = capsys.readouterr().out
        assert "截断" not in out
        assert all(f"DOMAIN-SUFFIX,{i}.com" in out for i in range(50))


class TestDisplayPager:
    """display_pager(results) → writes temp file, calls bat"""

    def test_calls_bat_with_temp_file(self):
        results = [
            ("ios_rule_script", "GitHub", ["rule1"], [Path("/f1")], ["rule/Clash/GitHub/GitHub.list"]),
        ]
        with patch("scripts.search.subprocess.run") as mock_run:
            with patch("scripts.search.os.unlink"):
                display_pager(results)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0][0] == "bat"
        assert args[0][1] == "--paging=always"
        assert "rule_search_" in args[0][2]

    def test_falls_back_to_batcat(self):
        results = [
            ("ios_rule_script", "GitHub", ["rule1"], [Path("/f1")], ["rule/Clash/GitHub/GitHub.list"]),
        ]
        with patch("scripts.search.subprocess.run") as mock_run:
            mock_run.side_effect = [FileNotFoundError, None]
            with patch("scripts.search.os.unlink"):
                display_pager(results)
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[1][0][0][0] == "batcat"

    def test_temp_file_cleaned_up(self):
        results = [
            ("ios_rule_script", "GitHub", ["rule1"], [Path("/f1")], ["rule/Clash/GitHub/GitHub.list"]),
        ]
        with patch("scripts.search.subprocess.run"):
            with patch("scripts.search.os.unlink") as mock_unlink:
                display_pager(results)
        mock_unlink.assert_called_once()
